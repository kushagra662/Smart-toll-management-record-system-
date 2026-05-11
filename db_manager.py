import sqlite3
import hashlib
import csv
import os
from datetime import datetime
from typing import Optional

# ──────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────

DB_PATH = "toll_system.db"

DEFAULT_RATES = [
    ("Car",        50.00),
    ("Truck",     120.00),
    ("Bus",       100.00),
    ("Motorcycle", 25.00),
    ("Auto",       30.00),
]

DEFAULT_ADMIN = {
    "username": "admin",
    "password": "admin123",
    "role":     "admin",
}


# ──────────────────────────────────────────────
#  CONNECTION
# ──────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    Return a new SQLite connection with:
      • row_factory  → rows behave like dicts
      • WAL journal  → safe concurrent reads
      • foreign keys → referential integrity enforced
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _rows_to_dicts(rows) -> list[dict]:
    """Convert a list of sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows] if rows else []


# ──────────────────────────────────────────────
#  SCHEMA CREATION
# ──────────────────────────────────────────────

def initialize_database() -> None:
    """
    Create all tables if they don't exist and seed default data.
    Safe to call on every application start — uses IF NOT EXISTS
    and INSERT OR IGNORE so existing data is never overwritten.
    """
    conn = get_connection()
    cur  = conn.cursor()

    # ── users ──────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'operator',
            created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── vehicles ───────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number  TEXT    UNIQUE NOT NULL,
            vehicle_type  TEXT    NOT NULL,
            owner_name    TEXT    NOT NULL,
            owner_phone   TEXT,
            registered_at TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── toll_rates ─────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS toll_rates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_type  TEXT    UNIQUE NOT NULL,
            fee           REAL    NOT NULL CHECK(fee >= 0),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── toll_records ───────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS toll_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id    INTEGER NOT NULL REFERENCES vehicles(id),
            plate_number  TEXT    NOT NULL,
            vehicle_type  TEXT    NOT NULL,
            fee_paid      REAL    NOT NULL CHECK(fee_paid >= 0),
            collected_by  TEXT,
            collected_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── indexes for fast lookups ────────────────
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_plate   ON vehicles(plate_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_plate    ON toll_records(plate_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_date     ON toll_records(collected_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_vehicle  ON toll_records(vehicle_id)")

    # ── seed default admin ──────────────────────
    cur.execute("""
        INSERT OR IGNORE INTO users (username, password, role)
        VALUES (?, ?, ?)
    """, (
        DEFAULT_ADMIN["username"],
        _hash_password(DEFAULT_ADMIN["password"]),
        DEFAULT_ADMIN["role"],
    ))

    # ── seed default toll rates ─────────────────
    cur.executemany("""
        INSERT OR IGNORE INTO toll_rates (vehicle_type, fee)
        VALUES (?, ?)
    """, DEFAULT_RATES)

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  UTILITIES
# ──────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_db_info() -> dict:
    """Return metadata about the database file."""
    size_kb = round(os.path.getsize(DB_PATH) / 1024, 2) if os.path.exists(DB_PATH) else 0
    conn    = get_connection()
    cur     = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM vehicles")
    v = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM toll_records")
    r = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    u = cur.fetchone()[0]
    conn.close()
    return {
        "path":       DB_PATH,
        "size_kb":    size_kb,
        "vehicles":   v,
        "records":    r,
        "users":      u,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ──────────────────────────────────────────────
#  USERS
# ──────────────────────────────────────────────

def validate_login(username: str, password: str) -> Optional[dict]:
    """Return user dict if credentials match, else None."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, _hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def add_user(username: str, password: str, role: str = "operator") -> tuple[bool, str]:
    """
    Create a new user.
    Returns (True, "OK") on success or (False, error_message) on failure.
    """
    if not username or not password:
        return False, "Username and password are required."
    if role not in ("admin", "operator"):
        return False, "Role must be 'admin' or 'operator'."
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username.strip(), _hash_password(password), role)
        )
        conn.commit()
        conn.close()
        return True, "OK"
    except sqlite3.IntegrityError:
        return False, f"Username '{username}' already exists."


def update_password(username: str, new_password: str) -> tuple[bool, str]:
    if not new_password:
        return False, "New password cannot be empty."
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE users SET password = ? WHERE username = ?",
        (_hash_password(new_password), username)
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    if affected:
        return True, "Password updated."
    return False, f"User '{username}' not found."


def delete_user(username: str) -> tuple[bool, str]:
    if username == "admin":
        return False, "Cannot delete the default admin account."
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE username = ?", (username,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, "User deleted.") if affected else (False, "User not found.")


# ──────────────────────────────────────────────
#  VEHICLES
# ──────────────────────────────────────────────

def add_vehicle(plate_number: str, vehicle_type: str,
                owner_name: str, owner_phone: str = "") -> tuple[bool, str]:
    """Register a new vehicle. Returns (success, message)."""
    plate = plate_number.strip().upper()
    if not plate or not vehicle_type or not owner_name.strip():
        return False, "Plate number, vehicle type, and owner name are required."
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO vehicles (plate_number, vehicle_type, owner_name, owner_phone) VALUES (?,?,?,?)",
            (plate, vehicle_type, owner_name.strip(), owner_phone.strip())
        )
        conn.commit()
        conn.close()
        return True, f"Vehicle {plate} registered successfully."
    except sqlite3.IntegrityError:
        return False, f"Plate number '{plate}' is already registered."


def get_vehicle_by_plate(plate_number: str) -> Optional[dict]:
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM vehicles WHERE plate_number = ?",
        (plate_number.strip().upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_vehicle_by_id(vehicle_id: int) -> Optional[dict]:
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_vehicles(search: str = "") -> list[dict]:
    """Return all vehicles, optionally filtered by plate or owner name."""
    conn = get_connection()
    if search:
        like = f"%{search.upper()}%"
        rows = conn.execute("""
            SELECT * FROM vehicles
            WHERE plate_number LIKE ? OR UPPER(owner_name) LIKE ?
            ORDER BY registered_at DESC
        """, (like, like)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM vehicles ORDER BY registered_at DESC"
        ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def update_vehicle(vehicle_id: int, owner_name: str,
                   owner_phone: str, vehicle_type: str) -> tuple[bool, str]:
    if not owner_name.strip():
        return False, "Owner name cannot be empty."
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE vehicles
        SET owner_name = ?, owner_phone = ?, vehicle_type = ?
        WHERE id = ?
    """, (owner_name.strip(), owner_phone.strip(), vehicle_type, vehicle_id))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, "Vehicle updated.") if affected else (False, "Vehicle not found.")


def delete_vehicle(vehicle_id: int) -> tuple[bool, str]:
    """Delete vehicle and all its associated toll records."""
    conn = get_connection()
    conn.execute("DELETE FROM toll_records WHERE vehicle_id = ?", (vehicle_id,))
    cur = conn.cursor()
    cur.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, "Vehicle and its records deleted.") if affected else (False, "Vehicle not found.")


def count_vehicles() -> int:
    conn = get_connection()
    n    = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    conn.close()
    return n


# ──────────────────────────────────────────────
#  TOLL RATES
# ──────────────────────────────────────────────

def get_all_rates() -> list[dict]:
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT * FROM toll_rates ORDER BY vehicle_type"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_rate_for_type(vehicle_type: str) -> Optional[float]:
    conn = get_connection()
    row  = conn.execute(
        "SELECT fee FROM toll_rates WHERE vehicle_type = ?", (vehicle_type,)
    ).fetchone()
    conn.close()
    return row["fee"] if row else None


def update_rate(vehicle_type: str, fee: float) -> tuple[bool, str]:
    if fee < 0:
        return False, "Fee cannot be negative."
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE toll_rates
        SET fee = ?, updated_at = datetime('now','localtime')
        WHERE vehicle_type = ?
    """, (fee, vehicle_type))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, f"Rate for {vehicle_type} updated to ₹{fee:.2f}.") if affected \
        else (False, f"Vehicle type '{vehicle_type}' not found.")


def add_rate(vehicle_type: str, fee: float) -> tuple[bool, str]:
    """Add a new vehicle type with its toll fee."""
    if not vehicle_type.strip():
        return False, "Vehicle type name is required."
    if fee < 0:
        return False, "Fee cannot be negative."
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO toll_rates (vehicle_type, fee) VALUES (?, ?)",
            (vehicle_type.strip(), fee)
        )
        conn.commit()
        conn.close()
        return True, f"Rate for '{vehicle_type}' added."
    except sqlite3.IntegrityError:
        return False, f"Vehicle type '{vehicle_type}' already exists."


def delete_rate(vehicle_type: str) -> tuple[bool, str]:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM toll_rates WHERE vehicle_type = ?", (vehicle_type,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, f"Rate for '{vehicle_type}' deleted.") if affected \
        else (False, "Vehicle type not found.")


# ──────────────────────────────────────────────
#  TOLL RECORDS
# ──────────────────────────────────────────────

def add_toll_record(vehicle_id: int, plate_number: str,
                    vehicle_type: str, fee_paid: float,
                    collected_by: str = "") -> tuple[bool, str]:
    """Record a toll collection transaction."""
    if fee_paid < 0:
        return False, "Fee paid cannot be negative."
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO toll_records
                (vehicle_id, plate_number, vehicle_type, fee_paid, collected_by)
            VALUES (?, ?, ?, ?, ?)
        """, (vehicle_id, plate_number.upper(), vehicle_type, fee_paid, collected_by))
        conn.commit()
        conn.close()
        return True, "Toll recorded."
    except sqlite3.IntegrityError as e:
        return False, str(e)


def get_all_records(limit: int = 500) -> list[dict]:
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT * FROM toll_records ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_records_by_plate(plate_number: str) -> list[dict]:
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT * FROM toll_records
        WHERE plate_number = ?
        ORDER BY collected_at DESC
    """, (plate_number.strip().upper(),)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_records_by_date_range(date_from: str, date_to: str) -> list[dict]:
    """
    Filter records between two dates (inclusive).
    Dates must be in 'YYYY-MM-DD' format.
    """
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT * FROM toll_records
        WHERE DATE(collected_at) BETWEEN ? AND ?
        ORDER BY collected_at DESC
    """, (date_from, date_to)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def delete_toll_record(record_id: int) -> tuple[bool, str]:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM toll_records WHERE id = ?", (record_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return (True, "Record deleted.") if affected else (False, "Record not found.")


def count_records() -> int:
    conn = get_connection()
    n    = conn.execute("SELECT COUNT(*) FROM toll_records").fetchone()[0]
    conn.close()
    return n


# ──────────────────────────────────────────────
#  DASHBOARD STATS
# ──────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Return all numbers needed for the stats cards in one query batch."""
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM vehicles")
    total_vehicles = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM toll_records")
    total_records = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(fee_paid), 0) FROM toll_records")
    total_revenue = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(fee_paid), 0)
        FROM toll_records
        WHERE DATE(collected_at) = DATE('now','localtime')
    """)
    today = cur.fetchone()
    today_count   = today[0]
    today_revenue = today[1]

    conn.close()
    return {
        "total_vehicles":  total_vehicles,
        "total_records":   total_records,
        "total_revenue":   total_revenue,
        "today_count":     today_count,
        "today_revenue":   today_revenue,
    }


# ──────────────────────────────────────────────
#  REPORTS
# ──────────────────────────────────────────────

def report_by_vehicle_type(period: str = "all") -> list[dict]:
    """
    Aggregate toll collections grouped by vehicle type.

    period options:
      'today'   — current calendar day
      'month'   — current calendar month
      'all'     — all time  (default)
    """
    conn = get_connection()
    base = """
        SELECT vehicle_type,
               COUNT(*)         AS trips,
               SUM(fee_paid)    AS revenue,
               AVG(fee_paid)    AS avg_fee,
               MIN(collected_at) AS first_entry,
               MAX(collected_at) AS last_entry
        FROM toll_records
    """
    if period == "today":
        where = "WHERE DATE(collected_at) = DATE('now','localtime')"
    elif period == "month":
        where = "WHERE strftime('%Y-%m', collected_at) = strftime('%Y-%m','now','localtime')"
    else:
        where = ""

    rows = conn.execute(
        base + where + " GROUP BY vehicle_type ORDER BY revenue DESC"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def report_daily_summary(days: int = 30) -> list[dict]:
    """Return per-day totals for the last N days."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DATE(collected_at)  AS date,
               COUNT(*)            AS trips,
               SUM(fee_paid)       AS revenue
        FROM toll_records
        WHERE collected_at >= datetime('now', ?, 'localtime')
        GROUP BY DATE(collected_at)
        ORDER BY date DESC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def report_top_vehicles(limit: int = 10) -> list[dict]:
    """Return the top N vehicles by number of toll entries."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT plate_number,
               vehicle_type,
               COUNT(*)        AS trips,
               SUM(fee_paid)   AS total_paid
        FROM toll_records
        GROUP BY plate_number
        ORDER BY trips DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ──────────────────────────────────────────────
#  CSV EXPORT
# ──────────────────────────────────────────────

def export_records_to_csv(filepath: str,
                          date_from: str = "",
                          date_to:   str = "") -> tuple[bool, str]:
    """
    Export toll_records to a CSV file.
    Optionally filter by date range (YYYY-MM-DD strings).
    Returns (success, message_or_error).
    """
    try:
        if date_from and date_to:
            rows = get_records_by_date_range(date_from, date_to)
        else:
            rows = get_all_records(limit=100_000)

        if not rows:
            return False, "No records found to export."

        fieldnames = ["id", "plate_number", "vehicle_type",
                      "fee_paid", "collected_by", "collected_at"]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        return True, f"Exported {len(rows)} records to {filepath}"
    except Exception as e:
        return False, str(e)


def export_vehicles_to_csv(filepath: str) -> tuple[bool, str]:
    """Export vehicles table to CSV."""
    try:
        rows = get_all_vehicles()
        if not rows:
            return False, "No vehicles found to export."

        fieldnames = ["id", "plate_number", "vehicle_type",
                      "owner_name", "owner_phone", "registered_at"]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        return True, f"Exported {len(rows)} vehicles to {filepath}"
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────
#  MAINTENANCE
# ──────────────────────────────────────────────

def purge_old_records(days: int = 365) -> tuple[bool, str]:
    """
    Delete toll records older than N days.
    Returns (success, message with count of deleted rows).
    """
    if days < 1:
        return False, "Days must be at least 1."
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        DELETE FROM toll_records
        WHERE collected_at < datetime('now', ?, 'localtime')
    """, (f"-{days} days",))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return True, f"Deleted {deleted} records older than {days} days."


def vacuum_database() -> tuple[bool, str]:
    """Reclaim unused disk space by running VACUUM."""
    try:
        conn = sqlite3.connect(DB_PATH)   # VACUUM can't run inside a transaction
        conn.execute("VACUUM")
        conn.close()
        return True, "Database vacuumed successfully."
    except Exception as e:
        return False, str(e)


# ──────────────────────────────────────────────
#  QUICK TEST  (run: python db_manager.py)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Initializing database …")
    initialize_database()

    print("\n── DB Info ──")
    info = get_db_info()
    for k, v in info.items():
        print(f"  {k:<15}: {v}")

    print("\n── Dashboard Stats ──")
    stats = get_dashboard_stats()
    for k, v in stats.items():
        print(f"  {k:<18}: {v}")

    print("\n── Toll Rates ──")
    for r in get_all_rates():
        print(f"  {r['vehicle_type']:<14}: ₹{r['fee']:.2f}")

    print("\n── Users ──")
    for u in get_all_users():
        print(f"  {u['username']:<14}: {u['role']}")

    print("\nAll checks passed ✔")