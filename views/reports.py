"""
reports.py
─────────────────────────────────────────────────────────────
Dedicated Reports Window for the Toll Record Management System.

Provides a full-screen reporting interface with:
  • Tab 1 — Revenue Summary   (by vehicle type, period filter)
  • Tab 2 — Daily Trend       (day-by-day table + ASCII bar chart)
  • Tab 3 — Vehicle History   (per-plate full toll history)
  • Tab 4 — Top Vehicles      (most frequent / highest paying)
  • Tab 5 — Hourly Analysis   (peak hour distribution)
  • Tab 6 — Export Centre     (CSV export with date filters)

Can be opened as a standalone Toplevel from the dashboard or
run directly for testing.

Usage:
    from reports import ReportsWindow
    ReportsWindow(parent)
─────────────────────────────────────────────────────────────
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, date, timedelta

import toll_ctrl    as tc
import vehicle_ctrl as vc


# ──────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────

BG      = "#0d1b2a"
BG2     = "#122236"
BG3     = "#1a3148"
BG4     = "#1e3a55"
ACCENT  = "#e8a020"
ACCENT2 = "#2d9cdb"
SUCCESS = "#27ae60"
DANGER  = "#e05252"
WARN    = "#f0c040"
TEXT    = "#d4e1f0"
TEXT2   = "#7a99bb"
BORDER  = "#243550"

MONO      = ("Courier", 10)
MONO_SM   = ("Courier", 9)
MONO_LG   = ("Courier", 12, "bold")
MONO_HDR  = ("Courier", 13, "bold")
MONO_XL   = ("Courier", 18, "bold")


# ──────────────────────────────────────────────
#  WIDGET HELPERS
# ──────────────────────────────────────────────

def _lbl(parent, text, font=MONO, fg=TEXT, bg=BG2, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def _entry(parent, width=14, textvariable=None):
    kw = dict(font=MONO, fg=TEXT, bg=BG3, insertbackground=ACCENT,
              relief="flat", bd=5, width=width)
    if textvariable:
        kw["textvariable"] = textvariable
    return tk.Entry(parent, **kw)


def _btn(parent, text, command, color=ACCENT, fg=BG, **kw):
    return tk.Button(
        parent, text=text, command=command,
        font=("Courier", 9, "bold"),
        fg=fg, bg=color,
        activeforeground=fg, activebackground=color,
        relief="flat", bd=0, cursor="hand2", **kw,
    )


def _sep(parent):
    return tk.Frame(parent, bg=BORDER, height=1)


def _tree_style():
    s = ttk.Style()
    s.theme_use("default")
    s.configure("R.Treeview",
                background=BG, foreground=TEXT,
                fieldbackground=BG, rowheight=25,
                font=("Courier", 9), borderwidth=0)
    s.configure("R.Treeview.Heading",
                background=BG3, foreground=ACCENT,
                font=("Courier", 9, "bold"), relief="flat")
    s.map("R.Treeview",
          background=[("selected", "#1f3a5a")],
          foreground=[("selected", TEXT)])


def _scrolled_tree(parent, cols, widths, height=12):
    _tree_style()
    frame = tk.Frame(parent, bg=BG)
    tree  = ttk.Treeview(frame, columns=cols, show="headings",
                          style="R.Treeview", height=height)
    sb    = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    for col, w in zip(cols, widths):
        tree.heading(col, text=col,
                     command=lambda c=col, t=tree: _sort_tree(t, c, False))
        tree.column(col, width=w, anchor="center", minwidth=30)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")
    return frame, tree


def _sort_tree(tree, col, reverse):
    """Click-to-sort for any Treeview column."""
    data = [(tree.set(k, col), k) for k in tree.get_children("")]
    try:
        data.sort(key=lambda t: float(t[0].replace(",", "").replace("₹", "")),
                  reverse=reverse)
    except ValueError:
        data.sort(reverse=reverse)
    for i, (_, k) in enumerate(data):
        tree.move(k, "", i)
    tree.heading(col, command=lambda: _sort_tree(tree, col, not reverse))


def _today_str():
    return date.today().strftime("%Y-%m-%d")


def _n_days_ago(n):
    return (date.today() - timedelta(days=n)).strftime("%Y-%m-%d")


# ──────────────────────────────────────────────
#  REPORTS WINDOW
# ──────────────────────────────────────────────

class ReportsWindow(tk.Toplevel):
    """
    Full-screen reports window. Opens as a Toplevel over the dashboard.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Toll Management System — Reports")
        self.geometry("1020x680")
        self.minsize(860, 560)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build_navbar()
        self._build_tab_bar()
        self._build_tabs()
        self._show_tab(0)

        self._center()
        self.focus_force()

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - 1020) // 2
        y  = (sh - 680)  // 2
        self.geometry(f"1020x680+{x}+{y}")

    # ── Navbar ────────────────────────────────

    def _build_navbar(self):
        nav = tk.Frame(self, bg=BG3, height=50)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Frame(nav, bg=ACCENT, width=4).pack(side="left", fill="y")

        _lbl(nav, "  📊  REPORTS & ANALYTICS",
             font=("Courier", 12, "bold"), fg=TEXT, bg=BG3).pack(
             side="left", padx=(10, 0), pady=12)

        _lbl(nav, datetime.now().strftime("Generated: %d %b %Y  %H:%M"),
             font=MONO_SM, fg=TEXT2, bg=BG3).pack(side="right", padx=18)

        _btn(nav, "✕  Close", self.destroy,
             color=BG3, fg=TEXT2).pack(side="right", ipadx=10, ipady=8)

    # ── Tab bar ───────────────────────────────

    def _build_tab_bar(self):
        bar = tk.Frame(self, bg=BG2, pady=0)
        bar.pack(fill="x")

        self._tab_btns = []
        labels = [
            "💰  Revenue Summary",
            "📅  Daily Trend",
            "🚗  Vehicle History",
            "🏆  Top Vehicles",
            "🕐  Hourly Analysis",
            "📤  Export Centre",
        ]
        for i, label in enumerate(labels):
            b = tk.Button(
                bar, text=label,
                font=("Courier", 9, "bold"),
                fg=TEXT2, bg=BG2,
                activeforeground=BG, activebackground=ACCENT,
                relief="flat", bd=0, cursor="hand2",
                padx=14, pady=10,
                command=lambda idx=i: self._show_tab(idx),
            )
            b.pack(side="left", padx=(0, 2))
            self._tab_btns.append(b)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _show_tab(self, index: int):
        for i, b in enumerate(self._tab_btns):
            b.config(fg=BG if i == index else TEXT2,
                     bg=ACCENT if i == index else BG2)
        for f in self._tab_frames:
            f.pack_forget()
        self._tab_frames[index].pack(fill="both", expand=True,
                                      padx=16, pady=12)

    def _build_tabs(self):
        self._tab_frames = [
            self._build_revenue(),
            self._build_daily(),
            self._build_vehicle_history(),
            self._build_top_vehicles(),
            self._build_hourly(),
            self._build_export(),
        ]

    # ══════════════════════════════════════════
    #  TAB 1 — REVENUE SUMMARY
    # ══════════════════════════════════════════

    def _build_revenue(self):
        outer = tk.Frame(self, bg=BG)

        # Period selector
        top = tk.Frame(outer, bg=BG2, padx=16, pady=12)
        top.pack(fill="x")

        _lbl(top, "Period:", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._rev_period = tk.StringVar(value="all")

        for label, val in [("Today", "today"), ("This Month", "month"), ("All Time", "all")]:
            rb = tk.Radiobutton(
                top, text=label, variable=self._rev_period, value=val,
                font=MONO_SM, fg=TEXT, bg=BG2,
                selectcolor=BG3, activebackground=BG2, cursor="hand2",
                command=self._rev_load,
            )
            rb.pack(side="left", padx=(12, 0))

        _btn(top, "↻ Refresh", self._rev_load,
             color=ACCENT2).pack(side="right", ipadx=12, ipady=5)

        # Summary cards
        self._rev_cards_frame = tk.Frame(outer, bg=BG)
        self._rev_cards_frame.pack(fill="x", pady=(10, 0))

        # Main table
        cols   = ("Vehicle Type", "Trips", "Revenue (₹)", "Avg Fee (₹)",
                  "% of Total", "First Entry", "Last Entry")
        widths = (120, 70, 110, 100, 90, 148, 148)
        tf, self._rev_tree = _scrolled_tree(outer, cols, widths, height=10)
        tf.pack(fill="both", expand=True, pady=(10, 0))

        # Totals footer
        foot = tk.Frame(outer, bg=BG3, padx=16, pady=10)
        foot.pack(fill="x", pady=(4, 0))
        self._rev_total_var = tk.StringVar()
        tk.Label(foot, textvariable=self._rev_total_var,
                 font=("Courier", 11, "bold"), fg=ACCENT, bg=BG3).pack(side="right")

        # ASCII bar chart area
        _sep(outer).pack(fill="x", pady=(12, 6))
        _lbl(outer, "Revenue Distribution (ASCII Chart)",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w")

        self._rev_chart = tk.Text(
            outer, font=("Courier", 9), fg=ACCENT2, bg=BG3,
            relief="flat", bd=6, height=8,
            state="disabled", wrap="none",
        )
        self._rev_chart.pack(fill="x", pady=(6, 0))

        self._rev_load()
        return outer

    def _rev_load(self):
        period = self._rev_period.get()
        res    = tc.get_revenue_report(period)

        # Clear cards
        for w in self._rev_cards_frame.winfo_children():
            w.destroy()

        self._rev_tree.delete(*self._rev_tree.get_children())

        if not res["success"] or not res["data"]["rows"]:
            self._rev_total_var.set("No data for selected period.")
            self._rev_chart_update([])
            return

        d           = res["data"]
        rows        = d["rows"]
        total_rev   = d["total_rev"]
        total_trips = d["total_trips"]

        # Summary cards
        cards = [
            ("Total Revenue",  f"₹{total_rev:,.0f}",  ACCENT),
            ("Total Trips",    str(total_trips),        ACCENT2),
            ("Vehicle Types",  str(len(rows)),          SUCCESS),
            ("Avg per Trip",   f"₹{total_rev/total_trips:.2f}" if total_trips else "—", WARN),
        ]
        for title, val, color in cards:
            card = tk.Frame(self._rev_cards_frame, bg=BG3, padx=16, pady=10)
            card.pack(side="left", padx=(0, 10), ipadx=4)
            tk.Label(card, text=val, font=MONO_XL, fg=color, bg=BG3).pack()
            tk.Label(card, text=title, font=MONO_SM, fg=TEXT2, bg=BG3).pack()

        # Table rows
        for r in rows:
            pct = f"{r['revenue']/total_rev*100:.1f}%" if total_rev else "—"
            self._rev_tree.insert("", "end", values=(
                r["vehicle_type"],
                r["trips"],
                f"{r['revenue']:,.2f}",
                f"{r['avg_fee']:.2f}",
                pct,
                (r["first_entry"] or "")[:16],
                (r["last_entry"]  or "")[:16],
            ))

        self._rev_total_var.set(
            f"TOTAL   {total_trips} trips     ₹{total_rev:,.2f}"
        )
        self._rev_chart_update(rows)

    def _rev_chart_update(self, rows):
        self._rev_chart.config(state="normal")
        self._rev_chart.delete("1.0", tk.END)

        if not rows:
            self._rev_chart.insert(tk.END, "  No data to display.")
            self._rev_chart.config(state="disabled")
            return

        max_rev  = max(r["revenue"] for r in rows) or 1
        bar_max  = 48

        lines = []
        for r in rows:
            bar_len = int(r["revenue"] / max_rev * bar_max)
            bar     = "█" * bar_len + "░" * (bar_max - bar_len)
            lines.append(
                f"  {r['vehicle_type']:<14}  {bar}  ₹{r['revenue']:>10,.2f}"
            )

        self._rev_chart.insert(tk.END, "\n".join(lines))
        self._rev_chart.config(state="disabled")

    # ══════════════════════════════════════════
    #  TAB 2 — DAILY TREND
    # ══════════════════════════════════════════

    def _build_daily(self):
        outer = tk.Frame(self, bg=BG)

        # Controls
        ctrl = tk.Frame(outer, bg=BG2, padx=16, pady=10)
        ctrl.pack(fill="x")

        _lbl(ctrl, "Show last", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._daily_days = tk.StringVar(value="30")
        dd = ttk.Combobox(ctrl, textvariable=self._daily_days,
                           values=["7", "14", "30", "60", "90", "180", "365"],
                           state="readonly", font=MONO, width=6)
        dd.pack(side="left", padx=(8, 6), ipady=3)
        _lbl(ctrl, "days", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        _btn(ctrl, "↻ Load", self._daily_load,
             color=ACCENT).pack(side="left", padx=(14, 0), ipadx=12, ipady=5)

        self._daily_total_var = tk.StringVar()
        tk.Label(ctrl, textvariable=self._daily_total_var,
                 font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="right", padx=(0, 10))

        # Table
        cols   = ("Date", "Day", "Trips", "Revenue (₹)", "Avg Fee (₹)")
        widths = (110, 90, 70, 120, 100)
        tf, self._daily_tree = _scrolled_tree(outer, cols, widths, height=11)
        tf.pack(fill="x", pady=(10, 0))

        # ASCII trend chart
        _sep(outer).pack(fill="x", pady=(12, 6))
        _lbl(outer, "Daily Revenue Trend (ASCII Sparkline)",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w")

        self._daily_chart = tk.Text(
            outer, font=("Courier", 9), fg=SUCCESS, bg=BG3,
            relief="flat", bd=6, height=9,
            state="disabled", wrap="none",
        )
        self._daily_chart.pack(fill="both", expand=True, pady=(6, 0))

        self._daily_load()
        return outer

    def _daily_load(self):
        try:
            days = int(self._daily_days.get())
        except ValueError:
            days = 30

        res = tc.get_daily_trend(days)
        self._daily_tree.delete(*self._daily_tree.get_children())

        if not res["success"] or not res["data"]:
            self._daily_total_var.set("No data found.")
            self._daily_chart_update([])
            return

        rows        = res["data"]
        total_rev   = sum(r["revenue"] for r in rows)
        total_trips = sum(r["trips"]   for r in rows)

        DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        for r in rows:
            try:
                d       = datetime.strptime(r["date"], "%Y-%m-%d")
                day_str = DAY_NAMES[d.weekday()]
            except Exception:
                day_str = "—"

            avg = r["revenue"] / r["trips"] if r["trips"] else 0
            self._daily_tree.insert("", "end", values=(
                r["date"], day_str,
                r["trips"],
                f"{r['revenue']:,.2f}",
                f"{avg:.2f}",
            ))

        self._daily_total_var.set(
            f"{len(rows)} days  |  {total_trips} trips  |  ₹{total_rev:,.2f} total"
        )
        self._daily_chart_update(rows)

    def _daily_chart_update(self, rows):
        self._daily_chart.config(state="normal")
        self._daily_chart.delete("1.0", tk.END)

        if not rows:
            self._daily_chart.insert(tk.END, "  No data to display.")
            self._daily_chart.config(state="disabled")
            return

        # Sparkline: show last 30 days max
        display   = list(reversed(rows[:30]))
        max_rev   = max(r["revenue"] for r in display) or 1
        bar_h     = 7    # rows in chart
        bar_w     = 3    # chars per day

        # Build grid top-down
        grid = []
        for row_i in range(bar_h, 0, -1):
            line = ""
            for r in display:
                threshold = (row_i / bar_h) * max_rev
                line += ("███" if r["revenue"] >= threshold else "   ")
            grid.append(line)

        # X-axis labels (date)
        x_labels = ""
        for r in display:
            x_labels += r["date"][5:][:3] + " "   # MM-D

        lines = [
            f"  ₹{max_rev:>8,.0f} ┤",
            *[f"  {'':>9} │{g}" for g in grid],
            f"  {'0':>9} └{'─' * (len(display) * bar_w)}",
            f"  {'':>11}{x_labels}",
        ]
        self._daily_chart.insert(tk.END, "\n".join(lines))
        self._daily_chart.config(state="disabled")

    # ══════════════════════════════════════════
    #  TAB 3 — VEHICLE HISTORY
    # ══════════════════════════════════════════

    def _build_vehicle_history(self):
        outer = tk.Frame(self, bg=BG)

        # Search bar
        sbar = tk.Frame(outer, bg=BG2, padx=16, pady=12)
        sbar.pack(fill="x")

        _lbl(sbar, "Plate Number:", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._vh_plate = _entry(sbar, width=16)
        self._vh_plate.pack(side="left", padx=(10, 0), ipady=5)
        _btn(sbar, "LOOKUP HISTORY", self._vh_load,
             color=ACCENT).pack(side="left", padx=(12, 0), ipadx=14, ipady=6)
        self._vh_plate.bind("<Return>", lambda e: self._vh_load())

        self._vh_status = tk.StringVar()
        tk.Label(sbar, textvariable=self._vh_status,
                 font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="right", padx=(0, 10))

        # Vehicle info card
        self._vh_info_frame = tk.Frame(outer, bg=BG3, padx=16, pady=12)
        self._vh_info_frame.pack(fill="x", pady=(10, 0))

        self._vh_info_vars = {}
        row_data = [
            ("owner",  "Owner"),
            ("type",   "Type"),
            ("phone",  "Phone"),
            ("reg",    "Registered"),
            ("trips",  "Total Trips"),
            ("paid",   "Total Paid"),
            ("avg",    "Avg Fee"),
            ("first",  "First Visit"),
            ("last",   "Last Visit"),
        ]
        cols_per_row = 3
        for idx, (key, label) in enumerate(row_data):
            r = (idx // cols_per_row) * 2
            c = (idx  % cols_per_row) * 2
            _lbl(self._vh_info_frame, label + ":",
                 font=MONO_SM, fg=TEXT2, bg=BG3,
                 anchor="w").grid(row=r, column=c, sticky="w",
                                   padx=(0 if c == 0 else 24, 4), pady=2)
            v = tk.StringVar(value="—")
            self._vh_info_vars[key] = v
            color = ACCENT if key in ("paid", "trips") else TEXT
            tk.Label(self._vh_info_frame, textvariable=v,
                     font=MONO if key not in ("paid","trips") else MONO_LG,
                     fg=color, bg=BG3, anchor="w").grid(
                     row=r, column=c + 1, sticky="w",
                     padx=(0, 8), pady=2)

        # History table
        _sep(outer).pack(fill="x", pady=(10, 6))
        _lbl(outer, "Toll Transaction History",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w", pady=(0, 6))

        cols   = ("ID", "Fee Paid (₹)", "Multiplier", "Collected By", "Date & Time")
        widths = (60, 110, 90, 130, 180)
        tf, self._vh_tree = _scrolled_tree(outer, cols, widths, height=10)
        tf.pack(fill="both", expand=True)

        return outer

    def _vh_load(self):
        plate = self._vh_plate.get().strip()
        res   = vc.get_vehicle_with_history(plate)

        if not res["success"]:
            self._vh_status.set("⚠  " + res["message"])
            for v in self._vh_info_vars.values():
                v.set("—")
            self._vh_tree.delete(*self._vh_tree.get_children())
            return

        d       = res["data"]
        vehicle = d["vehicle"]
        summary = d["summary"]
        records = d["records"]

        self._vh_status.set(res["message"])
        self._vh_info_vars["owner"].set(vehicle["owner_name"])
        self._vh_info_vars["type"].set(vehicle["vehicle_type"])
        self._vh_info_vars["phone"].set(vehicle["owner_phone"] or "—")
        self._vh_info_vars["reg"].set(vehicle["registered_at"][:16])
        self._vh_info_vars["trips"].set(str(summary["total_trips"]))
        self._vh_info_vars["paid"].set(f"₹{summary['total_paid']:,.2f}")
        self._vh_info_vars["avg"].set(f"₹{summary['avg_fee']:.2f}")
        self._vh_info_vars["first"].set((summary["first_seen"] or "—")[:16])
        self._vh_info_vars["last"].set((summary["last_seen"]  or "—")[:16])

        self._vh_tree.delete(*self._vh_tree.get_children())
        for r in records:
            self._vh_tree.insert("", "end", values=(
                r["id"],
                f"{r['fee_paid']:.2f}",
                "—",
                r["collected_by"] or "—",
                r["collected_at"],
            ))

    # ══════════════════════════════════════════
    #  TAB 4 — TOP VEHICLES
    # ══════════════════════════════════════════

    def _build_top_vehicles(self):
        outer = tk.Frame(self, bg=BG)

        ctrl = tk.Frame(outer, bg=BG2, padx=16, pady=10)
        ctrl.pack(fill="x")

        _lbl(ctrl, "Show top", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._top_limit = tk.StringVar(value="20")
        ttk.Combobox(ctrl, textvariable=self._top_limit,
                     values=["10", "20", "50", "100"],
                     state="readonly", font=MONO, width=6).pack(
                     side="left", padx=(8, 6), ipady=3)
        _lbl(ctrl, "vehicles", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")

        self._top_sort = tk.StringVar(value="trips")
        for label, val in [("by Trips", "trips"), ("by Revenue", "revenue")]:
            tk.Radiobutton(
                ctrl, text=label, variable=self._top_sort, value=val,
                font=MONO_SM, fg=TEXT, bg=BG2,
                selectcolor=BG3, activebackground=BG2, cursor="hand2",
            ).pack(side="left", padx=(14, 0))

        _btn(ctrl, "↻ Load", self._top_load,
             color=ACCENT).pack(side="left", padx=(14, 0), ipadx=12, ipady=5)

        # Two tables side by side
        tables = tk.Frame(outer, bg=BG)
        tables.pack(fill="both", expand=True, pady=(10, 0))

        left  = tk.Frame(tables, bg=BG)
        right = tk.Frame(tables, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        _lbl(left, "Most Frequent (by Trips)",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w", pady=(0, 6))
        cols1   = ("Rank", "Plate", "Type", "Trips", "Total Paid (₹)")
        widths1 = (50, 110, 90, 70, 120)
        tf1, self._top_trip_tree = _scrolled_tree(left, cols1, widths1, height=14)
        tf1.pack(fill="both", expand=True)

        _lbl(right, "Highest Revenue (by ₹)",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w", pady=(0, 6))
        cols2   = ("Rank", "Plate", "Type", "Total Paid (₹)", "Trips")
        widths2 = (50, 110, 90, 120, 70)
        tf2, self._top_rev_tree = _scrolled_tree(right, cols2, widths2, height=14)
        tf2.pack(fill="both", expand=True)

        self._top_load()
        return outer

    def _top_load(self):
        try:
            limit = int(self._top_limit.get())
        except ValueError:
            limit = 20

        res = tc.get_top_vehicles(limit)
        self._top_trip_tree.delete(*self._top_trip_tree.get_children())
        self._top_rev_tree.delete(*self._top_rev_tree.get_children())

        if not res["success"] or not res["data"]:
            return

        rows = res["data"]

        # By trips
        for i, r in enumerate(sorted(rows, key=lambda x: x["trips"], reverse=True), 1):
            self._top_trip_tree.insert("", "end", values=(
                f"#{i}", r["plate_number"], r["vehicle_type"],
                r["trips"], f"{r['total_paid']:,.2f}",
            ))

        # By revenue
        for i, r in enumerate(sorted(rows, key=lambda x: x["total_paid"], reverse=True), 1):
            self._top_rev_tree.insert("", "end", values=(
                f"#{i}", r["plate_number"], r["vehicle_type"],
                f"{r['total_paid']:,.2f}", r["trips"],
            ))

    # ══════════════════════════════════════════
    #  TAB 5 — HOURLY ANALYSIS
    # ══════════════════════════════════════════

    def _build_hourly(self):
        outer = tk.Frame(self, bg=BG)

        top = tk.Frame(outer, bg=BG2, padx=16, pady=10)
        top.pack(fill="x")
        _lbl(top, "Peak Hour Analysis — All Time",
             font=MONO_HDR, fg=ACCENT, bg=BG2).pack(side="left")
        _btn(top, "↻ Refresh", self._hourly_load,
             color=ACCENT2).pack(side="right", ipadx=12, ipady=5)

        # Table
        cols   = ("Hour", "Time Slot", "Trips", "Revenue (₹)", "Avg Fee (₹)", "Traffic")
        widths = (60, 120, 70, 110, 100, 200)
        tf, self._hr_tree = _scrolled_tree(outer, cols, widths, height=12)
        tf.pack(fill="x", pady=(10, 0))

        # Heatmap chart
        _sep(outer).pack(fill="x", pady=(12, 6))
        _lbl(outer, "24-Hour Traffic Heatmap",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(anchor="w")

        self._hr_chart = tk.Text(
            outer, font=("Courier", 9), fg=WARN, bg=BG3,
            relief="flat", bd=6, height=8,
            state="disabled", wrap="none",
        )
        self._hr_chart.pack(fill="both", expand=True, pady=(6, 0))

        self._hourly_load()
        return outer

    def _hourly_load(self):
        res = tc.get_hourly_distribution()
        self._hr_tree.delete(*self._hr_tree.get_children())

        if not res["success"] or not res["data"]:
            self._hr_chart_update([])
            return

        rows    = res["data"]
        max_t   = max(r["trips"] for r in rows) if rows else 1

        SLOTS = {
            (0, 5):   "🌙 Late Night",
            (6, 8):   "🌅 Early Morning",
            (9, 11):  "🌞 Morning Rush",
            (12, 13): "☀️  Midday",
            (14, 16): "🌤  Afternoon",
            (17, 19): "🌆 Evening Rush",
            (20, 21): "🌃 Evening",
            (22, 23): "🌙 Night",
        }

        def _slot(h):
            for (lo, hi), label in SLOTS.items():
                if lo <= h <= hi:
                    return label
            return "—"

        def _traffic(trips, max_t):
            pct = trips / max_t if max_t else 0
            if pct >= 0.8:  return "████████  PEAK"
            if pct >= 0.5:  return "██████    HIGH"
            if pct >= 0.2:  return "████      MEDIUM"
            return              "██        LOW"

        for r in rows:
            h   = r["hour"]
            avg = r["revenue"] / r["trips"] if r["trips"] else 0
            self._hr_tree.insert("", "end", values=(
                f"{h:02d}:00",
                f"{h:02d}:00 – {h+1:02d}:00",
                r["trips"],
                f"{r['revenue']:,.2f}",
                f"{avg:.2f}",
                _traffic(r["trips"], max_t),
            ))

        self._hr_chart_update(rows)

    def _hr_chart_update(self, rows):
        self._hr_chart.config(state="normal")
        self._hr_chart.delete("1.0", tk.END)

        if not rows:
            self._hr_chart.insert(tk.END, "  No data to display.")
            self._hr_chart.config(state="disabled")
            return

        # Build full 24-hour grid
        hour_map = {r["hour"]: r for r in rows}
        max_t    = max(r["trips"] for r in rows) if rows else 1
        bar_max  = 44

        BLOCKS = ["░", "▒", "▓", "█"]

        lines  = [f"  {'Hour':<6}  {'Traffic Bar':<46}  Trips"]
        lines += [f"  {'─'*6}  {'─'*46}  {'─'*5}"]

        for h in range(24):
            r       = hour_map.get(h, {"trips": 0, "revenue": 0})
            trips   = r["trips"]
            pct     = trips / max_t if max_t else 0
            bar_len = int(pct * bar_max)

            # Choose block character based on density
            if pct >= 0.75:   ch = "█"
            elif pct >= 0.5:  ch = "▓"
            elif pct >= 0.25: ch = "▒"
            else:             ch = "░"

            bar = ch * bar_len + " " * (bar_max - bar_len)
            lines.append(f"  {h:02d}:00   {bar}  {trips:>5}")

        self._hr_chart.insert(tk.END, "\n".join(lines))
        self._hr_chart.config(state="disabled")

    # ══════════════════════════════════════════
    #  TAB 6 — EXPORT CENTRE
    # ══════════════════════════════════════════

    def _build_export(self):
        outer = tk.Frame(self, bg=BG)

        _lbl(outer, "Export Centre",
             font=MONO_HDR, fg=ACCENT, bg=BG).pack(anchor="w", pady=(0, 16))

        # ── Toll Records Export ───────────────
        sec1 = tk.LabelFrame(outer, text="  Toll Records  ",
                              font=MONO_SM, fg=TEXT2, bg=BG2,
                              bd=1, relief="groove",
                              labelanchor="nw", padx=20, pady=16)
        sec1.pack(fill="x", pady=(0, 14))

        row1 = tk.Frame(sec1, bg=BG2)
        row1.pack(anchor="w")

        _lbl(row1, "From:", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._exp_from = _entry(row1, width=12)
        self._exp_from.insert(0, _n_days_ago(30))
        self._exp_from.pack(side="left", padx=(8, 16), ipady=4)

        _lbl(row1, "To:", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._exp_to = _entry(row1, width=12)
        self._exp_to.insert(0, _today_str())
        self._exp_to.pack(side="left", padx=(8, 16), ipady=4)

        _lbl(row1, "(YYYY-MM-DD)  leave blank for all records",
             font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")

        row1b = tk.Frame(sec1, bg=BG2)
        row1b.pack(anchor="w", pady=(10, 0))

        def _export_records():
            fp = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=f"toll_records_{_today_str()}.csv",
            )
            if not fp:
                return
            df = self._exp_from.get().strip()
            dt = self._exp_to.get().strip()
            res = tc.export_records(fp, df, dt)
            color = SUCCESS if res["success"] else DANGER
            self._exp_status.config(fg=color)
            self._exp_status.config(
                text=("✔  " if res["success"] else "⚠  ") + res["message"]
            )

        _btn(row1b, "📥  Export Toll Records (CSV)",
             _export_records, color=ACCENT2).pack(side="left", ipadx=14, ipady=8)

        # ── Vehicles Export ───────────────────
        sec2 = tk.LabelFrame(outer, text="  Registered Vehicles  ",
                              font=MONO_SM, fg=TEXT2, bg=BG2,
                              bd=1, relief="groove",
                              labelanchor="nw", padx=20, pady=16)
        sec2.pack(fill="x", pady=(0, 14))

        def _export_vehicles():
            fp = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=f"vehicles_{_today_str()}.csv",
            )
            if not fp:
                return
            res = vc.export_vehicles_to_csv(fp)
            color = SUCCESS if res["success"] else DANGER
            self._exp_status.config(fg=color)
            self._exp_status.config(
                text=("✔  " if res["success"] else "⚠  ") + res["message"]
            )

        _btn(sec2, "📥  Export Vehicle Register (CSV)",
             _export_vehicles, color=ACCENT).pack(anchor="w", ipadx=14, ipady=8)

        # ── Revenue Summary Export ────────────
        sec3 = tk.LabelFrame(outer, text="  Revenue Summary Report  ",
                              font=MONO_SM, fg=TEXT2, bg=BG2,
                              bd=1, relief="groove",
                              labelanchor="nw", padx=20, pady=16)
        sec3.pack(fill="x", pady=(0, 14))

        row3 = tk.Frame(sec3, bg=BG2)
        row3.pack(anchor="w")

        self._exp_rev_period = tk.StringVar(value="all")
        for label, val in [("Today", "today"), ("This Month", "month"), ("All Time", "all")]:
            tk.Radiobutton(
                row3, text=label, variable=self._exp_rev_period, value=val,
                font=MONO_SM, fg=TEXT, bg=BG2,
                selectcolor=BG3, activebackground=BG2, cursor="hand2",
            ).pack(side="left", padx=(0, 16))

        def _export_revenue():
            fp = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=f"revenue_summary_{_today_str()}.csv",
            )
            if not fp:
                return
            period = self._exp_rev_period.get()
            res    = tc.get_revenue_report(period)
            if not res["success"] or not res["data"]["rows"]:
                self._exp_status.config(fg=DANGER,
                    text="⚠  No revenue data to export.")
                return
            try:
                import csv
                with open(fp, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "vehicle_type", "trips", "revenue",
                        "avg_fee", "first_entry", "last_entry"
                    ], extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(res["data"]["rows"])
                self._exp_status.config(fg=SUCCESS,
                    text=f"✔  Revenue summary exported to {fp}")
            except Exception as e:
                self._exp_status.config(fg=DANGER, text=f"⚠  {e}")

        _btn(sec3, "📥  Export Revenue Summary (CSV)",
             _export_revenue, color=SUCCESS).pack(anchor="w",
             pady=(10, 0), ipadx=14, ipady=8)

        # ── Status label ──────────────────────
        _sep(outer).pack(fill="x", pady=(10, 8))
        self._exp_status = tk.Label(outer, text="",
                                     font=MONO_SM, fg=SUCCESS, bg=BG,
                                     anchor="w", wraplength=700)
        self._exp_status.pack(anchor="w")

        return outer


# ──────────────────────────────────────────────
#  STANDALONE TEST
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import db_manager as db
    db.initialize_database()

    root = tk.Tk()
    root.withdraw()

    def _open():
        ReportsWindow(root)
        root.deiconify()
        root.geometry("1x1+9999+9999")   # hide root, keep event loop alive

    root.after(100, _open)
    root.mainloop()