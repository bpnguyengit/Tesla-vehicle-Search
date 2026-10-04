#!/usr/bin/env python3
"""Tesla Vehicle Search — dark Tkinter GUI over Tesla's public inventory API."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk, messagebox
from typing import Optional

from inventory import (
    MODEL_CODES,
    InventoryError,
    SearchResult,
    Vehicle,
    listing_url,
    search_inventory,
)
from app_version import APP_DESCRIPTION, APP_NAME, APP_VERSION
from update_check import check_for_updates

# Tesla-inspired palette
BG = "#0b0b0b"
BG_PANEL = "#141414"
BG_INPUT = "#1c1c1c"
BG_ROW = "#121212"
BG_ROW_ALT = "#181818"
FG = "#f2f2f2"
FG_DIM = "#9a9a9a"
ACCENT = "#e31937"
ACCENT_HOVER = "#ff2a45"
BORDER = "#2a2a2a"
BEST = "#1f8f4e"
WARN = "#c9a227"

WINDOW_TITLE = "Tesla Vehicle Search"
DEFAULT_ZIP = "90210"
YEAR_LO_DEFAULT = 2018
YEAR_HI_DEFAULT = datetime.now().year + 1

DISTANCE_CHOICES = [
    ("Any / nationwide", None),
    ("25 miles", 25),
    ("50 miles", 50),
    ("100 miles", 100),
    ("200 miles", 200),
    ("500 miles", 500),
]


class TeslaSearchApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("1180x720")
        self.minsize(960, 600)
        self.configure(bg=BG)

        self._search_thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._vehicles: list[Vehicle] = []
        self._sort_column = "price"
        self._sort_reverse = False

        self._build_style()
        self._build_layout()
        self._build_menu()
        self._set_status("Ready. Set filters and click Search.")

    # --- styling ---------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=FG, fieldbackground=BG_INPUT)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=("Helvetica", 11))
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG, font=("Helvetica", 11))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Helvetica", 18, "bold"))
        style.configure("Accent.TLabel", background=BG, foreground=ACCENT, font=("Helvetica", 11, "bold"))
        style.configure("Status.TLabel", background=BG_PANEL, foreground=FG_DIM, font=("Helvetica", 10))
        style.configure("Section.TLabel", background=BG_PANEL, foreground=FG_DIM, font=("Helvetica", 9, "bold"))

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            focusthickness=0,
            padding=(16, 8),
            font=("Helvetica", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#5a1a22")],
            foreground=[("disabled", "#bbbbbb")],
        )
        style.configure(
            "Ghost.TButton",
            background=BG_INPUT,
            foreground=FG,
            bordercolor=BORDER,
            padding=(12, 6),
            font=("Helvetica", 10),
        )
        style.map("Ghost.TButton", background=[("active", "#252525")])

        style.configure(
            "Dark.TCheckbutton",
            background=BG_PANEL,
            foreground=FG,
            font=("Helvetica", 10),
            indicatorcolor=BG_INPUT,
        )
        style.map(
            "Dark.TCheckbutton",
            background=[("active", BG_PANEL)],
            foreground=[("active", FG)],
            indicatorcolor=[("selected", ACCENT), ("!selected", BG_INPUT)],
        )
        style.configure(
            "Dark.TRadiobutton",
            background=BG_PANEL,
            foreground=FG,
            font=("Helvetica", 10),
            indicatorcolor=BG_INPUT,
        )
        style.map(
            "Dark.TRadiobutton",
            background=[("active", BG_PANEL)],
            indicatorcolor=[("selected", ACCENT)],
        )

        style.configure(
            "Dark.TEntry",
            fieldbackground=BG_INPUT,
            foreground=FG,
            insertcolor=FG,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=6,
        )
        style.configure(
            "Dark.TSpinbox",
            fieldbackground=BG_INPUT,
            foreground=FG,
            background=BG_INPUT,
            arrowcolor=FG,
            bordercolor=BORDER,
            padding=4,
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=BG_INPUT,
            foreground=FG,
            background=BG_INPUT,
            arrowcolor=FG,
            bordercolor=BORDER,
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            foreground=[("readonly", FG)],
        )

        style.configure(
            "Results.Treeview",
            background=BG_ROW,
            foreground=FG,
            fieldbackground=BG_ROW,
            bordercolor=BORDER,
            rowheight=28,
            font=("Helvetica", 10),
        )
        style.configure(
            "Results.Treeview.Heading",
            background=BG_PANEL,
            foreground=FG,
            relief="flat",
            font=("Helvetica", 10, "bold"),
        )
        style.map(
            "Results.Treeview",
            background=[("selected", "#3a1218")],
            foreground=[("selected", FG)],
        )
        style.map("Results.Treeview.Heading", background=[("active", "#222")])

        self.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#fff")

    # --- layout ----------------------------------------------------------
    def _build_layout(self) -> None:
        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x", padx=18, pady=(14, 6))
        ttk.Label(header, text="TESLA", style="Accent.TLabel").pack(side="left")
        ttk.Label(header, text="  Vehicle Search", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Public inventory · best price first",
            style="TLabel",
        ).pack(side="right", padx=4)

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, padx=14, pady=6)

        filters = ttk.Frame(body, style="Panel.TFrame", padding=14)
        filters.pack(side="left", fill="y", padx=(0, 10))
        filters.configure(width=280)

        results_wrap = ttk.Frame(body, style="TFrame")
        results_wrap.pack(side="left", fill="both", expand=True)

        self._build_filters(filters)
        self._build_results(results_wrap)

        status_bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 8))
        status_bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="")
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

    def _build_filters(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="FILTERS", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Label(parent, text="ZIP code", style="Panel.TLabel").pack(anchor="w")
        zip_row = ttk.Frame(parent, style="Panel.TFrame")
        zip_row.pack(fill="x", pady=(2, 0))
        self.zip_var = tk.StringVar(value=DEFAULT_ZIP)
        ttk.Entry(zip_row, textvariable=self.zip_var, style="Dark.TEntry", width=12).pack(
            side="left", pady=4
        )
        ttk.Label(zip_row, text="  Search origin", style="Section.TLabel").pack(
            side="left", padx=(4, 0)
        )

        ttk.Separator(parent).pack(fill="x", pady=10)

        ttk.Label(parent, text="Models", style="Panel.TLabel").pack(anchor="w")
        self.model_vars: dict[str, tk.BooleanVar] = {}
        for name in MODEL_CODES:
            var = tk.BooleanVar(value=True)
            self.model_vars[name] = var
            ttk.Checkbutton(parent, text=name, variable=var, style="Dark.TCheckbutton").pack(
                anchor="w", pady=1
            )

        ttk.Separator(parent).pack(fill="x", pady=10)

        ttk.Label(parent, text="Condition", style="Panel.TLabel").pack(anchor="w")
        self.condition_var = tk.StringVar(value="both")
        for text, value in (("Both", "both"), ("New", "new"), ("Used", "used")):
            ttk.Radiobutton(
                parent, text=text, value=value, variable=self.condition_var, style="Dark.TRadiobutton"
            ).pack(anchor="w")

        ttk.Separator(parent).pack(fill="x", pady=10)

        ttk.Label(parent, text="Year range", style="Panel.TLabel").pack(anchor="w")
        year_row = ttk.Frame(parent, style="Panel.TFrame")
        year_row.pack(fill="x", pady=4)
        self.year_min_var = tk.StringVar(value=str(YEAR_LO_DEFAULT))
        self.year_max_var = tk.StringVar(value=str(YEAR_HI_DEFAULT))
        spin_lo = ttk.Spinbox(
            year_row,
            from_=2012,
            to=2035,
            textvariable=self.year_min_var,
            width=8,
            style="Dark.TSpinbox",
        )
        spin_hi = ttk.Spinbox(
            year_row,
            from_=2012,
            to=2035,
            textvariable=self.year_max_var,
            width=8,
            style="Dark.TSpinbox",
        )
        spin_lo.pack(side="left")
        ttk.Label(year_row, text="  to  ", style="Panel.TLabel").pack(side="left")
        spin_hi.pack(side="left")
        ttk.Label(
            parent,
            text="Narrowing years excludes cars with no Year.",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        ttk.Separator(parent).pack(fill="x", pady=10)

        ttk.Label(parent, text="Max distance", style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
        self.distance_var = tk.StringVar(value="Any / nationwide")
        combo = ttk.Combobox(
            parent,
            textvariable=self.distance_var,
            values=[label for label, _ in DISTANCE_CHOICES],
            state="readonly",
            style="Dark.TCombobox",
            width=20,
        )
        combo.pack(anchor="w", pady=4)

        ttk.Separator(parent).pack(fill="x", pady=12)

        self.search_btn = ttk.Button(
            parent, text="Search inventory", style="Accent.TButton", command=self.on_search
        )
        self.search_btn.pack(fill="x", pady=(0, 6))
        ttk.Button(parent, text="Clear results", style="Ghost.TButton", command=self.clear_results).pack(
            fill="x"
        )


    def _build_results(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="TFrame")
        top.pack(fill="x", pady=(0, 6))
        self.summary_var = tk.StringVar(value="No results yet")
        ttk.Label(top, textvariable=self.summary_var, style="TLabel").pack(side="left")

        columns = ("best", "price", "discount", "year", "model", "trim", "miles", "location", "distance", "vin")
        mid = ttk.Frame(parent, style="TFrame")
        mid.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            mid,
            columns=columns,
            show="headings",
            style="Results.Treeview",
            selectmode="browse",
        )
        headings = {
            "best": ("", 36),
            "price": ("Price", 90),
            "discount": ("Discount", 80),
            "year": ("Year", 60),
            "model": ("Model", 90),
            "trim": ("Trim", 180),
            "miles": ("Mileage", 90),
            "location": ("Location", 150),
            "distance": ("Dist mi", 70),
            "vin": ("VIN", 170),
        }
        for col, (label, width) in headings.items():
            self.tree.heading(col, text=label, command=lambda c=col: self.sort_by(c))
            anchor = "w" if col in ("trim", "location", "vin", "model") else "center"
            self.tree.column(col, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("best", foreground="#7dffb0")
        self.tree.tag_configure("odd", background=BG_ROW)
        self.tree.tag_configure("even", background=BG_ROW_ALT)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_row)
        self.tree.bind("<ButtonRelease-1>", self.on_open_listing)

        detail = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        detail.pack(fill="x", pady=(8, 0))
        self.detail_var = tk.StringVar(value="Select a vehicle for details.")
        ttk.Label(detail, text="DETAILS", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            detail,
            textvariable=self.detail_var,
            style="Panel.TLabel",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

    # --- actions ---------------------------------------------------------
    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _selected_models(self) -> list[str]:
        return [name for name, var in self.model_vars.items() if var.get()]

    def _distance_miles(self) -> Optional[int]:
        label = self.distance_var.get()
        for name, miles in DISTANCE_CHOICES:
            if name == label:
                return miles
        return None

    def _year_bounds(self) -> tuple[int, int, bool]:
        try:
            y_min = int(str(self.year_min_var.get()).strip())
            y_max = int(str(self.year_max_var.get()).strip())
        except ValueError as exc:
            raise InventoryError("Year min/max must be integers.") from exc
        if y_min > y_max:
            y_min, y_max = y_max, y_min
        # "Wide open" relative to defaults / full span
        filter_active = not (y_min <= YEAR_LO_DEFAULT and y_max >= YEAR_HI_DEFAULT)
        # Also treat very wide ranges as open
        if y_min <= 2012 and y_max >= datetime.now().year + 1:
            filter_active = False
        return y_min, y_max, filter_active

    def clear_results(self) -> None:
        self._vehicles = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.summary_var.set("No results yet")
        self.detail_var.set("Select a vehicle for details.")
        self._set_status("Results cleared.")

    def on_search(self) -> None:
        if self._search_thread and self._search_thread.is_alive():
            messagebox.showinfo(WINDOW_TITLE, "A search is already running.")
            return
        models = self._selected_models()
        if not models:
            messagebox.showwarning(WINDOW_TITLE, "Select at least one model.")
            return
        try:
            year_min, year_max, year_active = self._year_bounds()
        except InventoryError as exc:
            messagebox.showerror(WINDOW_TITLE, str(exc))
            return

        zip_code = self.zip_var.get().strip()
        max_miles = self._distance_miles()
        condition = self.condition_var.get()

        self.search_btn.state(["disabled"])
        self.clear_results()
        self._set_status("Searching…")
        self.summary_var.set("Searching Tesla inventory…")

        def worker() -> None:
            try:
                result = search_inventory(
                    models=models,
                    condition=condition,
                    zip_code=zip_code,
                    max_miles=max_miles,
                    year_min=year_min,
                    year_max=year_max,
                    year_filter_active=year_active,
                    progress=lambda msg: self.after(0, lambda m=msg: self._set_status(m)),
                )
                self.after(0, lambda: self._on_search_done(result, None))
            except Exception as exc:  # noqa: BLE001 — surface any failure in UI
                self.after(0, lambda: self._on_search_done(None, exc))

        self._search_thread = threading.Thread(target=worker, daemon=True)
        self._search_thread.start()

    def _on_search_done(self, result: Optional[SearchResult], error: Optional[BaseException]) -> None:
        self.search_btn.state(["!disabled"])
        if error is not None:
            self._set_status(f"Error: {error}")
            self.summary_var.set("Search failed")
            messagebox.showerror(WINDOW_TITLE, str(error))
            return
        assert result is not None
        self._vehicles = result.vehicles
        self._populate_tree()
        parts = [f"{len(result.vehicles)} vehicle(s)"]
        if result.truncated:
            parts.append("results truncated (per-model cap)")
        if result.errors:
            parts.append(f"{len(result.errors)} query warning(s)")
        self.summary_var.set(" · ".join(parts))
        status = f"Found {len(result.vehicles)} matching vehicle(s)."
        if result.truncated:
            status += " Some queries hit the paging cap — results may be incomplete."
        if result.errors:
            status += " " + "; ".join(result.errors[:2])
        self._set_status(status)
        if result.vehicles:
            best = result.vehicles[0]
            self.detail_var.set(self._format_detail(best, best_deal=True))

    def _populate_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        vehicles = list(self._vehicles)
        key_map = {
            "price": lambda v: (v.price is None, v.price or 0),
            "discount": lambda v: (v.discount is None, v.discount or 0),
            "year": lambda v: (v.year is None, v.year or 0),
            "distance": lambda v: (v.distance_miles is None, v.distance_miles or 0),
            "model": lambda v: v.model_name,
            "trim": lambda v: v.trim,
            "miles": lambda v: (v.odometer is None, v.odometer or 0),
            "location": lambda v: v.location,
            "vin": lambda v: v.vin,
            "best": lambda v: (0 if v.is_best_deal else 1, v.price or 0),
        }
        key = key_map.get(self._sort_column, key_map["price"])
        vehicles.sort(key=key, reverse=self._sort_reverse)
        for idx, v in enumerate(vehicles):
            tags = ["best" if v.is_best_deal else ("even" if idx % 2 == 0 else "odd")]
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "★" if v.is_best_deal else "",
                    self._fmt_money(v.price),
                    self._fmt_money(v.discount) if v.discount else "—",
                    v.year or "—",
                    v.model_name,
                    v.trim or "—",
                    self._fmt_miles(v),
                    v.location,
                    f"{v.distance_miles:.0f}" if v.distance_miles is not None else "—",
                    v.vin,
                ),
                tags=tags,
            )
        # keep mapping parallel to displayed order
        self._vehicles = vehicles

    def sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column in ("year", "discount")  # high first feels natural for these
            if column == "price":
                self._sort_reverse = False
        self._populate_tree()

    def on_select_row(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if 0 <= idx < len(self._vehicles):
            v = self._vehicles[idx]
            self.detail_var.set(self._format_detail(v, best_deal=v.is_best_deal))

    @staticmethod
    def _fmt_money(value: Optional[float]) -> str:
        if value is None:
            return "—"
        return f"${value:,.0f}"

    @staticmethod
    def _fmt_miles(v: Vehicle) -> str:
        if v.odometer is None:
            return "—"
        if (v.condition or "").lower() == "new" and v.odometer < 50:
            return f"{v.odometer:.0f} {v.odometer_unit}"
        return f"{v.odometer:,.0f} {v.odometer_unit}"

    def _format_detail(self, v: Vehicle, best_deal: bool = False) -> str:
        bits = []
        if best_deal:
            bits.append("BEST DEAL")
        bits.append(f"{v.year or '—'} {v.model_name} {v.trim}".strip())
        bits.append(f"Price {self._fmt_money(v.price)}")
        if v.discount:
            bits.append(f"Discount {self._fmt_money(v.discount)}")
        if v.list_price and v.price and v.list_price != v.price:
            bits.append(f"List {self._fmt_money(v.list_price)}")
        bits.append(v.condition.title())
        bits.append(self._fmt_miles(v))
        bits.append(v.location)
        if v.distance_miles is not None:
            bits.append(f"{v.distance_miles:.0f} mi away")
        if v.paint:
            bits.append(v.paint)
        if v.interior:
            bits.append(f"Interior {v.interior}")
        if v.transportation_fee:
            bits.append(f"Transport fee {self._fmt_money(v.transportation_fee)}")
        bits.append(f"VIN {v.vin}")
        url = listing_url(v)
        if url:
            bits.append(url)
        return "  ·  ".join(bits)

    def on_open_listing(self, event) -> None:
        """Open the official Tesla listing for the clicked result row."""
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        try:
            idx = int(row)
        except ValueError:
            return
        if not (0 <= idx < len(self._vehicles)):
            return
        vehicle = self._vehicles[idx]
        url = listing_url(vehicle)
        if not url:
            messagebox.showinfo(
                WINDOW_TITLE,
                "This result has no VIN, so the Tesla listing cannot be opened.",
            )
            return
        webbrowser.open(url)


    # --- Help menu -------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=ACCENT, activeforeground="#fff")
        help_menu = tk.Menu(menubar, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=ACCENT, activeforeground="#fff")
        help_menu.add_command(label="User guide", command=self.show_user_guide)
        help_menu.add_command(label="Check for updates", command=self.show_check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

    def show_about(self) -> None:
        win = tk.Toplevel(self)
        win.title(f"About — {APP_NAME}")
        win.configure(bg=BG_PANEL)
        win.transient(self)
        win.resizable(False, False)
        frame = ttk.Frame(win, style="Panel.TFrame", padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"Version {APP_VERSION}", style="Panel.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(
            frame,
            text=APP_DESCRIPTION,
            style="Panel.TLabel",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))
        ttk.Button(frame, text="Close", style="Ghost.TButton", command=win.destroy).pack(
            anchor="e", pady=(18, 0)
        )

    def show_user_guide(self) -> None:
        guide = (
            "Tesla Vehicle Search — User Guide\n"
            "================================\n\n"
            "What it does\n"
            "------------\n"
            "This app searches Tesla's public US inventory API and ranks matching "
            "vehicles by the lowest effective purchase price. The cheapest match "
            "is marked Best deal.\n\n"
            "Filters (set these, then click Search inventory)\n"
            "------------------------------------------------\n"
            "• Models — Multi-select Model 3, Model Y, Model S, Model X, and "
            "Cybertruck (default: all). Codes sent to Tesla: m3, my, ms, mx, ct.\n\n"
            "• Condition — New, Used, or Both (default Both). Both runs separate "
            "queries for new and used inventory.\n\n"
            "• Year — Min and max year spinboxes. When the range is left wide open, "
            "vehicles with no Year are kept. If you narrow the year range, cars "
            "with a missing Year or a Year outside the range are excluded.\n\n"
            "• ZIP code — At the top of the filter panel, above models, condition, "
            "and year. A labeled entry box titled \"ZIP code\" (default 90210, wide "
            "enough for 5 digits) with the hint \"Search origin\". That ZIP is the "
            "search origin. The app geocodes it via zippopotam.us to latitude/"
            "longitude for Tesla's API and for distance estimates.\n\n"
            "• Max distance — Choose a mile radius, or Any / nationwide to search "
            "across locations (large range + outsideSearch).\n\n"
            "Results\n"
            "-------\n"
            "• Sorted by effective price ascending (PurchasePrice when present).\n"
            "• Best deal highlights the cheapest priced match.\n"
            "• Columns: price, discount, year, model, trim, mileage, location, "
            "distance, VIN. Click a column header to sort. Click a row to open "
            "that car's Tesla listing in your browser (photos, price, and options). "
            "The detail strip still updates on selection.\n"
            "• Search runs on a background thread so the window stays responsive.\n\n"
            "Data source\n"
            "-----------\n"
            "Inventory comes from Tesla's public inventory endpoint "
            "(inventory/api/v4/inventory-results). Field availability and anti-bot "
            "rules can change. No Tesla account or secrets are used.\n\n"
            "Updates\n"
            "-------\n"
            "Help → Check for updates compares your stamped calendar version to "
            "app_release.json (GitHub raw when available, else the bundled file). "
            "It never downloads or installs anything automatically.\n"
        )
        win = tk.Toplevel(self)
        win.title("User guide — Tesla Vehicle Search")
        win.configure(bg=BG)
        win.geometry("640x520")
        win.transient(self)
        outer = ttk.Frame(win, style="TFrame", padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="USER GUIDE", style="Section.TLabel").pack(anchor="w")
        text_frame = ttk.Frame(outer, style="Panel.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(8, 0))
        scroll = ttk.Scrollbar(text_frame)
        scroll.pack(side="right", fill="y")
        box = tk.Text(
            text_frame,
            wrap="word",
            bg=BG_INPUT,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Helvetica", 11),
            yscrollcommand=scroll.set,
            padx=12,
            pady=12,
        )
        box.pack(side="left", fill="both", expand=True)
        scroll.config(command=box.yview)
        box.insert("1.0", guide)
        box.configure(state="disabled")
        ttk.Button(outer, text="Close", style="Ghost.TButton", command=win.destroy).pack(
            anchor="e", pady=(10, 0)
        )

    def show_check_updates(self) -> None:
        self._set_status("Checking for updates…")

        def worker() -> None:
            try:
                info = check_for_updates()
            except Exception as exc:  # noqa: BLE001
                info = {
                    "ok": False,
                    "newer": False,
                    "message": f"Update check failed:\n{exc}",
                }
            self.after(0, lambda: self._on_update_check_done(info))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_check_done(self, info: dict) -> None:
        newer = bool(info.get("newer"))
        ok = bool(info.get("ok"))
        msg = str(info.get("message") or "No update information.")
        if ok and newer:
            self._set_status(f"Update available: {info.get('latest')}")
            messagebox.showinfo("Check for updates", msg, parent=self)
        elif ok:
            self._set_status("You are up to date.")
            messagebox.showinfo("Check for updates", msg, parent=self)
        else:
            self._set_status("Update check could not read a release manifest.")
            messagebox.showwarning("Check for updates", msg, parent=self)



def main() -> None:
    app = TeslaSearchApp()
    app.mainloop()


if __name__ == "__main__":
    main()
