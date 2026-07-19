from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from batikcraft_studio.config import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _load_installer_module() -> ModuleType:
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        path = scripts / "build_installer.py"
        spec = importlib.util.spec_from_file_location("batikcraft_build_installer", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts))


def test_all_public_installer_names_include_release_version() -> None:
    module = _load_installer_module()
    filenames = (
        "BatikCraftStudio-Setup-Windows-x64.exe",
        "BatikCraftStudio-Installer-Linux-x64.deb",
        "BatikCraftStudio-Installer-macOS-x64.dmg",
        "BatikCraftStudio-Installer-macOS-arm64.dmg",
    )

    versioned = [
        module._versioned_artifact_path(Path(name), version=APP_VERSION).name
        for name in filenames
    ]

    assert versioned == [
        f"BatikCraftStudio-v{APP_VERSION}-Setup-Windows-x64.exe",
        f"BatikCraftStudio-v{APP_VERSION}-Installer-Linux-x64.deb",
        f"BatikCraftStudio-v{APP_VERSION}-Installer-macOS-x64.dmg",
        f"BatikCraftStudio-v{APP_VERSION}-Installer-macOS-arm64.dmg",
    ]


def test_versioned_installer_name_is_idempotent() -> None:
    module = _load_installer_module()
    artifact = Path(f"BatikCraftStudio-v{APP_VERSION}-Setup-Windows-x64.exe")

    assert module._versioned_artifact_path(artifact, version=APP_VERSION) == artifact
