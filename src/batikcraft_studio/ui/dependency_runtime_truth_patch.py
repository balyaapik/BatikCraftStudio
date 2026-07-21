"""Keep Dependency Center status aligned with usable runtimes.

A directory and version string are not proof that PyTorch can be imported. Likewise,
model families may live in different managed/legacy roots. This patch makes the table,
model tab, import-error message, and post-install refresh use the same validated truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_INSTALLED = False


def install_dependency_runtime_truth_patch() -> None:
    """Install runtime-aware status and recovery wrappers."""

    global _INSTALLED
    if _INSTALLED:
        return

    from batikcraft_studio import dependency_bootstrap
    from batikcraft_studio.ai import runtime_model_installer
    from batikcraft_studio.ai.torch_runtime_integrity import (
        clear_failed_torch_imports,
        inspect_torch_runtime,
        installed_torch_variant,
    )
    from batikcraft_studio.ui import dependency_catalog as catalog
    from batikcraft_studio.ui import dependency_center as center
    from batikcraft_studio.ui import dependency_integrity_patch as integrity_patch

    if getattr(center.DependencyCenterWindow, "_batikcraft_runtime_truth", False):
        _INSTALLED = True
        return

    original_is_installed = catalog.is_installed
    original_installed_fraction = catalog.installed_fraction
    original_integrity_status = catalog.integrity_status
    original_activate = dependency_bootstrap.activate_managed_ai_packages
    original_describe_import_error = dependency_bootstrap.describe_ai_import_error

    def model_folder(item: object) -> Path:
        key = str(getattr(item, "key", ""))
        if key == "sdxl":
            return runtime_model_installer.batikbrew_runtime_model_paths().base_model
        if key == "sd15":
            return runtime_model_installer.runtime_model_paths().base_model
        return catalog.managed_runtime_root() / str(getattr(item, "folder", ""))

    # Closures installed by dependency_integrity_patch resolve this global at call time.
    integrity_patch._model_folder = model_folder

    def _is_torch_item(item: catalog.DependencyItem) -> bool:
        return item.module.split(".")[0] == "torch" or bool(item.variant)

    def _torch_state(item: catalog.DependencyItem) -> tuple[bool, list[str]]:
        if not _is_torch_item(item):
            return False, []
        packages = dependency_bootstrap.default_managed_ai_package_dir()
        actual = installed_torch_variant(packages)
        selected = actual == item.variant
        if not selected:
            return False, []
        return True, inspect_torch_runtime(packages)

    def is_installed(item: catalog.DependencyItem) -> bool:
        selected, issues = _torch_state(item)
        if _is_torch_item(item):
            return selected and not issues
        return original_is_installed(item)

    def installed_fraction(item: catalog.DependencyItem) -> float:
        selected, issues = _torch_state(item)
        if _is_torch_item(item):
            if not selected:
                return 0.0
            return 0.99 if issues else 1.0
        return original_installed_fraction(item)

    def integrity_status(item: catalog.DependencyItem) -> tuple[str, str]:
        selected, issues = _torch_state(item)
        if not _is_torch_item(item):
            return original_integrity_status(item)
        if not selected:
            return "Belum terpasang", ""
        if issues:
            detail = "; ".join(issues[:4])
            return (
                "PERLU REPARASI",
                "Instalasi PyTorch tidak utuh dan tidak aman dipakai. " + detail,
            )
        return "Terpasang", ""

    def activate_managed_ai_packages(path: str | Path | None = None) -> Path:
        target = original_activate(path)
        clear_failed_torch_imports()
        return target

    def describe_ai_import_error(exc: BaseException) -> str:
        text = str(exc).casefold()
        if "torch" in text or " amp" in text or "partially initialized" in text:
            packages = dependency_bootstrap.default_managed_ai_package_dir()
            issues = inspect_torch_runtime(packages)
            details = "; ".join(issues[:4]) if issues else str(exc)
            return (
                "PyTorch terpasang sebagian atau tercampur sehingga tidak dapat di-import.\n"
                f"Folder runtime: {packages}\n"
                f"Masalah: {details}\n"
                "Buka Dependencies, centang kembali PyTorch GPU (CUDA) atau PyTorch CPU "
                "yang sesuai, lalu jalankan Unduh & Instal Terpilih. Setelah reparasi "
                "selesai, tutup dan buka kembali BatikCraft Studio."
            )
        return original_describe_import_error(exc)

    catalog.is_installed = is_installed
    catalog.installed_fraction = installed_fraction
    catalog.integrity_status = integrity_status
    center.is_installed = is_installed
    center.installed_fraction = installed_fraction
    center.integrity_status = integrity_status
    dependency_bootstrap.activate_managed_ai_packages = activate_managed_ai_packages
    dependency_bootstrap.describe_ai_import_error = describe_ai_import_error
    center.activate_managed_ai_packages = activate_managed_ai_packages
    center.DependencyCenterWindow._batikcraft_runtime_truth = True
    _INSTALLED = True


__all__ = [
    "install_dependency_runtime_truth_patch",
]
