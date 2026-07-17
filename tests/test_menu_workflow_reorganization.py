from __future__ import annotations

import inspect

import pytest

from batikcraft_studio import batikbrew_context_tool_app
from batikcraft_studio.ai.local_lora_training import LocalLoraTrainingConfig
from batikcraft_studio.ui import dependency_manager_dialog, enhanced_humanize_dialog
from batikcraft_studio.ui.marketplace_mint_dialog import MintCurrentProjectDialog


def test_top_level_menus_are_separated_by_workflow() -> None:
    source = inspect.getsource(batikbrew_context_tool_app.ContextToolApplication._build_menu)

    assert '_insert_before_help(menu_bar, "Effects"' in source
    assert '_insert_before_help(menu_bar, "Dependencies"' in source
    assert '_insert_before_help(menu_bar, "Marketplace"' in source
    assert '_insert_before_help(menu_bar, "Training AI Lokal"' in source
    assert "Mint & Publish Project Aktif sebagai NFT" in source
    assert "Train LoRA di Komputer Ini" in source


def test_file_export_removes_nft_package_command() -> None:
    source = inspect.getsource(
        batikbrew_context_tool_app.ContextToolApplication._remove_nft_export_from_file
    )
    assert '"nft" in label.casefold()' in source


def test_marketplace_is_not_added_to_ai_batik_menu() -> None:
    source = inspect.getsource(batikbrew_context_tool_app.ContextToolApplication._build_menu)
    marketplace_start = source.index("marketplace_menu =")
    ai_start = source.index("_ai_index, ai_menu")
    assert marketplace_start > ai_start
    assert "ai_menu.add_command" not in source[ai_start:marketplace_start]


def test_humanize_has_complete_presets() -> None:
    presets = enhanced_humanize_dialog.HUMANIZE_PRESETS
    assert set(presets) == {"subtle", "canting", "expressive", "vintage"}
    assert presets["canting"].edge_wobble > presets["subtle"].edge_wobble
    assert presets["vintage"].ink_breaks > presets["canting"].ink_breaks


def test_dependency_manager_covers_training_and_lora_runtime() -> None:
    requirements = {
        requirement
        for _module, requirement in dependency_manager_dialog.PYTHON_AI_DEPENDENCIES
    }
    assert any(value.startswith("torch") for value in requirements)
    assert any(value.startswith("diffusers") for value in requirements)
    assert any(value.startswith("peft") for value in requirements)
    source = inspect.getsource(dependency_manager_dialog.DependencyManagerWindow)
    assert "Instal / Kelola LoRA" in source
    assert "BatikBrew SDXL" in source


def test_local_training_config_rejects_missing_dataset(tmp_path) -> None:
    config = LocalLoraTrainingConfig(
        dataset_path=str(tmp_path / "missing.batikdataset"),
        base_model="sdxl-base",
        output_dir=str(tmp_path),
        model_name="Ornament",
        model_id="ornament-v1",
    )
    with pytest.raises(ValueError, match="Dataset tidak ditemukan"):
        config.validate()


def test_minting_uses_current_project_without_manual_package_export() -> None:
    source = inspect.getsource(MintCurrentProjectDialog._mint)
    assert "TemporaryDirectory" in source
    assert "export_batikcraft_nft" in source
    assert "publish_nft_package" in source
    assert "asksaveasfilename" not in source
