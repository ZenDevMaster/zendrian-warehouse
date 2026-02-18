"""Admin panel routes — session management, user CRUD, spot checks."""

import json
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models import db, User, StocktakeSession, SpotCheck
from services import session_service, spotcheck_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    """Decorator that requires the user to be an authenticated admin."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/")
@admin_required
def index():
    """Admin panel main page — overview of all sessions, spot checks, and links."""
    sessions = session_service.get_all_sessions()
    user_count = User.query.count()
    open_count = StocktakeSession.query.filter_by(is_open=True).count()
    closed_count = StocktakeSession.query.filter_by(is_open=False).count()
    spotchecks = spotcheck_service.get_all_spotchecks()

    return render_template(
        "admin.html",
        sessions=sessions,
        user_count=user_count,
        open_count=open_count,
        closed_count=closed_count,
        spotchecks=spotchecks,
    )


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------

@admin_bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@admin_required
def close_session(session_id):
    """Close any session."""
    sess = session_service.get_session(session_id)
    if not sess:
        flash("Session not found.", "error")
        return redirect(url_for("admin.index"))

    if not sess.is_open:
        flash("Session is already closed.", "error")
        return redirect(url_for("admin.index"))

    session_service.close_session(session_id)

    # Auto-complete spot check if this is a spot check session
    if sess.session_type == "spotcheck":
        sc = spotcheck_service.get_spotcheck_by_session(session_id)
        if sc and sc.status != "completed":
            spotcheck_service.complete_spotcheck(sc.id)
            flash(f"Spot check completed and results calculated.", "success")

    flash(f"Session #{sess.session_code} closed.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/sessions/<int:session_id>/resume", methods=["POST"])
@admin_required
def resume_session(session_id):
    """Resume (reopen) a closed session."""
    sess = session_service.get_session(session_id)
    if not sess:
        flash("Session not found.", "error")
        return redirect(url_for("admin.index"))

    if sess.is_open:
        flash("Session is already open.", "error")
        return redirect(url_for("admin.index"))

    session_service.reopen_session(session_id)
    flash(f"Session #{sess.session_code} reopened.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@admin_required
def delete_session(session_id):
    """Delete a session and all its scan entries."""
    sess = session_service.get_session(session_id)
    if not sess:
        flash("Session not found.", "error")
        return redirect(url_for("admin.index"))

    code = sess.session_code
    success = session_service.delete_session(session_id)
    if success:
        flash(f"Session #{code} and all its data deleted.", "success")
    else:
        flash(f"Failed to delete session #{code}.", "error")
    return redirect(url_for("admin.index"))


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@admin_required
def users():
    """List all users with management actions."""
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=all_users)


@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    """Create a new user."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    is_admin = request.form.get("is_admin") == "on"

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("admin.users"))

    if len(username) < 2:
        flash("Username must be at least 2 characters.", "error")
        return redirect(url_for("admin.users"))

    if len(password) < 4:
        flash("Password must be at least 4 characters.", "error")
        return redirect(url_for("admin.users"))

    # Check for duplicate username
    existing = User.query.filter_by(username=username).first()
    if existing:
        flash(f"Username '{username}' already exists.", "error")
        return redirect(url_for("admin.users"))

    user = User(
        username=username,
        display_name=username.title(),
        is_admin=is_admin,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    role = "admin" if is_admin else "user"
    flash(f"User '{username}' created as {role}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    """Delete a user. Cannot delete yourself."""
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users"))

    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))

    # Check if user has sessions
    session_count = StocktakeSession.query.filter_by(operator_id=user_id).count()
    if session_count > 0:
        flash(
            f"Cannot delete '{user.username}' — they have {session_count} session(s). "
            "Delete their sessions first or deactivate the user instead.",
            "error",
        )
        return redirect(url_for("admin.users"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/password", methods=["POST"])
@admin_required
def change_password(user_id):
    """Change a user's password."""
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))

    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 4:
        flash("Password must be at least 4 characters.", "error")
        return redirect(url_for("admin.users"))

    user.set_password(new_password)
    db.session.commit()
    flash(f"Password changed for '{user.username}'.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id):
    """Toggle admin status for a user. Cannot remove your own admin."""
    if user_id == current_user.id:
        flash("You cannot change your own admin status.", "error")
        return redirect(url_for("admin.users"))

    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))

    user.is_admin = not user.is_admin
    db.session.commit()

    status = "admin" if user.is_admin else "regular user"
    flash(f"'{user.username}' is now a {status}.", "success")
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------
# Spot Check Creation Wizard
# ---------------------------------------------------------------------------

@admin_bp.route("/spotcheck/create")
@admin_required
def spotcheck_select():
    """Step 1: Select a closed session to spot check."""
    closed_sessions = spotcheck_service.get_closed_normal_sessions()
    return render_template("admin_spotcheck_select.html", sessions=closed_sessions)


@admin_bp.route("/spotcheck/configure/<int:session_id>")
@admin_required
def spotcheck_configure(session_id):
    """Step 2: Configure the spot check — select locations and assign user."""
    sess = session_service.get_session(session_id)
    if not sess:
        flash("Session not found.", "error")
        return redirect(url_for("admin.spotcheck_select"))

    if sess.is_open or sess.session_type != "normal":
        flash("Only closed, normal sessions can be spot checked.", "error")
        return redirect(url_for("admin.spotcheck_select"))

    locations = spotcheck_service.get_session_locations(session_id)
    all_users = User.query.filter_by(is_active=True).order_by(User.username).all()

    return render_template(
        "admin_spotcheck_configure.html",
        sess=sess,
        locations=locations,
        users=all_users,
    )


@admin_bp.route("/spotcheck/create", methods=["POST"])
@admin_required
def spotcheck_create():
    """Step 3: Process the spot check creation form."""
    original_session_id = request.form.get("original_session_id", type=int)
    assigned_user = request.form.get("assigned_user", "").strip()
    selection_mode = request.form.get("selection_mode", "").strip()

    if not original_session_id or not assigned_user or not selection_mode:
        flash("Missing required fields.", "error")
        return redirect(url_for("admin.spotcheck_select"))

    try:
        if selection_mode == "percentage":
            percentage = request.form.get("selection_percentage", type=int)
            if not percentage or percentage < 1 or percentage > 100:
                flash("Invalid percentage value.", "error")
                return redirect(url_for("admin.spotcheck_configure", session_id=original_session_id))

            spotcheck = spotcheck_service.create_spotcheck(
                original_session_id=original_session_id,
                assigned_user=assigned_user,
                selection_mode="percentage",
                selection_percentage=percentage,
            )
        elif selection_mode == "specific":
            selected_locations = request.form.getlist("locations")
            if not selected_locations:
                flash("Please select at least one location.", "error")
                return redirect(url_for("admin.spotcheck_configure", session_id=original_session_id))

            spotcheck = spotcheck_service.create_spotcheck(
                original_session_id=original_session_id,
                assigned_user=assigned_user,
                selection_mode="specific",
                selected_locations=selected_locations,
            )
        else:
            flash("Invalid selection mode.", "error")
            return redirect(url_for("admin.spotcheck_configure", session_id=original_session_id))

        locations = json.loads(spotcheck.selected_locations)
        flash(
            f"Spot check created! {len(locations)} location(s) assigned to {assigned_user}.",
            "success",
        )
        return redirect(url_for("admin.index"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.spotcheck_configure", session_id=original_session_id))


# ---------------------------------------------------------------------------
# Spot Check Results
# ---------------------------------------------------------------------------

@admin_bp.route("/spotcheck/<int:spotcheck_id>")
@admin_required
def spotcheck_results(spotcheck_id):
    """View detailed spot check results."""
    spotcheck = spotcheck_service.get_spotcheck(spotcheck_id)
    if not spotcheck:
        flash("Spot check not found.", "error")
        return redirect(url_for("admin.index"))

    mismatches = []
    if spotcheck.mismatches:
        mismatches = json.loads(spotcheck.mismatches)

    selected_locations = json.loads(spotcheck.selected_locations)
    confidence_stats = spotcheck_service.get_confidence_description(spotcheck)

    return render_template(
        "admin_spotcheck_results.html",
        spotcheck=spotcheck,
        mismatches=mismatches,
        selected_locations=selected_locations,
        confidence_stats=confidence_stats,
    )
