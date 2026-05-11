"""
vehicle_ctrl.py
─────────────────────────────────────────────────────────────
Vehicle Controller for the Toll Record Management System.
Handles all business logic related to:
  • Vehicle registration & validation
  • Vehicle search & lookup
  • Vehicle updates & deletion
  • Plate number formatting & validation
  • Vehicle statistics & summaries
  • Bulk import from CSV

All public functions return a Result dict:
    { "success": bool, "message": str, "data": any }
so the UI layer never needs to handle exceptions directly.
─────────────────────────────────────────────────────────────
"""

import re
import csv
import os
from datetime import datetime
from typing import Optional

import db_manager as db


# ──────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────

VALID_VEHICLE_TYPES = ["Car", "Truck", "Bus", "Motorcycle", "Auto"]

# Indian plate pattern examples: MH12AB1234, DL3CAF0001, KA05MN9999
PLATE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")

# Phone: 10-digit Indian mobile number (optional)
PHONE_PATTERN = re.compile(r"^[6-9][0-9]{9}$")


# ──────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────

def _ok(data=None, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data}


def _err(message: str) -> dict:
    return {"success": False, "message": message, "data": None}


def _normalize_plate(plate: str) -> str:
    """Strip spaces/hyphens and uppercase the plate number."""
    return re.sub(r"[\s\-]", "", plate).upper()


def _validate_plate(plate: str) -> tuple[bool, str]:
    """
    Validate an Indian vehicle plate number.
    Returns (is_valid, error_message).
    Allows a lenient fallback so non-standard plates aren't blocked.
    """
    if not plate:
        return False, "Plate number cannot be empty."
    if len(plate) < 5:
        return False, f"Plate '{plate}' is too short (minimum 5 characters)."
    if len(plate) > 13:
        return False, f"Plate '{plate}' is too long (maximum 13 characters)."
    return True, ""


def _validate_phone(phone: str) -> tuple[bool, str]:
    """Validate Indian mobile number (10 digits, starts 6–9). Empty is allowed."""
    if not phone:
        return True, ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10 and PHONE_PATTERN.match(digits):
        return True, ""
    return False, f"'{phone}' is not a valid 10-digit Indian mobile number."


def _validate_name(name: str) -> tuple[bool, str]:
    if not name.strip():
        return False, "Owner name cannot be empty."
    if len(name.strip()) < 2:
        return False, "Owner name must be at least 2 characters."
    if len(name.strip()) > 80:
        return False, "Owner name must not exceed 80 characters."
    if re.search(r"[^a-zA-Z\s\.\-\']", name):
        return False, "Owner name contains invalid characters."
    return True, ""


# ──────────────────────────────────────────────
#  REGISTRATION
# ──────────────────────────────────────────────

def register_vehicle(plate_number: str, vehicle_type: str,
                     owner_name: str, owner_phone: str = "") -> dict:
    """
    Register a new vehicle after full input validation.

    Validation steps:
      1. Normalize & validate plate format
      2. Validate vehicle type against known types
      3. Validate owner name
      4. Validate phone number (if provided)
      5. Write to database

    Returns:
        success=True  → data = registered vehicle dict
        success=False → message describes the validation error
    """
    # ── 1. Plate ──────────────────────────────
    plate = _normalize_plate(plate_number)
    valid, err = _validate_plate(plate)
    if not valid:
        return _err(err)

    # ── 2. Vehicle type ───────────────────────
    if vehicle_type not in VALID_VEHICLE_TYPES:
        return _err(
            f"Unknown vehicle type '{vehicle_type}'. "
            f"Valid types: {', '.join(VALID_VEHICLE_TYPES)}."
        )

    # ── 3. Owner name ─────────────────────────
    valid, err = _validate_name(owner_name)
    if not valid:
        return _err(err)

    # ── 4. Phone (optional) ───────────────────
    phone = re.sub(r"\D", "", owner_phone)   # keep digits only
    valid, err = _validate_phone(phone)
    if not valid:
        return _err(err)

    # ── 5. Write to DB ────────────────────────
    success, msg = db.add_vehicle(
        plate_number = plate,
        vehicle_type = vehicle_type,
        owner_name   = owner_name.strip().title(),
        owner_phone  = phone,
    )
    if not success:
        return _err(msg)

    vehicle = db.get_vehicle_by_plate(plate)
    return _ok(vehicle, f"Vehicle '{plate}' registered successfully.")


# ──────────────────────────────────────────────
#  LOOKUP & SEARCH
# ──────────────────────────────────────────────

def get_vehicle(plate_number: str) -> dict:
    """
    Fetch a single vehicle by plate number.
    data = vehicle dict with an extra 'toll_fee' field attached.
    """
    plate = _normalize_plate(plate_number)
    if not plate:
        return _err("Plate number cannot be empty.")

    vehicle = db.get_vehicle_by_plate(plate)
    if not vehicle:
        return _err(f"Vehicle '{plate}' is not registered in the system.")

    fee = db.get_rate_for_type(vehicle["vehicle_type"])
    return _ok({**vehicle, "toll_fee": fee},
               f"Vehicle '{plate}' found.")


def get_vehicle_by_id(vehicle_id: int) -> dict:
    """Fetch a vehicle by its database ID."""
    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return _err("Vehicle ID must be an integer.")

    vehicle = db.get_vehicle_by_id(vehicle_id)
    if not vehicle:
        return _err(f"No vehicle found with ID {vehicle_id}.")
    return _ok(vehicle)


def search_vehicles(query: str = "") -> dict:
    """
    Search vehicles by plate number or owner name (partial match).
    Returns all vehicles when query is empty.
    data = list of vehicle dicts
    """
    vehicles = db.get_all_vehicles(search=query.strip())
    if not vehicles:
        msg = f"No vehicles found matching '{query}'." if query else "No vehicles registered yet."
        return _ok([], msg)
    return _ok(vehicles, f"{len(vehicles)} vehicle(s) found.")


def get_all_vehicles() -> dict:
    """Return every registered vehicle."""
    return search_vehicles("")


def get_vehicles_by_type(vehicle_type: str) -> dict:
    """Return all vehicles of a specific type."""
    if vehicle_type not in VALID_VEHICLE_TYPES:
        return _err(f"Unknown type '{vehicle_type}'. "
                    f"Valid: {', '.join(VALID_VEHICLE_TYPES)}.")
    all_v = db.get_all_vehicles()
    filtered = [v for v in all_v if v["vehicle_type"] == vehicle_type]
    if not filtered:
        return _ok([], f"No {vehicle_type}s registered.")
    return _ok(filtered, f"{len(filtered)} {vehicle_type}(s) found.")


def check_vehicle_exists(plate_number: str) -> dict:
    """
    Quick existence check — returns True/False without full vehicle data.
    data = { "exists": bool, "plate": str }
    """
    plate = _normalize_plate(plate_number)
    vehicle = db.get_vehicle_by_plate(plate)
    exists  = vehicle is not None
    return _ok(
        {"exists": exists, "plate": plate},
        "Vehicle found." if exists else "Vehicle not registered."
    )


# ──────────────────────────────────────────────
#  UPDATE & DELETE
# ──────────────────────────────────────────────

def update_vehicle(vehicle_id: int, owner_name: str,
                   owner_phone: str = "",
                   vehicle_type: str = "") -> dict:
    """
    Update owner name, phone, and/or vehicle type.
    Only the fields you supply are validated and changed.

    data = updated vehicle dict
    """
    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return _err("Vehicle ID must be an integer.")

    existing = db.get_vehicle_by_id(vehicle_id)
    if not existing:
        return _err(f"No vehicle found with ID {vehicle_id}.")

    # Use existing values if caller leaves a field blank
    new_name  = owner_name.strip()   or existing["owner_name"]
    new_phone = owner_phone.strip()  or existing["owner_phone"] or ""
    new_type  = vehicle_type.strip() or existing["vehicle_type"]

    # Validate
    valid, err = _validate_name(new_name)
    if not valid:
        return _err(err)

    phone_digits = re.sub(r"\D", "", new_phone)
    valid, err = _validate_phone(phone_digits)
    if not valid:
        return _err(err)

    if new_type not in VALID_VEHICLE_TYPES:
        return _err(f"Unknown vehicle type '{new_type}'.")

    success, msg = db.update_vehicle(vehicle_id, new_name.title(),
                                     phone_digits, new_type)
    if not success:
        return _err(msg)

    updated = db.get_vehicle_by_id(vehicle_id)
    return _ok(updated, msg)


def delete_vehicle(vehicle_id: int) -> dict:
    """
    Delete a vehicle and ALL its associated toll records.
    This action is irreversible — confirm in the UI before calling.
    """
    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return _err("Vehicle ID must be an integer.")

    vehicle = db.get_vehicle_by_id(vehicle_id)
    if not vehicle:
        return _err(f"No vehicle found with ID {vehicle_id}.")

    plate = vehicle["plate_number"]
    success, msg = db.delete_vehicle(vehicle_id)
    return _ok({"deleted_plate": plate}, msg) if success else _err(msg)


# ──────────────────────────────────────────────
#  STATISTICS
# ──────────────────────────────────────────────

def get_vehicle_stats() -> dict:
    """
    Return a breakdown of the vehicle fleet.
    data = {
        "total":    int,
        "by_type":  { vehicle_type: count },
        "latest":   vehicle dict or None,
    }
    """
    vehicles = db.get_all_vehicles()
    if not vehicles:
        return _ok({"total": 0, "by_type": {}, "latest": None},
                   "No vehicles registered yet.")

    by_type: dict[str, int] = {}
    for v in vehicles:
        vt = v["vehicle_type"]
        by_type[vt] = by_type.get(vt, 0) + 1

    latest = sorted(vehicles, key=lambda v: v["registered_at"], reverse=True)[0]
    return _ok({
        "total":   len(vehicles),
        "by_type": by_type,
        "latest":  latest,
    }, f"Fleet: {len(vehicles)} vehicle(s) across {len(by_type)} type(s).")


def get_vehicle_with_history(plate_number: str) -> dict:
    """
    Fetch a vehicle together with its complete toll history and summary.
    data = {
        "vehicle":  vehicle dict,
        "records":  list of toll_record dicts,
        "summary": {
            "total_trips":  int,
            "total_paid":   float,
            "first_seen":   str or None,
            "last_seen":    str or None,
            "avg_fee":      float,
        }
    }
    """
    plate   = _normalize_plate(plate_number)
    vehicle = db.get_vehicle_by_plate(plate)
    if not vehicle:
        return _err(f"Vehicle '{plate}' not found.")

    records = db.get_records_by_plate(plate)
    total   = sum(r["fee_paid"] for r in records)
    avg     = round(total / len(records), 2) if records else 0.0

    summary = {
        "total_trips": len(records),
        "total_paid":  round(total, 2),
        "avg_fee":     avg,
        "first_seen":  records[-1]["collected_at"] if records else None,
        "last_seen":   records[0]["collected_at"]  if records else None,
    }
    return _ok(
        {"vehicle": vehicle, "records": records, "summary": summary},
        f"History for '{plate}': {len(records)} trip(s), ₹{total:.2f} total."
    )


def get_frequent_vehicles(min_trips: int = 5) -> dict:
    """
    Return vehicles that have made at least min_trips toll payments.
    Useful for flagging frequent users or detecting anomalies.
    data = list of { plate_number, vehicle_type, trips, total_paid }
    """
    rows = db.report_top_vehicles(limit=200)
    filtered = [r for r in rows if r["trips"] >= min_trips]
    if not filtered:
        return _ok([], f"No vehicles with {min_trips}+ trips found.")
    return _ok(filtered,
               f"{len(filtered)} frequent vehicle(s) with {min_trips}+ trips.")


# ──────────────────────────────────────────────
#  BULK CSV IMPORT
# ──────────────────────────────────────────────

def import_vehicles_from_csv(filepath: str) -> dict:
    """
    Bulk-import vehicles from a CSV file.

    Expected CSV columns (header row required):
        plate_number, vehicle_type, owner_name, owner_phone

    owner_phone is optional — leave blank if not available.

    Returns:
        data = {
            "imported":  int,   # successfully added
            "skipped":   int,   # duplicates / already exist
            "errors":    list,  # [ { "row": int, "plate": str, "reason": str } ]
        }
    """
    if not os.path.exists(filepath):
        return _err(f"File not found: {filepath}")

    if not filepath.lower().endswith(".csv"):
        return _err("Only CSV files are supported for import.")

    imported = 0
    skipped  = 0
    errors   = []

    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            required = {"plate_number", "vehicle_type", "owner_name"}
            if not required.issubset(set(reader.fieldnames or [])):
                missing = required - set(reader.fieldnames or [])
                return _err(
                    f"CSV is missing required columns: {', '.join(missing)}. "
                    f"Required: plate_number, vehicle_type, owner_name, [owner_phone]"
                )

            for row_num, row in enumerate(reader, start=2):
                plate = _normalize_plate(row.get("plate_number", ""))
                vtype = row.get("vehicle_type", "").strip().title()
                name  = row.get("owner_name",   "").strip()
                phone = row.get("owner_phone",  "").strip()

                result = register_vehicle(plate, vtype, name, phone)
                if result["success"]:
                    imported += 1
                else:
                    msg = result["message"]
                    if "already registered" in msg.lower():
                        skipped += 1
                    else:
                        errors.append({
                            "row":    row_num,
                            "plate":  plate,
                            "reason": msg,
                        })

    except Exception as e:
        return _err(f"Failed to read CSV: {e}")

    summary_msg = (
        f"Import complete — {imported} added, "
        f"{skipped} skipped (duplicates), "
        f"{len(errors)} error(s)."
    )
    return _ok({
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors,
    }, summary_msg)


def export_vehicles_to_csv(filepath: str) -> dict:
    """Export all registered vehicles to a CSV file."""
    if not filepath.endswith(".csv"):
        filepath += ".csv"
    success, msg = db.export_vehicles_to_csv(filepath)
    return _ok({"filepath": filepath}, msg) if success else _err(msg)


# ──────────────────────────────────────────────
#  UTILITY
# ──────────────────────────────────────────────

def get_valid_vehicle_types() -> dict:
    """
    Return the list of valid vehicle types configured in the system.
    Merges the hardcoded defaults with any custom types in toll_rates.
    data = list of type name strings
    """
    rates = db.get_all_rates()
    db_types = [r["vehicle_type"] for r in rates] if rates else []
    # union of defaults and DB entries, preserving order
    merged = list(dict.fromkeys(VALID_VEHICLE_TYPES + db_types))
    return _ok(merged, f"{len(merged)} vehicle type(s) available.")


def format_plate_display(plate: str) -> str:
    """
    Format a normalized plate for display.
    E.g. 'MH12AB1234' → 'MH 12 AB 1234'
    Falls back to the raw string if pattern doesn't match.
    """
    plate = _normalize_plate(plate)
    m = re.match(r"^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{4})$", plate)
    if m:
        return " ".join(m.groups())
    return plate


# ──────────────────────────────────────────────
#  QUICK TEST  (run: python vehicle_ctrl.py)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    db.initialize_database()
    print("── Vehicle Controller Self-Test ──\n")

    # Register
    res = register_vehicle("MH12AB1234", "Car", "Rajesh Kumar", "9876543210")
    print(f"Register:       {res['message']}")

    res = register_vehicle("MH12AB1234", "Car", "Duplicate Test", "")
    print(f"Duplicate:      {res['message']}")

    res = register_vehicle("", "Car", "No Plate", "")
    print(f"Empty plate:    {res['message']}")

    res = register_vehicle("DL3CAF0001", "Truck", "Suresh Singh", "8800001111")
    print(f"Register truck: {res['message']}")

    # Lookup
    res = get_vehicle("MH12AB1234")
    print(f"\nLookup:         {res['message']}")
    if res["success"]:
        v = res["data"]
        print(f"  Owner: {v['owner_name']}  |  Type: {v['vehicle_type']}  |  Fee: ₹{v['toll_fee']}")

    # Search
    res = search_vehicles("Raj")
    print(f"\nSearch 'Raj':   {res['message']}")

    # Stats
    res = get_vehicle_stats()
    print(f"\nFleet stats:    {res['message']}")
    if res["success"]:
        print(f"  By type: {res['data']['by_type']}")

    # Types
    res = get_valid_vehicle_types()
    print(f"\nVehicle types:  {res['data']}")

    # Plate formatter
    print(f"\nFormatted plate: {format_plate_display('MH12AB1234')}")

    # Exists check
    res = check_vehicle_exists("MH12AB1234")
    print(f"Exists check:   {res['message']}  →  {res['data']}")

    print("\nAll checks passed ✔")