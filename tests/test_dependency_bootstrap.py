from __future__ import annotations

import inspect
from pathlib import Path

from batikcraft_studio import dependency_bootstrap
from batikcraft_studio.ui import dependency_manager_dialog

ROOT = Path(__file__).resolve().parents[1]


def test_managed_ai_package_dir_uses_local_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert dependency_bootstrap.default_managed_ai_package_dir() == (
        tmp_path / "BatikCraftStudio" / "ai-runtime" / "site-packages"
    )


def test_frozen_install_command_relaunches_same_executable_with_private_flag(
    tmp_path: Path,
) -> None:
    target = tmp_path / "packages"
    log_file = tmp_path / "install.log"

    command = dependency_bootstrap.managed_ai_install_command(
        ["torch>=2.4", "diffusers>=0.39,<0.40"],
        target=target,
        executable="BatikCraftStudio.exe",
        frozen=True,
        log_file=log_file,
    )

    assert command[0] == "BatikCraftStudio.exe"
    assert command[1] == dependency_bootstrap.INSTALL_FLAG
    assert command[command.index("--target") + 1] == str(target.resolve())
    assert command[command.index("--log-file") + 1] == str(log_file.resolve())
    assert "-m" not in command
    assert "pip" not in command
    assert command[-2:] == ["torch>=2.4", "diffusers>=0.39,<0.40"]


def test_source_install_command_uses_python_pip_with_app_local_target(tmp_path: Path) -> None:
    target = tmp_path / "packages"

    command = dependency_bootstrap.managed_ai_install_command(
        ["peft>=0.17"],
        target=target,
        executable="python",
        frozen=False,
    )

    assert command[:4] == ["python", "-m", "pip", "install"]
    assert command[command.index("--target") + 1] == str(target.resolve())
    assert command[-1] == "peft>=0.17"


def test_hidden_installer_dispatches_to_bundled_pip(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path]] = []

    def fake_install(requirements: list[str], *, target: Path) -> int:
        calls.append((requirements, target))
        return 7

    monkeypatch.setattr(dependency_bootstrap, "run_bundled_pip_install", fake_install)
    target = tmp_path / "runtime"

    code = dependency_bootstrap.maybe_run_dependency_installer(
        [
            dependency_bootstrap.INSTALL_FLAG,
            "--target",
            str(target),
            "--",
            "torch>=2.4",
            "diffusers>=0.39,<0.40",
        ]
    )

    assert code == 7
    assert calls == [(["torch>=2.4", "diffusers>=0.39,<0.40"], target.resolve())]


def test_desktop_entry_handles_installer_before_importing_application() -> None:
    source = (ROOT / "packaging" / "desktop_entry.py").read_text(encoding="utf-8")

    assert source.index("maybe_run_dependency_installer") < source.index(
        "from batikcraft_studio.__main__ import main"
    )


def test_dependency_gui_has_one_click_setup_without_terminal_instruction() -> None:
    source = inspect.getsource(dependency_manager_dialog.DependencyManagerWindow)

    assert "Instal Semua AI + BatikBrew SDXL" in source
    assert "managed_ai_install_command" in source
    assert "terminal tidak diperlukan" in source
    assert 'pip install -e ".[ai]"' not in source


def test_desktop_build_bundles_bootstrap_and_model_downloader() -> None:
    build_script = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"--collect-all",\n            "pip"' in build_script
    assert '"--collect-all",\n            "huggingface_hub"' in build_script
    assert '"pip>=24,<26"' in pyproject
    assert '"huggingface-hub>=0.27"' in pyproject
    assert '"--exclude-module",\n            "torch"' in build_script


def test_main_activates_managed_packages_before_application_import() -> None:
    source = (ROOT / "src" / "batikcraft_studio" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert source.index("activate_managed_ai_packages()") < source.index(
        "from .integrated_market_app import ContextToolApplication"
    )
