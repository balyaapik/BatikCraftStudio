"""Expanded Batik palette and menu-first Stable Diffusion AI workflows."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.lora_object_batification import LoraObjectBatificationProvider
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    ProjectSessionError,
)
from batikcraft_studio.i18n import tr

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .batik_palette import BATIK_COLORS
from .context_tool_editor_hotfix_v10 import ContextToolEditorWorkspaceView as _HotfixV10Editor
from .theme import COLORS
from .tooltip import ToolTip

_AI_CONTEXT_LABEL = "Batifikasi AI — Stable Diffusion + LoRA…"
_NON_AI_CONTEXT_LABEL = "Batifikasi Cepat (Non-AI)…"


class ContextToolEditorWorkspaceView(_HotfixV10Editor):
    """Show a larger Batik palette and open object AI through a LoRA settings window."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._remove_background_ai_from_editor_chrome()
        self._configure_object_batification_context_actions()
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(LoraObjectBatificationProvider())

    def _build_color_palette(self, parent: ttk.Frame) -> None:
        """Build a wide, named palette based on common Indonesian Batik colours."""

        parent.columnconfigure(1, weight=1)
        controls = ttk.Frame(parent, style="Toolbar.TFrame")
        controls.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 8))
        ttk.Label(controls, text="Palet Warna Batik", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(0, 3),
        )
        self._primary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.SUNKEN,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=True),
        )
        self._primary_color_preview.grid(row=1, column=0, rowspan=2, padx=(0, 3))
        self._secondary_color_preview = tk.Button(
            controls,
            width=3,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=lambda: self._choose_palette_color(primary=False),
        )
        self._secondary_color_preview.grid(row=2, column=1, padx=(0, 3))
        ttk.Button(
            controls,
            text="⇄",
            width=3,
            style="Secondary.TButton",
            command=self.swap_palette_colors,
        ).grid(row=1, column=2, padx=1)
        ttk.Button(
            controls,
            text="D",
            width=3,
            style="Secondary.TButton",
            command=self.reset_palette_colors,
        ).grid(row=2, column=2, padx=1)

        palette_area = ttk.Frame(parent, style="Toolbar.TFrame")
        palette_area.grid(row=0, column=1, rowspan=2, sticky="ew")
        palette_area.columnconfigure(0, weight=1)
        ttk.Label(
            palette_area,
            text=(
                "Soga · Malam · Mori · Mengkudu · Nila · Mega Mendung · "
                "Hijau Alam · Aksen Pesisir"
            ),
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        swatches = ttk.Frame(palette_area, style="Toolbar.TFrame")
        swatches.grid(row=1, column=0, sticky="ew")
        self._batik_swatch_buttons: list[tk.Button] = []
        columns = 22
        for index, color in enumerate(BATIK_COLORS):
            row, column = divmod(index, columns)
            button = tk.Button(
                swatches,
                background=color.hex_value,
                activebackground=color.hex_value,
                width=2,
                height=1,
                relief=tk.FLAT,
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=COLORS["line"],
                cursor="hand2",
                command=lambda value=color.hex_value: self._set_primary_color(value),
            )
            button.grid(row=row, column=column, padx=1, pady=1)
            button.bind(
                "<Button-3>",
                lambda _event, value=color.hex_value: self._set_secondary_color(value),
            )
            ToolTip(
                button,
                f"{color.name} · {color.hex_value}\n"
                "Klik kiri: warna utama · Klik kanan: warna sekunder",
            )
            self._batik_swatch_buttons.append(button)

        ttk.Button(
            parent,
            text=tr("palette.custom"),
            style="Secondary.TButton",
            command=lambda: self._choose_palette_color(primary=True),
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

        canvas_controls = ttk.Frame(parent, style="Toolbar.TFrame")
        canvas_controls.grid(row=0, column=3, rowspan=2, sticky="e", padx=(10, 0))
        ttk.Label(
            canvas_controls,
            text=tr("palette.canvas"),
            style="PanelTitle.TLabel",
        ).pack(side="left", padx=(0, 5))
        self._canvas_color_preview = tk.Button(
            canvas_controls,
            width=4,
            height=1,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            command=self._choose_canvas_color,
        )
        self._canvas_color_preview.pack(side="left")
        ToolTip(self._canvas_color_preview, tr("palette.canvas_tooltip"))
        self._update_color_previews()

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open AI settings and Batikify one object with an optional motif reference."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek sumber. Shift-pilih satu motif Batik bila ingin memakai "
                "referensi khusus."
            )
            return

        defaults = pretrained_batification_options_from_global()
        installed_models = (
            self.session.installed_models
            if isinstance(self.session, OfflineAIProjectSession)
            else ()
        )
        runtime = (
            self.session.runtime_selection
            if isinstance(self.session, OfflineAIProjectSession)
            else None
        )
        if runtime is not None:
            installed_models = tuple(
                sorted(
                    installed_models,
                    key=lambda item: item.manifest.model_id != runtime.model_id,
                )
            )
        dialog = AIObjectBatificationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        self.wait_window(dialog)
        options = dialog.result
        if options is None:
            self.set_status("Batifikasi Objek dengan AI dibatalkan.")
            return
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        reference = "motif terpilih" if plan.uses_selected_motif else "referensi Batik otomatis"
        self.set_status(
            f"Stable Diffusion + LoRA sedang membatikkan {plan.source_name} dengan {reference}. "
            "Bentuk dan alpha objek akan dipertahankan."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - worker failures return to Tk
                message = str(exc)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_pretrained_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-object-stable-diffusion-lora",
        ).start()

    def _remove_background_ai_from_editor_chrome(self) -> None:
        button = getattr(self, "_background_ai_button", None)
        if button is not None:
            try:
                button.destroy()
            except tk.TclError:
                pass
            self._background_ai_button = None
        _delete_menu_command(self._selection_context_menu, "AI Batik Background…")

    def _configure_object_batification_context_actions(self) -> None:
        """Guarantee that right-click AI opens the Stable Diffusion + LoRA dialog."""

        menu = self._selection_context_menu
        ai_index: int | None = None
        non_ai_index: int | None = None
        end = menu.index("end")
        if end is not None:
            for index in range(int(end) + 1):
                try:
                    label = str(menu.entrycget(index, "label"))
                except tk.TclError:
                    continue
                if label.startswith(("Batifikasi AI Pretrained", "Batifikasi Objek dengan AI")):
                    ai_index = index
                elif label in {"Batifikasi Non-AI…", _NON_AI_CONTEXT_LABEL}:
                    non_ai_index = index

        if non_ai_index is not None:
            menu.entryconfigure(non_ai_index, label=_NON_AI_CONTEXT_LABEL)
        if ai_index is not None:
            menu.entryconfigure(
                ai_index,
                label=_AI_CONTEXT_LABEL,
                command=self.batify_selected_with_pretrained_ai,
            )
            return

        menu.add_separator()
        menu.add_command(
            label=_AI_CONTEXT_LABEL,
            command=self.batify_selected_with_pretrained_ai,
        )


def _delete_menu_command(menu: tk.Menu, label: str) -> bool:
    """Delete a named command and an immediately preceding orphan separator."""

    end = menu.index("end")
    if end is None:
        return False
    for index in range(int(end), -1, -1):
        try:
            current = str(menu.entrycget(index, "label"))
        except tk.TclError:
            continue
        if current != label:
            continue
        menu.delete(index)
        if index > 0:
            try:
                if menu.type(index - 1) == "separator":
                    menu.delete(index - 1)
            except tk.TclError:
                pass
        return True
    return False


__all__ = [
    "ContextToolEditorWorkspaceView",
    "_AI_CONTEXT_LABEL",
    "_NON_AI_CONTEXT_LABEL",
    "_delete_menu_command",
]
