"""UI command for pretrained AI Batification without custom training."""

from __future__ import annotations

import threading
import tkinter as tk

from batikcraft_studio.ai import PretrainedAIBatificationResult
from batikcraft_studio.application import (
    PretrainedAIBatificationProjectSession,
    PretrainedAIPlan,
    ProjectSessionError,
)

from .context_tool_editor_hotfix_v4 import ContextToolEditorWorkspaceView as _HotfixV4Editor


class ContextToolEditorWorkspaceView(_HotfixV4Editor):
    """Expose pretrained img2img Batification while keeping Tk mutations on main."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._pretrained_ai_running = False
        self._pretrained_ai_destroyed = False
        super().__init__(*args, **kwargs)
        self._selection_context_menu.add_command(
            label="Batifikasi AI Pretrained (Tanpa Training)",
            command=self.batify_selected_with_pretrained_ai,
        )
        self.bind_all(
            "<Control-Alt-B>",
            self._on_pretrained_ai_shortcut,
            add="+",
        )

    def batify_selected_with_pretrained_ai(self) -> None:
        """Run Stable Diffusion img2img from source-first, motif-second selection."""

        if self._pretrained_ai_running:
            self.set_status("Batifikasi AI masih berjalan. Tunggu hasil sebelumnya selesai.")
            return
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai()
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        self.set_status(
            "Batifikasi AI dimulai. Model pretrained akan diunduh pada penggunaan pertama."
        )

        def worker() -> None:
            try:
                result = self._pretrained_ai_session.render_pretrained_ai_plan(plan)
            except Exception as exc:  # noqa: BLE001 - convert worker errors to UI status
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
            name="batikcraft-pretrained-ai",
        ).start()

    def _post_pretrained_ai_callback(self, callback: object) -> None:
        if self._pretrained_ai_destroyed:
            return
        try:
            self.after(0, callback)
        except tk.TclError:
            self._pretrained_ai_destroyed = True

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
        self.set_status(
            f"{output.name} dibuat dengan model pretrained tanpa training khusus."
        )

    def _finish_pretrained_ai_error(self, message: str) -> None:
        self._pretrained_ai_running = False
        if not self._pretrained_ai_destroyed:
            self.set_status(message)

    def _on_pretrained_ai_shortcut(
        self,
        _event: tk.Event[tk.Misc],
    ) -> str:
        self.batify_selected_with_pretrained_ai()
        return "break"

    @property
    def _pretrained_ai_session(self) -> PretrainedAIBatificationProjectSession:
        if not isinstance(self.session, PretrainedAIBatificationProjectSession):
            raise RuntimeError("Editor memerlukan PretrainedAIBatificationProjectSession.")
        return self.session

    def destroy(self) -> None:
        self._pretrained_ai_destroyed = True
        if not self._pretrained_ai_running:
            self._pretrained_ai_session.unload_pretrained_ai()
        super().destroy()


__all__ = ["ContextToolEditorWorkspaceView"]
