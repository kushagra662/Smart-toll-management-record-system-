import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib
import os
from datetime import datetime


# ──────────────────────────────────────────────
#  DATABASE SETUP
# ──────────────────────────────────────────────

DB_PATH = "toll_system.db"


def get_connection():
    """Return a SQLite connection with row_factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    """Create all tables and seed default data on first run."""
    conn = get_connection()
    cur = conn.cursor()

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            password TEXT    NOT NULL,
            role     TEXT    DEFAULT 'operator'
        )
    """)

    # Vehicles table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT    UNIQUE NOT NULL,
            vehicle_type TEXT    NOT NULL,
            owner_name   TEXT    NOT NULL,
            owner_phone  TEXT,
            registered_at TEXT   DEFAULT (datetime('now','localtime'))
        )
    """)

    # Toll rates table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS toll_rates (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_type TEXT    UNIQUE NOT NULL,
            fee          REAL    NOT NULL
        )
    """)

    # Toll records table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS toll_records (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id),
            plate_number TEXT    NOT NULL,
            vehicle_type TEXT    NOT NULL,
            fee_paid     REAL    NOT NULL,
            collected_by TEXT,
            collected_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── Seed default admin user ──
    hashed = hashlib.sha256("admin123".encode()).hexdigest()
    cur.execute("""
        INSERT OR IGNORE INTO users (username, password, role)
        VALUES (?, ?, 'admin')
    """, ("admin", hashed))

    # ── Seed default toll rates ──
    default_rates = [
        ("Car",        50.00),
        ("Truck",     120.00),
        ("Bus",       100.00),
        ("Motorcycle", 25.00),
        ("Auto",       30.00),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO toll_rates (vehicle_type, fee)
        VALUES (?, ?)
    """, default_rates)

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def validate_login(username: str, password: str):
    """Return user row if credentials match, else None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, hash_password(password))
    )
    user = cur.fetchone()
    conn.close()
    return user


# ──────────────────────────────────────────────
#  LOGIN WINDOW
# ──────────────────────────────────────────────

class LoginWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Toll System — Login")
        self.geometry("420x480")
        self.resizable(False, False)
        self.configure(bg="#0f1923")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self.center()
        self.grab_set()

    def center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 420) // 2
        y = (self.winfo_screenheight() - 480) // 2
        self.geometry(f"420x480+{x}+{y}")

    def _build_ui(self):
        # Header band
        header = tk.Frame(self, bg="#1a2e42", height=90)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="🛣  TOLL MANAGEMENT",
            font=("Courier", 15, "bold"),
            fg="#f0c040", bg="#1a2e42"
        ).pack(pady=(20, 2))
        tk.Label(
            header, text="Authorized access only",
            font=("Courier", 9), fg="#7a9cbb", bg="#1a2e42"
        ).pack()

        # Form area
        form = tk.Frame(self, bg="#0f1923", padx=40)
        form.pack(fill="both", expand=True, pady=20)

        def field(label, show=None):
            tk.Label(form, text=label, font=("Courier", 10),
                     fg="#7a9cbb", bg="#0f1923", anchor="w").pack(fill="x", pady=(10, 2))
            e = tk.Entry(form, font=("Courier", 12), fg="#e8eaf0",
                         bg="#1c2d3e", insertbackground="#f0c040",
                         relief="flat", bd=6, show=show)
            e.pack(fill="x", ipady=6)
            return e

        self.username_entry = field("USERNAME")
        self.password_entry = field("PASSWORD", show="●")

        # Error label
        self.error_var = tk.StringVar()
        tk.Label(form, textvariable=self.error_var,
                 font=("Courier", 9), fg="#e05555", bg="#0f1923").pack(pady=(8, 0))

        # Login button
        btn = tk.Button(
            form, text="LOGIN  →",
            font=("Courier", 11, "bold"),
            fg="#0f1923", bg="#f0c040",
            activebackground="#d4a800",
            relief="flat", bd=0, cursor="hand2",
            command=self.attempt_login
        )
        btn.pack(fill="x", pady=(18, 0), ipady=10)

        # Hint
        tk.Label(form, text="Default: admin / admin123",
                 font=("Courier", 8), fg="#3a5570", bg="#0f1923").pack(pady=(12, 0))

        # Bind Enter key
        self.bind("<Return>", lambda e: self.attempt_login())

    def attempt_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            self.error_var.set("⚠  Please enter both fields.")
            return

        user = validate_login(username, password)
        if user:
            self.destroy()
            self.parent.on_login_success(dict(user))
        else:
            self.error_var.set("⚠  Invalid username or password.")
            self.password_entry.delete(0, tk.END)

    def on_close(self):
        self.parent.destroy()


# ──────────────────────────────────────────────
#  DASHBOARD WINDOW
# ──────────────────────────────────────────────

class DashboardWindow(tk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent, bg="#0f1923")
        self.parent = parent
        self.user = user
        self.pack(fill="both", expand=True)
        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        # Top navbar
        nav = tk.Frame(self, bg="#1a2e42", height=55)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Label(nav, text="🛣  TOLL MANAGEMENT SYSTEM",
                 font=("Courier", 13, "bold"),
                 fg="#f0c040", bg="#1a2e42").pack(side="left", padx=20, pady=12)

        user_info = f"● {self.user['username'].upper()}  [{self.user['role'].upper()}]"
        tk.Label(nav, text=user_info,
                 font=("Courier", 9), fg="#7a9cbb", bg="#1a2e42").pack(side="right", padx=20)

        # Stats strip
        self.stats_frame = tk.Frame(self, bg="#0f1923")
        self.stats_frame.pack(fill="x", padx=20, pady=(18, 10))

        # Tab bar
        tab_bar = tk.Frame(self, bg="#0f1923")
        tab_bar.pack(fill="x", padx=20, pady=(0, 8))

        self.tab_content = tk.Frame(self, bg="#1c2d3e", relief="flat")
        self.tab_content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        tabs = [
            ("🚗  Vehicle Entry",    self.show_vehicle_entry),
            ("💰  Toll Collection",  self.show_toll_collection),
            ("📋  Records",          self.show_records),
            ("📊  Reports",          self.show_reports),
            ("⚙   Settings",         self.show_settings),
        ]
        self.tab_buttons = []
        for label, cmd in tabs:
            b = tk.Button(
                tab_bar, text=label,
                font=("Courier", 9, "bold"),
                fg="#7a9cbb", bg="#1c2d3e",
                activeforeground="#f0c040",
                activebackground="#253d55",
                relief="flat", bd=0, cursor="hand2",
                padx=14, pady=8,
                command=cmd
            )
            b.pack(side="left", padx=(0, 4))
            self.tab_buttons.append(b)

        # Load default tab
        self.show_vehicle_entry()

    # ── Stats cards ──────────────────────────

    def refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM vehicles")
        total_vehicles = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM toll_records")
        total_records = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(fee_paid),0) FROM toll_records")
        total_revenue = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM toll_records
            WHERE DATE(collected_at) = DATE('now','localtime')
        """)
        today_count = cur.fetchone()[0]

        conn.close()

        cards = [
            ("Total Vehicles",  str(total_vehicles), "#3a9fd8"),
            ("Total Records",   str(total_records),  "#5cb85c"),
            ("Today's Entries", str(today_count),    "#f0c040"),
            ("Revenue (₹)",     f"{total_revenue:,.2f}", "#e05555"),
        ]
        for title, value, color in cards:
            card = tk.Frame(self.stats_frame, bg="#1c2d3e", padx=18, pady=12)
            card.pack(side="left", padx=(0, 12), ipadx=4)
            tk.Label(card, text=value, font=("Courier", 22, "bold"),
                     fg=color, bg="#1c2d3e").pack()
            tk.Label(card, text=title, font=("Courier", 8),
                     fg="#7a9cbb", bg="#1c2d3e").pack()

    # ── Clear tab content ─────────────────────

    def _clear_tab(self):
        for w in self.tab_content.winfo_children():
            w.destroy()
        for b in self.tab_buttons:
            b.config(fg="#7a9cbb", bg="#1c2d3e")

    def _activate_tab(self, index):
        self.tab_buttons[index].config(fg="#0f1923", bg="#f0c040")

    # ── Vehicle Entry Tab ─────────────────────

    def show_vehicle_entry(self):
        self._clear_tab()
        self._activate_tab(0)
        frame = tk.Frame(self.tab_content, bg="#1c2d3e", padx=30, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Register New Vehicle",
                 font=("Courier", 13, "bold"), fg="#f0c040", bg="#1c2d3e").grid(
                 row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        fields = [
            ("Plate Number *", "plate"),
            ("Owner Name *",   "owner"),
            ("Owner Phone",    "phone"),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields, start=1):
            tk.Label(frame, text=label, font=("Courier", 10),
                     fg="#7a9cbb", bg="#1c2d3e").grid(row=i, column=0, sticky="w", pady=4)
            e = tk.Entry(frame, font=("Courier", 11), fg="#e8eaf0",
                         bg="#0f1923", insertbackground="#f0c040",
                         relief="flat", bd=6, width=28)
            e.grid(row=i, column=1, sticky="w", padx=(16, 0), pady=4, ipady=5)
            entries[key] = e

        # Vehicle type dropdown
        tk.Label(frame, text="Vehicle Type *", font=("Courier", 10),
                 fg="#7a9cbb", bg="#1c2d3e").grid(row=len(fields)+1, column=0, sticky="w", pady=4)
        vtype_var = tk.StringVar(value="Car")
        types = ["Car", "Truck", "Bus", "Motorcycle", "Auto"]
        dd = ttk.Combobox(frame, textvariable=vtype_var, values=types,
                          state="readonly", font=("Courier", 11), width=26)
        dd.grid(row=len(fields)+1, column=1, sticky="w", padx=(16, 0), pady=4, ipady=3)

        status_var = tk.StringVar()
        tk.Label(frame, textvariable=status_var, font=("Courier", 9),
                 fg="#5cb85c", bg="#1c2d3e").grid(row=len(fields)+3, column=0,
                 columnspan=2, sticky="w", pady=(6, 0))

        def save_vehicle():
            plate = entries["plate"].get().strip().upper()
            owner = entries["owner"].get().strip()
            phone = entries["phone"].get().strip()
            vtype = vtype_var.get()

            if not plate or not owner:
                status_var.set("⚠  Plate number and owner name are required.")
                return

            try:
                conn = get_connection()
                conn.execute(
                    "INSERT INTO vehicles (plate_number, vehicle_type, owner_name, owner_phone) VALUES (?,?,?,?)",
                    (plate, vtype, owner, phone)
                )
                conn.commit()
                conn.close()
                status_var.set(f"✔  Vehicle {plate} registered successfully.")
                for e in entries.values():
                    e.delete(0, tk.END)
                self.refresh_stats()
            except sqlite3.IntegrityError:
                status_var.set(f"⚠  Plate {plate} already exists.")

        tk.Button(
            frame, text="REGISTER VEHICLE",
            font=("Courier", 10, "bold"),
            fg="#0f1923", bg="#f0c040",
            activebackground="#d4a800",
            relief="flat", bd=0, cursor="hand2",
            command=save_vehicle
        ).grid(row=len(fields)+2, column=0, columnspan=2, sticky="w",
               pady=(14, 0), ipadx=14, ipady=8)

    # ── Toll Collection Tab ───────────────────

    def show_toll_collection(self):
        self._clear_tab()
        self._activate_tab(1)
        frame = tk.Frame(self.tab_content, bg="#1c2d3e", padx=30, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Collect Toll",
                 font=("Courier", 13, "bold"), fg="#f0c040", bg="#1c2d3e").grid(
                 row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        tk.Label(frame, text="Plate Number *", font=("Courier", 10),
                 fg="#7a9cbb", bg="#1c2d3e").grid(row=1, column=0, sticky="w", pady=4)
        plate_entry = tk.Entry(frame, font=("Courier", 11), fg="#e8eaf0",
                               bg="#0f1923", insertbackground="#f0c040",
                               relief="flat", bd=6, width=22)
        plate_entry.grid(row=1, column=1, sticky="w", padx=(16, 0), pady=4, ipady=5)

        info_var  = tk.StringVar()
        fee_var   = tk.StringVar()
        status_var = tk.StringVar()

        tk.Label(frame, textvariable=info_var, font=("Courier", 10),
                 fg="#3a9fd8", bg="#1c2d3e").grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        tk.Label(frame, textvariable=fee_var, font=("Courier", 14, "bold"),
                 fg="#f0c040", bg="#1c2d3e").grid(row=3, column=0, columnspan=2, sticky="w")
        tk.Label(frame, textvariable=status_var, font=("Courier", 9),
                 fg="#5cb85c", bg="#1c2d3e").grid(row=6, column=0, columnspan=2, sticky="w", pady=4)

        current_vehicle = {}

        def lookup():
            plate = plate_entry.get().strip().upper()
            if not plate:
                return
            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM vehicles WHERE plate_number = ?", (plate,)
            ).fetchone()
            conn.close()
            if row:
                rate_conn = get_connection()
                rate = rate_conn.execute(
                    "SELECT fee FROM toll_rates WHERE vehicle_type = ?",
                    (row["vehicle_type"],)
                ).fetchone()
                rate_conn.close()
                fee = rate["fee"] if rate else 0.0
                current_vehicle.update(dict(row))
                current_vehicle["fee"] = fee
                info_var.set(f"Owner: {row['owner_name']}  |  Type: {row['vehicle_type']}")
                fee_var.set(f"Fee: ₹ {fee:.2f}")
                status_var.set("")
            else:
                info_var.set("⚠  Vehicle not found. Please register first.")
                fee_var.set("")
                current_vehicle.clear()

        def collect():
            if not current_vehicle:
                status_var.set("⚠  Lookup a vehicle first.")
                return
            conn = get_connection()
            conn.execute("""
                INSERT INTO toll_records
                    (vehicle_id, plate_number, vehicle_type, fee_paid, collected_by)
                VALUES (?, ?, ?, ?, ?)
            """, (
                current_vehicle["id"],
                current_vehicle["plate_number"],
                current_vehicle["vehicle_type"],
                current_vehicle["fee"],
                self.user["username"]
            ))
            conn.commit()
            conn.close()
            status_var.set(f"✔  ₹{current_vehicle['fee']:.2f} collected from {current_vehicle['plate_number']}")
            info_var.set("")
            fee_var.set("")
            plate_entry.delete(0, tk.END)
            current_vehicle.clear()
            self.refresh_stats()

        btn_row = tk.Frame(frame, bg="#1c2d3e")
        btn_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))

        tk.Button(btn_row, text="LOOKUP",
                  font=("Courier", 10, "bold"), fg="#0f1923", bg="#3a9fd8",
                  activebackground="#2887c0", relief="flat", bd=0, cursor="hand2",
                  command=lookup).pack(side="left", ipadx=14, ipady=8)

        tk.Button(btn_row, text="COLLECT TOLL",
                  font=("Courier", 10, "bold"), fg="#0f1923", bg="#5cb85c",
                  activebackground="#4aa84a", relief="flat", bd=0, cursor="hand2",
                  command=collect).pack(side="left", padx=(12, 0), ipadx=14, ipady=8)

    # ── Records Tab ───────────────────────────

    def show_records(self):
        self._clear_tab()
        self._activate_tab(2)
        frame = tk.Frame(self.tab_content, bg="#1c2d3e", padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Toll Records",
                 font=("Courier", 13, "bold"), fg="#f0c040", bg="#1c2d3e").pack(anchor="w", pady=(0, 10))

        # Treeview
        cols = ("ID", "Plate", "Type", "Fee (₹)", "Collected By", "Date & Time")
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Toll.Treeview",
                        background="#0f1923", foreground="#c8d8e8",
                        fieldbackground="#0f1923", rowheight=26,
                        font=("Courier", 9))
        style.configure("Toll.Treeview.Heading",
                        background="#1a2e42", foreground="#f0c040",
                        font=("Courier", 9, "bold"), relief="flat")
        style.map("Toll.Treeview", background=[("selected", "#253d55")])

        tree = ttk.Treeview(frame, columns=cols, show="headings",
                            style="Toll.Treeview", height=16)
        widths = [50, 110, 100, 80, 110, 160]
        for col, w in zip(cols, widths):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        conn = get_connection()
        rows = conn.execute("""
            SELECT id, plate_number, vehicle_type, fee_paid,
                   collected_by, collected_at
            FROM toll_records ORDER BY id DESC LIMIT 500
        """).fetchall()
        conn.close()

        for r in rows:
            tree.insert("", "end", values=(
                r["id"], r["plate_number"], r["vehicle_type"],
                f"{r['fee_paid']:.2f}", r["collected_by"] or "—",
                r["collected_at"]
            ))

    # ── Reports Tab ───────────────────────────

    def show_reports(self):
        self._clear_tab()
        self._activate_tab(3)
        frame = tk.Frame(self.tab_content, bg="#1c2d3e", padx=30, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Revenue Reports",
                 font=("Courier", 13, "bold"), fg="#f0c040", bg="#1c2d3e").pack(anchor="w")

        result_var = tk.StringVar()
        tk.Label(frame, textvariable=result_var, font=("Courier", 10),
                 fg="#e8eaf0", bg="#1c2d3e", justify="left").pack(anchor="w", pady=(16, 0))

        def run_report(query, label):
            conn = get_connection()
            rows = conn.execute(query).fetchall()
            conn.close()
            lines = [f"── {label} ──"]
            for r in rows:
                lines.append(f"  {r[0]:<14}  Trips: {r[1]:>5}   Revenue: ₹{r[2]:>10.2f}")
            result_var.set("\n".join(lines))

        btn_cfg = dict(font=("Courier", 10, "bold"), fg="#0f1923", bg="#3a9fd8",
                       activebackground="#2887c0", relief="flat", bd=0, cursor="hand2")

        btn_row = tk.Frame(frame, bg="#1c2d3e")
        btn_row.pack(anchor="w", pady=(14, 0))

        tk.Button(btn_row, text="Today", **btn_cfg, command=lambda: run_report("""
            SELECT vehicle_type, COUNT(*) as trips, SUM(fee_paid) as rev
            FROM toll_records WHERE DATE(collected_at) = DATE('now','localtime')
            GROUP BY vehicle_type ORDER BY rev DESC
        """, "Today's Report")).pack(side="left", ipadx=12, ipady=7)

        tk.Button(btn_row, text="This Month", **btn_cfg, command=lambda: run_report("""
            SELECT vehicle_type, COUNT(*) as trips, SUM(fee_paid) as rev
            FROM toll_records
            WHERE strftime('%Y-%m', collected_at) = strftime('%Y-%m','now','localtime')
            GROUP BY vehicle_type ORDER BY rev DESC
        """, "Monthly Report")).pack(side="left", padx=(10, 0), ipadx=12, ipady=7)

        tk.Button(btn_row, text="All Time", **btn_cfg, command=lambda: run_report("""
            SELECT vehicle_type, COUNT(*) as trips, SUM(fee_paid) as rev
            FROM toll_records GROUP BY vehicle_type ORDER BY rev DESC
        """, "All-Time Report")).pack(side="left", padx=(10, 0), ipadx=12, ipady=7)

    # ── Settings Tab ─────────────────────────

    def show_settings(self):
        self._clear_tab()
        self._activate_tab(4)
        frame = tk.Frame(self.tab_content, bg="#1c2d3e", padx=30, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Toll Rate Settings",
                 font=("Courier", 13, "bold"), fg="#f0c040", bg="#1c2d3e").grid(
                 row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        conn = get_connection()
        rates = conn.execute("SELECT vehicle_type, fee FROM toll_rates ORDER BY vehicle_type").fetchall()
        conn.close()

        rate_entries = {}
        for i, r in enumerate(rates, start=1):
            tk.Label(frame, text=r["vehicle_type"], font=("Courier", 10),
                     fg="#7a9cbb", bg="#1c2d3e", width=14, anchor="w").grid(
                     row=i, column=0, sticky="w", pady=4)
            e = tk.Entry(frame, font=("Courier", 11), fg="#e8eaf0",
                         bg="#0f1923", insertbackground="#f0c040",
                         relief="flat", bd=6, width=10)
            e.insert(0, str(r["fee"]))
            e.grid(row=i, column=1, sticky="w", padx=(12, 0), pady=4, ipady=5)
            rate_entries[r["vehicle_type"]] = e
            tk.Label(frame, text="₹", font=("Courier", 10),
                     fg="#7a9cbb", bg="#1c2d3e").grid(row=i, column=2, sticky="w", padx=(4, 0))

        status_var = tk.StringVar()
        tk.Label(frame, textvariable=status_var, font=("Courier", 9),
                 fg="#5cb85c", bg="#1c2d3e").grid(
                 row=len(rates)+2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        def save_rates():
            conn = get_connection()
            try:
                for vtype, entry in rate_entries.items():
                    val = float(entry.get())
                    conn.execute(
                        "UPDATE toll_rates SET fee = ? WHERE vehicle_type = ?",
                        (val, vtype)
                    )
                conn.commit()
                status_var.set("✔  Rates updated successfully.")
            except ValueError:
                status_var.set("⚠  Enter valid numeric values.")
            finally:
                conn.close()

        tk.Button(
            frame, text="SAVE RATES",
            font=("Courier", 10, "bold"),
            fg="#0f1923", bg="#f0c040",
            activebackground="#d4a800",
            relief="flat", bd=0, cursor="hand2",
            command=save_rates
        ).grid(row=len(rates)+1, column=0, columnspan=2, sticky="w",
               pady=(14, 0), ipadx=14, ipady=8)


# ──────────────────────────────────────────────
#  APPLICATION ROOT
# ──────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Toll Record Management System")
        self.geometry("900x640")
        self.minsize(800, 560)
        self.configure(bg="#0f1923")

        self.withdraw()           # Hide root until login succeeds
        initialize_database()
        self._show_login()

    def _show_login(self):
        LoginWindow(self)

    def on_login_success(self, user: dict):
        self.deiconify()
        self.center()
        DashboardWindow(self, user)

    def center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 900) // 2
        y = (self.winfo_screenheight() - 640) // 2
        self.geometry(f"900x640+{x}+{y}")


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()