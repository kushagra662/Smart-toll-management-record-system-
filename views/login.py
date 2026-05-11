

import tkinter as tk
from tkinter import font as tkfont
import db_manager as db


# ──────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────

BG          = "#0d1b2a"       # deep navy
BG2         = "#122236"       # card background
BG3         = "#1a3148"       # input background
ACCENT      = "#e8a020"       # amber gold
ACCENT2     = "#2d9cdb"       # sky blue
SUCCESS     = "#27ae60"
DANGER      = "#e05252"
TEXT        = "#d4e1f0"
TEXT2       = "#7a99bb"
BORDER      = "#243550"

MONO        = ("Courier", 11)
MONO_SM     = ("Courier", 9)
MONO_LG     = ("Courier", 13, "bold")
MONO_XL     = ("Courier", 28, "bold")
MONO_HDR    = ("Courier", 12, "bold")


# ──────────────────────────────────────────────
#  LOGIN WINDOW
# ──────────────────────────────────────────────

class LoginWindow(tk.Toplevel):
    """
    Modal login window that sits on top of the root.

    Parameters
    ----------
    parent      : tk.Tk root window
    on_success  : callable(user: dict) — invoked when login succeeds
    on_close    : callable() — invoked when user closes the window
                  (default: destroy parent)
    """

    WIDTH  = 460
    HEIGHT = 580

    def __init__(self, parent: tk.Tk,
                 on_success=None,
                 on_close=None):
        super().__init__(parent)
        self.parent      = parent
        self._on_success = on_success
        self._on_close   = on_close or (lambda: parent.destroy())

        self.title("Toll Management System — Login")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        # State
        self._show_pass   = False
        self._attempts    = 0
        self._locked      = False
        self._shake_job   = None
        self._dot_count   = 0

        self._build_ui()
        self._center()
        self.grab_set()
        self.focus_force()
        self.after(120, self._animate_in)

    # ──────────────────────────────────────────
    #  LAYOUT
    # ──────────────────────────────────────────

    def _build_ui(self):
        # ── Outer canvas for subtle grid background ──
        self._canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self._canvas.place(relwidth=1, relheight=1)
        self._draw_grid()

        # ── Card container (starts off-screen, slides in) ──
        self._card = tk.Frame(self, bg=BG2, bd=0)
        self._card.place(relx=0.5, rely=0.5, anchor="center",
                         width=340, height=460)

        self._build_header()
        self._build_form()
        self._build_footer()

    def _draw_grid(self):
        """Draw a faint grid pattern on the canvas background."""
        w, h   = self.WIDTH, self.HEIGHT
        step   = 40
        color  = "#142030"
        for x in range(0, w, step):
            self._canvas.create_line(x, 0, x, h, fill=color, width=1)
        for y in range(0, h, step):
            self._canvas.create_line(0, y, w, y, fill=color, width=1)

        # Diagonal accent lines
        self._canvas.create_line(0, h, w, 0,
                                  fill="#1a3040", width=1, dash=(4, 8))
        self._canvas.create_line(0, h // 2, w // 2, 0,
                                  fill="#1a3040", width=1, dash=(4, 8))

        # Corner accent
        for size, alpha in [(80, "#162840"), (50, "#1c3050")]:
            self._canvas.create_rectangle(
                self.WIDTH - size, 0, self.WIDTH, size,
                fill=alpha, outline=""
            )

    def _build_header(self):
        hdr = tk.Frame(self._card, bg=BG2, pady=0)
        hdr.pack(fill="x", padx=0, pady=0)

        # Top amber stripe
        stripe = tk.Frame(self._card, bg=ACCENT, height=4)
        stripe.pack(fill="x", side="top")

        # Icon
        icon_frame = tk.Frame(self._card, bg=BG2)
        icon_frame.pack(pady=(26, 0))

        self._icon_canvas = tk.Canvas(icon_frame, width=68, height=68,
                                       bg=BG2, highlightthickness=0)
        self._icon_canvas.pack()
        self._draw_icon(self._icon_canvas)

        # Title
        tk.Label(self._card, text="TOLL MANAGEMENT",
                 font=("Courier", 15, "bold"),
                 fg=TEXT, bg=BG2).pack(pady=(10, 0))

        tk.Label(self._card, text="SYSTEM",
                 font=("Courier", 15, "bold"),
                 fg=ACCENT, bg=BG2).pack()

        tk.Label(self._card, text="Authorized access only",
                 font=MONO_SM, fg=TEXT2, bg=BG2).pack(pady=(4, 0))

        # Separator
        tk.Frame(self._card, bg=BORDER, height=1).pack(
            fill="x", padx=30, pady=(16, 0))

    def _draw_icon(self, canvas):
        """Draw a stylised road/toll hexagon icon."""
        cx, cy, r = 34, 34, 30
        # Hexagon
        import math
        pts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            pts += [cx + r * math.cos(angle), cy + r * math.sin(angle)]
        canvas.create_polygon(pts, fill=BG3, outline=ACCENT, width=2)

        # Road lines
        canvas.create_rectangle(cx - 12, cy - 4, cx + 12, cy + 4,
                                  fill=ACCENT, outline="")
        canvas.create_rectangle(cx - 2, cy - 14, cx + 2, cy - 6,
                                  fill=TEXT2, outline="")
        canvas.create_rectangle(cx - 2, cy + 6, cx + 2, cy + 14,
                                  fill=TEXT2, outline="")

    def _build_form(self):
        form = tk.Frame(self._card, bg=BG2, padx=32)
        form.pack(fill="x", pady=(20, 0))

        # Username field
        self._build_field(form, "USERNAME", "username", row=0)

        # Password field with toggle
        self._build_field(form, "PASSWORD", "password", row=1, secret=True)

        # Error / status label
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(
            form, textvariable=self._status_var,
            font=MONO_SM, fg=DANGER, bg=BG2,
            anchor="w", wraplength=276,
        )
        self._status_lbl.grid(row=4, column=0, columnspan=2,
                               sticky="w", pady=(6, 0))

        # Login button
        self._login_btn = tk.Button(
            form, text="LOGIN  →",
            font=("Courier", 12, "bold"),
            fg=BG, bg=ACCENT,
            activeforeground=BG, activebackground="#c8881a",
            relief="flat", bd=0, cursor="hand2",
            command=self._attempt_login,
        )
        self._login_btn.grid(row=5, column=0, columnspan=2,
                              sticky="ew", pady=(16, 0), ipady=11)

        # Loading dots label (hidden until login attempt)
        self._dots_var = tk.StringVar()
        tk.Label(form, textvariable=self._dots_var,
                 font=MONO_SM, fg=ACCENT2, bg=BG2).grid(
                 row=6, column=0, columnspan=2, pady=(6, 0))

        # Bind Enter key
        self.bind("<Return>", lambda e: self._attempt_login())

    def _build_field(self, parent, label: str, key: str,
                     row: int, secret: bool = False):
        """Build a labelled input row inside the form grid."""
        tk.Label(parent, text=label, font=MONO_SM,
                 fg=TEXT2, bg=BG2, anchor="w").grid(
                 row=row * 2, column=0, columnspan=2,
                 sticky="w", pady=(12, 2))

        entry_frame = tk.Frame(parent, bg=BG3)
        entry_frame.grid(row=row * 2 + 1, column=0, columnspan=2,
                          sticky="ew", ipady=0)
        parent.columnconfigure(0, weight=1)

        entry = tk.Entry(
            entry_frame,
            font=("Courier", 12),
            fg=TEXT, bg=BG3,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            show="●" if secret else "",
        )
        entry.pack(side="left", fill="x", expand=True,
                   padx=(10, 0), pady=8, ipady=2)

        # Underline accent
        tk.Frame(parent, bg=ACCENT, height=1).grid(
            row=row * 2 + 1, column=0, columnspan=2,
            sticky="ew", pady=(0, 0))

        if secret:
            self._pass_entry = entry
            toggle = tk.Button(
                entry_frame, text="👁",
                font=("Courier", 9),
                fg=TEXT2, bg=BG3,
                activebackground=BG3, activeforeground=ACCENT,
                relief="flat", bd=0, cursor="hand2",
                command=self._toggle_password,
            )
            toggle.pack(side="right", padx=(0, 8))
        else:
            self._user_entry = entry

    def _build_footer(self):
        footer = tk.Frame(self._card, bg=BG2)
        footer.pack(fill="x", pady=(16, 0), padx=32, side="bottom")

        tk.Frame(self._card, bg=BORDER, height=1).pack(
            fill="x", padx=30, pady=(0, 12), side="bottom")

        tk.Label(footer, text="Default credentials:  admin  /  admin123",
                 font=MONO_SM, fg=BORDER, bg=BG2).pack(side="bottom", pady=(0, 14))

    # ──────────────────────────────────────────
    #  ANIMATION
    # ──────────────────────────────────────────

    def _animate_in(self):
        """Slide the card up from slightly below centre."""
        target_y  = 0.5
        start_y   = 0.62
        steps     = 18
        self._anim_step = 0

        def _step():
            if self._anim_step >= steps:
                self._card.place(relx=0.5, rely=target_y, anchor="center",
                                  width=340, height=460)
                return
            progress = self._anim_step / steps
            ease     = 1 - (1 - progress) ** 3        # ease-out cubic
            y        = start_y + (target_y - start_y) * ease
            self._card.place(relx=0.5, rely=y, anchor="center",
                              width=340, height=460)
            self._anim_step += 1
            self.after(14, _step)

        _step()

    def _shake(self):
        """Shake the card left-right to signal a wrong password."""
        offsets = [10, -10, 8, -8, 5, -5, 3, -3, 0]
        cx      = self.WIDTH  // 2
        cy      = self.HEIGHT // 2

        def _move(idx=0):
            if idx >= len(offsets):
                self._card.place(x=cx - 170, y=cy - 230)
                return
            self._card.place(x=cx - 170 + offsets[idx], y=cy - 230)
            self.after(30, lambda: _move(idx + 1))

        _move()

    def _animate_dots(self):
        """Show pulsing dots while validating credentials."""
        dots = ["●", "● ●", "● ● ●"]
        self._dots_var.set(dots[self._dot_count % 3])
        self._dot_count += 1
        if self._locked:
            return
        self._dot_job = self.after(300, self._animate_dots)

    def _stop_dots(self):
        if hasattr(self, "_dot_job"):
            self.after_cancel(self._dot_job)
        self._dots_var.set("")

    # ──────────────────────────────────────────
    #  TOGGLE PASSWORD VISIBILITY
    # ──────────────────────────────────────────

    def _toggle_password(self):
        self._show_pass = not self._show_pass
        self._pass_entry.config(show="" if self._show_pass else "●")

    # ──────────────────────────────────────────
    #  LOGIN LOGIC
    # ──────────────────────────────────────────

    def _attempt_login(self):
        if self._locked:
            return

        username = self._user_entry.get().strip()
        password = self._pass_entry.get().strip()

        # ── Basic field validation ──
        if not username and not password:
            self._set_status("⚠  Please enter your username and password.", DANGER)
            return
        if not username:
            self._set_status("⚠  Username cannot be empty.", DANGER)
            return
        if not password:
            self._set_status("⚠  Password cannot be empty.", DANGER)
            return

        # ── Disable UI & show dots ──
        self._login_btn.config(state="disabled", text="Checking …",
                                bg=BG3, fg=TEXT2)
        self._set_status("", ACCENT2)
        self._dot_count = 0
        self._animate_dots()

        # ── Simulate a tiny delay so the UI responds (100 ms) ──
        self.after(120, lambda: self._do_validate(username, password))

    def _do_validate(self, username: str, password: str):
        self._stop_dots()
        user = db.validate_login(username, password)

        if user:
            # ── Success ──
            self._set_status(f"✔  Welcome, {user['username'].upper()}!", SUCCESS)
            self._login_btn.config(text="✔  Authenticated",
                                    bg=SUCCESS, fg=BG,
                                    state="disabled")
            self.after(500, lambda: self._login_success(user))
        else:
            # ── Failure ──
            self._attempts += 1
            self._shake()
            self._pass_entry.delete(0, tk.END)
            self._login_btn.config(state="normal", text="LOGIN  →",
                                    bg=ACCENT, fg=BG)

            if self._attempts >= 5:
                self._locked = True
                self._login_btn.config(
                    state="disabled",
                    text="LOCKED — too many attempts",
                    bg=DANGER, fg=TEXT,
                )
                self._set_status(
                    "⛔  Account locked after 5 failed attempts.\n"
                    "   Please restart the application.",
                    DANGER,
                )
            elif self._attempts >= 3:
                remaining = 5 - self._attempts
                self._set_status(
                    f"⚠  Wrong credentials.  "
                    f"{remaining} attempt(s) remaining.",
                    DANGER,
                )
            else:
                self._set_status("⚠  Invalid username or password.", DANGER)

    def _login_success(self, user: dict):
        self.destroy()
        if self._on_success:
            self._on_success(user)

    # ──────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────

    def _set_status(self, message: str, color: str = DANGER):
        self._status_var.set(message)
        self._status_lbl.config(fg=color)

    def _center(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - self.WIDTH)  // 2
        y  = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _handle_close(self):
        self._on_close()


# ──────────────────────────────────────────────
#  STANDALONE TEST
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import db_manager as db

    db.initialize_database()

    root = tk.Tk()
    root.withdraw()

    def on_login(user):
        root.deiconify()
        root.geometry("400x200")
        root.configure(bg="#0d1b2a")
        tk.Label(
            root,
            text=f"✔  Logged in as: {user['username'].upper()}  [{user['role']}]",
            font=("Courier", 12, "bold"),
            fg="#e8a020", bg="#0d1b2a",
        ).pack(expand=True)

    LoginWindow(root, on_success=on_login)
    root.mainloop()