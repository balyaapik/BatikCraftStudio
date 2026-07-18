"""Create BatikCraft's managed AI storage before dialogs or workers use it."""

from __future__ import annotations

from pathlib import Path

from batikcraft_studio.dependency_bootstrap import (
    default_managed_ai_package_dir,
    default_managed_dependency_log,
    default_managed_dependency_root,
    default_managed_huggingface_cache_dir,
    default_managed_model_library_dir,
    default_managed_pip_cache_dir,
    default_managed_runtime_model_dir,
)


def managed_storage_directories() -> tuple[Path, ...]:
    """Return every writable directory required by dependency/model workflows."""

    huggingface = default_managed_huggingface_cache_dir()
    return (
        default_managed_dependency_root(),
        default_managed_ai_package_dir(),
        default_managed_pip_cache_dir(),
        huggingface,
        huggingface / "hub",
        huggingface / "transformers",
        huggingface / "diffusers",
        default_managed_runtime_model_dir(),
        default_managed_model_library_dir(),
        default_managed_dependency_log().parent,
    )


def ensure_managed_storage() -> tuple[Path, ...]:
    """Create and verify all managed directories.

    Raising the original ``OSError`` is intentional: the caller can show a useful
    storage-permission error instead of continuing into a false successful install.
    """

    directories = managed_storage_directories()
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise OSError(f"Direktori penyimpanan tidak tersedia: {directory}")
    return directories


def nearest_existing_directory(value: str | Path | None) -> Path:
    """Return the requested folder or its nearest existing parent."""

    candidate = Path(value).expanduser() if value else Path.home()
    candidate = candidate.resolve(strict=False)
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.is_dir() else Path.home()


__all__ = [
    "ensure_managed_storage",
    "managed_storage_directories",
    "nearest_existing_directory",
]
