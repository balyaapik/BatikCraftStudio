"""Install and activate optional AI packages without requiring system Python.

Frozen desktop builds invoke the same BatikCraft Studio executable with a private
bootstrap flag. The child process runs the bundled pip module and installs optional
AI wheels into a stable per-user directory. Normal application startup adds that
directory to ``sys.path`` before any AI provider is imported.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

INSTALL_FLAG = "--batikcraft-install-ai-dependencies"
_DLL_DIRECTORY_HANDLES: list[object] = []


def default_managed_ai_package_dir() -> Path:
    """Return the per-user directory used for optional AI Python packages."""

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        root = Path(local_appdata)
    else:
        data_home = os.environ.get("XDG_DATA_HOME")
        root = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return root / "BatikCraftStudio" / "ai-runtime" / "site-packages"


def activate_managed_ai_packages(path: str | Path | None = None) -> Path:
    """Make app-managed packages importable in this process.

    The directory is activated even before it exists so packages installed later in
    the same application session can be discovered after cache invalidation.
    """

    target = Path(path) if path is not None else default_managed_ai_package_dir()
    target = target.expanduser().resolve()
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
    executable: str | Path | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """Build the child-process command used by the dependency manager GUI."""

    packages = [str(value).strip() for value in requirements if str(value).strip()]
    if not packages:
        raise ValueError("Daftar dependency AI kosong.")
    install_target = Path(target) if target is not None else default_managed_ai_package_dir()
    install_target = install_target.expanduser().resolve()
    launcher = str(executable or sys.executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        return [
            launcher,
            INSTALL_FLAG,
            "--target",
            str(install_target),
            "--",
            *packages,
        ]
    return [
        launcher,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
        "--prefer-binary",
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
    parser.add_argument("requirements", nargs=argparse.REMAINDER)
    namespace = parser.parse_args(arguments)
    requirements = list(namespace.requirements)
    if requirements and requirements[0] == "--":
        requirements.pop(0)
    if not requirements:
        parser.error("setidaknya satu dependency diperlukan")

    target = Path(namespace.target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return run_bundled_pip_install(requirements, target=target)


def run_bundled_pip_install(requirements: Sequence[str], *, target: Path) -> int:
    """Install optional packages using pip bundled inside the desktop executable."""

    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        print(
            "Installer dependency internal tidak tersedia pada build ini. "
            "Unduh release BatikCraft Studio terbaru.",
            file=sys.stderr,
        )
        return 2

    arguments = [
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
        "--prefer-binary",
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
    "INSTALL_FLAG",
    "activate_managed_ai_packages",
    "default_managed_ai_package_dir",
    "managed_ai_install_command",
    "maybe_run_dependency_installer",
    "run_bundled_pip_install",
]
