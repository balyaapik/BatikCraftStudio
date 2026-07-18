from __future__ import annotations

import inspect
from typing import Any

from batikcraft_studio import __main__
from batikcraft_studio.ai.model_connectivity import (
    OFFLINE_ENVIRONMENT_NAMES,
    apply_model_connectivity,
    set_model_online,
)
from batikcraft_studio.ai.runtime_settings import AIRuntimeSettings
from batikcraft_studio.ui import model_connectivity_settings_patch


class _Store:
    def __init__(self, settings: AIRuntimeSettings) -> None:
        self.settings = settings
        self.saved: AIRuntimeSettings | None = None

    def load(self) -> AIRuntimeSettings:
        return self.settings

    def save(self, settings: AIRuntimeSettings) -> None:
        self.settings = settings
        self.saved = settings


def test_online_mode_clears_all_inherited_offline_environment() -> None:
    environment = {name: "1" for name in OFFLINE_ENVIRONMENT_NAMES}

    online = apply_model_connectivity(
        AIRuntimeSettings(local_files_only=False),
        environ=environment,
    )

    assert online is True
    assert all(name not in environment for name in OFFLINE_ENVIRONMENT_NAMES)


def test_offline_mode_sets_all_provider_environment_flags() -> None:
    environment: dict[str, str] = {}

    online = apply_model_connectivity(
        AIRuntimeSettings(local_files_only=True),
        environ=environment,
    )

    assert online is False
    assert environment == {name: "1" for name in OFFLINE_ENVIRONMENT_NAMES}


def test_menu_toggle_persists_the_user_visible_connection_mode(monkeypatch: Any) -> None:
    store = _Store(AIRuntimeSettings(local_files_only=True))
    environment: dict[str, str] = {}
    monkeypatch.setattr(
        "batikcraft_studio.ai.model_connectivity.os.environ",
        environment,
    )

    updated = set_model_online(True, store)  # type: ignore[arg-type]

    assert store.saved is not None
    assert updated.local_files_only is False
    assert environment == {}


def test_settings_patch_exposes_online_download_control() -> None:
    source = inspect.getsource(
        model_connectivity_settings_patch.install_model_connectivity_settings_patch
    )
    module_source = inspect.getsource(model_connectivity_settings_patch)

    assert "_patch_runtime_dialog" in source
    assert "_patch_application_menu" in source
    assert "Izinkan Download & Reparasi Model (Online)" in module_source
    assert "insert_checkbutton" in module_source


def test_connectivity_is_applied_before_sdxl_repair_on_startup() -> None:
    source = inspect.getsource(__main__.main)

    assert source.index("apply_saved_model_connectivity()") < source.index(
        "install_sdxl_text_component_repair()"
    )
    assert source.index("install_sdxl_runtime_integrity()") < source.index(
        "install_sdxl_online_component_repair()"
    )
