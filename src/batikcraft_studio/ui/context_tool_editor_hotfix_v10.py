"""Global AI/GPU settings integration for every editor inference workflow."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.ai.global_runtime import (
    GlobalPretrainedBatikBackgroundProvider,
    GlobalPretrainedImg2ImgBatificationProvider,
    pretrained_batification_options_from_global,
)
from batikcraft_studio.application import (
    AIBatikBackgroundProjectSession,
    OfflineAIProjectSession,
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)
from batikcraft_studio.assets import AssetLibraryError, PersonalAssetStore

from .ai_batik_background_dialog_global import GlobalAIBatikBackgroundDialog
from .context_tool_editor_hotfix_v9 import ContextToolEditorWorkspaceView as _HotfixV9Editor
from .offline_ai_dialogs_global import GlobalOfflineModelManagerWindow


class ContextToolEditorWorkspaceView(_HotfixV9Editor):
    """Consume one persisted compute profile for background, pretrained, and LoRA AI."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(self.session, PretrainedAIBatificationProjectSession):
            self.session.set_pretrained_ai_provider(
                GlobalPretrainedImg2ImgBatificationProvider()
            )
        if isinstance(self.session, AIBatikBackgroundProjectSession):
            self.session.set_background_ai_provider(
                GlobalPretrainedBatikBackgroundProvider()
            )

    def batify_selected_with_pretrained_ai(self) -> None:
        """Run object Batification using the global device and memory configuration."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        try:
            options = pretrained_batification_options_from_global()
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        self.set_status(
            f"Batifikasi AI dimulai dengan runtime global {options.device} / "
            f"{options.precision}."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - worker errors return to Tk
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
            name="batikcraft-pretrained-ai-global-runtime",
        ).start()

    def _finish_pretrained_ai_success(
        self,
        plan: PretrainedAIPlan,
        result: PretrainedAIBatificationResult,
    ) -> None:
        self._pretrained_ai_running = False
        if self._pretrained_ai_destroyed:
            return
        try:
            output = self._pretrained_ai_session.commit_pretrained_ai_result(plan, result)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        device = result.metadata.get("device", "-")
        self.set_status(
            f"{output.name} selesai menggunakan {device}. "
            "Runtime dapat diubah melalui Edit → Preferences → AI & GPU."
        )

    def generate_ai_batik_background(self) -> None:
        """Generate a preview using the current persisted global runtime profile."""

        if not self.session.has_project:
            self.set_status("Buat atau buka project sebelum membuat AI Batik Background.")
            return
        try:
            context = self._background_ai_session.prepare_background_ai_context()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        reference_content, reference_name = self._selected_library_reference()
        dialog = GlobalAIBatikBackgroundDialog(
            self,
            reference_content=reference_content,
            reference_name=reference_name,
            render_preview=lambda options, content, name: (
                self._background_ai_session.render_background_ai_preview(
                    context,
                    options,
                    reference_content=content,
                    reference_name=name,
                )
            ),
        )
        self.wait_window(dialog)
        preview = dialog.result
        if preview is None:
            self.set_status("Generasi AI Batik Background dibatalkan. Canvas tidak berubah.")
            return
        try:
            result = self._background_ai_session.commit_background_ai_preview(preview)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        saved = False
        try:
            PersonalAssetStore(self.asset_library).import_image(
                f"ai-batik-background-seed-{preview.options.seed}.png",
                preview.result.content,
                category="ornamen",
            )
        except AssetLibraryError as exc:
            messagebox.showwarning(
                "Background diterapkan, tetapi pustaka gagal diperbarui",
                str(exc),
                parent=self.winfo_toplevel(),
            )
        else:
            saved = True
            try:
                self.refresh_library()
            except (AttributeError, tk.TclError):
                pass

        self.refresh_context()
        device = preview.result.metadata.get("device", "-")
        suffix = " Hasil juga disimpan ke Gambar Impor Saya." if saved else ""
        self.set_status(
            f"{result.name} diterapkan menggunakan {device} pada layer paling bawah."
            f"{suffix} Gunakan Undo untuk kembali."
        )

    def open_offline_model_manager(self) -> None:
        """Keep model paths local while device/precision come from global preferences."""

        window = self._model_window
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            return
        if not isinstance(self.session, OfflineAIProjectSession):
            raise RuntimeError("Editor AI offline memerlukan OfflineAIProjectSession.")
        self._model_window = GlobalOfflineModelManagerWindow(
            self,
            self.session,
            on_change=self._announce_provider,
        )


__all__ = ["ContextToolEditorWorkspaceView"]
