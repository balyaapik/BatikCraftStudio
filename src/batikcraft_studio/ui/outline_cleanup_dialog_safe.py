"""Race-safe outline cleanup dialog that discards stale worker results."""

from __future__ import annotations

from queue import Empty
from tkinter import messagebox

from batikcraft_studio.application.outline_cleanup_session import OutlineCleanupPreview

from .outline_cleanup_dialog import OutlineCleanupDialog as _BaseOutlineCleanupDialog


class OutlineCleanupDialog(_BaseOutlineCleanupDialog):
    """Keep Apply synchronized with the exact settings used by the latest preview."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._rerun_requested = False
        super().__init__(*args, **kwargs)

    def process_preview(self) -> None:
        if self._working:
            self._rerun_requested = True
            self.status_value.set(
                "Pengaturan baru akan diproses setelah preview yang sedang berjalan selesai…"
            )
            return
        self._rerun_requested = False
        super().process_preview()

    def _mark_dirty(self, *_args: object) -> None:
        if hasattr(self, "_generation"):
            self._generation += 1
        super()._mark_dirty(*_args)

    def _poll_worker(self) -> None:
        self._poll_after_id = None
        if self._destroyed:
            return
        terminal: tuple[int, str, object] | None = None
        while True:
            try:
                terminal = self._queue.get_nowait()
            except Empty:
                break
        if terminal is None:
            self._poll_after_id = self.after(60, self._poll_worker)
            return

        generation, kind, payload = terminal
        self._working = False
        self.preview_button.configure(state="normal")
        if generation != self._generation:
            self._current_preview = None
            self.apply_button.configure(state="disabled")
            if self._rerun_requested:
                self._rerun_requested = False
                self.status_value.set("Membuang preview lama dan memproses pengaturan terbaru…")
                self.after_idle(self.process_preview)
            else:
                self.status_value.set(
                    "Preview lama dibuang karena pengaturan berubah. Klik Proses Preview."
                )
            return

        if kind == "error":
            self.status_value.set(str(payload))
            messagebox.showerror("Preview outline gagal", str(payload), parent=self)
            return
        if not isinstance(payload, OutlineCleanupPreview):
            self.status_value.set("Hasil preview outline tidak dikenali.")
            return

        self._current_preview = payload
        self._result_photo = self._photo_from_content(payload.result.content)
        self.result_preview.configure(image=self._result_photo, text="")
        self.apply_button.configure(state="normal")
        result = payload.result
        self.diagnostics_value.set(
            f"Mode: {result.resolved_source_mode} · "
            f"{result.removed_components} bercak / {result.removed_pixels} piksel dihapus · "
            f"cakupan garis {result.output_coverage * 100:.1f}%"
        )
        self.status_value.set("Preview selesai. Terapkan bila garis sudah sesuai.")


__all__ = ["OutlineCleanupDialog"]
