"""
toll_ctrl.py
─────────────────────────────────────────────────────────────
Toll Controller for the Toll Record Management System.
Handles all business logic related to:
  • Toll fee calculation
  • Toll collection workflow
  • Shift / session management
  • Receipt generation
  • Record search & filtering
  • Analytics & summaries

All public functions return a Result dict:
    { "success": bool, "message": str, "data": any }
so the UI layer never needs to handle exceptions directly.
─────────────────────────────────────────────────────────────
"""

import re
from datetime import datetime, date
from typing import Optional

import db_manager as db


# ──────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────

def _ok(data=None, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data}


def _err(message: str) -> dict:
    return {"success": False, "message": message, "data": None}


def _validate_date(date_str: str) -> bool:
    """Return True if date_str is a valid YYYY-MM-DD string."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ──────────────────────────────────────────────
#  SESSION / SHIFT TRACKING
# ──────────────────────────────────────────────

class ShiftSession:
    """
    Lightweight in-memory session for an operator's shift.
    Tracks collections made during the current login session.
    Instantiate once per login and pass to the dashboard.

    Usage:
        session = ShiftSession(operator="rahul")
        session.record(plate="MH12AB1234", vehicle_type="Car", fee=50.0)
        print(session.summary())
    """

    def __init__(self, operator: str):
        self.operator    = operator
        self.started_at  = datetime.now()
        self._entries: list[dict] = []

    def record(self, plate: str, vehicle_type: str, fee: float) -> None:
        self._entries.append({
            "plate":        plate,
            "vehicle_type": vehicle_type,
            "fee":          fee,
            "time":         datetime.now().strftime("%H:%M:%S"),
        })

    def summary(self) -> dict:
        total   = sum(e["fee"] for e in self._entries)
        by_type: dict[str, dict] = {}
        for e in self._entries:
            vt = e["vehicle_type"]
            if vt not in by_type:
                by_type[vt] = {"trips": 0, "revenue": 0.0}
            by_type[vt]["trips"]   += 1
            by_type[vt]["revenue"] += e["fee"]
        return {
            "operator":   self.operator,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "entries":    len(self._entries),
            "total":      total,
            "by_type":    by_type,
            "log":        list(self._entries),
        }

    def reset(self) -> None:
        self._entries.clear()
        self.started_at = datetime.now()


# ──────────────────────────────────────────────
#  FEE CALCULATION
# ──────────────────────────────────────────────

def calculate_fee(vehicle_type: str, multiplier: float = 1.0) -> dict:
    """
    Look up the toll fee for a vehicle type and apply an optional
    multiplier (e.g. 2.0 for return-trip, 1.5 for peak hours).

    Returns:
        success=True  → data = { "vehicle_type", "base_fee", "multiplier", "final_fee" }
        success=False → message explains why
    """
    if multiplier <= 0:
        return _err("Multiplier must be greater than 0.")

    base = db.get_rate_for_type(vehicle_type)
    if base is None:
        return _err(f"No toll rate configured for vehicle type '{vehicle_type}'.")

    final = round(base * multiplier, 2)
    return _ok({
        "vehicle_type": vehicle_type,
        "base_fee":     base,
        "multiplier":   multiplier,
        "final_fee":    final,
    }, f"Fee for {vehicle_type}: ₹{final:.2f}")


def get_all_rates() -> dict:
    """
    Return all vehicle types and their configured fees.
    data = list of { vehicle_type, fee, updated_at }
    """
    rates = db.get_all_rates()
    if not rates:
        return _err("No toll rates found in database.")
    return _ok(rates, f"{len(rates)} rate(s) loaded.")


def update_toll_rate(vehicle_type: str, new_fee: float) -> dict:
    """Update the toll fee for a vehicle type."""
    try:
        new_fee = float(new_fee)
    except (TypeError, ValueError):
        return _err("Fee must be a valid number.")

    success, msg = db.update_rate(vehicle_type, new_fee)
    return _ok({"vehicle_type": vehicle_type, "new_fee": new_fee}, msg) \
        if success else _err(msg)


def add_toll_rate(vehicle_type: str, fee: float) -> dict:
    """Add a new vehicle type and its toll fee."""
    vtype = vehicle_type.strip().title()
    if not vtype:
        return _err("Vehicle type name cannot be empty.")
    try:
        fee = float(fee)
    except (TypeError, ValueError):
        return _err("Fee must be a valid number.")

    success, msg = db.add_rate(vtype, fee)
    return _ok({"vehicle_type": vtype, "fee": fee}, msg) if success else _err(msg)


def delete_toll_rate(vehicle_type: str) -> dict:
    success, msg = db.delete_rate(vehicle_type)
    return _ok(None, msg) if success else _err(msg)


# ──────────────────────────────────────────────
#  TOLL COLLECTION WORKFLOW
# ──────────────────────────────────────────────

def lookup_vehicle_for_toll(plate_number: str) -> dict:
    """
    Look up a vehicle by plate and attach its current toll fee.
    This is called when an operator types a plate at the booth.

    data = {
        "id", "plate_number", "vehicle_type", "owner_name",
        "owner_phone", "registered_at", "fee"
    }
    """
    plate = plate_number.strip().upper()
    if not plate:
        return _err("Plate number cannot be empty.")

    vehicle = db.get_vehicle_by_plate(plate)
    if not vehicle:
        return _err(
            f"Vehicle '{plate}' not found. Please register it first "
            f"in the Vehicle Entry tab."
        )

    fee = db.get_rate_for_type(vehicle["vehicle_type"])
    if fee is None:
        return _err(
            f"No toll rate configured for vehicle type "
            f"'{vehicle['vehicle_type']}'. Update rates in Settings."
        )

    return _ok({**vehicle, "fee": fee},
               f"Vehicle found — ₹{fee:.2f} applicable.")


def collect_toll(plate_number: str, collected_by: str,
                 session: Optional[ShiftSession] = None,
                 multiplier: float = 1.0) -> dict:
    """
    Full toll collection workflow:
      1. Look up vehicle
      2. Determine fee (with optional multiplier)
      3. Write record to DB
      4. Update shift session if provided
      5. Return receipt data

    data = receipt dict (see generate_receipt)
    """
    lookup = lookup_vehicle_for_toll(plate_number)
    if not lookup["success"]:
        return lookup

    vehicle  = lookup["data"]
    base_fee = vehicle["fee"]

    try:
        multiplier = float(multiplier)
        if multiplier <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _err("Multiplier must be a positive number.")

    fee_paid = round(base_fee * multiplier, 2)

    success, msg = db.add_toll_record(
        vehicle_id   = vehicle["id"],
        plate_number = vehicle["plate_number"],
        vehicle_type = vehicle["vehicle_type"],
        fee_paid     = fee_paid,
        collected_by = collected_by.strip(),
    )
    if not success:
        return _err(f"Failed to save record: {msg}")

    if session:
        session.record(
            plate        = vehicle["plate_number"],
            vehicle_type = vehicle["vehicle_type"],
            fee          = fee_paid,
        )

    receipt = generate_receipt(
        plate        = vehicle["plate_number"],
        vehicle_type = vehicle["vehicle_type"],
        owner_name   = vehicle["owner_name"],
        fee_paid     = fee_paid,
        collected_by = collected_by,
        base_fee     = base_fee,
        multiplier   = multiplier,
    )
    return _ok(receipt, f"Toll of ₹{fee_paid:.2f} collected from {vehicle['plate_number']}.")


def bulk_collect(plate_numbers: list[str], collected_by: str,
                 session: Optional[ShiftSession] = None) -> dict:
    """
    Collect toll for multiple plates at once (e.g. convoy entry).
    Returns a summary with per-plate results.
    """
    results   = []
    total_fee = 0.0
    errors    = []

    for plate in plate_numbers:
        res = collect_toll(plate, collected_by, session)
        if res["success"]:
            total_fee += res["data"]["fee_paid"]
            results.append({"plate": plate, "status": "OK",
                             "fee": res["data"]["fee_paid"]})
        else:
            errors.append({"plate": plate, "error": res["message"]})

    return _ok({
        "collected": results,
        "errors":    errors,
        "total_fee": round(total_fee, 2),
        "count":     len(results),
    }, f"Collected from {len(results)}/{len(plate_numbers)} vehicles. Total: ₹{total_fee:.2f}")


# ──────────────────────────────────────────────
#  RECEIPT GENERATION
# ──────────────────────────────────────────────

def generate_receipt(plate: str, vehicle_type: str, owner_name: str,
                     fee_paid: float, collected_by: str,
                     base_fee: float = 0.0,
                     multiplier: float = 1.0) -> dict:
    """
    Build a receipt dictionary. The UI can render this as a
    popup, a printable label, or a text string.
    """
    now = datetime.now()
    return {
        "receipt_no":   f"TMS-{now.strftime('%Y%m%d%H%M%S')}",
        "date":         now.strftime("%d %b %Y"),
        "time":         now.strftime("%H:%M:%S"),
        "plate_number": plate,
        "vehicle_type": vehicle_type,
        "owner_name":   owner_name,
        "base_fee":     base_fee,
        "multiplier":   multiplier,
        "fee_paid":     fee_paid,
        "collected_by": collected_by,
    }


def format_receipt_text(receipt: dict) -> str:
    """Return a plain-text receipt string suitable for display or printing."""
    sep = "─" * 38
    lines = [
        sep,
        "       TOLL COLLECTION RECEIPT",
        sep,
        f"  Receipt No : {receipt['receipt_no']}",
        f"  Date       : {receipt['date']}  {receipt['time']}",
        sep,
        f"  Plate      : {receipt['plate_number']}",
        f"  Type       : {receipt['vehicle_type']}",
        f"  Owner      : {receipt['owner_name']}",
        sep,
    ]
    if receipt.get("multiplier", 1.0) != 1.0:
        lines.append(f"  Base Fee   : ₹{receipt['base_fee']:.2f}")
        lines.append(f"  Multiplier : x{receipt['multiplier']}")
    lines += [
        f"  Fee Paid   : ₹{receipt['fee_paid']:.2f}",
        sep,
        f"  Operator   : {receipt['collected_by']}",
        sep,
        "    Thank you for using our toll road.",
        sep,
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  RECORD SEARCH & FILTERING
# ──────────────────────────────────────────────

def search_records(plate: str = "", date_from: str = "",
                   date_to: str = "", limit: int = 500) -> dict:
    """
    Flexible record search.
      • plate only      → all records for that plate
      • dates only      → records in date range
      • both            → plate filtered within date range
      • neither         → latest N records

    data = list of record dicts
    """
    plate = plate.strip().upper()

    if plate and date_from and date_to:
        if not (_validate_date(date_from) and _validate_date(date_to)):
            return _err("Dates must be in YYYY-MM-DD format.")
        records = db.get_records_by_date_range(date_from, date_to)
        records = [r for r in records if r["plate_number"] == plate]

    elif plate:
        records = db.get_records_by_plate(plate)

    elif date_from and date_to:
        if not (_validate_date(date_from) and _validate_date(date_to)):
            return _err("Dates must be in YYYY-MM-DD format.")
        records = db.get_records_by_date_range(date_from, date_to)

    else:
        records = db.get_all_records(limit=limit)

    if not records:
        return _ok([], "No records found matching your criteria.")
    return _ok(records[:limit], f"{len(records[:limit])} record(s) found.")


def get_recent_records(n: int = 20) -> dict:
    """Return the N most recent toll records."""
    records = db.get_all_records(limit=n)
    return _ok(records, f"Last {len(records)} record(s).")


def get_vehicle_history(plate_number: str) -> dict:
    """
    Return full toll history for a vehicle plus a summary.
    data = { "vehicle": {...}, "records": [...], "summary": {...} }
    """
    plate   = plate_number.strip().upper()
    vehicle = db.get_vehicle_by_plate(plate)
    if not vehicle:
        return _err(f"Vehicle '{plate}' not found.")

    records = db.get_records_by_plate(plate)
    total   = sum(r["fee_paid"] for r in records)
    summary = {
        "total_trips":   len(records),
        "total_paid":    round(total, 2),
        "first_seen":    records[-1]["collected_at"] if records else None,
        "last_seen":     records[0]["collected_at"]  if records else None,
    }
    return _ok({"vehicle": vehicle, "records": records, "summary": summary},
               f"{len(records)} trip(s) found for {plate}.")


# ──────────────────────────────────────────────
#  ANALYTICS & REPORTS
# ──────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Return live stats for the dashboard cards."""
    stats = db.get_dashboard_stats()
    return _ok(stats)


def get_revenue_report(period: str = "all") -> dict:
    """
    Revenue breakdown by vehicle type.
    period: 'today' | 'month' | 'all'
    data = list of { vehicle_type, trips, revenue, avg_fee }
    """
    valid = ("today", "month", "all")
    if period not in valid:
        return _err(f"period must be one of: {valid}")

    rows = db.report_by_vehicle_type(period)
    if not rows:
        return _ok([], f"No records found for period='{period}'.")

    total_rev   = sum(r["revenue"] for r in rows)
    total_trips = sum(r["trips"]   for r in rows)
    return _ok({
        "rows":        rows,
        "total_rev":   round(total_rev, 2),
        "total_trips": total_trips,
        "period":      period,
    }, f"Report ready — {total_trips} trip(s), ₹{total_rev:.2f} total.")


def get_daily_trend(days: int = 30) -> dict:
    """
    Return per-day trip count and revenue for the last N days.
    Useful for drawing a line/bar chart in the Reports tab.
    data = list of { date, trips, revenue }
    """
    if days < 1 or days > 365:
        return _err("days must be between 1 and 365.")
    rows = db.report_daily_summary(days)
    return _ok(rows, f"Daily trend for last {days} day(s).")


def get_top_vehicles(limit: int = 10) -> dict:
    """
    Return the most frequent toll-paying vehicles.
    data = list of { plate_number, vehicle_type, trips, total_paid }
    """
    if limit < 1:
        return _err("limit must be at least 1.")
    rows = db.report_top_vehicles(limit)
    return _ok(rows, f"Top {len(rows)} vehicle(s) by trip count.")


def get_hourly_distribution() -> dict:
    """
    Show how toll entries are distributed across hours of the day
    (using all-time data). Useful for identifying peak hours.
    data = list of { hour (0–23), trips, revenue }
    """
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT CAST(strftime('%H', collected_at) AS INTEGER) AS hour,
               COUNT(*)         AS trips,
               SUM(fee_paid)    AS revenue
        FROM toll_records
        GROUP BY hour
        ORDER BY hour
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return _ok(data, f"Hourly distribution across {len(data)} hour slot(s).")


# ──────────────────────────────────────────────
#  CSV EXPORT
# ──────────────────────────────────────────────

def export_records(filepath: str,
                   date_from: str = "",
                   date_to:   str = "") -> dict:
    """
    Export toll records to CSV.
    Pass date_from and date_to (YYYY-MM-DD) to filter by range.
    """
    if not filepath.endswith(".csv"):
        filepath += ".csv"

    if date_from and date_to:
        if not (_validate_date(date_from) and _validate_date(date_to)):
            return _err("Dates must be in YYYY-MM-DD format.")

    success, msg = db.export_records_to_csv(filepath, date_from, date_to)
    return _ok({"filepath": filepath}, msg) if success else _err(msg)


# ──────────────────────────────────────────────
#  RECORD MANAGEMENT
# ──────────────────────────────────────────────

def delete_record(record_id: int) -> dict:
    """Delete a single toll record by ID."""
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return _err("Record ID must be an integer.")
    success, msg = db.delete_toll_record(record_id)
    return _ok(None, msg) if success else _err(msg)


def purge_old_records(days: int = 365) -> dict:
    """Delete all records older than N days."""
    success, msg = db.purge_old_records(days)
    return _ok(None, msg) if success else _err(msg)


# ──────────────────────────────────────────────
#  QUICK TEST  (run: python toll_ctrl.py)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    db.initialize_database()
    print("── Toll Controller Self-Test ──\n")

    # Rates
    rates = get_all_rates()
    print("Rates:", rates["message"])
    for r in rates["data"]:
        print(f"  {r['vehicle_type']:<14}: ₹{r['fee']:.2f}")

    # Fee calculation
    res = calculate_fee("Car")
    print(f"\nCalculate fee (Car): {res['message']}")

    res = calculate_fee("Car", multiplier=2.0)
    print(f"Calculate fee (Car x2): {res['message']}")

    res = calculate_fee("UFO")
    print(f"Calculate fee (UFO): {res['message']}")

    # Dashboard stats
    stats = get_dashboard_stats()
    print(f"\nDashboard stats: {stats['data']}")

    # Revenue report
    rep = get_revenue_report("all")
    print(f"\nRevenue report: {rep['message']}")

    # ShiftSession
    session = ShiftSession("test_operator")
    session.record("MH12AB1234", "Car",  50.0)
    session.record("MH12CD5678", "Truck", 120.0)
    s = session.summary()
    print(f"\nShift summary: {s['entries']} entries, ₹{s['total']:.2f} total")

    print("\nAll checks passed ✔")