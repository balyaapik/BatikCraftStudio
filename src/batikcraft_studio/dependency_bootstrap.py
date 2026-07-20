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
import json
import os
import shutil
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TextIO

INSTALL_FLAG = "--batikcraft-install-ai-dependencies"
DEPENDENCIES_DIR_ENV = "BATIKCRAFT_DEPENDENCIES_DIR"
AI_CACHE_DIR_ENV = "BATIKCRAFT_AI_CACHE_DIR"
MODEL_LIBRARY_DIR_ENV = "BATIKCRAFT_MODEL_LIBRARY"
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


def _per_user_cache_root() -> Path:
    if os.name == "nt":
        return _per_user_application_data_root()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "BatikCraftStudio"
    cache_home = os.environ.get("XDG_CACHE_HOME")
    root = Path(cache_home) if cache_home else Path.home() / ".cache"
    return root / "BatikCraftStudio"


def _per_user_config_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "BatikCraftStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BatikCraftStudio"
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
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

    if _is_frozen_windows():
        beside_executable = Path(sys.executable).resolve().parent / "dependencies"
        # Instalasi per-mesin (C:\Program Files) TIDAK dapat ditulis tanpa
        # admin: pip "berhasil" semu / dialihkan Windows, lalu import gagal
        # dengan "Paket AI lokal belum aktif" meski unduhan tampak selesai.
        # Gunakan folder samping exe hanya bila benar-benar dapat ditulis.
        if _directory_is_writable(beside_executable):
            return beside_executable
        return _per_user_application_data_root() / "dependencies"

    return _per_user_application_data_root() / "dependencies"


def _is_frozen_windows() -> bool:
    """Seam kecil agar perilaku build Windows beku dapat diuji lintas OS."""

    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def _directory_is_writable(directory: Path) -> bool:
    """Uji tulis sungguhan (os.access tidak andal di Windows/UAC)."""

    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".batikcraft-write-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def legacy_frozen_dependency_root() -> Path | None:
    """Folder dependensi samping exe untuk fallback BACA instalasi lama."""

    if _is_frozen_windows():
        return Path(sys.executable).resolve().parent / "dependencies"
    return None


def default_managed_ai_package_dir() -> Path:
    """Return the managed site-packages directory used by optional AI frameworks."""

    return default_managed_dependency_root() / "python" / "site-packages"


def default_managed_pip_cache_dir() -> Path:
    """Return the pip wheel/download cache kept inside managed dependencies."""

    return default_managed_dependency_root() / "cache" / "pip"


def default_managed_huggingface_cache_dir() -> Path:
    """Return the Hugging Face cache inside the managed dependency tree."""

    return default_managed_dependency_root() / "cache" / "huggingface"


def default_managed_runtime_model_dir() -> Path:
    """Return the Stable Diffusion runtime directory."""

    return default_managed_dependency_root() / "models" / "runtime"


def default_managed_model_library_dir() -> Path:
    """Return the local LoRA library directory."""

    return default_managed_dependency_root() / "models" / "lora"


def default_managed_dependency_log() -> Path:
    return default_managed_dependency_root() / "logs" / "dependency-install.log"


def _legacy_managed_ai_package_dir() -> Path:
    return _per_user_application_data_root() / "ai-runtime" / "site-packages"


def _merge_directory(source: Path, target: Path) -> None:
    """Move a legacy directory without replacing already migrated files."""

    if not source.is_dir() or source.resolve() == target.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            shutil.move(str(source), str(target))
        except OSError:
            return
        return

    try:
        children = tuple(source.iterdir())
    except OSError:
        return
    for child in children:
        destination = target / child.name
        if destination.exists():
            continue
        try:
            shutil.move(str(child), str(destination))
        except OSError:
            continue
    try:
        source.rmdir()
    except OSError:
        pass


def _migrate_legacy_lora_models(target: Path) -> None:
    legacy = _per_user_application_data_root() / "models"
    if not legacy.is_dir() or legacy.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    try:
        candidates = tuple(legacy.iterdir())
    except OSError:
        return
    for candidate in candidates:
        if candidate.name.casefold() in {"runtime", "huggingface"}:
            continue
        if not candidate.is_dir() or not (candidate / "manifest.json").is_file():
            continue
        destination = target / candidate.name
        if destination.exists():
            continue
        try:
            shutil.move(str(candidate), str(destination))
        except OSError:
            continue


def _remap_saved_path(value: object, mappings: Sequence[tuple[Path, Path]]) -> object:
    text = str(value or "").strip()
    if not text:
        return value
    path = Path(text).expanduser()
    for old_root, new_root in mappings:
        try:
            relative = path.resolve(strict=False).relative_to(old_root.resolve(strict=False))
        except (OSError, ValueError):
            continue
        return str((new_root / relative).resolve(strict=False))
    return value


def _rewrite_json_paths(path: Path, keys: Sequence[str], mappings: Sequence[tuple[Path, Path]]) -> None:
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    changed = False
    for key in keys:
        if key not in payload:
            continue
        replacement = _remap_saved_path(payload[key], mappings)
        if replacement != payload[key]:
            payload[key] = replacement
            changed = True
    if not changed:
        return
    temporary = path.with_name(f".{path.name}.migration.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)


def migrate_legacy_dependencies() -> Path:
    """Move old packages, model runtimes, caches, and LoRA packs into dependencies."""

    dependency_root = default_managed_dependency_root()
    package_target = default_managed_ai_package_dir()
    runtime_target = default_managed_runtime_model_dir()
    cache_target = default_managed_huggingface_cache_dir()
    lora_target = default_managed_model_library_dir()

    _merge_directory(_legacy_managed_ai_package_dir(), package_target)
    _merge_directory(_per_user_cache_root() / "models" / "runtime", runtime_target)
    _merge_directory(_per_user_cache_root() / "models" / "huggingface", cache_target)
    _migrate_legacy_lora_models(lora_target)

    mappings = (
        (_per_user_cache_root() / "models" / "runtime", runtime_target),
        (_per_user_cache_root() / "models" / "huggingface", cache_target),
        (_per_user_application_data_root() / "models" / "runtime", runtime_target),
        (_per_user_application_data_root() / "models" / "huggingface", cache_target),
        (_per_user_application_data_root() / "models", lora_target),
    )
    config_root = _per_user_config_root()
    _rewrite_json_paths(
        config_root / "ai_runtime.json",
        ("cache_dir", "default_model"),
        mappings,
    )
    _rewrite_json_paths(
        config_root / "batikbrew_model.json",
        ("base_model_path", "lora_path"),
        mappings,
    )
    return dependency_root


def _configure_managed_dependency_environment() -> None:
    cache = default_managed_huggingface_cache_dir()
    os.environ.setdefault(AI_CACHE_DIR_ENV, str(cache))
    os.environ.setdefault(MODEL_LIBRARY_DIR_ENV, str(default_managed_model_library_dir()))
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("HF_HUB_CACHE", str(cache / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache / "transformers"))
    os.environ.setdefault("DIFFUSERS_CACHE", str(cache / "diffusers"))


def describe_ai_import_error(exc: BaseException) -> str:
    """Pesan aksi untuk kegagalan impor runtime AI di aplikasi desktop.

    Aplikasi memasang paket AI ke folder terkelola lewat Dependency Manager,
    jadi jangan pernah menyuruh user menjalankan pip di terminal.
    """

    if isinstance(exc, ModuleNotFoundError):
        packages = default_managed_ai_package_dir()
        torch_ready = (packages / "torch").is_dir()
        status = "berisi torch" if torch_ready else (
            "ada tetapi belum berisi torch" if packages.is_dir() else "belum ada"
        )
        return (
            f"Paket AI lokal belum aktif (modul hilang: {getattr(exc, 'name', '?')}).\n"
            f"Folder paket: {packages} — {status}.\n"
            "Buka menu Dependencies → 'Instal Semua AI + BatikBrew SDXL'. "
            "Jika instalasi baru saja selesai, tutup dan buka kembali aplikasi."
        )
    return (
        f"Runtime AI gagal dimuat: {exc}. Buka menu Dependencies → "
        "'Instal / Reparasi Paket AI' untuk memperbaiki instalasi."
    )


def activate_managed_ai_packages(path: str | Path | None = None) -> Path:
    """Make app-managed packages importable and migrate previous storage layouts."""

    if path is None:
        migrate_legacy_dependencies()
        _configure_managed_dependency_environment()
    target = Path(path) if path is not None else default_managed_ai_package_dir()
    target = target.expanduser().resolve()
    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)

    legacy_root = legacy_frozen_dependency_root()
    if legacy_root is not None:
        legacy_packages = legacy_root / "python" / "site-packages"
        legacy_text = str(legacy_packages)
        if (
            legacy_packages.is_dir()
            and legacy_text != target_text
            and legacy_text not in sys.path
        ):
            # Paket hasil instalasi lama (mis. saat aplikasi pernah berjalan
            # sebagai admin) tetap dapat dipakai walau folder kini read-only.
            sys.path.append(legacy_text)

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
        *_torch_index_arguments(),
        *packages,
    ]


def _torch_index_arguments() -> list[str]:
    """Index wheel PyTorch sesuai perangkat keras (CUDA bila GPU NVIDIA ada)."""

    try:
        from batikcraft_studio.ai.torch_wheel_index import torch_index_arguments

        return torch_index_arguments()
    except Exception:  # noqa: BLE001 - instalasi tidak boleh gagal karena ini
        return []


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
        *_torch_index_arguments(),
        *requirements,
    ]
    try:
        return int(pip_main(arguments))
    except Exception as exc:  # noqa: BLE001 - pip errors must reach the GUI log
        print(f"Installer dependency AI gagal: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "AI_CACHE_DIR_ENV",
    "DEPENDENCIES_DIR_ENV",
    "INSTALL_FLAG",
    "MODEL_LIBRARY_DIR_ENV",
    "activate_managed_ai_packages",
    "default_managed_ai_package_dir",
    "default_managed_dependency_log",
    "default_managed_dependency_root",
    "default_managed_huggingface_cache_dir",
    "default_managed_model_library_dir",
    "default_managed_pip_cache_dir",
    "default_managed_runtime_model_dir",
    "managed_ai_install_command",
    "maybe_run_dependency_installer",
    "migrate_legacy_dependencies",
    "run_bundled_pip_install",
]
