"""Visual theme configuration for the native Tkinter application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS: dict[str, str] = {
    "ink": "#242424",
    "muted_ink": "#666666",
    "canvas": "#D5D5D5",
    "surface": "#F3F3F3",
    "surface_alt": "#E7E7E7",
    "toolbar": "#ECECEC",
    "rail": "#383838",
    "rail_hover": "#4A4A4A",
    "rail_active": "#A85F32",
    "accent": "#A85F32",
    "accent_dark": "#7D4326",
    "accent_soft": "#E8C7A8",
    "line": "#BDBDBD",
    "line_dark": "#8F8F8F",
    "success": "#46654B",
    "warning": "#9A6B27",
    "white": "#FFFFFF",
}


def configure_theme(root: tk.Tk) -> ttk.Style:
    """Configure a compact editor-style theme using native ttk widgets."""

    root.configure(background=COLORS["surface_alt"])
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(
        ".",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=("Segoe UI", 9),
        bordercolor=COLORS["line"],
        lightcolor=COLORS["surface"],
        darkcolor=COLORS["line_dark"],
    )
    style.configure("App.TFrame", background=COLORS["surface_alt"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Toolbar.TFrame", background=COLORS["toolbar"])
    style.configure("Rail.TFrame", background=COLORS["rail"])
    style.configure("Dock.TFrame", background=COLORS["surface"])

    style.configure(
        "ProjectTitle.TLabel",
        background=COLORS["toolbar"],
        foreground=COLORS["ink"],
        font=("Segoe UI Semibold", 9),
    )
    style.configure(
        "ProjectMeta.TLabel",
        background=COLORS["toolbar"],
        foreground=COLORS["muted_ink"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "ProjectPath.TLabel",
        background=COLORS["toolbar"],
        foreground=COLORS["muted_ink"],
        font=("Segoe UI", 8),
    )
    style.configure(
        "PanelTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=("Segoe UI Semibold", 9),
        padding=(6, 5),
    )
    style.configure(
        "Muted.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted_ink"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Status.TLabel",
        background=COLORS["toolbar"],
        foreground=COLORS["muted_ink"],
        padding=(8, 3),
        font=("Segoe UI", 8),
    )

    style.configure(
        "Tool.TButton",
        background=COLORS["toolbar"],
        foreground=COLORS["ink"],
        borderwidth=1,
        relief="flat",
        padding=5,
        width=2,
    )
    style.map(
        "Tool.TButton",
        background=[("pressed", COLORS["accent_soft"]), ("active", "#DADADA")],
        relief=[("pressed", "sunken")],
    )
    style.configure(
        "ToolActive.TButton",
        background=COLORS["accent_soft"],
        foreground=COLORS["ink"],
        borderwidth=1,
        relief="sunken",
        padding=5,
        width=2,
    )
    style.map("ToolActive.TButton", background=[("active", COLORS["accent_soft"])])

    style.configure(
        "Rail.TButton",
        background=COLORS["rail"],
        foreground=COLORS["white"],
        borderwidth=0,
        relief="flat",
        padding=8,
        width=2,
    )
    style.map("Rail.TButton", background=[("active", COLORS["rail_hover"])])
    style.configure(
        "RailActive.TButton",
        background=COLORS["rail_active"],
        foreground=COLORS["white"],
        borderwidth=0,
        relief="flat",
        padding=8,
        width=2,
    )
    style.map("RailActive.TButton", background=[("active", COLORS["rail_active"])])

    style.configure(
        "Primary.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        borderwidth=1,
        padding=(10, 5),
        font=("Segoe UI Semibold", 9),
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLORS["accent_dark"]), ("disabled", COLORS["line"])],
        foreground=[("disabled", COLORS["muted_ink"])],
    )
    style.configure(
        "Secondary.TButton",
        background=COLORS["toolbar"],
        foreground=COLORS["ink"],
        borderwidth=1,
        padding=(9, 5),
        font=("Segoe UI", 9),
    )
    style.map("Secondary.TButton", background=[("active", "#DADADA")])

    style.configure("TNotebook", background=COLORS["surface"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=COLORS["toolbar"],
        foreground=COLORS["ink"],
        padding=(12, 5),
        font=("Segoe UI", 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["surface"]), ("active", "#DDDDDD")],
        font=[("selected", ("Segoe UI Semibold", 9))],
    )
    style.configure("TLabelframe", background=COLORS["surface"], bordercolor=COLORS["line"])
    style.configure("TLabelframe.Label", background=COLORS["surface"], font=("Segoe UI", 9))
    style.configure("TEntry", fieldbackground=COLORS["white"], padding=3)

    return style
