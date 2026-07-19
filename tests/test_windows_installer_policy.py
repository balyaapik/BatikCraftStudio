from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_policy_module() -> ModuleType:
    path = ROOT / "scripts" / "windows_installer_policy.py"
    spec = importlib.util.spec_from_file_location("windows_installer_policy", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_installer_defaults_to_program_files() -> None:
    module = _load_policy_module()
    script = module.build_inno_setup_script(
        app_name="BatikCraftStudio",
        display_name="BatikCraft Studio",
        app_id="{{00000000-0000-0000-0000-000000000000}}",
        architecture="x64",
        source_executable=Path("C:/build/BatikCraftStudio.exe"),
        output_directory=Path("C:/release"),
        icon_path=Path("C:/build/logo.ico"),
        version="0.3.0",
    )

    assert "DefaultDirName={autopf}\\BatikCraft Studio" in script
    assert "DefaultDirName={localappdata}" not in script
    assert "PrivilegesRequired=admin" in script
    assert "UsePreviousAppDir=no" in script
    assert "AppVerName=BatikCraft Studio v0.3.0" in script
    assert "OutputBaseFilename=BatikCraftStudio-v0.3.0-Setup-Windows-x64" in script


def test_only_dependencies_directory_is_user_writable() -> None:
    module = _load_policy_module()
    script = module.build_inno_setup_script(
        app_name="BatikCraftStudio",
        display_name="BatikCraft Studio",
        app_id="{{00000000-0000-0000-0000-000000000000}}",
        architecture="x64",
        source_executable=Path("C:/build/BatikCraftStudio.exe"),
        output_directory=Path("C:/release"),
        icon_path=Path("C:/build/logo.ico"),
        version="0.3.0",
    )

    assert '[Dirs]\nName: "{app}\\dependencies"; Permissions: users-modify' in script
    assert 'Type: filesandordirs; Name: "{app}\\dependencies"' in script
    assert 'Permissions: users-modify' in script
    assert 'Name: "{app}"; Permissions:' not in script


def test_workflow_uses_policy_aware_installer_entrypoint() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "python scripts/build_installer.py" in workflow
    assert '"scripts/windows_installer_policy.py"' in workflow
