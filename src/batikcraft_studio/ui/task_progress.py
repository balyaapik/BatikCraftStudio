"""Reusable, thread-safe progress feedback for long-running Tk tasks."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class TaskProgressUpdate:
    """One progress update produced by a worker thread."""

    message: str
    completed: float | None = None
    total: float | None = None
    detail: str = ""


class TaskCancelled(RuntimeError):
    """Raised when a cancellable worker notices a cancellation request."""


class TaskProgressReporter:
    """Worker-facing reporter that never touches Tk widgets directly."""

    def __init__(self, events: queue.Queue[object], cancel_event: threading.Event) -> None:
        self._events = events
        self._cancel_event = cancel_event

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled("Proses dibatalkan oleh pengguna.")

    def indeterminate(self, message: str, *, detail: str = "") -> None:
        self._events.put(TaskProgressUpdate(message=message, detail=detail))

    def update(
        self,
        completed: float,
        total: float,
        message: str,
        *,
        detail: str = "",
    ) -> None:
        self._events.put(
            TaskProgressUpdate(
                message=message,
                completed=completed,
                total=total,
                detail=detail,
            )
        )


TaskWorker = Callable[[TaskProgressReporter], Any]
SuccessCallback = Callable[[Any], object]
ErrorCallback = Callable[[BaseException], object]


class TaskProgressDialog(tk.Toplevel):
    """Modal progress dialog with determinate and indeterminate modes."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial_message: str,
        cancellable: bool = False,
        auto_close_ms: int = 650,
    ) -> None:
        super().__init__(parent)
        self._events: queue.Queue[object] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._finished = False
        self._cancellable = cancellable
        self._auto_close_ms = max(0, int(auto_close_ms))

        self.title(title)
        self.geometry("560x220")
        self.minsize(500, 205)
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel_or_close)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text=title, font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.status = ttk.Label(
            body,
            text=initial_message,
            wraplength=520,
            justify="left",
        )
        self.status.grid(row=1, column=0, sticky="ew", pady=(10, 8))

        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=2, column=0, sticky="ew")
        self.progress.start(12)

        self.percent = ttk.Label(body, text="", style="Muted.TLabel")
        self.percent.grid(row=3, column=0, sticky="e", pady=(4, 0))
        self.detail = ttk.Label(
            body,
            text="",
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        )
        self.detail.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, sticky="e", pady=(14, 0))
        self.action_button = ttk.Button(
            actions,
            text="Batal" if cancellable else "Tutup",
            command=self._cancel_or_close,
            state=tk.NORMAL if cancellable else tk.DISABLED,
        )
        self.action_button.pack(side="right")

        self.grab_set()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    def run(
        self,
        worker: TaskWorker,
        *,
        on_success: SuccessCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        """Run one worker and relay all progress safely to the Tk main thread."""

        if self._worker is not None:
            raise RuntimeError("Task progress dialog sudah menjalankan worker.")

        def target() -> None:
            reporter = TaskProgressReporter(self._events, self._cancel_event)
            try:
                result = worker(reporter)
            except BaseException as exc:  # noqa: BLE001 - report worker failure to UI
                self._events.put(("error", exc, on_error))
            else:
                self._events.put(("success", result, on_success))

        self._worker = threading.Thread(
            target=target,
            daemon=True,
            name="batikcraft-progress-task",
        )
        self._worker.start()
        self.after(80, self._poll)

    def post(self, update: TaskProgressUpdate) -> None:
        """Allow existing workers to publish progress into this dialog."""

        self._events.put(update)

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                self._handle_event(self._events.get_nowait())
        except queue.Empty:
            pass
        if not self._finished:
            self.after(80, self._poll)

    def _handle_event(self, event: object) -> None:
        if isinstance(event, TaskProgressUpdate):
            self._apply_update(event)
            return
        if not isinstance(event, tuple) or len(event) != 3:
            return
        kind, payload, callback = event
        if kind == "success":
            self._finish_success(payload, callback)
        elif kind == "error" and isinstance(payload, BaseException):
            self._finish_error(payload, callback)

    def _apply_update(self, update: TaskProgressUpdate) -> None:
        self.status.configure(text=update.message)
        self.detail.configure(text=update.detail)
        if update.completed is None or update.total is None or update.total <= 0:
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.stop()
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            self.percent.configure(text="")
            return

        completed = max(0.0, min(float(update.completed), float(update.total)))
        total = float(update.total)
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=total, value=completed)
        self.percent.configure(text=f"{round(completed / total * 100)}%")

    def _finish_success(self, result: object, callback: object) -> None:
        self._finished = True
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=1)
        self.percent.configure(text="100%")
        self.status.configure(text="Selesai")
        self.action_button.configure(text="Tutup", state=tk.NORMAL, command=self.destroy)
        if callable(callback):
            callback(result)
        if self._auto_close_ms:
            self.after(self._auto_close_ms, self._safe_destroy)

    def _finish_error(self, error: BaseException, callback: object) -> None:
        self._finished = True
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=0)
        self.percent.configure(text="")
        self.status.configure(text="Proses gagal")
        self.detail.configure(text=str(error))
        self.action_button.configure(text="Tutup", state=tk.NORMAL, command=self.destroy)
        if callable(callback):
            callback(error)

    def _cancel_or_close(self) -> None:
        if self._finished:
            self.destroy()
            return
        if not self._cancellable:
            return
        self._cancel_event.set()
        self.status.configure(text="Membatalkan proses…")
        self.detail.configure(text="Menunggu tahap aktif berhenti dengan aman.")
        self.action_button.configure(state=tk.DISABLED)

    def _safe_destroy(self) -> None:
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass


__all__ = [
    "TaskCancelled",
    "TaskProgressDialog",
    "TaskProgressReporter",
    "TaskProgressUpdate",
]
