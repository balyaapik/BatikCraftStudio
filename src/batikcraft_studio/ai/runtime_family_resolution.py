"""Resolve each local model family independently across managed and legacy roots.

Older Windows releases could place dependencies beside the executable, while newer
builds prefer the writable per-user dependency root. A single global root decision is
incorrect when SDXL lives in one location and SD 1.5 + ControlNet lives in the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

_INSTALLED = False


def _candidate_roots() -> tuple[Path, ...]:
    from batikcraft_studio.dependency_bootstrap import (
        default_managed_dependency_root,
        legacy_frozen_dependency_root,
    )

    values = [default_managed_dependency_root() / "models" / "runtime"]
    legacy_root = legacy_frozen_dependency_root()
    if legacy_root is not None:
        values.append(legacy_root / "models" / "runtime")

    unique: list[Path] = []
    seen: set[str] = set()
    for value in values:
        resolved = value.expanduser().resolve(strict=False)
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return tuple(unique)


def _resolve_complete_paths(
    builder: Callable[[str | Path | None], Any],
    validator: Callable[[Any], None],
) -> Any:
    roots = _candidate_roots()
    for root in roots:
        paths = builder(root)
        try:
            validator(paths)
        except Exception:  # noqa: BLE001 - an incomplete candidate is expected
            continue
        return paths
    preferred = roots[0]
    return builder(preferred)


def install_runtime_family_resolution() -> None:
    """Patch runtime path helpers before model-manager dialogs import them."""

    global _INSTALLED
    if _INSTALLED:
        return

    from batikcraft_studio.ai import runtime_model_installer as installer

    if getattr(installer, "_batikcraft_family_root_resolution", False):
        _INSTALLED = True
        return

    original_runtime_model_paths = installer.runtime_model_paths
    original_batikbrew_runtime_model_paths = installer.batikbrew_runtime_model_paths
    validate_runtime_models = installer.validate_runtime_models
    validate_batikbrew_runtime = installer.validate_batikbrew_runtime

    def runtime_model_paths(root: str | Path | None = None) -> Any:
        if root is not None:
            return original_runtime_model_paths(root)
        return _resolve_complete_paths(original_runtime_model_paths, validate_runtime_models)

    def batikbrew_runtime_model_paths(root: str | Path | None = None) -> Any:
        if root is not None:
            return original_batikbrew_runtime_model_paths(root)
        return _resolve_complete_paths(
            original_batikbrew_runtime_model_paths,
            validate_batikbrew_runtime,
        )

    def find_installed_runtime_models(root: str | Path | None = None) -> Any | None:
        paths = runtime_model_paths(root)
        try:
            validate_runtime_models(paths)
        except installer.RuntimeModelInstallError:
            return None
        return paths

    def find_installed_batikbrew_runtime(root: str | Path | None = None) -> Any | None:
        paths = batikbrew_runtime_model_paths(root)
        try:
            validate_batikbrew_runtime(paths)
        except installer.RuntimeModelInstallError:
            return None
        return paths

    installer.runtime_model_paths = runtime_model_paths
    installer.batikbrew_runtime_model_paths = batikbrew_runtime_model_paths
    installer.find_installed_runtime_models = find_installed_runtime_models
    installer.find_installed_batikbrew_runtime = find_installed_batikbrew_runtime
    installer._batikcraft_family_root_resolution = True
    _INSTALLED = True


__all__ = [
    "install_runtime_family_resolution",
]
