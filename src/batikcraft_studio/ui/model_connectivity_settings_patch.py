"""Expose the model download mode directly in Settings and the runtime dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from batikcraft_studio import batikbrew_context_tool_app
from batikcraft_studio.ai.model_connectivity import (
    apply_model_connectivity,
    model_online,
    set_model_online,
)
from batikcraft_studio.ai.runtime_settings import get_ai_runtime_store
from batikcraft_studio.context_tool_app import _find_cascade_menu
from batikcraft_studio.ui.ai_runtime_settings_dialog import AIRuntimeSettingsDialog

_INSTALLED = False
_ONLINE_LABEL = "Izinkan Download & Reparasi Model (Online)"
_OFFLINE_CHECKBOX_TEXT = "Gunakan file model lokal saja (tanpa download)"


def install_model_connectivity_settings_patch() -> None:
    """Install the visible Settings control and synchronize the runtime dialog."""

    global _INSTALLED
    if _INSTALLED:
        return
    _patch_runtime_dialog()
    _patch_application_menu()
    _INSTALLED = True


def _patch_runtime_dialog() -> None:
    dialog_class = AIRuntimeSettingsDialog
    if getattr(dialog_class, "_batikcraft_online_mode_patch", False):
        return

    original_init = dialog_class.__init__
    original_collect = dialog_class.collect_settings
    original_reset = dialog_class.reset_defaults
    original_save = dialog_class.save

    def init(dialog: Any, *args: object, **kwargs: object) -> None:
        original_init(dialog, *args, **kwargs)
        dialog.online_model_access_value = tk.BooleanVar(
            master=dialog,
            value=not bool(dialog.local_only_value.get()),
        )
        checkbox = _find_checkbutton(dialog, _OFFLINE_CHECKBOX_TEXT)
        if checkbox is not None:
            checkbox.configure(
                text=_ONLINE_LABEL,
                variable=dialog.online_model_access_value,
            )

    def collect_settings(dialog: Any) -> Any:
        dialog.local_only_value.set(not bool(dialog.online_model_access_value.get()))
        return original_collect(dialog)

    def reset_defaults(dialog: Any) -> None:
        original_reset(dialog)
        dialog.online_model_access_value.set(not bool(dialog.local_only_value.get()))

    def save(dialog: Any) -> None:
        original_save(dialog)
        if dialog.result is not None:
            apply_model_connectivity(dialog.result)

    dialog_class.__init__ = init  # type: ignore[assignment]
    dialog_class.collect_settings = collect_settings  # type: ignore[assignment]
    dialog_class.reset_defaults = reset_defaults  # type: ignore[assignment]
    dialog_class.save = save  # type: ignore[assignment]
    dialog_class._batikcraft_online_mode_patch = True  # type: ignore[attr-defined]


def _patch_application_menu() -> None:
    application_class = batikbrew_context_tool_app.ContextToolApplication
    if getattr(application_class, "_batikcraft_online_menu_patch", False):
        return

    original_build_menu = application_class._build_menu
    original_open_runtime = application_class.open_ai_runtime_settings

    def build_menu(application: Any) -> None:
        original_build_menu(application)
        menu_bar = application.root.nametowidget(str(application.root.cget("menu")))
        _index, settings_menu = _find_cascade_menu(menu_bar, "Settings")
        online_value = tk.BooleanVar(
            master=application.root,
            value=model_online(),
        )
        application._model_online_menu_value = online_value
        settings_menu.insert_checkbutton(
            0,
            label=_ONLINE_LABEL,
            variable=online_value,
            command=lambda: _toggle_online_access(application),
        )
        settings_menu.insert_separator(1)

    def open_runtime_settings(application: Any) -> None:
        original_open_runtime(application)
        _sync_menu_value(application)

    application_class._build_menu = build_menu  # type: ignore[assignment]
    application_class.open_ai_runtime_settings = open_runtime_settings  # type: ignore[assignment]
    application_class._batikcraft_online_menu_patch = True  # type: ignore[attr-defined]


def _toggle_online_access(application: Any) -> None:
    variable = getattr(application, "_model_online_menu_value", None)
    enabled = bool(variable.get()) if variable is not None else True
    settings = set_model_online(enabled)

    unload = getattr(application, "_unload_ai_models", None)
    if callable(unload):
        try:
            unload()
        except Exception:  # noqa: BLE001 - the connectivity setting was still saved
            pass

    status = (
        "Mode Online aktif: BatikCraft boleh mengunduh dan memperbaiki model."
        if enabled
        else "Mode Offline aktif: BatikCraft hanya memakai cache dan folder lokal."
    )
    main_window = getattr(application, "main_window", None)
    flash = getattr(main_window, "flash_status", None)
    if callable(flash):
        flash(status)
    apply_model_connectivity(settings)


def _sync_menu_value(application: Any) -> None:
    variable = getattr(application, "_model_online_menu_value", None)
    if variable is not None:
        variable.set(model_online(get_ai_runtime_store()))


def _find_checkbutton(parent: tk.Misc, text: str) -> ttk.Checkbutton | None:
    for child in parent.winfo_children():
        if isinstance(child, ttk.Checkbutton) and str(child.cget("text")) == text:
            return child
        found = _find_checkbutton(child, text)
        if found is not None:
            return found
    return None


__all__ = ["install_model_connectivity_settings_patch"]
