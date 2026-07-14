from __future__ import annotations

from dataclasses import dataclass

import pytest

from batikcraft_studio.app import BatikCraftApplication
from batikcraft_studio.i18n import category_label, current_language, set_language, tr
from batikcraft_studio.ui.keyboard import event_targets_text_input, run_single_key_shortcut


@dataclass
class _Widget:
    widget_class: str

    def winfo_class(self) -> str:
        return self.widget_class


@dataclass
class _Event:
    widget: _Widget


@pytest.mark.parametrize(
    "widget_class",
    ["Entry", "TEntry", "Spinbox", "TSpinbox", "Text", "TCombobox", "Combobox"],
)
def test_single_key_shortcuts_do_not_run_while_typing(widget_class: str) -> None:
    calls: list[str] = []
    event = _Event(_Widget(widget_class))

    result = run_single_key_shortcut(event, lambda: calls.append("opened"))

    assert result is None
    assert calls == []
    assert event_targets_text_input(event)


def test_single_key_shortcut_runs_from_canvas() -> None:
    calls: list[str] = []
    event = _Event(_Widget("Canvas"))

    result = run_single_key_shortcut(event, lambda: calls.append("opened"))

    assert result == "break"
    assert calls == ["opened"]
    assert not event_targets_text_input(event)


def test_global_control_and_delete_shortcuts_do_not_run_in_text_fields() -> None:
    calls: list[str] = []

    result = BatikCraftApplication._run_shortcut(
        _Event(_Widget("TEntry")),  # type: ignore[arg-type]
        lambda: calls.append("changed-canvas"),
    )

    assert result is None
    assert calls == []


def test_global_shortcuts_still_run_from_canvas() -> None:
    calls: list[str] = []

    result = BatikCraftApplication._run_shortcut(
        _Event(_Widget("Canvas")),  # type: ignore[arg-type]
        lambda: calls.append("saved"),
    )

    assert result == "break"
    assert calls == ["saved"]


def test_indonesian_and_english_catalogs_format_messages() -> None:
    original = current_language()
    try:
        set_language("id")
        assert tr("file.new_project") == "Proyek Baru"
        assert category_label("motif-pokok") == "Motif Pokok"
        assert tr("status.project_created", title="Merapi") == "Proyek dibuat: Merapi"

        set_language("en")
        assert tr("file.new_project") == "New Project"
        assert category_label("motif-pokok") == "Main Motif"
        assert tr("status.project_created", title="Merapi") == "Created project: Merapi"
    finally:
        set_language(original)


def test_language_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="Unsupported language"):
        set_language("fr")
