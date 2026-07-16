from __future__ import annotations

import tkinter as tk

import pytest

from batikcraft_studio.context_tool_app import _find_cascade_menu


class _FakeMenu:
    def __init__(self) -> None:
        self.entries = [
            ("cascade", "File", "file-menu"),
            ("cascade", "Edit", "edit-menu"),
            ("cascade", "AI Batik", "ai-menu"),
            ("cascade", "Produksi", "production-menu"),
        ]
        self.children = {name: object() for _, _, name in self.entries}

    def index(self, value: str) -> int:
        assert value == tk.END
        return len(self.entries) - 1

    def type(self, index: int) -> str:
        return self.entries[index][0]

    def entrycget(self, index: int, option: str) -> str:
        _, label, child = self.entries[index]
        return label if option == "label" else child

    def nametowidget(self, name: str) -> object:
        return self.children[name]


def test_find_ai_menu_by_label_instead_of_fixed_position() -> None:
    menu = _FakeMenu()

    index, child = _find_cascade_menu(menu, "AI", "AI Batik")  # type: ignore[arg-type]

    assert index == 2
    assert child is menu.children["ai-menu"]


def test_find_ai_menu_reports_missing_cascade() -> None:
    menu = _FakeMenu()

    with pytest.raises(RuntimeError, match="AI Batik"):
        _find_cascade_menu(menu, "AI")  # type: ignore[arg-type]
