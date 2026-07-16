"""Global progress feedback for long-running editor AI operations."""

from __future__ import annotations

from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    ProjectSessionError,
)

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .context_tool_editor_hotfix_v11 import ContextToolEditorWorkspaceView as _HotfixV11Editor
from .task_progress import TaskProgressDialog, TaskProgressReporter


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
        progress = TaskProgressDialog(
            self,
            title="Batifikasi AI — Stable Diffusion + LoRA",
            initial_message="Menyiapkan objek sumber…",
            cancellable=False,
            auto_close_ms=750,
        )

        def worker(reporter: TaskProgressReporter):
            reporter.update(
                1,
                6,
                "Memvalidasi objek sumber…",
                detail=plan.source_name,
            )
            reporter.update(
                2,
                6,
                "Menyiapkan referensi motif Batik…",
                detail=reference,
            )
            reporter.update(
                3,
                6,
                "Memuat Stable Diffusion, ControlNet, dan LoRA…",
                detail="Pemakaian pertama dapat membutuhkan waktu lebih lama.",
            )
            reporter.indeterminate(
                "Menjalankan inferensi Stable Diffusion + LoRA…",
                detail=(
                    f"{plan.options.inference_steps} inference steps · "
                    f"seed {plan.options.seed}. Aplikasi tetap responsif."
                ),
            )
            result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            reporter.update(
                5,
                6,
                "Memulihkan siluet, alpha, dan outline objek…",
            )
            reporter.update(6, 6, "Menerapkan hasil ke canvas…")
            return result

        def success(result: object) -> None:
            self._finish_pretrained_ai_success(plan, result)

        def failure(error: BaseException) -> None:
            self._finish_pretrained_ai_error(str(error))

        progress.run(worker, on_success=success, on_error=failure)


__all__ = ["ContextToolEditorWorkspaceView"]
