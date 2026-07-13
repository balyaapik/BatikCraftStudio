"""Reusable native UI helpers."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .icons import create_icon
from .tooltip import ToolTip


def icon_button(
    parent: tk.Misc,
    *,
    icon: str,
    tooltip: str,
    command: Callable[[], object],
    style: str = "Tool.TButton",
    size: int = 20,
) -> ttk.Button:
    """Create an icon-only ttk button and keep its image alive."""

    image = create_icon(parent, icon, size=size)
    button = ttk.Button(parent, image=image, command=command, style=style, takefocus=True)
    button.image = image  # type: ignore[attr-defined]
    ToolTip(button, tooltip)
    return button
