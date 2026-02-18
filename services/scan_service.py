"""Scan processing and validation logic."""

import re
from datetime import datetime
from models import db, ScanEntry, LocationInventory, StocktakeSession

LOCATION_PATTERN = re.compile(r"^[A-Za-z0-9]+\.[A-Za-z0-9]+\.[A-Za-z0-9]+$")
CMD_PATTERN = re.compile(r"^CMD-[A-Z0-9]+$", re.IGNORECASE)


class ScanResult:
    """Encapsulates the result of processing a scan."""

    def __init__(self, success, message, sound="bleep", scan_type=None,
                 location=None, sku=None, quantity=None, running_total=None):
        self.success = success
        self.message = message
        self.sound = sound
        self.scan_type = scan_type
        self.location = location
        self.sku = sku
        self.quantity = quantity
        self.running_total = running_total


def classify_input(raw_input):
    """Classify scan input as location, command, or SKU."""
    text = raw_input.strip()
    if not text:
        return "empty", text

    if CMD_PATTERN.match(text):
        return "command", text.upper()

    if LOCATION_PATTERN.match(text):
        return "location", text.upper()

    # Everything else is treated as a SKU
    return "sku", text.upper()


def process_scan(session_id, raw_input, current_location, mode="add", bulk_qty=None):
    """
    Process a single scan input.

    Args:
        session_id: The active session ID.
        raw_input: Raw string from the barcode scanner.
        current_location: The currently active location (or None).
        mode: 'add', 'subtract', or 'bulk'.
        bulk_qty: Quantity for bulk mode.

    Returns:
        ScanResult with outcome details.
    """
    input_type, value = classify_input(raw_input)

    if input_type == "empty":
        return ScanResult(False, "Empty scan input.", sound="error")

    # --- Location scanned ---
    if input_type == "location":
        return ScanResult(
            success=True,
            message=f"Location set to {value}",
            sound="newlocation",
            scan_type="LOCATION",
            location=value,
        )

    # --- Command scanned ---
    if input_type == "command":
        return _handle_command(value, session_id, current_location)

    # --- SKU scanned ---
    if not current_location:
        return ScanResult(
            False,
            "No location set. Please scan a location first.",
            sound="error",
        )

    session = StocktakeSession.query.get(session_id)
    if not session or not session.is_open:
        return ScanResult(False, "Session is not open.", sound="error")

    # Determine quantity change
    if mode == "subtract":
        return _subtract_sku(session, current_location, value)
    elif mode == "bulk" and bulk_qty:
        return _add_sku(session, current_location, value, bulk_qty, "BULK")
    else:
        return _add_sku(session, current_location, value, 1, "ADD")


def _add_sku(session, location, sku, quantity, scan_type):
    """Add quantity of a SKU at a location."""
    inv = LocationInventory.query.filter_by(
        session_id=session.id, location=location, sku=sku
    ).first()

    if inv:
        inv.quantity += quantity
    else:
        inv = LocationInventory(
            session_id=session.id, location=location, sku=sku, quantity=quantity
        )
        db.session.add(inv)

    # Create audit entry
    entry = ScanEntry(
        session_id=session.id,
        location=location,
        sku=sku,
        quantity_change=quantity,
        running_total=inv.quantity,
        scan_type=scan_type,
    )
    db.session.add(entry)

    # Update session counters
    session.total_scans += 1
    session.last_scan_at = datetime.utcnow()

    db.session.commit()

    return ScanResult(
        success=True,
        message=f"+{quantity} {sku} → Total: {inv.quantity}",
        sound="bleep",
        scan_type=scan_type,
        location=location,
        sku=sku,
        quantity=quantity,
        running_total=inv.quantity,
    )


def _subtract_sku(session, location, sku):
    """Subtract 1 from a SKU at a location."""
    inv = LocationInventory.query.filter_by(
        session_id=session.id, location=location, sku=sku
    ).first()

    if not inv or inv.quantity <= 0:
        return ScanResult(
            False,
            f"Cannot subtract. {sku} has quantity {inv.quantity if inv else 0}",
            sound="error",
        )

    inv.quantity -= 1

    entry = ScanEntry(
        session_id=session.id,
        location=location,
        sku=sku,
        quantity_change=-1,
        running_total=inv.quantity,
        scan_type="SUBTRACT",
    )
    db.session.add(entry)

    session.total_scans += 1
    session.last_scan_at = datetime.utcnow()

    db.session.commit()

    return ScanResult(
        success=True,
        message=f"-1 {sku} → Total: {inv.quantity}",
        sound="deleted",
        scan_type="SUBTRACT",
        location=location,
        sku=sku,
        quantity=-1,
        running_total=inv.quantity,
    )


def adjust_quantity(session_id, location, sku, new_quantity):
    """Directly set the quantity for a SKU at a location."""
    session = StocktakeSession.query.get(session_id)
    if not session or not session.is_open:
        return ScanResult(False, "Session is not open.", sound="error")

    inv = LocationInventory.query.filter_by(
        session_id=session_id, location=location, sku=sku
    ).first()

    if not inv:
        return ScanResult(False, f"SKU {sku} not found at {location}.", sound="error")

    old_qty = inv.quantity
    change = new_quantity - old_qty
    inv.quantity = new_quantity

    entry = ScanEntry(
        session_id=session_id,
        location=location,
        sku=sku,
        quantity_change=change,
        running_total=new_quantity,
        scan_type="ADJUST",
    )
    db.session.add(entry)

    session.total_scans += 1
    session.last_scan_at = datetime.utcnow()

    db.session.commit()

    return ScanResult(
        success=True,
        message=f"Adjusted {sku}: {old_qty} → {new_quantity}",
        sound="bleep",
        scan_type="ADJUST",
        location=location,
        sku=sku,
        quantity=change,
        running_total=new_quantity,
    )


def get_location_inventory(session_id, location):
    """Get all SKUs and quantities at a location for a session."""
    return (
        LocationInventory.query
        .filter_by(session_id=session_id, location=location)
        .filter(LocationInventory.quantity > 0)
        .order_by(LocationInventory.sku)
        .all()
    )


def get_all_locations(session_id):
    """Get all locations with item counts for a session."""
    results = (
        db.session.query(
            LocationInventory.location,
            db.func.count(LocationInventory.sku).label("sku_count"),
            db.func.sum(LocationInventory.quantity).label("total_items"),
        )
        .filter_by(session_id=session_id)
        .filter(LocationInventory.quantity > 0)
        .group_by(LocationInventory.location)
        .order_by(LocationInventory.location)
        .all()
    )
    return results


def get_recent_scans(session_id, limit=10):
    """Get the most recent scan entries for a session."""
    return (
        ScanEntry.query
        .filter_by(session_id=session_id)
        .order_by(ScanEntry.scanned_at.desc())
        .limit(limit)
        .all()
    )


def _handle_command(cmd, session_id, current_location):
    """Handle a CMD-* command."""
    if cmd == "CMD-END":
        return ScanResult(
            success=True,
            message="Session end requested.",
            sound="success",
            scan_type="CMD-END",
        )
    elif cmd == "CMD-SUB":
        return ScanResult(
            success=True,
            message="Subtract mode activated. Next scan will subtract 1.",
            sound="bleep",
            scan_type="CMD-SUB",
        )
    elif cmd == "CMD-BULK":
        return ScanResult(
            success=True,
            message="Bulk mode activated. Enter quantity.",
            sound="bleep",
            scan_type="CMD-BULK",
        )
    elif cmd == "CMD-STATS":
        return ScanResult(
            success=True,
            message="Showing statistics.",
            sound="bleep",
            scan_type="CMD-STATS",
        )
    elif cmd == "CMD-LAST5":
        return ScanResult(
            success=True,
            message="Showing last 5 scans.",
            sound="bleep",
            scan_type="CMD-LAST5",
        )
    else:
        return ScanResult(False, f"Unknown command: {cmd}", sound="error")
