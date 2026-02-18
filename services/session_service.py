"""Session lifecycle management."""

import random
from datetime import datetime
from models import db, StocktakeSession, ScanEntry, LocationInventory, SpotCheck


def generate_session_code():
    """Generate a unique 4-digit session code."""
    for _ in range(100):
        code = str(random.randint(1000, 9999))
        if not StocktakeSession.query.filter_by(session_code=code).first():
            return code
    raise RuntimeError("Unable to generate unique session code")


def create_session(operator_id, owner=None):
    """Create a new scanning session."""
    session = StocktakeSession(
        session_code=generate_session_code(),
        operator_id=operator_id,
        owner=owner,
    )
    db.session.add(session)
    db.session.commit()
    return session


def get_session(session_id):
    """Get a session by ID."""
    return db.session.get(StocktakeSession, session_id)


def get_session_by_code(code):
    """Get a session by its human-readable code."""
    return StocktakeSession.query.filter_by(session_code=code).first()


def get_open_sessions(operator_id=None):
    """Get all open sessions, optionally filtered by operator."""
    query = StocktakeSession.query.filter_by(is_open=True)
    if operator_id:
        query = query.filter_by(operator_id=operator_id)
    return query.order_by(StocktakeSession.last_scan_at.desc()).all()


def get_all_sessions():
    """Get all sessions ordered by most recent first."""
    return StocktakeSession.query.order_by(StocktakeSession.started_at.desc()).all()


def close_session(session_id):
    """Close a session."""
    session = db.session.get(StocktakeSession, session_id)
    if not session or not session.is_open:
        return None

    session.is_open = False
    session.closed_at = datetime.utcnow()
    db.session.commit()
    return session


def reopen_session(session_id):
    """Reopen a closed session."""
    session = db.session.get(StocktakeSession, session_id)
    if not session or session.is_open:
        return None

    session.is_open = True
    session.closed_at = None
    db.session.commit()
    return session


def _delete_session_data(session_id):
    """Delete scan entries and location inventory for a session (no commit)."""
    ScanEntry.query.filter_by(session_id=session_id).delete()
    LocationInventory.query.filter_by(session_id=session_id).delete()


def delete_session(session_id):
    """Delete a session and all its associated scan entries, inventory data, and spot checks.

    - If the session is the *original* session for a spot check, the SpotCheck record
      AND the spot-check scanning session (plus its data) are also removed.
    - If the session is the *spot-check scanning* session, only the SpotCheck record
      is removed (the original session is left intact).
    """
    session = db.session.get(StocktakeSession, session_id)
    if not session:
        return False

    # --- Handle spot checks where this session is the ORIGINAL session ---
    spotchecks_as_original = SpotCheck.query.filter_by(original_session_id=session_id).all()
    for sc in spotchecks_as_original:
        # Delete the spot-check scanning session's data (if it exists)
        if sc.spotcheck_session_id:
            _delete_session_data(sc.spotcheck_session_id)
            sc_session = db.session.get(StocktakeSession, sc.spotcheck_session_id)
            if sc_session:
                db.session.delete(sc_session)
        # Delete the SpotCheck record itself
        db.session.delete(sc)

    # --- Handle spot checks where this session is the SPOTCHECK session ---
    spotchecks_as_scanning = SpotCheck.query.filter_by(spotcheck_session_id=session_id).all()
    for sc in spotchecks_as_scanning:
        # Only delete the SpotCheck record; leave the original session intact
        db.session.delete(sc)

    # Delete scan entries and inventory for the session being deleted
    _delete_session_data(session_id)

    # Delete the session itself
    db.session.delete(session)
    db.session.commit()
    return True


def touch_session(session):
    """Update the last_scan_at timestamp."""
    session.last_scan_at = datetime.utcnow()
    db.session.commit()
