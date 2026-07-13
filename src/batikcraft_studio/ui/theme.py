"""Visual theme configuration for the native Tkinter application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS: dict[str, str] = {
    "ink": "#211A17",
    "muted_ink": "#6E625B",
    "canvas": "#F3EFE7",
    "surface": "#FFFDF8",
    "surface_alt": "#E9E1D4",
    "sidebar": "#2D2926",
    "sidebar_hover": "#403A36",
    "sidebar_active": "#B97745",
    "accent": "#A85F32",
    "accent_dark": "#7D4326",
    "accent_soft": "#E8C7A8",
    "line": "#D9D0C3",
    "success": "#46654B",
    "warning": "#9A6B27",
    "white": "#FFFFFF",
}


def configure_theme(root: tk.Tk) -> ttk.Style:
    """Configure a restrained, unisex earth-tone theme and return its style."""

    root.configure(background=COLORS["canvas"])
    style = ttk.Style(root)

    # ``clam`` supports background and border styling more consistently across
    # Windows, Linux, and macOS than most platform-native ttk themes.
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(
        ".",
        background=COLORS["canvas"],
        foreground=COLORS["ink"],
        font=("Segoe UI", 10),
    )
    style.configure("App.TFrame", background=COLORS["canvas"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Sidebar.TFrame", background=COLORS["sidebar"])

    style.configure(
        "Brand.TLabel",
        background=COLORS["sidebar"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 18),
    )
    style.configure(
        "BrandMeta.TLabel",
        background=COLORS["sidebar"],
        foreground="#CFC3B8",
        font=("Segoe UI", 9),
    )
    style.configure(
        "Eyebrow.TLabel",
        background=COLORS["canvas"],
        foreground=COLORS["accent_dark"],
        font=("Segoe UI Semibold", 9),
    )
    style.configure(
        "Title.TLabel",
        background=COLORS["canvas"],
        foreground=COLORS["ink"],
        font=("Segoe UI Semibold", 25),
    )
    style.configure(
        "Description.TLabel",
        background=COLORS["canvas"],
        foreground=COLORS["muted_ink"],
        font=("Segoe UI", 11),
    )
    style.configure(
        "CardTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        font=("Segoe UI Semibold", 13),
    )
    style.configure(
        "CardText.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted_ink"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Status.TLabel",
        background=COLORS["surface_alt"],
        foreground=COLORS["muted_ink"],
        padding=(14, 7),
        font=("Segoe UI", 9),
    )

    style.configure(
        "Nav.TButton",
        anchor="w",
        background=COLORS["sidebar"],
        foreground="#E7DED5",
        borderwidth=0,
        padding=(16, 12),
        font=("Segoe UI", 10),
    )
    style.map(
        "Nav.TButton",
        background=[("active", COLORS["sidebar_hover"])],
        foreground=[("active", COLORS["white"])],
    )
    style.configure(
        "NavActive.TButton",
        anchor="w",
        background=COLORS["sidebar_active"],
        foreground=COLORS["white"],
        borderwidth=0,
        padding=(16, 12),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "NavActive.TButton",
        background=[("active", COLORS["sidebar_active"])],
        foreground=[("active", COLORS["white"])],
    )

    style.configure(
        "Primary.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        borderwidth=0,
        padding=(16, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLORS["accent_dark"]), ("disabled", COLORS["line"])],
        foreground=[("disabled", COLORS["muted_ink"])],
    )
    style.configure(
        "Secondary.TButton",
        background=COLORS["surface"],
        foreground=COLORS["ink"],
        bordercolor=COLORS["line"],
        borderwidth=1,
        padding=(16, 10),
        font=("Segoe UI Semibold", 10),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", COLORS["surface_alt"])],
    )

    return style
