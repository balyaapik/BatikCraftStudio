from __future__ import annotations

import inspect
from pathlib import Path

from batikcraft_studio import dependency_bootstrap
from batikcraft_studio.ui import dependency_manager_dialog

ROOT = Path(__file__).resolve().parents[1]


def test_managed_dependencies_support_explicit_install_location(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dependency_root = tmp_path / "BatikCraft Studio" / "dependencies"
    monkeypatch.setenv(
        dependency_bootstrap.DEPENDENCIES_DIR_ENV,
        str(dependency_root),
    )

    assert dependency_bootstrap.default_managed_dependency_root() == dependency_root
    assert dependency_bootstrap.default_managed_ai_package_dir() == (
        dependency_root / "python" / "site-packages"
    )
    assert dependency_bootstrap.default_managed_pip_cache_dir() == (
        dependency_root / "cache" / "pip"
    )
    assert dependency_bootstrap.default_managed_dependency_log() == (
        dependency_root / "logs" / "dependency-install.log"
    )


def test_frozen_install_command_relaunches_same_executable_with_private_flag(
    tmp_path: Path,
) -> None:
    target = tmp_path / "packages"
    cache_dir = tmp_path / "cache"
    log_file = tmp_path / "install.log"

    command = dependency_bootstrap.managed_ai_install_command(
        ["torch>=2.4", "diffusers>=0.39,<0.40"],
        target=target,
        cache_dir=cache_dir,
        executable="BatikCraftStudio.exe",
        frozen=True,
        log_file=log_file,
    )

    assert command[0] == "BatikCraftStudio.exe"
    assert command[1] == dependency_bootstrap.INSTALL_FLAG
    assert command[command.index("--target") + 1] == str(target.resolve())
    assert command[command.index("--cache-dir") + 1] == str(cache_dir.resolve())
    assert command[command.index("--log-file") + 1] == str(log_file.resolve())
    assert "-m" not in command
    assert "pip" not in command
    assert command[-2:] == ["torch>=2.4", "diffusers>=0.39,<0.40"]


def test_source_install_command_uses_python_pip_with_app_local_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "packages"
    cache_dir = tmp_path / "cache"

    command = dependency_bootstrap.managed_ai_install_command(
        ["peft>=0.17"],
        target=target,
        cache_dir=cache_dir,
        executable="python",
        frozen=False,
    )

    assert command[:4] == ["python", "-m", "pip", "install"]
    assert command[command.index("--target") + 1] == str(target.resolve())
    assert command[command.index("--cache-dir") + 1] == str(cache_dir.resolve())
    assert command[command.index("--progress-bar") + 1] == "raw"
    assert command[-1] == "peft>=0.17"


def test_hidden_installer_dispatches_to_bundled_pip(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path, Path]] = []

    def fake_install(
        requirements: list[str],
        *,
        target: Path,
        cache_dir: Path,
    ) -> int:
        calls.append((requirements, target, cache_dir))
        return 7

    monkeypatch.setattr(dependency_bootstrap, "run_bundled_pip_install", fake_install)
    target = tmp_path / "runtime"
    cache_dir = tmp_path / "cache"

    code = dependency_bootstrap.maybe_run_dependency_installer(
        [
            dependency_bootstrap.INSTALL_FLAG,
            "--target",
            str(target),
            "--cache-dir",
            str(cache_dir),
            "--",
            "torch>=2.4",
            "diffusers>=0.39,<0.40",
        ]
    )

    assert code == 7
    assert calls == [
        (
            ["torch>=2.4", "diffusers>=0.39,<0.40"],
            target.resolve(),
            cache_dir.resolve(),
        )
    ]


def test_distlib_registers_the_current_loader_as_a_resource_finder(monkeypatch) -> None:
    import pip._vendor.distlib as distlib_package
    from pip._vendor.distlib import resources as distlib_resources

    loader = distlib_package.__loader__
    assert loader is not None
    loader_type = type(loader)
    monkeypatch.delitem(distlib_resources._finder_registry, loader_type, raising=False)

    dependency_bootstrap._register_distlib_frozen_resource_finder()

    assert (
        distlib_resources._finder_registry[loader_type]
        is distlib_resources.ResourceFinder
    )


def test_bundled_pip_registers_distlib_before_importing_pip_main() -> None:
    source = inspect.getsource(dependency_bootstrap.run_bundled_pip_install)

    assert source.index("_register_distlib_frozen_resource_finder()") < source.index(
        "from pip._internal.cli.main import main as pip_main"
    )


def test_desktop_entry_handles_installer_before_importing_application() -> None:
    source = (ROOT / "packaging" / "desktop_entry.py").read_text(encoding="utf-8")

    assert source.index("maybe_run_dependency_installer") < source.index(
        "from batikcraft_studio.__main__ import main"
    )


def test_dependency_gui_has_one_click_setup_and_real_process_cancellation() -> None:
    source = inspect.getsource(dependency_manager_dialog.DependencyManagerWindow)

    assert "Instal Semua AI + BatikBrew SDXL" in source
    assert "managed_ai_install_command" in source
    assert "tanpa jendela terminal" in source
    assert "Buka Folder Dependencies" in source
    assert "CREATE_NEW_PROCESS_GROUP" in source
    assert '"taskkill"' in source
    assert 'pip install -e ".[ai]"' not in source


def test_desktop_build_bundles_bootstrap_and_model_downloader() -> None:
    build_script = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"--collect-all",\n            "pip"' in build_script
    assert '"--collect-all",\n            "huggingface_hub"' in build_script
    assert '"pip>=24,<26"' in pyproject
    assert '"huggingface-hub>=0.34,<1"' in pyproject
    assert '"--exclude-module",\n            "torch"' in build_script


def test_main_activates_managed_packages_before_application_import() -> None:
    source = (ROOT / "src" / "batikcraft_studio" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert source.index("activate_managed_ai_packages()") < source.index(
        "from .integrated_market_app import ContextToolApplication"
    )


def test_frozen_windows_root_falls_back_when_program_files_not_writable(
    monkeypatch, tmp_path
) -> None:
    """Instalasi per-mesin (Program Files) tidak dapat ditulis tanpa admin:
    root dependensi harus jatuh ke folder per-user agar pip dan import
    konsisten — bukan 'terinstal' semu lalu gagal import."""

    from batikcraft_studio import dependency_bootstrap as bootstrap

    monkeypatch.delenv(bootstrap.DEPENDENCIES_DIR_ENV, raising=False)
    monkeypatch.setattr(bootstrap, "_is_frozen_windows", lambda: True)
    exe = tmp_path / "app" / "BatikCraftStudio.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(bootstrap.sys, "executable", str(exe))

    per_user = tmp_path / "peruser"
    monkeypatch.setattr(
        bootstrap, "_per_user_application_data_root", lambda: per_user
    )

    # samping exe dapat ditulis -> pakai samping exe
    assert bootstrap.default_managed_dependency_root() == exe.parent / "dependencies"

    # samping exe TIDAK dapat ditulis -> jatuh ke per-user
    monkeypatch.setattr(bootstrap, "_directory_is_writable", lambda _d: False)
    assert bootstrap.default_managed_dependency_root() == per_user / "dependencies"


def test_import_error_message_names_missing_module_and_folder() -> None:
    from batikcraft_studio.dependency_bootstrap import describe_ai_import_error

    message = describe_ai_import_error(ModuleNotFoundError("x", name="torch"))
    assert "torch" in message
    assert "Folder paket" in message
    assert "Dependencies" in message
    assert "pip install" not in message
