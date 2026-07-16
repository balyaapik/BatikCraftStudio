"""Application shell with one menu-bar home for every AI model setting."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.ai.generation_providers import provider_label

from .context_tool_app import _find_cascade_menu
from .progress_context_tool_app import ContextToolApplication as _ProgressApplication
from .ui.cloud_ai_settings_dialog import CloudAISettingsDialog


class ContextToolApplication(_ProgressApplication):
    """Keep generation actions separate from persistent AI configuration."""

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        editor = self.main_window._editor()

        _ai_index, ai_menu = _find_cascade_menu(
            menu_bar,
            "AI Batik",
            "Batik AI",
            "AI",
        )
        _remove_commands_containing(ai_menu, "Pengaturan AI")
        _remove_commands_containing(ai_menu, "Stable Diffusion + LoRA", rename=True)

        try:
            _edit_index, edit_menu = _find_cascade_menu(menu_bar, "Edit")
        except RuntimeError:
            edit_menu = None
        if edit_menu is not None:
            _remove_commands_containing(edit_menu, "Preferences → AI")

        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(
            label="Provider Cloud & Model API…",
            command=self.open_cloud_ai_settings,
        )
        settings_menu.add_command(
            label="Model Lokal, Runtime & LoRA…",
            command=editor.open_offline_model_manager,
        )
        settings_menu.add_separator()
        settings_menu.add_command(
            label="Runtime AI & GPU…",
            accelerator="Ctrl+,",
            command=self.open_ai_runtime_settings,
        )

        end = menu_bar.index(tk.END)
        if end is None:
            menu_bar.add_cascade(label="Settings", menu=settings_menu)
        else:
            menu_bar.insert_cascade(end, label="Settings", menu=settings_menu)

    def open_cloud_ai_settings(self) -> None:
        """Configure provider defaults, API models, endpoints, and API keys."""

        dialog = CloudAISettingsDialog(self.root)
        self.root.wait_window(dialog)
        settings = dialog.result
        if settings is None:
            return
        self.main_window.flash_status(
            "Pengaturan provider disimpan: "
            f"Ornamen {provider_label(settings.ornament_provider)} · "
            f"Pola {provider_label(settings.pattern_provider)}."
        )


def _remove_commands_containing(
    menu: tk.Menu,
    fragment: str,
    *,
    rename: bool = False,
) -> None:
    end = menu.index(tk.END)
    if end is None:
        return
    for index in range(int(end), -1, -1):
        if menu.type(index) != "command":
            continue
        label = str(menu.entrycget(index, "label"))
        if fragment not in label:
            continue
        if rename:
            menu.entryconfigure(index, label="Generate Motif BatikBrew…")
        else:
            menu.delete(index)


__all__ = ["ContextToolApplication"]
