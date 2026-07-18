"""Install and activate optional AI packages without requiring system Python.

Frozen desktop builds invoke the same BatikCraft Studio executable with a private
bootstrap flag. The child process runs the bundled pip module and installs optional
AI wheels into the application's managed ``dependencies`` directory. Normal startup
adds that directory to ``sys.path`` before any AI provider is imported.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import os
import shutil
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

INSTALL_FLAG = "--batikcraft-install-ai-dependencies"
DEPENDENCIES_DIR_ENV = "BATIKCRAFT_DEPENDENCIES_DIR"
_DLL_DIRECTORY_HANDLES: list[object] = []


def _per_user_application_data_root() -> Path:
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "BatikCraftStudio"
        return Path.home() / "AppData" / "Local" / "BatikCraftStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BatikCraftStudio"
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return root / "BatikCraftStudio"


def default_managed_dependency_root() -> Path:
    """Return the root containing every downloaded BatikCraft dependency.

    Installed Windows builds are per-user and writable, so dependencies live beside
    ``BatikCraftStudio.exe`` in ``dependencies``. macOS application bundles must not
    be modified after signing and Linux system packages are normally root-owned, so
    those platforms use the application's per-user data directory instead. The path
    can be overridden with ``BATIKCRAFT_DEPENDENCIES_DIR``.
    """

    configured = os.environ.get(DEPENDENCIES_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    if bool(getattr(sys, "frozen", False)) and os.name == "nt":
        return Path(sys.executable).resolve().parent / "dependencies"

    return _per_user_application_data_root() / "dependencies"


def default_managed_ai_package_dir() -> Path:
    """Return the managed site-packages directory used by optional AI frameworks."""

    return default_managed_dependency_root() / "python" / "site-packages"


def default_managed_pip_cache_dir() -> Path:
    """Return the pip wheel/download cache kept inside managed dependencies."""

    return default_managed_dependency_root() / "cache" / "pip"


def default_managed_dependency_log() -> Path:
    return default_managed_dependency_root() / "logs" / "dependency-install.log"


def _legacy_managed_ai_package_dir() -> Path:
    return _per_user_application_data_root() / "ai-runtime" / "site-packages"


def _migrate_legacy_ai_packages(target: Path) -> None:
    """Move the previous per-user runtime into the installation dependency folder."""

    legacy = _legacy_managed_ai_package_dir()
    if target.exists() or not legacy.is_dir() or legacy.resolve() == target.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy), str(target))
    except OSError:
        # Migration is best-effort. A repair install will populate the new folder.
        return


def activate_managed_ai_packages(path: str | Path | None = None) -> Path:
    """Make app-managed packages importable in this process."""

    target = Path(path) if path is not None else default_managed_ai_package_dir()
    target = target.expanduser().resolve()
    if path is None:
        _migrate_legacy_ai_packages(target)
    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)

    importlib.invalidate_caches()
    if os.name == "nt" and target.is_dir():
        dll_directories = (
            target,
            target / "torch" / "lib",
            target / "numpy.libs",
        )
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        for directory in dll_directories:
            if not directory.is_dir():
                continue
            directory_text = str(directory)
            if directory_text not in path_entries:
                path_entries.insert(0, directory_text)
            add_dll_directory = getattr(os, "add_dll_directory", None)
            if add_dll_directory is not None:
                try:
                    _DLL_DIRECTORY_HANDLES.append(add_dll_directory(directory_text))
                except OSError:
                    pass
        os.environ["PATH"] = os.pathsep.join(path_entries)
    return target


def managed_ai_install_command(
    requirements: Iterable[str],
    *,
    target: str | Path | None = None,
    cache_dir: str | Path | None = None,
    executable: str | Path | None = None,
    frozen: bool | None = None,
    log_file: str | Path | None = None,
) -> list[str]:
    """Build the child-process command used by the dependency manager GUI."""

    packages = [str(value).strip() for value in requirements if str(value).strip()]
    if not packages:
        raise ValueError("Daftar dependency AI kosong.")
    install_target = Path(target) if target is not None else default_managed_ai_package_dir()
    install_target = install_target.expanduser().resolve()
    pip_cache = Path(cache_dir) if cache_dir is not None else default_managed_pip_cache_dir()
    pip_cache = pip_cache.expanduser().resolve()
    launcher = str(executable or sys.executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        command = [
            launcher,
            INSTALL_FLAG,
            "--target",
            str(install_target),
            "--cache-dir",
            str(pip_cache),
        ]
        if log_file is not None:
            command.extend(["--log-file", str(Path(log_file).expanduser().resolve())])
        command.extend(["--", *packages])
        return command
    return [
        launcher,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
        "--prefer-binary",
        "--progress-bar",
        "raw",
        "--cache-dir",
        str(pip_cache),
        "--target",
        str(install_target),
        *packages,
    ]


def maybe_run_dependency_installer(argv: Sequence[str] | None = None) -> int | None:
    """Run the hidden bundled-pip entry point when requested by the frozen EXE."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != INSTALL_FLAG:
        return None

    parser = argparse.ArgumentParser(prog="BatikCraftStudio AI dependency installer")
    parser.add_argument(INSTALL_FLAG, action="store_true")
    parser.add_argument("--target", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--log-file")
    parser.add_argument("requirements", nargs=argparse.REMAINDER)
    namespace = parser.parse_args(arguments)
    requirements = list(namespace.requirements)
    if requirements and requirements[0] == "--":
        requirements.pop(0)
    if not requirements:
        parser.error("setidaknya satu dependency diperlukan")

    target = Path(namespace.target).expanduser().resolve()
    cache_dir = Path(namespace.cache_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if namespace.log_file:
        log_path = Path(namespace.log_file).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace", buffering=1) as stream:
            return _run_with_redirected_output(
                requirements,
                target=target,
                cache_dir=cache_dir,
                stream=stream,
            )
    return run_bundled_pip_install(requirements, target=target, cache_dir=cache_dir)


def _run_with_redirected_output(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path,
    stream: TextIO,
) -> int:
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        return run_bundled_pip_install(requirements, target=target, cache_dir=cache_dir)


def _register_distlib_frozen_resource_finder() -> None:
    """Teach pip's vendored distlib how to read resources from a frozen loader."""

    try:
        import pip._vendor.distlib as distlib_package
        from pip._vendor.distlib import resources as distlib_resources
    except ImportError:
        return

    loader = getattr(distlib_package, "__loader__", None)
    if loader is None:
        return
    distlib_resources.register_finder(loader, distlib_resources.ResourceFinder)
    finder_cache = getattr(distlib_resources, "_finder_cache", None)
    if isinstance(finder_cache, dict):
        finder_cache.pop(distlib_package.__name__, None)


def run_bundled_pip_install(
    requirements: Sequence[str],
    *,
    target: Path,
    cache_dir: Path | None = None,
) -> int:
    """Install optional packages using pip bundled inside the desktop executable."""

    _register_distlib_frozen_resource_finder()
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        print(
            "Installer dependency internal tidak tersedia pada build ini. "
            "Unduh release BatikCraft Studio terbaru.",
            file=sys.stderr,
        )
        return 2

    resolved_cache = cache_dir or default_managed_pip_cache_dir()
    resolved_cache.mkdir(parents=True, exist_ok=True)
    arguments = [
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
        "--prefer-binary",
        "--progress-bar",
        "raw",
        "--cache-dir",
        str(resolved_cache),
        "--target",
        str(target),
        *requirements,
    ]
    try:
        return int(pip_main(arguments))
    except Exception as exc:  # noqa: BLE001 - pip errors must reach the GUI log
        print(f"Installer dependency AI gagal: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "DEPENDENCIES_DIR_ENV",
    "INSTALL_FLAG",
    "activate_managed_ai_packages",
    "default_managed_ai_package_dir",
    "default_managed_dependency_log",
    "default_managed_dependency_root",
    "default_managed_pip_cache_dir",
    "managed_ai_install_command",
    "maybe_run_dependency_installer",
    "run_bundled_pip_install",
]
