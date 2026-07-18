"""Apply the user-visible online/offline model-access preference.

Hugging Face, Transformers, and Diffusers each honour their own offline
environment variable.  Older BatikCraft builds could inherit one of those
variables while the application UI gave the user no authoritative way to
change it.  This module makes the persisted AI runtime setting the source of
truth for the current BatikCraft process.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from dataclasses import replace

from batikcraft_studio.ai.runtime_settings import (
    AIRuntimeSettings,
    AIRuntimeSettingsStore,
    get_ai_runtime_store,
)

OFFLINE_ENVIRONMENT_NAMES = (
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "DIFFUSERS_OFFLINE",
)


def apply_model_connectivity(
    settings: AIRuntimeSettings,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> bool:
    """Apply one runtime profile and return ``True`` when online access is enabled."""

    target = os.environ if environ is None else environ
    online = not bool(settings.local_files_only)
    for name in OFFLINE_ENVIRONMENT_NAMES:
        if online:
            target.pop(name, None)
        else:
            target[name] = "1"
    return online


def apply_saved_model_connectivity(
    store: AIRuntimeSettingsStore | None = None,
) -> AIRuntimeSettings:
    """Load and apply the persisted connection mode during application startup."""

    resolved_store = store or get_ai_runtime_store()
    settings = resolved_store.load()
    apply_model_connectivity(settings)
    return settings


def set_model_online(
    enabled: bool,
    store: AIRuntimeSettingsStore | None = None,
) -> AIRuntimeSettings:
    """Persist and immediately apply the model-download connection mode."""

    resolved_store = store or get_ai_runtime_store()
    current = resolved_store.load()
    updated = replace(current, local_files_only=not bool(enabled))
    resolved_store.save(updated)
    apply_model_connectivity(updated)
    return updated


def model_online(store: AIRuntimeSettingsStore | None = None) -> bool:
    """Return the persisted user-visible connection state."""

    resolved_store = store or get_ai_runtime_store()
    return not resolved_store.load().local_files_only


__all__ = [
    "OFFLINE_ENVIRONMENT_NAMES",
    "apply_model_connectivity",
    "apply_saved_model_connectivity",
    "model_online",
    "set_model_online",
]
