"""Release 0.4.2 fixes for Torch selection and post-install validation."""

from __future__ import annotations

import os
from collections.abc import Iterable

from batikcraft_studio.ai.torch_runtime_integrity import (
    installed_torch_variant,
    purge_managed_torch_installation,
    validate_torch_variant,
)
from batikcraft_studio.ai.torch_wheel_index import nvidia_gpu_present
from batikcraft_studio.dependency_bootstrap import default_managed_ai_package_dir

_TORCH_KEYS = {"torch_cpu", "torch_cuda"}
_PATCHED = False


def preferred_torch_key() -> str:
    """Select CUDA on NVIDIA systems and CPU everywhere else."""

    return "torch_cuda" if nvidia_gpu_present() else "torch_cpu"


def normalise_checked_keys(keys: Iterable[str]) -> set[str]:
    """Never allow the CPU and CUDA wheel rows to be selected together."""

    checked = {str(key) for key in keys}
    selected_torch = checked & _TORCH_KEYS
    if selected_torch:
        checked.difference_update(_TORCH_KEYS)
        checked.add(preferred_torch_key())
    return checked


def install_dependency_cuda_selection_patch() -> None:
    """Patch the Dependency Center without duplicating its large Tk implementation."""

    global _PATCHED
    if _PATCHED:
        return

    from batikcraft_studio.ui.dependency_catalog import CATALOG, eligibility
    from batikcraft_studio.ui.dependency_center import DependencyCenterWindow

    original_install_packages = DependencyCenterWindow._install_packages

    def on_tree_click(self, event) -> None:  # type: ignore[no-untyped-def]
        row = self.tree.identify_row(event.y)
        if not row:
            return
        item = next((entry for entry in CATALOG if entry.key == row), None)
        if item is None:
            return
        eligible, reason = eligibility(item)
        if not eligible:
            self.status_value.set(f"{item.name}: {reason}")
            return
        if row in self._checked:
            self._checked.discard(row)
        else:
            if row in _TORCH_KEYS:
                self._checked.difference_update(_TORCH_KEYS)
            self._checked.add(row)
        self.refresh()

    def select_all(self) -> None:  # type: ignore[no-untyped-def]
        checked = {item.key for item in CATALOG if eligibility(item)[0]}
        if checked & _TORCH_KEYS:
            checked.difference_update(_TORCH_KEYS)
            checked.add(preferred_torch_key())
        self._checked = checked
        self.refresh()

    def selected_items(self):  # type: ignore[no-untyped-def]
        self._checked = normalise_checked_keys(self._checked)
        return [item for item in CATALOG if item.key in self._checked]

    def install_packages(self, item) -> None:  # type: ignore[no-untyped-def]
        target = default_managed_ai_package_dir()
        before_variant = installed_torch_variant(target)
        if item.variant:
            removed = purge_managed_torch_installation(target)
            self._messages.put(
                (
                    "log",
                    f"Runtime Torch lama dibersihkan sebelum pemasangan "
                    f"{item.variant.upper()}: {removed} path dihapus.",
                )
            )

        target_text = str(target.expanduser().resolve())
        previous_pythonpath = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = (
            target_text
            if not previous_pythonpath
            else target_text + os.pathsep + previous_pythonpath
        )
        try:
            original_install_packages(self, item)
        finally:
            if previous_pythonpath:
                os.environ["PYTHONPATH"] = previous_pythonpath
            else:
                os.environ.pop("PYTHONPATH", None)

        if item.variant:
            version = validate_torch_variant(target, item.variant)
            self._messages.put(
                (
                    "log",
                    f"Verifikasi akhir PyTorch: {version} ({item.variant.upper()}). "
                    "Tutup dan buka kembali aplikasi sebelum menjalankan AI.",
                )
            )
            return

        after_variant = installed_torch_variant(target)
        if before_variant and after_variant != before_variant:
            raise RuntimeError(
                "Paket pendamping mengubah varian PyTorch dari "
                f"{before_variant.upper()} menjadi {(after_variant or 'TIDAK ADA').upper()}. "
                "Pasang ulang baris PyTorch yang sesuai lalu restart aplikasi."
            )

    DependencyCenterWindow._on_tree_click = on_tree_click
    DependencyCenterWindow.select_all = select_all
    DependencyCenterWindow._selected_items = selected_items
    DependencyCenterWindow._install_packages = install_packages
    _PATCHED = True


__all__ = [
    "install_dependency_cuda_selection_patch",
    "normalise_checked_keys",
    "preferred_torch_key",
]
