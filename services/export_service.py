"""CSV export generation."""

import csv
import io
from models import LocationInventory, ScanEntry


def generate_summary_csv(session_id):
    """Generate a summary CSV (Location, Product, Checked Quantity)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Location", "Product", "Checked Quantity"])

    items = (
        LocationInventory.query
        .filter_by(session_id=session_id)
        .filter(LocationInventory.quantity > 0)
        .order_by(LocationInventory.location, LocationInventory.sku)
        .all()
    )

    for item in items:
        writer.writerow([item.location, item.sku, item.quantity])

    output.seek(0)
    return output.getvalue()


def generate_scan_log_csv(session_id):
    """Generate a full scan log CSV with all entries."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "location", "sku", "quantity_change",
        "running_total", "scan_type"
    ])

    entries = (
        ScanEntry.query
        .filter_by(session_id=session_id)
        .order_by(ScanEntry.scanned_at.asc())
        .all()
    )

    for entry in entries:
        writer.writerow([
            entry.scanned_at.isoformat(),
            entry.location,
            entry.sku,
            entry.quantity_change,
            entry.running_total,
            entry.scan_type,
        ])

    output.seek(0)
    return output.getvalue()
