"""
vehicle_entry.py
─────────────────────────────────────────────────────────────
Dedicated Vehicle Entry Window for the Toll Record Management System.

Provides a full-featured vehicle registration interface with:
  • Smart plate number formatter & real-time validator
  • Auto-complete owner name suggestions
  • Vehicle type selector with fee preview
  • Duplicate plate detection before submission
  • Recent registrations live feed
  • Bulk CSV import with progress feedback
  • Quick search / lookup panel
  • Animated success / error feedback

Can be opened as a standalone Toplevel from the dashboard or
run directly for testing.

Usage:
    from vehicle_entry import VehicleEntryWindow
    VehicleEntryWindow(parent, on_register=callback)
─────────────────────────────────────────────────────────────
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

import vehicle_ctrl as vc
import db_manager   as db


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
MONO_XL   = ("Courier", 22, "bold")


# ──────────────────────────────────────────────
#  WIDGET HELPERS
# ──────────────────────────────────────────────

def _lbl(parent, text, font=MONO, fg=TEXT, bg=BG2, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def _entry(parent, width=24, textvariable=None, **kw):
    cfg = dict(font=MONO, fg=TEXT, bg=BG3, insertbackground=ACCENT,
               relief="flat", bd=6, width=width)
    cfg.update(kw)
    if textvariable:
        cfg["textvariable"] = textvariable
    return tk.Entry(parent, **cfg)


def _btn(parent, text, command, color=ACCENT, fg=BG, **kw):
    return tk.Button(
        parent, text=text, command=command,
        font=("Courier", 9, "bold"),
        fg=fg, bg=color,
        activeforeground=fg, activebackground=color,
        relief="flat", bd=0, cursor="hand2", **kw,
    )


def _sep(parent, color=BORDER):
    return tk.Frame(parent, bg=color, height=1)


def _tree_style():
    s = ttk.Style()
    s.theme_use("default")
    s.configure("VE.Treeview",
                background=BG, foreground=TEXT,
                fieldbackground=BG, rowheight=26,
                font=("Courier", 9), borderwidth=0)
    s.configure("VE.Treeview.Heading",
                background=BG3, foreground=ACCENT,
                font=("Courier", 9, "bold"), relief="flat")
    s.map("VE.Treeview",
          background=[("selected", "#1f3a5a")],
          foreground=[("selected", TEXT)])


def _scrolled_tree(parent, cols, widths, height=10):
    _tree_style()
    frame = tk.Frame(parent, bg=BG)
    tree  = ttk.Treeview(frame, columns=cols, show="headings",
                          style="VE.Treeview", height=height)
    vsb   = ttk.Scrollbar(frame, orient="vertical",   command=tree.yview)
    hsb   = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    for col, w in zip(cols, widths):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor="center", minwidth=40)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


# ──────────────────────────────────────────────
#  VEHICLE ENTRY WINDOW
# ──────────────────────────────────────────────

class VehicleEntryWindow(tk.Toplevel):
    """
    Standalone vehicle registration window.

    Parameters
    ----------
    parent      : tk widget
    on_register : callable(vehicle: dict) — fired after each successful registration
    """

    WIDTH  = 1060
    HEIGHT = 700

    def __init__(self, parent, on_register=None):
        super().__init__(parent)
        self.parent      = parent
        self._on_register = on_register

        self.title("Toll Management System — Vehicle Entry")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(860, 580)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # State
        self._plate_ok    = False
        self._check_job   = None     # debounce timer for plate validation
        self._anim_job    = None
        self._reg_count   = 0        # registrations this session

        self._build_navbar()
        self._build_body()
        self._center()
        self.focus_force()
        self._load_recent()

    # ──────────────────────────────────────────
    #  NAVBAR
    # ──────────────────────────────────────────

    def _build_navbar(self):
        nav = tk.Frame(self, bg=BG3, height=50)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Frame(nav, bg=ACCENT, width=4).pack(side="left", fill="y")

        _lbl(nav, "  🚗  VEHICLE REGISTRATION",
             font=("Courier", 12, "bold"), fg=TEXT, bg=BG3).pack(
             side="left", padx=(10, 0), pady=12)

        _btn(nav, "✕  Close", self.destroy,
             color=BG3, fg=TEXT2).pack(side="right", ipadx=10, ipady=8)

        self._session_var = tk.StringVar(value="Session: 0 registered")
        tk.Label(nav, textvariable=self._session_var,
                 font=MONO_SM, fg=TEXT2, bg=BG3).pack(side="right", padx=16)

    # ──────────────────────────────────────────
    #  BODY — three-column layout
    # ──────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Col 0 — Registration form
        self._build_form(body)

        # Vertical divider
        tk.Frame(body, bg=BORDER, width=1).grid(
            row=0, column=1, sticky="ns", padx=10)

        # Col 2 — Right panel (tabs: Recent | Search | Import)
        self._build_right_panel(body)

    # ──────────────────────────────────────────
    #  REGISTRATION FORM  (left column)
    # ──────────────────────────────────────────

    def _build_form(self, parent):
        form = tk.Frame(parent, bg=BG2, padx=24, pady=20)
        form.grid(row=0, column=0, sticky="ns")

        # ── Title ──
        _lbl(form, "Register New Vehicle",
             font=MONO_HDR, fg=ACCENT, bg=BG2).grid(
             row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))

        # ── Plate number ──
        _lbl(form, "PLATE NUMBER  *", font=MONO_SM,
             fg=TEXT2, bg=BG2).grid(row=1, column=0, columnspan=3,
                                     sticky="w", pady=(0, 4))

        plate_row = tk.Frame(form, bg=BG2)
        plate_row.grid(row=2, column=0, columnspan=3, sticky="w")

        self._plate_var = tk.StringVar()
        self._plate_var.trace_add("write", self._on_plate_type)

        self._plate_entry = tk.Entry(
            plate_row,
            textvariable=self._plate_var,
            font=("Courier", 16, "bold"),
            fg=ACCENT, bg=BG3,
            insertbackground=ACCENT,
            relief="flat", bd=6, width=16,
        )
        self._plate_entry.pack(side="left", ipady=8)

        # Plate status indicator (✔ / ✘ / ...)
        self._plate_indicator = tk.Label(
            plate_row, text="  ", font=("Courier", 14, "bold"),
            fg=TEXT2, bg=BG2, width=3,
        )
        self._plate_indicator.pack(side="left", padx=(10, 0))

        # Formatted display
        self._plate_display = tk.StringVar()
        tk.Label(form, textvariable=self._plate_display,
                 font=("Courier", 10), fg=TEXT2, bg=BG2).grid(
                 row=3, column=0, columnspan=3, sticky="w", pady=(3, 0))

        _sep(form).grid(row=4, column=0, columnspan=3,
                        sticky="ew", pady=(14, 0))

        # ── Owner name ──
        _lbl(form, "OWNER NAME  *", font=MONO_SM,
             fg=TEXT2, bg=BG2).grid(row=5, column=0, columnspan=3,
                                     sticky="w", pady=(12, 4))
        self._owner_entry = _entry(form, width=28)
        self._owner_entry.grid(row=6, column=0, columnspan=3,
                                sticky="w", ipady=6)

        # ── Phone ──
        _lbl(form, "PHONE NUMBER", font=MONO_SM,
             fg=TEXT2, bg=BG2).grid(row=7, column=0, columnspan=3,
                                     sticky="w", pady=(12, 4))

        phone_row = tk.Frame(form, bg=BG2)
        phone_row.grid(row=8, column=0, columnspan=3, sticky="w")

        self._phone_entry = _entry(phone_row, width=16)
        self._phone_entry.pack(side="left", ipady=6)
        _lbl(phone_row, " 10-digit", font=MONO_SM,
             fg=TEXT2, bg=BG2).pack(side="left", padx=(8, 0))

        # ── Vehicle type ──
        _lbl(form, "VEHICLE TYPE  *", font=MONO_SM,
             fg=TEXT2, bg=BG2).grid(row=9, column=0, columnspan=3,
                                     sticky="w", pady=(12, 4))

        type_row = tk.Frame(form, bg=BG2)
        type_row.grid(row=10, column=0, columnspan=3, sticky="w")

        types_res    = vc.get_valid_vehicle_types()
        self._types  = types_res["data"] if types_res["success"] else ["Car"]
        self._type_var = tk.StringVar(value=self._types[0])
        self._type_var.trace_add("write", self._on_type_change)

        self._type_combo = ttk.Combobox(
            type_row, textvariable=self._type_var,
            values=self._types, state="readonly",
            font=MONO, width=18,
        )
        self._type_combo.pack(side="left", ipady=4)

        # Fee badge
        self._fee_var = tk.StringVar(value="")
        self._fee_lbl = tk.Label(
            type_row, textvariable=self._fee_var,
            font=("Courier", 11, "bold"),
            fg=ACCENT, bg=BG4,
            padx=10, pady=4,
        )
        self._fee_lbl.pack(side="left", padx=(12, 0))
        self._refresh_fee()

        _sep(form).grid(row=11, column=0, columnspan=3,
                        sticky="ew", pady=(18, 0))

        # ── Status message ──
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(
            form, textvariable=self._status_var,
            font=MONO_SM, fg=SUCCESS, bg=BG2,
            anchor="w", wraplength=300, justify="left",
        )
        self._status_lbl.grid(row=12, column=0, columnspan=3,
                               sticky="w", pady=(8, 0))

        # ── Buttons ──
        btn_row = tk.Frame(form, bg=BG2)
        btn_row.grid(row=13, column=0, columnspan=3,
                     sticky="w", pady=(14, 0))

        self._register_btn = _btn(
            btn_row, "  REGISTER VEHICLE  ",
            self._register,
        )
        self._register_btn.pack(side="left", ipadx=10, ipady=10)

        _btn(btn_row, "CLEAR",
             self._clear_form,
             color=BG3, fg=TEXT2).pack(side="left", padx=(10, 0),
                                        ipadx=14, ipady=10)

        # ── Quick stats footer ──
        stats_frame = tk.Frame(form, bg=BG3, padx=12, pady=10)
        stats_frame.grid(row=14, column=0, columnspan=3,
                          sticky="ew", pady=(20, 0))

        self._stat_vars = {}
        for i, (key, label, color) in enumerate([
            ("total",   "Total Registered", ACCENT2),
            ("session", "This Session",     SUCCESS),
        ]):
            tk.Label(stats_frame, text="0",
                     font=("Courier", 18, "bold"),
                     fg=color, bg=BG3).grid(row=0, column=i * 2,
                                             padx=(0 if i == 0 else 20, 0))
            _lbl(stats_frame, label, font=MONO_SM,
                 fg=TEXT2, bg=BG3).grid(row=1, column=i * 2,
                                         padx=(0 if i == 0 else 20, 0))
            self._stat_vars[key] = stats_frame.grid_slaves(
                row=0, column=i * 2)[0]

        self._refresh_stats()

        # Bind Enter key to register
        self._plate_entry.bind("<Return>", lambda e: self._owner_entry.focus())
        self._owner_entry.bind("<Return>", lambda e: self._phone_entry.focus())
        self._phone_entry.bind("<Return>", lambda e: self._register())

    # ──────────────────────────────────────────
    #  RIGHT PANEL  (tabbed: Recent | Search | Import)
    # ──────────────────────────────────────────

    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=2, sticky="nsew")
        parent.columnconfigure(2, weight=1)

        # Mini tab bar
        tab_bar = tk.Frame(right, bg=BG2)
        tab_bar.pack(fill="x")

        self._right_tab_btns = []
        self._right_tab_frames = []

        labels = ["📋  Recent", "🔍  Search", "📥  Import CSV"]
        for i, label in enumerate(labels):
            b = tk.Button(
                tab_bar, text=label,
                font=MONO_SM,
                fg=TEXT2, bg=BG2,
                activeforeground=BG, activebackground=ACCENT,
                relief="flat", bd=0, cursor="hand2",
                padx=12, pady=8,
                command=lambda idx=i: self._show_right_tab(idx),
            )
            b.pack(side="left", padx=(0, 2))
            self._right_tab_btns.append(b)

        _sep(right).pack(fill="x")

        # Content frames
        self._right_tab_frames = [
            self._build_recent_tab(right),
            self._build_search_tab(right),
            self._build_import_tab(right),
        ]

        self._show_right_tab(0)

    def _show_right_tab(self, index: int):
        for i, b in enumerate(self._right_tab_btns):
            b.config(fg=BG if i == index else TEXT2,
                     bg=ACCENT if i == index else BG2)
        for f in self._right_tab_frames:
            f.pack_forget()
        self._right_tab_frames[index].pack(fill="both", expand=True,
                                            padx=0, pady=0)

    # ── Recent Registrations ──────────────────

    def _build_recent_tab(self, parent):
        frame = tk.Frame(parent, bg=BG)

        top = tk.Frame(frame, bg=BG, padx=10, pady=8)
        top.pack(fill="x")
        _lbl(top, "Latest Registrations",
             font=("Courier", 10, "bold"), fg=TEXT2, bg=BG).pack(side="left")
        _btn(top, "↻", self._load_recent,
             color=BG3, fg=TEXT2).pack(side="right", ipadx=8, ipady=3)

        cols   = ("Plate", "Type", "Owner", "Phone", "Registered At")
        widths = (110, 90, 150, 105, 145)
        tf, self._recent_tree = _scrolled_tree(frame, cols, widths, height=20)
        tf.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Double-click to populate form
        self._recent_tree.bind("<Double-1>", self._on_recent_select)

        return frame

    def _load_recent(self, *_):
        self._recent_tree.delete(*self._recent_tree.get_children())
        res = vc.get_all_vehicles()
        for v in (res["data"] or [])[:100]:
            self._recent_tree.insert("", "end", iid=str(v["id"]), values=(
                v["plate_number"],
                v["vehicle_type"],
                v["owner_name"],
                v["owner_phone"] or "—",
                v["registered_at"][:16],
            ))

    def _on_recent_select(self, event):
        """Double-click a row → fill the form for quick reference."""
        sel = self._recent_tree.selection()
        if not sel:
            return
        vals = self._recent_tree.item(sel[0])["values"]
        self._status_var.set(
            f"ℹ  Loaded '{vals[0]}' from recent list (read-only preview)."
        )
        self._status_lbl.config(fg=ACCENT2)

    # ── Search Tab ────────────────────────────

    def _build_search_tab(self, parent):
        frame = tk.Frame(parent, bg=BG)

        top = tk.Frame(frame, bg=BG2, padx=10, pady=10)
        top.pack(fill="x")

        _lbl(top, "Search:", font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_type)

        search_entry = _entry(top, width=20, textvariable=self._search_var)
        search_entry.pack(side="left", padx=(8, 10), ipady=5)

        _btn(top, "Search", self._do_search,
             color=ACCENT).pack(side="left", ipadx=10, ipady=5)
        _btn(top, "Clear", lambda: self._search_var.set(""),
             color=BG3, fg=TEXT2).pack(side="left", padx=(6, 0),
                                        ipadx=10, ipady=5)

        self._search_count = tk.StringVar(value="")
        tk.Label(top, textvariable=self._search_count,
                 font=MONO_SM, fg=TEXT2, bg=BG2).pack(side="right")

        cols   = ("Plate", "Type", "Owner", "Phone", "Registered At")
        widths = (110, 90, 150, 105, 145)
        tf, self._search_tree = _scrolled_tree(frame, cols, widths, height=18)
        tf.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        # Detail panel
        detail = tk.Frame(frame, bg=BG3, padx=12, pady=10)
        detail.pack(fill="x", padx=8, pady=(0, 8))

        self._detail_vars = {}
        detail_fields = [
            ("plate",   "Plate:"),
            ("type",    "Type:"),
            ("owner",   "Owner:"),
            ("phone",   "Phone:"),
            ("fee",     "Toll Fee:"),
            ("reg",     "Registered:"),
        ]
        for i, (key, label) in enumerate(detail_fields):
            r, c = divmod(i, 2)
            _lbl(detail, label, font=MONO_SM, fg=TEXT2, bg=BG3,
                 width=11, anchor="w").grid(row=r, column=c * 2,
                                             sticky="w", padx=(0 if c == 0 else 16, 0), pady=1)
            v = tk.StringVar(value="—")
            self._detail_vars[key] = v
            color = ACCENT if key == "fee" else TEXT
            tk.Label(detail, textvariable=v, font=MONO,
                     fg=color, bg=BG3, anchor="w").grid(
                     row=r, column=c * 2 + 1, sticky="w", padx=(4, 0), pady=1)

        self._search_tree.bind("<<TreeviewSelect>>", self._on_search_select)
        return frame

    def _on_search_type(self, *_):
        """Debounced live search as user types."""
        if self._check_job:
            self.after_cancel(self._check_job)
        self._check_job = self.after(300, self._do_search)

    def _do_search(self, *_):
        query = self._search_var.get().strip()
        res   = vc.search_vehicles(query)
        self._search_tree.delete(*self._search_tree.get_children())

        vehicles = res["data"] or []
        for v in vehicles[:200]:
            self._search_tree.insert("", "end", iid=str(v["id"]), values=(
                v["plate_number"],
                v["vehicle_type"],
                v["owner_name"],
                v["owner_phone"] or "—",
                v["registered_at"][:16],
            ))

        self._search_count.set(f"{len(vehicles)} found")

    def _on_search_select(self, event):
        sel = self._search_tree.selection()
        if not sel:
            return
        vals  = self._search_tree.item(sel[0])["values"]
        plate = vals[0]
        res   = vc.get_vehicle(plate)
        if not res["success"]:
            return
        v = res["data"]
        self._detail_vars["plate"].set(v["plate_number"])
        self._detail_vars["type"].set(v["vehicle_type"])
        self._detail_vars["owner"].set(v["owner_name"])
        self._detail_vars["phone"].set(v["owner_phone"] or "—")
        fee = v.get("toll_fee")
        self._detail_vars["fee"].set(f"₹{fee:.2f}" if fee else "—")
        self._detail_vars["reg"].set(v["registered_at"][:16])

    # ── CSV Import Tab ────────────────────────

    def _build_import_tab(self, parent):
        frame = tk.Frame(parent, bg=BG, padx=14, pady=14)

        _lbl(frame, "Bulk Import from CSV",
             font=MONO_HDR, fg=ACCENT, bg=BG).pack(anchor="w")

        _sep(frame).pack(fill="x", pady=(10, 14))

        # Instructions
        inst = (
            "CSV must have a header row with these columns:\n\n"
            "   plate_number  —  e.g. MH12AB1234\n"
            "   vehicle_type  —  Car / Truck / Bus / Motorcycle / Auto\n"
            "   owner_name    —  full name\n"
            "   owner_phone   —  10-digit (optional)\n\n"
            "Duplicate plates are skipped automatically.\n"
            "Invalid rows are logged in the error report below."
        )
        tk.Label(frame, text=inst, font=MONO_SM, fg=TEXT2, bg=BG3,
                 justify="left", padx=12, pady=12, anchor="w").pack(
                 fill="x", pady=(0, 14))

        # File selector
        file_row = tk.Frame(frame, bg=BG)
        file_row.pack(anchor="w", fill="x")

        self._import_file_var = tk.StringVar(value="No file selected")
        tk.Label(file_row, textvariable=self._import_file_var,
                 font=MONO_SM, fg=TEXT2, bg=BG3,
                 anchor="w", padx=10, pady=6, width=38).pack(side="left")

        _btn(file_row, "Browse …", self._browse_csv,
             color=ACCENT2).pack(side="left", padx=(8, 0), ipadx=10, ipady=6)

        # Progress bar
        self._import_progress = ttk.Progressbar(
            frame, orient="horizontal", mode="determinate", length=400
        )
        self._import_progress.pack(anchor="w", pady=(14, 0))

        # Import button
        self._import_btn = _btn(
            frame, "  START IMPORT  ",
            self._do_import, color=SUCCESS,
        )
        self._import_btn.pack(anchor="w", pady=(12, 0),
                               ipadx=14, ipady=10)

        # Result log
        _sep(frame).pack(fill="x", pady=(14, 8))
        _lbl(frame, "Import Log", font=MONO_SM, fg=TEXT2, bg=BG).pack(anchor="w")

        log_frame = tk.Frame(frame, bg=BG)
        log_frame.pack(fill="both", expand=True, pady=(6, 0))

        self._import_log = tk.Text(
            log_frame, font=MONO_SM, fg=TEXT, bg=BG3,
            relief="flat", bd=6, height=10,
            state="disabled", wrap="none",
        )
        log_sb = ttk.Scrollbar(log_frame, command=self._import_log.yview)
        self._import_log.configure(yscrollcommand=log_sb.set)
        self._import_log.pack(side="left", fill="both", expand=True)
        log_sb.pack(side="left", fill="y")

        self._import_filepath = None
        return frame

    def _browse_csv(self):
        fp = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if fp:
            self._import_filepath = fp
            # Show only filename, not full path
            fname = fp.split("/")[-1].split("\\")[-1]
            self._import_file_var.set(fname)
            self._log_write(f"File selected: {fp}\n")

    def _do_import(self):
        if not self._import_filepath:
            self._log_write("⚠  Please select a CSV file first.\n")
            return

        self._import_btn.config(state="disabled", text="Importing …")
        self._import_progress["value"] = 0
        self.update()

        # Simulate progress bar fill (import is synchronous but fast)
        for pct in range(0, 60, 10):
            self._import_progress["value"] = pct
            self.update()
            self.after(40)

        res = vc.import_vehicles_from_csv(self._import_filepath)

        self._import_progress["value"] = 100
        self.update()

        self._import_btn.config(state="normal", text="  START IMPORT  ")

        if res["success"]:
            d = res["data"]
            self._log_write(
                f"\n{'─'*44}\n"
                f"  RESULT: {res['message']}\n"
                f"  ✔  Imported : {d['imported']}\n"
                f"  ↷  Skipped  : {d['skipped']} (duplicates)\n"
                f"  ✘  Errors   : {len(d['errors'])}\n"
            )
            if d["errors"]:
                self._log_write(f"\n  Error Details:\n")
                for err in d["errors"]:
                    self._log_write(
                        f"    Row {err['row']:>3} | {err['plate']:<14} | {err['reason']}\n"
                    )
            self._log_write(f"{'─'*44}\n")

            if d["imported"] > 0:
                self._reg_count += d["imported"]
                self._refresh_stats()
                self._load_recent()
                if self._on_register:
                    self._on_register(None)

            self.after(500, lambda: setattr(self, "_", self._import_progress.configure(value=0)))
        else:
            self._log_write(f"⚠  {res['message']}\n")
            self._import_progress["value"] = 0

    def _log_write(self, text: str):
        self._import_log.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self._import_log.insert(tk.END, f"[{ts}] {text}")
        self._import_log.see(tk.END)
        self._import_log.config(state="disabled")

    # ──────────────────────────────────────────
    #  PLATE VALIDATION (debounced, real-time)
    # ──────────────────────────────────────────

    def _on_plate_type(self, *_):
        """Called on every keystroke in the plate field."""
        if self._check_job:
            self.after_cancel(self._check_job)
        self._check_job = self.after(400, self._validate_plate_live)

    def _validate_plate_live(self):
        raw   = self._plate_var.get()
        plate = raw.replace(" ", "").replace("-", "").upper()

        if raw != plate:                          # auto-normalize
            self._plate_var.set(plate)
            self._plate_entry.icursor(tk.END)

        self._plate_display.set(
            f"Formatted: {vc.format_plate_display(plate)}" if plate else ""
        )

        if not plate:
            self._plate_indicator.config(text="  ", fg=TEXT2)
            self._plate_ok = False
            return

        if len(plate) < 5:
            self._plate_indicator.config(text=" ?", fg=WARN)
            self._plate_ok = False
            return

        # Check duplicate
        exists_res = vc.check_vehicle_exists(plate)
        if exists_res["data"] and exists_res["data"]["exists"]:
            self._plate_indicator.config(text=" ✘", fg=DANGER)
            self._status_var.set(f"⚠  Plate '{plate}' is already registered.")
            self._status_lbl.config(fg=DANGER)
            self._plate_ok = False
        else:
            self._plate_indicator.config(text=" ✔", fg=SUCCESS)
            self._status_var.set("")
            self._plate_ok = True

    # ──────────────────────────────────────────
    #  VEHICLE TYPE → FEE PREVIEW
    # ──────────────────────────────────────────

    def _on_type_change(self, *_):
        self._refresh_fee()

    def _refresh_fee(self):
        vtype = self._type_var.get()
        fee   = db.get_rate_for_type(vtype)
        if fee is not None:
            self._fee_var.set(f"  ₹ {fee:.2f}  ")
            self._fee_lbl.config(fg=ACCENT)
        else:
            self._fee_var.set("  Rate: —  ")
            self._fee_lbl.config(fg=TEXT2)

    # ──────────────────────────────────────────
    #  REGISTER
    # ──────────────────────────────────────────

    def _register(self):
        plate = self._plate_var.get().strip()
        owner = self._owner_entry.get().strip()
        phone = self._phone_entry.get().strip()
        vtype = self._type_var.get()

        res = vc.register_vehicle(plate, vtype, owner, phone)

        if res["success"]:
            self._status_var.set("✔  " + res["message"])
            self._status_lbl.config(fg=SUCCESS)
            self._animate_success()
            self._reg_count += 1
            self._refresh_stats()
            self._clear_form(keep_type=True)
            self._load_recent()
            if self._on_register:
                self._on_register(res["data"])
        else:
            self._status_var.set("⚠  " + res["message"])
            self._status_lbl.config(fg=DANGER)
            self._animate_error()

    def _animate_success(self):
        """Flash the register button green briefly."""
        orig_bg = ACCENT
        self._register_btn.config(bg=SUCCESS, text="✔  REGISTERED!")
        self.after(900, lambda: self._register_btn.config(
            bg=orig_bg, text="  REGISTER VEHICLE  "))

    def _animate_error(self):
        """Flash the register button red briefly."""
        orig_bg = ACCENT
        self._register_btn.config(bg=DANGER, text="✘  CHECK FIELDS")
        self.after(900, lambda: self._register_btn.config(
            bg=orig_bg, text="  REGISTER VEHICLE  "))

    # ──────────────────────────────────────────
    #  CLEAR FORM
    # ──────────────────────────────────────────

    def _clear_form(self, keep_type=False):
        self._plate_var.set("")
        self._owner_entry.delete(0, tk.END)
        self._phone_entry.delete(0, tk.END)
        self._plate_indicator.config(text="  ", fg=TEXT2)
        self._plate_display.set("")
        self._plate_ok = False
        if not keep_type:
            self._type_var.set(self._types[0])
        self._plate_entry.focus()

    # ──────────────────────────────────────────
    #  STATS
    # ──────────────────────────────────────────

    def _refresh_stats(self):
        total = db.count_vehicles()
        self._stat_vars["total"].config(text=str(total))
        self._stat_vars["session"].config(text=str(self._reg_count))
        self._session_var.set(f"Session: {self._reg_count} registered")

    # ──────────────────────────────────────────
    #  CENTER
    # ──────────────────────────────────────────

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - self.WIDTH)  // 2
        y  = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")


# ──────────────────────────────────────────────
#  STANDALONE TEST
# ──────────────────────────────────────────────

if __name__ == "__main__":
    db.initialize_database()

    root = tk.Tk()
    root.withdraw()

    def on_reg(v):
        if v:
            print(f"Registered: {v.get('plate_number')} — {v.get('owner_name')}")

    def _open():
        VehicleEntryWindow(root, on_register=on_reg)
        root.deiconify()
        root.geometry("1x1+9999+9999")

    root.after(100, _open)
    root.mainloop()