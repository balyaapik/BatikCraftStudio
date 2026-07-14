"""Keyboard helpers shared by global editor shortcuts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_TEXT_INPUT_CLASSES = frozenset(
    {
        "Entry",
        "TEntry",
        "Spinbox",
        "TSpinbox",
        "Text",
        "TCombobox",
        "Combobox",
    }
)


def event_targets_text_input(event: Any) -> bool:
    """Return whether a Tk event originated from a text-editing widget."""

    widget = getattr(event, "widget", None)
    if widget is None:
        return False
    try:
        widget_class = widget.winfo_class()
    except (AttributeError, TypeError):
        return False
    return str(widget_class) in _TEXT_INPUT_CLASSES


def run_single_key_shortcut(event: Any, command: Callable[[], object]) -> str | None:
    """Run a letter shortcut unless the user is typing into a text control."""

    if event_targets_text_input(event):
        return None
    command()
    return "break"


__all__ = ["event_targets_text_input", "run_single_key_shortcut"]
