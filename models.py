"""SQLAlchemy database models."""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Operator / user account with Flask-Login support."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sessions = db.relationship("StocktakeSession", back_populates="operator", lazy="dynamic")

    def set_password(self, password):
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Return the user ID as a string (required by Flask-Login)."""
        return str(self.id)

    def __repr__(self):
        return f"<User {self.username}>"


class StocktakeSession(db.Model):
    """A stocktake scanning session."""

    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    owner = db.Column(db.String(80), nullable=True)
    name = db.Column(db.String(200), nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_scan_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    is_open = db.Column(db.Boolean, default=True, nullable=False, index=True)
    total_scans = db.Column(db.Integer, default=0, nullable=False)
    session_type = db.Column(db.String(20), default="normal", nullable=False)  # 'normal' or 'spotcheck'

    operator = db.relationship("User", back_populates="sessions")
    scan_entries = db.relationship(
        "ScanEntry", back_populates="session", lazy="dynamic",
        order_by="ScanEntry.scanned_at.desc()"
    )
    location_inventory = db.relationship(
        "LocationInventory", back_populates="session", lazy="dynamic"
    )

    @property
    def unique_locations(self):
        return (
            db.session.query(db.func.count(db.distinct(LocationInventory.location)))
            .filter(LocationInventory.session_id == self.id)
            .scalar()
        ) or 0

    @property
    def unique_skus(self):
        return (
            db.session.query(db.func.count(db.distinct(LocationInventory.sku)))
            .filter(LocationInventory.session_id == self.id, LocationInventory.quantity > 0)
            .scalar()
        ) or 0

    @property
    def total_items(self):
        return (
            db.session.query(db.func.coalesce(db.func.sum(LocationInventory.quantity), 0))
            .filter(LocationInventory.session_id == self.id)
            .scalar()
        ) or 0

    @property
    def scans_per_minute(self):
        if self.total_scans == 0:
            return 0.0
        now = datetime.utcnow()
        duration = (now - self.started_at).total_seconds() / 60
        if duration < 0.01:
            return 0.0
        return round(self.total_scans / duration, 1)

    def __repr__(self):
        return f"<Session {self.session_code}>"


class ScanEntry(db.Model):
    """Append-only audit log of every scan action."""

    __tablename__ = "scan_entries"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    location = db.Column(db.String(50), nullable=False)
    sku = db.Column(db.String(100), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    running_total = db.Column(db.Integer, nullable=False)
    scan_type = db.Column(db.String(20), nullable=False)  # ADD, SUBTRACT, BULK, ADJUST
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    session = db.relationship("StocktakeSession", back_populates="scan_entries")

    def __repr__(self):
        return f"<Scan {self.scan_type} {self.sku} {self.quantity_change:+d}>"


class LocationInventory(db.Model):
    """Materialised current inventory state per location+SKU."""

    __tablename__ = "location_inventory"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    location = db.Column(db.String(50), nullable=False)
    sku = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)

    session = db.relationship("StocktakeSession", back_populates="location_inventory")

    __table_args__ = (
        db.UniqueConstraint("session_id", "location", "sku", name="uq_session_location_sku"),
    )

    def __repr__(self):
        return f"<Inventory {self.location}/{self.sku}: {self.quantity}>"


class SpotCheck(db.Model):
    """A spot check linking an original session to a verification session."""

    __tablename__ = "spot_checks"

    id = db.Column(db.Integer, primary_key=True)
    original_session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False
    )
    spotcheck_session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=True
    )  # The new scanning session created for the spot check
    assigned_user = db.Column(db.String(80), nullable=False)  # Username of assigned user
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending, in_progress, completed
    selection_mode = db.Column(db.String(20), nullable=False)  # 'specific' or 'percentage'
    selection_percentage = db.Column(db.Integer, nullable=True)  # If percentage mode
    selected_locations = db.Column(db.Text, nullable=False)  # JSON list of location names to check
    expected_inventory = db.Column(db.Text, nullable=False)  # JSON snapshot of original inventory
    result = db.Column(db.String(20), nullable=True)  # 'match' or 'mismatch' after completion
    mismatches = db.Column(db.Text, nullable=True)  # JSON details of any mismatches found
    confidence_score = db.Column(db.Float, nullable=True)  # Statistical confidence percentage

    original_session = db.relationship(
        "StocktakeSession", foreign_keys=[original_session_id]
    )
    spotcheck_session = db.relationship(
        "StocktakeSession", foreign_keys=[spotcheck_session_id]
    )

    def __repr__(self):
        return f"<SpotCheck {self.id} orig={self.original_session_id} status={self.status}>"
