"""Reusable responsive progress dialog for BatikCraft background operations."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any, TypeVar

from batikcraft_studio.progress import OperationCancelledError, ProgressUpdate

_T = TypeVar("_T")
TaskOperation = Callable[[Callable[[ProgressUpdate], object], Callable[[], bool]], _T]


class ProgressTaskDialog(tk.Toplevel):
    """Run one non-Tk operation on a worker and render its progress on the Tk thread."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial_message: str,
        cancelable: bool = False,
        auto_close_ms: int = 350,
    ) -> None:
        super().__init__(parent)
        self.result: Any = None
        self.error: BaseException | None = None
        self.was_cancelled = False
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._finished = False
        self._destroyed = False
        self._auto_close_ms = max(0, int(auto_close_ms))
        self._cancelable = bool(cancelable)
        self._indeterminate_running = False

        self.title(title)
        self.geometry("600x245")
        self.minsize(520, 225)
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel_or_close)

        self.status_value = tk.StringVar(master=self, value=initial_message)
        self.stage_value = tk.StringVar(master=self, value="Menyiapkan…")
        self.detail_value = tk.StringVar(master=self, value="")
        self.percent_value = tk.StringVar(master=self, value="")
        self._build()
        self.grab_set()
        self.focus_set()

    @property
    def cancellation_requested(self) -> bool:
        return self._cancel_event.is_set()

    def start(self, operation: TaskOperation[_T]) -> None:
        """Start a background operation exactly once."""

        if self._worker is not None:
            raise RuntimeError("Progress task sudah dijalankan.")
        self._set_indeterminate(True)

        def report(update: ProgressUpdate) -> None:
            self._events.put(("update", update))

        def worker() -> None:
            try:
                value = operation(report, self._cancel_event.is_set)
                if self._cancel_event.is_set():
                    raise OperationCancelledError("Proses dibatalkan oleh pengguna.")
            except OperationCancelledError as exc:
                self._events.put(("cancelled", exc))
            except BaseException as exc:  # noqa: BLE001 - surface worker failures in UI
                self._events.put(("error", exc))
            else:
                self._events.put(("success", value))

        self._worker = threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-progress-task",
        )
        self._worker.start()
        self.after(60, self._poll_events)

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(
            body,
            textvariable=self.stage_value,
            font=("TkDefaultFont", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            textvariable=self.status_value,
            wraplength=555,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 10))

        progress_row = ttk.Frame(body)
        progress_row.grid(row=2, column=0, sticky="ew")
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            progress_row,
            textvariable=self.percent_value,
            width=7,
            anchor="e",
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            body,
            textvariable=self.detail_value,
            style="Muted.TLabel",
            wraplength=555,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="e", pady=(16, 0))
        self.action_button = ttk.Button(
            actions,
            text="Batal" if self._cancelable else "Mohon tunggu…",
            command=self._cancel_or_close,
            state="normal" if self._cancelable else "disabled",
        )
        self.action_button.pack(side="right")

    def _poll_events(self) -> None:
        if self._destroyed or not self.winfo_exists():
            return
        terminal = False
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "update" and isinstance(payload, ProgressUpdate):
                self._apply_update(payload)
            elif kind == "success":
                self.result = payload
                self._finish_success()
                terminal = True
            elif kind == "cancelled":
                self.was_cancelled = True
                self.error = payload if isinstance(payload, BaseException) else None
                self._finish_cancelled(str(payload))
                terminal = True
            elif kind == "error":
                self.error = (
                    payload
                    if isinstance(payload, BaseException)
                    else RuntimeError(str(payload))
                )
                self._finish_error(str(payload))
                terminal = True
        if not terminal and not self._finished:
            self.after(60, self._poll_events)

    def _apply_update(self, update: ProgressUpdate) -> None:
        self.stage_value.set(_stage_label(update.stage))
        self.status_value.set(update.message)
        self.detail_value.set(update.detail)
        percent = update.percent
        if percent is None:
            self.percent_value.set("")
            self._set_indeterminate(True)
            return
        self._set_indeterminate(False)
        self.progress.configure(mode="determinate", maximum=100, value=percent)
        self.percent_value.set(f"{percent}%")

    def _set_indeterminate(self, enabled: bool) -> None:
        if enabled:
            if not self._indeterminate_running:
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
                self._indeterminate_running = True
            return
        if self._indeterminate_running:
            self.progress.stop()
            self._indeterminate_running = False

    def _finish_success(self) -> None:
        self._finished = True
        self._set_indeterminate(False)
        self.progress.configure(mode="determinate", maximum=100, value=100)
        self.percent_value.set("100%")
        self.stage_value.set("Selesai")
        self.status_value.set("Proses berhasil diselesaikan.")
        self.action_button.configure(
            text="Selesai",
            state="normal",
            command=self._close,
        )
        self.after(self._auto_close_ms, self._close)

    def _finish_cancelled(self, message: str) -> None:
        self._finished = True
        self._set_indeterminate(False)
        self.stage_value.set("Dibatalkan")
        self.status_value.set(message or "Proses dibatalkan oleh pengguna.")
        self.percent_value.set("")
        self.action_button.configure(
            text="Tutup",
            state="normal",
            command=self._close,
        )
        self.after(max(500, self._auto_close_ms), self._close)

    def _finish_error(self, message: str) -> None:
        self._finished = True
        self._set_indeterminate(False)
        self.stage_value.set("Proses gagal")
        self.status_value.set("Terjadi kesalahan saat menjalankan proses.")
        self.detail_value.set(message)
        self.percent_value.set("")
        self.action_button.configure(
            text="Tutup",
            state="normal",
            command=self._close,
        )

    def _cancel_or_close(self) -> None:
        if self._finished:
            self._close()
            return
        if not self._cancelable:
            return
        self._cancel_event.set()
        self.status_value.set(
            "Permintaan pembatalan diterima. Menunggu tahap yang aman…"
        )
        self.action_button.configure(state="disabled")

    def _close(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._set_indeterminate(False)
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


def run_modal_progress(
    parent: tk.Misc,
    *,
    title: str,
    initial_message: str,
    operation: TaskOperation[_T],
    cancelable: bool = False,
    auto_close_ms: int = 350,
) -> _T:
    """Run a worker while a modal progress dialog keeps Tk responsive."""

    dialog = ProgressTaskDialog(
        parent,
        title=title,
        initial_message=initial_message,
        cancelable=cancelable,
        auto_close_ms=auto_close_ms,
    )
    dialog.start(operation)
    parent.wait_window(dialog)
    if dialog.was_cancelled:
        raise OperationCancelledError("Proses dibatalkan oleh pengguna.")
    if dialog.error is not None:
        raise dialog.error
    return dialog.result


def _stage_label(stage: str) -> str:
    normalized = stage.strip().replace("_", " ").replace("-", " ")
    return normalized[:1].upper() + normalized[1:] if normalized else "Memproses"


__all__ = ["ProgressTaskDialog", "TaskOperation", "run_modal_progress"]
