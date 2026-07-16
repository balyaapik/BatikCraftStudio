"""Progress-aware Stable Diffusion and LoRA object Batification."""

from __future__ import annotations

import threading

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.application import (
    OfflineAIProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)

from .ai_object_batification_dialog import AIObjectBatificationDialog
from .context_tool_editor_hotfix_v11 import ContextToolEditorWorkspaceView as _HotfixV11Editor
from .progress_dialog import ProgressDialog, ProgressUpdate


class ContextToolEditorWorkspaceView(_HotfixV11Editor):
    """Keep the editor responsive and visibly progressing while AI runs."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._object_ai_progress: ProgressDialog | None = None
        super().__init__(*args, **kwargs)

    def batify_selected_with_pretrained_ai(self) -> None:
        """Open settings, then show progress throughout Stable Diffusion inference."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
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

        progress = ProgressDialog(
            self,
            title="Batifikasi AI",
            message="Menyiapkan objek dan referensi motif…",
            cancellable=False,
            auto_close_ms=800,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Menyiapkan input objek",
                1,
                6,
                detail="Membaca alpha, siluet, dan objek sumber dari canvas.",
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        reference = "motif terpilih" if plan.uses_selected_motif else "referensi Batik otomatis"
        self.set_status(
            f"Stable Diffusion + LoRA sedang membatikkan {plan.source_name} dengan {reference}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menyiapkan runtime AI",
                    2,
                    6,
                    detail=(
                        f"Model: {plan.options.model_id_or_path}\n"
                        "Memuat Stable Diffusion, ControlNet bila aktif, dan LoRA Batik."
                    ),
                )
                reporter.update(
                    "Tahap 3/6 — Menjalankan Stable Diffusion + LoRA",
                    detail=(
                        f"Inference steps: {plan.options.inference_steps}. "
                        "Tahap ini biasanya memerlukan waktu paling lama."
                    ),
                )
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
                reporter.update(
                    "Tahap 4/6 — Memulihkan bentuk objek",
                    4,
                    6,
                    detail="Menerapkan kembali alpha, siluet, dan outline objek sumber.",
                )
                reporter.update(
                    "Tahap 5/6 — Menyiapkan hasil untuk canvas",
                    5,
                    6,
                    detail="Menyusun PNG hasil dan metadata model.",
                )
            except Exception as exc:  # noqa: BLE001 - worker failures return to Tk
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_pretrained_ai_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._finish_progress_ai_success(plan, result)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-object-ai-with-progress",
        ).start()

    def _finish_progress_ai_success(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> None:
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.post(
                ProgressUpdate(
                    "Tahap 6/6 — Menambahkan hasil ke canvas",
                    6,
                    6,
                    detail="Menyimpan hasil sebagai objek baru dan menyiapkan Undo.",
                )
            )
        super()._finish_pretrained_ai_success(plan, result)
        if progress is not None and progress.winfo_exists():
            progress.finish("Batifikasi AI selesai")
        self._object_ai_progress = None

    def _finish_pretrained_ai_error(self, message: str) -> None:
        super()._finish_pretrained_ai_error(message)
        progress = self._object_ai_progress
        if progress is not None and progress.winfo_exists():
            progress.fail(message)
        self._object_ai_progress = None


__all__ = ["ContextToolEditorWorkspaceView"]
