"""Bearer-authenticated, read-only stocktake API."""

import hmac
import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request

from models import LocationInventory, StocktakeSession, db


api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _iso(value):
    return value.isoformat() + "Z" if value else None


def _authorized():
    configured = os.environ.get("STOCKTAKE_READ_API_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not configured or not supplied.startswith("Bearer "):
        return False
    return hmac.compare_digest(supplied[7:], configured)


def read_token_required(view):
    """Require the dedicated read-only API bearer token."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _authorized():
            response = jsonify({"error": "unauthorized"})
            response.status_code = 401
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return view(*args, **kwargs)

    return wrapped


def _session_dict(session):
    return {
        "id": session.id,
        "session_code": session.session_code,
        "owner": session.owner,
        "operator": session.operator.username,
        "name": session.name,
        "session_type": session.session_type,
        "is_open": session.is_open,
        "started_at": _iso(session.started_at),
        "last_scan_at": _iso(session.last_scan_at),
        "closed_at": _iso(session.closed_at),
        "total_scans": session.total_scans,
        "unique_locations": session.unique_locations,
        "unique_skus": session.unique_skus,
        "total_items": session.total_items,
    }


def _filtered_sessions():
    query = StocktakeSession.query
    owner = request.args.get("owner", "").strip()
    if owner:
        query = query.filter(db.func.lower(StocktakeSession.owner) == owner.lower())
    session_type = request.args.get("session_type", "normal").strip()
    if session_type:
        query = query.filter(StocktakeSession.session_type == session_type)
    if request.args.get("closed_only", "false").lower() in {"1", "true", "yes"}:
        query = query.filter(StocktakeSession.is_open.is_(False))
    since = request.args.get("since", "").strip()
    if since:
        try:
            since_at = datetime.fromisoformat(since.removesuffix("Z"))
        except ValueError as exc:
            raise ValueError("since must be an ISO-8601 datetime") from exc
        query = query.filter(StocktakeSession.started_at >= since_at)
    return query


def _inventory_rows(session_id):
    return (
        LocationInventory.query.filter_by(session_id=session_id)
        .filter(LocationInventory.quantity != 0)
        .order_by(LocationInventory.sku, LocationInventory.location)
        .all()
    )


def _inventory_response(session):
    rows = _inventory_rows(session.id)
    totals = {}
    inventory = []
    for row in rows:
        inventory.append(
            {"location": row.location, "sku": row.sku, "quantity": row.quantity}
        )
        totals[row.sku] = totals.get(row.sku, 0) + row.quantity
    return {
        "session": _session_dict(session),
        "inventory": inventory,
        "sku_totals": [
            {"sku": sku, "quantity": quantity}
            for sku, quantity in sorted(totals.items())
        ],
    }


def _session_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise ValueError("date must be an ISO-8601 date") from exc


def _inventory_for_sessions(sessions):
    session_ids = [session.id for session in sessions]
    rows = (
        LocationInventory.query.filter(LocationInventory.session_id.in_(session_ids))
        .filter(LocationInventory.quantity != 0)
        .order_by(LocationInventory.sku, LocationInventory.location)
        .all()
    )
    totals = {}
    inventory = []
    for row in rows:
        inventory.append(
            {
                "session_id": row.session_id,
                "location": row.location,
                "sku": row.sku,
                "quantity": row.quantity,
            }
        )
        totals[row.sku] = totals.get(row.sku, 0) + row.quantity
    return {
        "sessions": [_session_dict(session) for session in sessions],
        "inventory": inventory,
        "sku_totals": [
            {"sku": sku, "quantity": quantity}
            for sku, quantity in sorted(totals.items())
        ],
    }


@api_bp.get("/health")
@read_token_required
def health():
    return jsonify({"ok": True, "mode": "read_only"})


@api_bp.get("/sessions")
@read_token_required
def sessions():
    try:
        limit = min(max(request.args.get("limit", 50, type=int), 1), 250)
        query = _filtered_sessions()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    rows = query.order_by(StocktakeSession.started_at.desc()).limit(limit).all()
    return jsonify({"sessions": [_session_dict(row) for row in rows]})


@api_bp.get("/sessions/<int:session_id>/inventory")
@read_token_required
def session_inventory(session_id):
    session = db.session.get(StocktakeSession, session_id)
    if not session:
        return jsonify({"error": "session_not_found"}), 404
    return jsonify(_inventory_response(session))


@api_bp.get("/inventory/latest")
@read_token_required
def latest_inventory():
    try:
        query = _filtered_sessions()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    session = query.order_by(StocktakeSession.started_at.desc()).first()
    if not session:
        return jsonify({"error": "session_not_found"}), 404
    return jsonify(_inventory_response(session))


@api_bp.get("/inventory/by-date")
@read_token_required
def inventory_by_date():
    try:
        count_date = _session_date(request.args.get("date", "").strip())
        query = _filtered_sessions()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if count_date is None:
        latest = query.order_by(StocktakeSession.started_at.desc()).first()
        if not latest:
            return jsonify({"error": "session_not_found"}), 404
        count_date = latest.started_at.date()
    start = datetime.combine(count_date, datetime.min.time())
    end = datetime.combine(count_date, datetime.max.time())
    sessions = (
        query.filter(StocktakeSession.started_at.between(start, end))
        .order_by(StocktakeSession.started_at.asc())
        .all()
    )
    if not sessions:
        return jsonify({"error": "session_not_found"}), 404
    response = _inventory_for_sessions(sessions)
    response["count_date"] = count_date.isoformat()
    return jsonify(response)
