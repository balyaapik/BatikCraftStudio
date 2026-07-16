"""Application shell that exposes BatikBrew as the primary generative AI action."""

from __future__ import annotations

import tkinter as tk

from .context_tool_app import _find_cascade_menu
from .progress_context_tool_app import ContextToolApplication as _ProgressApplication


class ContextToolApplication(_ProgressApplication):
    """Keep progress-enabled application services and clarify the SDXL AI menu."""

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_bar = self.root.nametowidget(str(self.root.cget("menu")))
        _index, ai_menu = _find_cascade_menu(
            menu_bar,
            "AI Batik",
            "Batik AI",
            "AI",
        )
        end = ai_menu.index(tk.END)
        if end is None:
            return
        for index in range(int(end) + 1):
            if ai_menu.type(index) != "command":
                continue
            label = str(ai_menu.entrycget(index, "label"))
            if "Stable Diffusion + LoRA" not in label:
                continue
            ai_menu.entryconfigure(
                index,
                label="Generate Motif BatikBrew — SDXL LoRA…",
            )
            return


__all__ = ["ContextToolApplication"]
