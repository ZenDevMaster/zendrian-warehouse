"""Scanning routes — main scanning interface and HTMX endpoints."""

import json
from flask import (
    Blueprint, render_template, request, session as flask_session,
    redirect, url_for, make_response, Response, abort,
)
from flask_login import login_required, current_user
from services import scan_service, session_service, export_service, spotcheck_service

bp = Blueprint("scanning", __name__)


def _check_session_access(sess):
    """Check that the current user can access this session.

    Admin users can access all sessions.
    Non-admin users can only access sessions they own.
    Returns the session if access is allowed, aborts with 403 otherwise.
    """
    if not sess:
        return None
    if not current_user.is_admin and sess.owner != current_user.username:
        abort(403)
    return sess


def _get_spotcheck_info(sess):
    """Get spot check info if this is a spot check session.

    Returns (spotcheck, selected_locations) or (None, None).
    """
    if sess.session_type != "spotcheck":
        return None, None

    sc = spotcheck_service.get_spotcheck_by_session(sess.id)
    if not sc:
        return None, None

    selected_locations = json.loads(sc.selected_locations)
    return sc, selected_locations


def _htmx_response(template, context, sound=None, status=200):
    """Build an HTMX fragment response with optional sound trigger header."""
    resp = make_response(render_template(template, **context), status)
    if sound:
        resp.headers["X-Play-Sound"] = sound
    return resp


@bp.route("/sessions/<int:session_id>")
@login_required
def scan_view(session_id):
    """Main scanning interface for a session."""
    sess = session_service.get_session(session_id)
    if not sess:
        return redirect(url_for("dashboard.index"))

    _check_session_access(sess)

    # Mark spot check as in_progress when first viewed
    spotcheck, selected_locations = _get_spotcheck_info(sess)
    if spotcheck and spotcheck.status == "pending":
        spotcheck.status = "in_progress"
        from models import db
        db.session.commit()

    current_location = flask_session.get(f"loc_{session_id}", None)
    mode = flask_session.get(f"mode_{session_id}", "add")

    # Get inventory for current location
    inventory = []
    if current_location:
        inventory = scan_service.get_location_inventory(session_id, current_location)

    # Get recent scans
    recent = scan_service.get_recent_scans(session_id, limit=10)

    # Get all locations
    locations = scan_service.get_all_locations(session_id)

    # For spot checks, determine which locations have been scanned
    spotcheck_progress = None
    if spotcheck and selected_locations:
        scanned_locations = set(loc.location for loc in locations)
        spotcheck_progress = {
            "selected": selected_locations,
            "scanned": [loc for loc in selected_locations if loc in scanned_locations],
            "remaining": [loc for loc in selected_locations if loc not in scanned_locations],
            "total": len(selected_locations),
            "done": len([loc for loc in selected_locations if loc in scanned_locations]),
        }

    return render_template(
        "scan.html",
        user=current_user,
        sess=sess,
        current_location=current_location,
        mode=mode,
        inventory=inventory,
        recent=recent,
        locations=locations,
        spotcheck=spotcheck,
        selected_locations=selected_locations,
        spotcheck_progress=spotcheck_progress,
    )


@bp.route("/sessions/<int:session_id>/scan", methods=["POST"])
@login_required
def process_scan(session_id):
    """Process a scan input — returns HTMX fragments."""
    sess = session_service.get_session(session_id)
    _check_session_access(sess)

    if not sess or not sess.is_open:
        return _htmx_response(
            "fragments/feedback.html",
            {"result": scan_service.ScanResult(False, "Session is closed.", sound="error")},
            sound="error",
        )

    raw_input = request.form.get("scan_input", "").strip()
    current_location = flask_session.get(f"loc_{session_id}", None)
    mode = flask_session.get(f"mode_{session_id}", "add")
    bulk_qty = flask_session.get(f"bulk_{session_id}", None)

    # For spot check sessions, enforce location restrictions
    spotcheck, selected_locations = _get_spotcheck_info(sess)

    if spotcheck and selected_locations:
        # Check if this is a location scan
        input_type, value = scan_service.classify_input(raw_input)
        if input_type == "location":
            # Enforce: only allow selected locations
            if value not in selected_locations:
                result = scan_service.ScanResult(
                    False,
                    f"Location {value} is not part of this spot check. "
                    f"Only these locations are included: {', '.join(selected_locations)}",
                    sound="error",
                )
                return _htmx_response(
                    "fragments/feedback.html",
                    {"result": result},
                    sound="error",
                )

    # Process the scan
    result = scan_service.process_scan(
        session_id=session_id,
        raw_input=raw_input,
        current_location=current_location,
        mode=mode,
        bulk_qty=bulk_qty,
    )

    # Handle location change
    if result.scan_type == "LOCATION":
        flask_session[f"loc_{session_id}"] = result.location
        current_location = result.location
        # Reset mode on location change
        flask_session[f"mode_{session_id}"] = "add"
        flask_session.pop(f"bulk_{session_id}", None)

    # Handle commands that change mode
    elif result.scan_type == "CMD-SUB":
        flask_session[f"mode_{session_id}"] = "subtract"

    elif result.scan_type == "CMD-BULK":
        flask_session[f"mode_{session_id}"] = "bulk"

    elif result.scan_type == "CMD-END":
        session_service.close_session(session_id)

        # Auto-complete spot check
        if spotcheck and spotcheck.status != "completed":
            spotcheck_service.complete_spotcheck(spotcheck.id)

        resp = make_response("", 200)
        resp.headers["HX-Redirect"] = url_for("dashboard.index")
        resp.headers["X-Play-Sound"] = "success"
        return resp

    # Reset mode after a successful SKU scan (subtract/bulk are one-shot)
    elif result.scan_type in ("SUBTRACT", "BULK", "ADD"):
        flask_session[f"mode_{session_id}"] = "add"
        flask_session.pop(f"bulk_{session_id}", None)

    # Refresh session object for updated stats
    sess = session_service.get_session(session_id)

    # Build the full page update response (multiple HTMX OOB swaps)
    inventory = []
    if current_location:
        inventory = scan_service.get_location_inventory(session_id, current_location)

    recent = scan_service.get_recent_scans(session_id, limit=10)
    locations = scan_service.get_all_locations(session_id)
    mode = flask_session.get(f"mode_{session_id}", "add")

    # Recalculate spot check progress for OOB swap
    spotcheck_progress = None
    if spotcheck and selected_locations:
        scanned_locations = set(loc.location for loc in locations)
        spotcheck_progress = {
            "selected": selected_locations,
            "scanned": [loc for loc in selected_locations if loc in scanned_locations],
            "remaining": [loc for loc in selected_locations if loc not in scanned_locations],
            "total": len(selected_locations),
            "done": len([loc for loc in selected_locations if loc in scanned_locations]),
        }

    resp = make_response(render_template(
        "fragments/scan_response.html",
        result=result,
        sess=sess,
        current_location=current_location,
        mode=mode,
        inventory=inventory,
        recent=recent,
        locations=locations,
        spotcheck=spotcheck,
        selected_locations=selected_locations,
        spotcheck_progress=spotcheck_progress,
    ))
    if result.sound:
        resp.headers["X-Play-Sound"] = result.sound
    return resp


@bp.route("/sessions/<int:session_id>/bulk", methods=["POST"])
@login_required
def set_bulk_quantity(session_id):
    """Set the bulk quantity for the next scan."""
    sess = session_service.get_session(session_id)
    _check_session_access(sess)

    qty = request.form.get("bulk_qty", "1")
    try:
        qty = int(qty)
        if qty <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return _htmx_response(
            "fragments/feedback.html",
            {"result": scan_service.ScanResult(False, "Invalid quantity.", sound="error")},
            sound="error",
        )

    flask_session[f"bulk_{session_id}"] = qty
    flask_session[f"mode_{session_id}"] = "bulk"

    return _htmx_response(
        "fragments/feedback.html",
        {"result": scan_service.ScanResult(True, f"Bulk mode: next scan adds {qty}.", sound="bleep")},
        sound="bleep",
    )


@bp.route("/sessions/<int:session_id>/adjust", methods=["POST"])
@login_required
def adjust_quantity(session_id):
    """Adjust quantity for a specific SKU at a location."""
    sess = session_service.get_session(session_id)
    _check_session_access(sess)

    location = request.form.get("location", "").strip()
    sku = request.form.get("sku", "").strip()
    new_qty = request.form.get("new_qty", "0")

    try:
        new_qty = int(new_qty)
        if new_qty < 0:
            raise ValueError
    except (ValueError, TypeError):
        return _htmx_response(
            "fragments/feedback.html",
            {"result": scan_service.ScanResult(False, "Invalid quantity.", sound="error")},
            sound="error",
        )

    result = scan_service.adjust_quantity(session_id, location, sku, new_qty)

    # Refresh data
    sess = session_service.get_session(session_id)
    current_location = flask_session.get(f"loc_{session_id}", location)
    inventory = scan_service.get_location_inventory(session_id, current_location)
    recent = scan_service.get_recent_scans(session_id, limit=10)
    locations = scan_service.get_all_locations(session_id)
    mode = flask_session.get(f"mode_{session_id}", "add")

    # Spot check info
    spotcheck, selected_locations = _get_spotcheck_info(sess)
    spotcheck_progress = None
    if spotcheck and selected_locations:
        scanned_locations = set(loc.location for loc in locations)
        spotcheck_progress = {
            "selected": selected_locations,
            "scanned": [loc for loc in selected_locations if loc in scanned_locations],
            "remaining": [loc for loc in selected_locations if loc not in scanned_locations],
            "total": len(selected_locations),
            "done": len([loc for loc in selected_locations if loc in scanned_locations]),
        }

    resp = make_response(render_template(
        "fragments/scan_response.html",
        result=result,
        sess=sess,
        current_location=current_location,
        mode=mode,
        inventory=inventory,
        recent=recent,
        locations=locations,
        spotcheck=spotcheck,
        selected_locations=selected_locations,
        spotcheck_progress=spotcheck_progress,
    ))
    if result.sound:
        resp.headers["X-Play-Sound"] = result.sound
    return resp


@bp.route("/sessions/<int:session_id>/location/<location>")
@login_required
def switch_location(session_id, location):
    """Switch to viewing a specific location."""
    sess = session_service.get_session(session_id)
    _check_session_access(sess)

    # For spot check sessions, enforce location restrictions
    spotcheck, selected_locations = _get_spotcheck_info(sess)
    if spotcheck and selected_locations:
        if location not in selected_locations:
            from flask import flash
            flash(f"Location {location} is not part of this spot check.", "error")
            return redirect(url_for("scanning.scan_view", session_id=session_id))

    flask_session[f"loc_{session_id}"] = location
    return redirect(url_for("scanning.scan_view", session_id=session_id))


@bp.route("/sessions/<int:session_id>/export")
@login_required
def export_summary(session_id):
    """Download summary CSV."""
    sess = session_service.get_session(session_id)
    if not sess:
        return redirect(url_for("dashboard.index"))

    _check_session_access(sess)

    csv_data = export_service.generate_summary_csv(session_id)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=session_{sess.session_code}_summary.csv"
        },
    )


@bp.route("/sessions/<int:session_id>/export-log")
@login_required
def export_log(session_id):
    """Download full scan log CSV."""
    sess = session_service.get_session(session_id)
    if not sess:
        return redirect(url_for("dashboard.index"))

    _check_session_access(sess)

    csv_data = export_service.generate_scan_log_csv(session_id)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=session_{sess.session_code}_log.csv"
        },
    )
