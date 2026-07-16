"""Global progress feedback for long-running editor AI operations."""

from __future__ import annotations

import threading

from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.application import OfflineAIProjectSession, ProjectSessionError

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .context_tool_editor_hotfix_v11 import ContextToolEditorWorkspaceView as _HotfixV11Editor
from .progress_dialog import ProgressDialog


class ContextToolEditorWorkspaceView(_HotfixV11Editor):
    """Display visible progress while Stable Diffusion and LoRA are working."""

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open AI settings, then run the complete operation with progress feedback."""

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
        settings = AIObjectBatificationDialog(
            self,
            defaults=defaults,
            installed_models=installed_models,
        )
        self.wait_window(settings)
        options = settings.result
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
        self.set_status(f"Batifikasi AI {plan.source_name} sedang berjalan…")
        progress = ProgressDialog(
            self,
            title="Batifikasi AI — Stable Diffusion + LoRA",
            message="Menyiapkan objek sumber…",
            cancellable=False,
            auto_close_ms=750,
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 1/6 — Memvalidasi objek sumber",
                    1,
                    6,
                    detail=plan.source_name,
                )
                reporter.update(
                    "Tahap 2/6 — Menyiapkan referensi motif Batik",
                    2,
                    6,
                    detail=reference,
                )
                reporter.update(
                    "Tahap 3/6 — Memuat Stable Diffusion, ControlNet, dan LoRA",
                    3,
                    6,
                    detail="Pemakaian pertama dapat membutuhkan waktu lebih lama.",
                )
                reporter.update(
                    "Tahap 4/6 — Menjalankan inferensi Stable Diffusion + LoRA",
                    detail=(
                        f"{plan.options.inference_steps} inference steps · "
                        f"seed {plan.options.seed}. Aplikasi tetap responsif."
                    ),
                )
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
                reporter.update(
                    "Tahap 5/6 — Memulihkan siluet, alpha, dan outline objek",
                    5,
                    6,
                )
                reporter.update("Tahap 6/6 — Menerapkan hasil ke canvas", 6, 6)
            except Exception as exc:  # noqa: BLE001 - surface worker failure in UI
                self.after(
                    0,
                    lambda error=exc: self._finish_progress_ai_error(progress, error),
                )
                return
            self.after(
                0,
                lambda: self._finish_progress_ai_success(progress, plan, result),
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-object-ai-progress",
        ).start()

    def _finish_progress_ai_success(self, progress: ProgressDialog, plan, result) -> None:
        progress.finish("Batifikasi AI selesai")
        self._finish_pretrained_ai_success(plan, result)

    def _finish_progress_ai_error(self, progress: ProgressDialog, error: Exception) -> None:
        progress.fail(str(error))
        self._finish_pretrained_ai_error(str(error))


__all__ = ["ContextToolEditorWorkspaceView"]
