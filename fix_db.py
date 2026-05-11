"""
fix_db.py
─────────────────────────────────────────────────────────────
One-time migration script.
Adds the missing `created_at` column to the `users` table
if it doesn't already exist, then re-runs initialize_database()
to apply any other schema updates safely.

Run once:
    python fix_db.py
─────────────────────────────────────────────────────────────
"""

import sqlite3
import os

DB_PATH = "toll_system.db"


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"⚠  Database '{DB_PATH}' not found.")
        print("   Run main.py first to create it, then re-run this script.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # ── Check existing columns in users table ──
    cur.execute("PRAGMA table_info(users)")
    existing_cols = [row[1] for row in cur.fetchall()]
    print(f"Current columns in 'users': {existing_cols}")

    # ── Add created_at if missing ──
    if "created_at" not in existing_cols:
        print("Adding missing column: created_at ...")
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN created_at TEXT NOT NULL
            DEFAULT (datetime('now','localtime'))
        """)
        conn.commit()
        print("✔  created_at column added.")
    else:
        print("✔  created_at column already exists — no changes needed.")

    # ── Check toll_rates for updated_at ──
    cur.execute("PRAGMA table_info(toll_rates)")
    rate_cols = [row[1] for row in cur.fetchall()]
    print(f"\nCurrent columns in 'toll_rates': {rate_cols}")

    if "updated_at" not in rate_cols:
        print("Adding missing column: toll_rates.updated_at ...")
        cur.execute("""
            ALTER TABLE toll_rates
            ADD COLUMN updated_at TEXT NOT NULL
            DEFAULT (datetime('now','localtime'))
        """)
        conn.commit()
        print("✔  updated_at column added to toll_rates.")
    else:
        print("✔  toll_rates.updated_at already exists — no changes needed.")

    conn.close()

    # ── Re-run initialize_database to apply indexes & seed data ──
    print("\nRe-running initialize_database() ...")
    import db_manager as db
    db.initialize_database()
    print("✔  Database is fully up to date.\n")

    # ── Quick verification ──
    print("── Verification ──")
    info = db.get_db_info()
    for k, v in info.items():
        print(f"  {k:<15}: {v}")

    print("\n── Users ──")
    for u in db.get_all_users():
        print(f"  {u['username']:<14}: {u['role']}")

    print("\n✔  All checks passed. You can now run main.py normally.")


if __name__ == "__main__":
    migrate()