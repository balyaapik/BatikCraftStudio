"""Consolidate every AI workflow under one top-level AI menu."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from batikcraft_studio.ai import sdxl_text_component_repair
from batikcraft_studio.context_tool_app import _find_cascade_menu

_INSTALLED = False


def install_ai_menu_consolidation(application_class: type[Any]) -> None:
    """Move Dependencies, local training, and AI settings below one AI cascade."""

    global _INSTALLED
    if _INSTALLED or getattr(application_class, "_batikcraft_single_ai_menu", False):
        _INSTALLED = True
        return

    original_build_menu = application_class._build_menu

    def build_menu(application: Any) -> None:
        original_build_menu(application)
        menu_bar = application.root.nametowidget(str(application.root.cget("menu")))
        ai_index, ai_menu = _find_cascade_menu(menu_bar, "AI Batik", "Batik AI", "AI")
        menu_bar.entryconfigure(ai_index, label="AI")

        moved: list[tuple[str, tk.Menu]] = []
        for source_label, target_label in (
            ("Dependencies", "Runtime & Dependencies"),
            ("Training AI Lokal", "Training LoRA Lokal"),
            ("Settings", "Pengaturan AI"),
        ):
            try:
                source_index, source_menu = _find_cascade_menu(menu_bar, source_label)
            except RuntimeError:
                continue
            _prepare_submenu(source_menu, source_label)
            menu_bar.delete(source_index)
            moved.append((target_label, source_menu))

        if moved:
            _remove_ai_group_cascades(ai_menu)
            _normalize_separators(ai_menu)
            if ai_menu.index(tk.END) is not None:
                ai_menu.add_separator()
            for label, submenu in moved:
                ai_menu.add_cascade(label=label, menu=submenu)
            _normalize_separators(ai_menu)

    application_class._build_menu = build_menu  # type: ignore[assignment]
    application_class._batikcraft_single_ai_menu = True  # type: ignore[attr-defined]
    _patch_missing_component_guidance()
    _INSTALLED = True


def _prepare_submenu(menu: tk.Menu, source_label: str) -> None:
    if source_label == "Dependencies":
        _rename_command(menu, "Dependency Manager…", "Kelola Paket AI…")
        _delete_command(menu, "Instal / Reparasi Python AI Packages…")
    _normalize_separators(menu)


def _rename_command(menu: tk.Menu, old_label: str, new_label: str) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end) + 1):
        if menu.type(index) != "command":
            continue
        if str(menu.entrycget(index, "label")) == old_label:
            menu.entryconfigure(index, label=new_label)
            return


def _delete_command(menu: tk.Menu, label: str) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        if menu.type(index) != "command":
            continue
        if str(menu.entrycget(index, "label")) == label:
            menu.delete(index)


def _remove_ai_group_cascades(menu: tk.Menu) -> None:
    labels = {"Runtime & Dependencies", "Training LoRA Lokal", "Pengaturan AI"}
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        if menu.type(index) != "cascade":
            continue
        if str(menu.entrycget(index, "label")) in labels:
            menu.delete(index)


def _normalize_separators(menu: tk.Menu) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    previous_separator = True
    for index in range(int(end), -1, -1):
        entry_type = menu.type(index)
        if entry_type == "separator" and previous_separator:
            menu.delete(index)
            continue
        previous_separator = entry_type == "separator"
    end = menu.index(tk.END)
    if end is not None and menu.type(end) == "separator":
        menu.delete(end)


def _patch_missing_component_guidance() -> None:
    original = getattr(sdxl_text_component_repair, "_missing_component_message", None)
    if not callable(original) or getattr(original, "_batikcraft_ai_menu_guidance", False):
        return

    def menu_aware_message(settings: Any, missing: list[str]) -> str:
        text = str(original(settings, missing))
        replacements = (
            ("Buka Settings", "Buka AI → Pengaturan AI"),
            ("buka Settings", "buka AI → Pengaturan AI"),
            ("buka Dependencies", "buka AI → Runtime & Dependencies"),
            ("Buka Dependencies", "Buka AI → Runtime & Dependencies"),
        )
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    menu_aware_message._batikcraft_ai_menu_guidance = True  # type: ignore[attr-defined]
    sdxl_text_component_repair._missing_component_message = menu_aware_message


__all__ = ["install_ai_menu_consolidation"]
