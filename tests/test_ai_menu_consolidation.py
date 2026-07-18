from __future__ import annotations

import inspect
import tkinter as tk
from pathlib import Path

import pytest

from batikcraft_studio.context_tool_app import _find_cascade_menu
from batikcraft_studio.ui import ai_menu_consolidation_patch

ROOT = Path(__file__).resolve().parents[1]


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


def test_find_menu_reports_expected_labels_when_missing() -> None:
    menu = _FakeMenu()

    with pytest.raises(RuntimeError, match="Menu tidak ditemukan: AI"):
        _find_cascade_menu(menu, "AI")  # type: ignore[arg-type]


def test_ai_menu_patch_moves_every_ai_top_level_menu() -> None:
    source = inspect.getsource(ai_menu_consolidation_patch)

    assert '("Dependencies", "Runtime & Dependencies")' in source
    assert '("Training AI Lokal", "Training LoRA Lokal")' in source
    assert '("Settings", "Pengaturan AI")' in source
    assert 'entryconfigure(ai_index, label="AI")' in source


def test_ai_menu_removes_duplicate_dependency_manager_action() -> None:
    source = inspect.getsource(ai_menu_consolidation_patch)

    assert '"Kelola Paket AI…"' in source
    assert '"Instal / Reparasi Python AI Packages…"' in source
    assert "_delete_command" in source


def test_startup_installs_profile_and_menu_patches() -> None:
    source = (ROOT / "src" / "batikcraft_studio" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert "install_dependency_profiles_patch()" in source
    assert "install_ai_menu_consolidation(ContextToolApplication)" in source
    assert source.index("install_model_connectivity_settings_patch()") < source.index(
        "install_dependency_profiles_patch()"
    )
