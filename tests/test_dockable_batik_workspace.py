from __future__ import annotations

import re

from batikcraft_studio.i18n import current_language, set_language, tr
from batikcraft_studio.ui.compact_asset_editor import (
    _BATIK_PALETTE,
    CompactAssetEditorWorkspaceView,
)
from batikcraft_studio.ui.dockable_panel import DockablePanel
from batikcraft_studio.workspace_translations import install_workspace_translations


def test_batik_palette_has_many_unique_valid_colors() -> None:
    assert len(_BATIK_PALETTE) >= 30
    assert len(_BATIK_PALETTE) == len(set(_BATIK_PALETTE))
    assert all(re.fullmatch(r"#[0-9A-F]{6}", color) for color in _BATIK_PALETTE)


def test_workspace_translation_extension_is_bilingual() -> None:
    original = current_language()
    try:
        install_workspace_translations()
        set_language("id")
        assert tr("dock.tools") == "Peralatan Batik"
        assert tr("toolbox.canting") == "Canting Lilin"
        assert tr("palette.custom") == "Warna Lain…"

        set_language("en")
        assert tr("dock.tools") == "Batik Tools"
        assert tr("toolbox.canting") == "Wax Canting"
        assert tr("palette.custom") == "More Colors…"
    finally:
        set_language(original)


def test_workspace_exposes_all_dock_and_tool_commands() -> None:
    for method_name in (
        "toggle_tools_panel",
        "toggle_asset_panel",
        "toggle_layers_panel",
        "dock_all_panels",
        "activate_canting_tool",
        "activate_soft_brush_tool",
        "activate_pencil_tool",
        "swap_palette_colors",
        "reset_palette_colors",
    ):
        assert callable(getattr(CompactAssetEditorWorkspaceView, method_name))


def test_dockable_panel_contract_has_reversible_actions() -> None:
    assert callable(DockablePanel.dock)
    assert callable(DockablePanel.undock)
    assert callable(DockablePanel.toggle)
    assert callable(DockablePanel.close)
