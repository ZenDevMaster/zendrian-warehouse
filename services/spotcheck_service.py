"""Spot check creation, comparison, and statistical analysis."""

import json
import random
import math
from datetime import datetime
from models import db, StocktakeSession, LocationInventory, SpotCheck
from services import session_service


def get_closed_normal_sessions():
    """Get all closed, normal-type sessions suitable for spot checking."""
    return (
        StocktakeSession.query
        .filter_by(is_open=False, session_type="normal")
        .order_by(StocktakeSession.closed_at.desc())
        .all()
    )


def get_session_locations(session_id):
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


def snapshot_inventory(session_id, locations):
    """Create a JSON snapshot of inventory at the given locations.

    Returns a dict: {location: {sku: quantity, ...}, ...}
    """
    inventory = (
        LocationInventory.query
        .filter(
            LocationInventory.session_id == session_id,
            LocationInventory.location.in_(locations),
            LocationInventory.quantity > 0,
        )
        .all()
    )

    snapshot = {}
    for item in inventory:
        if item.location not in snapshot:
            snapshot[item.location] = {}
        snapshot[item.location][item.sku] = item.quantity

    return snapshot


def select_locations_by_percentage(session_id, percentage):
    """Randomly select a percentage of locations from a session.

    Returns a list of location names.
    """
    all_locations = get_session_locations(session_id)
    location_names = [loc.location for loc in all_locations]

    if not location_names:
        return []

    count = max(1, math.ceil(len(location_names) * percentage / 100))
    count = min(count, len(location_names))

    return sorted(random.sample(location_names, count))


def create_spotcheck(original_session_id, assigned_user, selection_mode,
                     selected_locations=None, selection_percentage=None):
    """Create a spot check with a new scanning session.

    Args:
        original_session_id: ID of the original session to check.
        assigned_user: Username to assign the spot check to.
        selection_mode: 'specific' or 'percentage'.
        selected_locations: List of location names (for specific mode).
        selection_percentage: Percentage value (for percentage mode).

    Returns:
        The created SpotCheck object.
    """
    original = session_service.get_session(original_session_id)
    if not original:
        raise ValueError("Original session not found")

    # Determine locations to check
    if selection_mode == "percentage":
        if not selection_percentage:
            raise ValueError("Percentage required for percentage mode")
        locations = select_locations_by_percentage(original_session_id, selection_percentage)
    elif selection_mode == "specific":
        if not selected_locations:
            raise ValueError("Locations required for specific mode")
        locations = sorted(selected_locations)
    else:
        raise ValueError(f"Invalid selection mode: {selection_mode}")

    if not locations:
        raise ValueError("No locations selected")

    # Snapshot the expected inventory
    expected = snapshot_inventory(original_session_id, locations)

    # Find the assigned user's ID
    from models import User
    user = User.query.filter_by(username=assigned_user).first()
    if not user:
        raise ValueError(f"User '{assigned_user}' not found")

    # Create the spot check scanning session
    session_name = f"Spot Check: #{original.session_code}"
    sc_session = StocktakeSession(
        session_code=session_service.generate_session_code(),
        operator_id=user.id,
        owner=assigned_user,
        name=session_name,
        session_type="spotcheck",
    )
    db.session.add(sc_session)
    db.session.flush()  # Get the ID

    # Create the SpotCheck record
    spotcheck = SpotCheck(
        original_session_id=original_session_id,
        spotcheck_session_id=sc_session.id,
        assigned_user=assigned_user,
        selection_mode=selection_mode,
        selection_percentage=selection_percentage,
        selected_locations=json.dumps(locations),
        expected_inventory=json.dumps(expected),
        status="pending",
    )
    db.session.add(spotcheck)
    db.session.commit()

    return spotcheck


def get_spotcheck(spotcheck_id):
    """Get a spot check by ID."""
    return db.session.get(SpotCheck, spotcheck_id)


def get_all_spotchecks():
    """Get all spot checks ordered by most recent first."""
    return SpotCheck.query.order_by(SpotCheck.created_at.desc()).all()


def get_spotcheck_by_session(session_id):
    """Get the spot check associated with a scanning session."""
    return SpotCheck.query.filter_by(spotcheck_session_id=session_id).first()


def get_selected_locations(spotcheck):
    """Get the list of selected locations from a spot check."""
    return json.loads(spotcheck.selected_locations)


def complete_spotcheck(spotcheck_id):
    """Complete a spot check by comparing actual vs expected inventory.

    Called when the spot check session is closed.

    Returns:
        The updated SpotCheck object with results.
    """
    spotcheck = get_spotcheck(spotcheck_id)
    if not spotcheck:
        return None

    expected = json.loads(spotcheck.expected_inventory)
    selected_locations = json.loads(spotcheck.selected_locations)

    # Get actual inventory from the spot check session
    actual = snapshot_inventory(spotcheck.spotcheck_session_id, selected_locations)

    # Compare location by location, item by item
    mismatches = []
    for location in selected_locations:
        expected_items = expected.get(location, {})
        actual_items = actual.get(location, {})

        # All SKUs from both expected and actual
        all_skus = set(list(expected_items.keys()) + list(actual_items.keys()))

        for sku in sorted(all_skus):
            exp_qty = expected_items.get(sku, 0)
            act_qty = actual_items.get(sku, 0)

            if exp_qty != act_qty:
                mismatches.append({
                    "location": location,
                    "sku": sku,
                    "expected": exp_qty,
                    "actual": act_qty,
                    "difference": act_qty - exp_qty,
                })

    # Determine result
    if len(mismatches) == 0:
        result = "match"
    else:
        result = "mismatch"

    # Calculate statistical confidence
    original_session = spotcheck.original_session
    total_locations = original_session.unique_locations
    sample_size = len(selected_locations)

    # Count locations with mismatches
    mismatch_locations = len(set(m["location"] for m in mismatches))

    confidence = calculate_confidence(total_locations, sample_size, mismatch_locations)

    # Update the spot check record
    spotcheck.status = "completed"
    spotcheck.result = result
    spotcheck.mismatches = json.dumps(mismatches) if mismatches else None
    spotcheck.confidence_score = confidence

    db.session.commit()

    return spotcheck


def calculate_confidence(N, n, k):
    """Calculate statistical confidence using hypergeometric distribution.

    Args:
        N: Total number of locations in original session (population size).
        n: Number of locations spot checked (sample size).
        k: Number of locations with mismatches found in sample.

    Returns:
        Confidence score as a percentage (0-100).
    """
    if N <= 0 or n <= 0:
        return 0.0

    if n > N:
        n = N

    if k == 0:
        # No mismatches found — calculate detection probability
        # P(detect ≥ 1 defect | D=1 defect exists) = 1 - C(N-1, n) / C(N, n) = n/N
        # More generally, for D defects:
        # P(detect ≥ 1 | D) = 1 - C(N-D, n) / C(N, n)
        # We report the probability of detecting at least one error
        # assuming there was exactly 1 defective location
        # This simplifies to n/N
        detection_prob = n / N * 100

        # Also calculate 95% upper confidence bound on defect rate
        # Using the formula: if we sample n from N and find 0 defects,
        # the 95% upper bound on the number of defects D is:
        # Find largest D where P(finding 0 in sample | D defects) > 0.05
        # P(0 defects in sample | D) = C(N-D, n) / C(N, n)
        # We want P(0|D) <= 0.05, i.e., C(N-D,n)/C(N,n) <= 0.05

        return round(detection_prob, 1)
    else:
        # Mismatches found — estimate defect rate
        # Point estimate: k/n * N (estimated total defective locations)
        # Confidence is lower when mismatches are found
        # Report as: (1 - k/n) * 100 = percentage of sample that matched
        match_rate = (1 - k / n) * 100
        return round(match_rate, 1)


def get_confidence_description(spotcheck):
    """Generate a human-readable description of the confidence statistics.

    Returns a dict with statistical details.
    """
    if not spotcheck or spotcheck.status != "completed":
        return None

    selected_locations = json.loads(spotcheck.selected_locations)
    n = len(selected_locations)
    N = spotcheck.original_session.unique_locations

    mismatches = json.loads(spotcheck.mismatches) if spotcheck.mismatches else []
    k = len(set(m["location"] for m in mismatches))

    stats = {
        "total_locations": N,
        "sample_size": n,
        "sample_percentage": round(n / N * 100, 1) if N > 0 else 0,
        "mismatch_locations": k,
        "total_mismatches": len(mismatches),
    }

    if k == 0:
        # Calculate detection probability for various assumed defect counts
        detection_probs = []
        for D in [1, 2, 3]:
            if D <= N:
                try:
                    prob = 1 - math.comb(N - D, n) / math.comb(N, n)
                    detection_probs.append({
                        "assumed_defects": D,
                        "detection_probability": round(prob * 100, 1),
                    })
                except (ValueError, ZeroDivisionError):
                    pass

        stats["detection_probs"] = detection_probs
        stats["description"] = (
            f"Checked {n} of {N} locations ({stats['sample_percentage']}%). "
            f"No discrepancies found. "
            f"If 1 location had errors, there was a {round(n/N*100, 1)}% chance of detecting it."
        )

        # 95% upper confidence bound on defect rate
        # Find max D where C(N-D,n)/C(N,n) > 0.05
        upper_bound_D = 0
        for D in range(1, N + 1):
            try:
                p_miss = math.comb(N - D, n) / math.comb(N, n)
                if p_miss <= 0.05:
                    upper_bound_D = D
                    break
            except (ValueError, ZeroDivisionError):
                upper_bound_D = D
                break

        if upper_bound_D > 0:
            stats["upper_bound_defects"] = upper_bound_D
            stats["upper_bound_rate"] = round(upper_bound_D / N * 100, 1)
        else:
            stats["upper_bound_defects"] = 0
            stats["upper_bound_rate"] = 0.0

    else:
        # Mismatches found
        estimated_total = round(k / n * N)
        estimated_rate = round(k / n * 100, 1)

        stats["estimated_total_defects"] = estimated_total
        stats["estimated_defect_rate"] = estimated_rate
        stats["description"] = (
            f"Checked {n} of {N} locations ({stats['sample_percentage']}%). "
            f"Found discrepancies in {k} location(s). "
            f"Estimated {estimated_rate}% of all locations may have errors "
            f"(~{estimated_total} of {N} locations)."
        )

    return stats
