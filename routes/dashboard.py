"""Dashboard routes — session list, create, close."""

from flask import Blueprint, render_template, redirect, url_for, request, abort, flash
from flask_login import login_required, current_user
from services import session_service, spotcheck_service
from models import StocktakeSession, SpotCheck

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    """Show dashboard with open sessions and history."""
    if current_user.is_admin:
        open_sessions = session_service.get_open_sessions()
        all_sessions = session_service.get_all_sessions()
    else:
        open_sessions = session_service.get_open_sessions(operator_id=current_user.id)
        all_sessions = StocktakeSession.query.filter_by(
            owner=current_user.username
        ).order_by(StocktakeSession.started_at.desc()).all()

    # Get spot check info for spot check sessions assigned to this user
    spotcheck_map = {}
    user_spotchecks = SpotCheck.query.filter_by(assigned_user=current_user.username).all()
    for sc in user_spotchecks:
        if sc.spotcheck_session_id:
            spotcheck_map[sc.spotcheck_session_id] = sc

    return render_template(
        "dashboard.html",
        user=current_user,
        open_sessions=open_sessions,
        all_sessions=all_sessions,
        spotcheck_map=spotcheck_map,
    )


@bp.route("/sessions", methods=["POST"])
@login_required
def create_session():
    """Create a new scanning session."""
    session = session_service.create_session(current_user.id, owner=current_user.username)
    return redirect(url_for("scanning.scan_view", session_id=session.id))


@bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@login_required
def close_session(session_id):
    """Close a session."""
    sess = session_service.get_session(session_id)
    if not sess:
        abort(404)

    # Non-admin users can only close their own sessions
    if not current_user.is_admin and sess.owner != current_user.username:
        abort(403)

    session_service.close_session(session_id)

    # Auto-complete spot check if this is a spot check session
    if sess.session_type == "spotcheck":
        sc = spotcheck_service.get_spotcheck_by_session(session_id)
        if sc and sc.status != "completed":
            spotcheck_service.complete_spotcheck(sc.id)
            flash("Spot check completed! Results are now available.", "success")

    return redirect(url_for("dashboard.index"))


@bp.route("/sessions/<int:session_id>/resume")
@login_required
def resume_session(session_id):
    """Resume an open session (redirect to scan view)."""
    sess = session_service.get_session(session_id)
    if not sess:
        abort(404)

    # Non-admin users can only resume their own sessions
    if not current_user.is_admin and sess.owner != current_user.username:
        abort(403)

    return redirect(url_for("scanning.scan_view", session_id=session_id))
