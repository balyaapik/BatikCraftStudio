"""Notebook-compatible BatikBrew SDXL generation as the primary object AI workflow."""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import replace

from batikcraft_studio.ai.batikbrew_generation import SDXL_BASE_MODEL_ID
from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    BatikBrewModeGenerationOptions,
    BatikBrewModeGenerationProvider,
)
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationResult
from batikcraft_studio.ai.runtime_model_installer import find_installed_batikbrew_runtime
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)

from .batikbrew_generation_dialog import BatikBrewGenerationDialog
from .batikbrew_output_mode_dialog import BatikBrewOutputModeDialog
from .batikbrew_variation_dialog import BatikBrewVariationDialog
from .context_tool_editor_hotfix_v13 import ContextToolEditorWorkspaceView as _HotfixV13Editor
from .progress_dialog import ProgressDialog, ProgressUpdate

_BATIKBREW_CONTEXT_LABEL = "Generate Motif BatikBrew — SDXL LoRA…"


class ContextToolEditorWorkspaceView(_HotfixV13Editor):
    """Generate an isolated ornament or a full pattern with BatikBrew SDXL."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(BatikBrewModeGenerationProvider())
        self._configure_batikbrew_context_action()

    def batify_selected_with_pretrained_ai(self) -> None:
        """Analyse selected inspiration, generate seed variations, and let the user choose."""

        if self._pretrained_ai_running:
            self.set_status("Generasi BatikBrew masih berjalan. Tunggu proses sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek inspirasi. Shift-pilih objek kedua untuk menggabungkan "
                "dua sumber inspirasi."
            )
            return

        mode_dialog = BatikBrewOutputModeDialog(self)
        self.wait_window(mode_dialog)
        output_mode = mode_dialog.result
        if output_mode is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return

        defaults = pretrained_batification_options_from_global()
        managed = find_installed_batikbrew_runtime()
        defaults = replace(
            defaults,
            model_id_or_path=(
                str(managed.base_model) if managed is not None else SDXL_BASE_MODEL_ID
            ),
            local_files_only=managed is not None,
            inference_steps=max(30, defaults.inference_steps),
            guidance_scale=7.5,
            resolution=max(512, defaults.resolution),
        )
        installed_models = (
            self.session.installed_models
            if isinstance(self.session, OfflineAIProjectSession)
            else ()
        )
        dialog = BatikBrewGenerationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        if output_mode == OUTPUT_MODE_ORNAMENT:
            dialog.title("BatikBrew — Ornamen Tunggal")
            dialog.tileable_value.set(False)
        else:
            dialog.title("BatikBrew — Pola")
        self.wait_window(dialog)
        raw_options = dialog.result
        if raw_options is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return

        try:
            options = BatikBrewModeGenerationOptions(
                **raw_options.to_properties(),
                output_mode=output_mode,
            )
        except (TypeError, ValueError) as exc:
            self.set_status(f"Pengaturan BatikBrew tidak valid: {exc}")
            return

        progress = ProgressDialog(
            self,
            title=(
                "Generate Ornamen BatikBrew"
                if output_mode == OUTPUT_MODE_ORNAMENT
                else "Generate Pola BatikBrew"
            ),
            message="Menyiapkan objek inspirasi…",
            cancellable=False,
            auto_close_ms=None,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Membaca objek inspirasi",
                1,
                6,
                detail=(
                    "Satu objek" if len(selected) == 1 else "Dua objek akan dianalisis bersama"
                ),
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        kind = "ornamen tunggal" if output_mode == OUTPUT_MODE_ORNAMENT else "pola penuh"
        self.set_status(
            f"BatikBrew sedang membuat {options.variation_count} variasi {kind}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menganalisis warna, garis, tema, dan komposisi",
                    2,
                    6,
                    detail="Dominant palette, edge density, theme keywords, dan prompt Batik.",
                )
                reporter.update(
                    "Tahap 3/6 — Memuat Stable Diffusion XL dan LoRA BatikBrew",
                    3,
                    6,
                    detail=f"Base model: {options.model_id_or_path}",
                )
                reporter.update(
                    "Tahap 4/6 — Menghasilkan variasi dengan seed berbeda",
                    detail=(
                        f"{options.variation_count} variasi · {options.inference_steps} steps · "
                        f"guidance {options.guidance_scale}"
                    ),
                )
                results = self._pretrained_ai_session.render_pretrained_ai_variations(plan)
                reporter.update(
                    "Tahap 5/6 — Menyelesaikan transparansi atau tileable output",
                    5,
                    6,
                    detail=(
                        "Background dihapus untuk ornamen tunggal"
                        if output_mode == OUTPUT_MODE_ORNAMENT
                        else "Opposite-edge blending untuk pola seamless"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_batikbrew_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._show_batikbrew_variations(plan, results)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-batikbrew-sdxl-generation",
        ).start()

    def _show_batikbrew_variations(
        self,
        plan: PretrainedAIPlan,
        results: tuple[PretrainedAIBatificationResult, ...],
    ) -> None:
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.post(
                ProgressUpdate(
                    "Tahap 6/6 — Pilih variasi yang akan dipakai",
                    6,
                    6,
                    detail=f"{len(results)} variasi berhasil dibuat.",
                )
            )
            progress.close()
        self._object_ai_progress = None
        if self._pretrained_ai_destroyed:
            self._pretrained_ai_running = False
            return

        chooser = BatikBrewVariationDialog(self, results)
        self.wait_window(chooser)
        selected = chooser.result
        if selected is None:
            self._pretrained_ai_running = False
            self.set_status("Hasil BatikBrew tidak diterapkan karena pemilihan dibatalkan.")
            return
        super()._finish_pretrained_ai_success(plan, selected)

        # Returning focus to the editor is important on Windows: otherwise Ctrl+C may
        # still target the destroyed modal dialog. Reassert the active AI object so the
        # normal multi-object clipboard captures its PNG asset and metadata.
        project = self.session.project
        if project is not None and project.active_object_id is not None:
            self.session.set_selected_objects([project.active_object_id])
        self.focus_set()
        self.set_status("Hasil AI aktif dan siap disalin dengan Ctrl+C / Ctrl+V.")

    def _finish_batikbrew_error(self, message: str) -> None:
        super()._finish_pretrained_ai_error(message)
        self._object_ai_progress = None

    def _configure_batikbrew_context_action(self) -> None:
        menu = self._selection_context_menu
        end = menu.index(tk.END)
        if end is None:
            return
        for index in range(int(end) + 1):
            try:
                label = str(menu.entrycget(index, "label"))
            except tk.TclError:
                continue
            if label.startswith(("Batifikasi AI", "Generate Motif BatikBrew")):
                menu.entryconfigure(
                    index,
                    label=_BATIKBREW_CONTEXT_LABEL,
                    command=self.batify_selected_with_pretrained_ai,
                )
                return
        menu.add_separator()
        menu.add_command(
            label=_BATIKBREW_CONTEXT_LABEL,
            command=self.batify_selected_with_pretrained_ai,
        )


__all__ = ["ContextToolEditorWorkspaceView", "_BATIKBREW_CONTEXT_LABEL"]
