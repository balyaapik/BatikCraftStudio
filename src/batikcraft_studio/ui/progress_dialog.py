"""Reusable, thread-safe progress feedback for long-running desktop tasks."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """One progress message emitted by a worker thread."""

    message: str
    completed: float | None = None
    total: float | None = None
    detail: str = ""

    @property
    def determinate(self) -> bool:
        return self.completed is not None and self.total is not None and self.total > 0

    @property
    def percent(self) -> int | None:
        if not self.determinate:
            return None
        assert self.completed is not None and self.total is not None
        value = max(0.0, min(float(self.completed), float(self.total)))
        return round(value / float(self.total) * 100)


class ProgressReporter:
    """Worker-facing API that never touches Tk widgets directly."""

    def __init__(self, events: queue.Queue[object], cancel_event: threading.Event) -> None:
        self._events = events
        self.cancel_event = cancel_event

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def update(
        self,
        message: str,
        completed: float | None = None,
        total: float | None = None,
        *,
        detail: str = "",
    ) -> None:
        self._events.put(ProgressUpdate(message, completed, total, detail))

    def complete(self, message: str = "Selesai") -> None:
        self._events.put(("complete", message))

    def fail(self, message: str) -> None:
        self._events.put(("error", message))


class ProgressDialog(tk.Toplevel):
    """Modal progress window supporting determinate and indeterminate work."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        message: str,
        cancellable: bool = False,
        auto_close_ms: int | None = 700,
    ) -> None:
        super().__init__(parent)
        self._events: queue.Queue[object] = queue.Queue()
        self._cancel_event = threading.Event()
        self.reporter = ProgressReporter(self._events, self._cancel_event)
        self._finished = False
        self._auto_close_ms = auto_close_ms

        self.title(title)
        self.geometry("560x220")
        self.minsize(500, 210)
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel if cancellable else lambda: None)

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        self.message_value = tk.StringVar(master=self, value=message)
        self.detail_value = tk.StringVar(master=self, value="")
        self.percent_value = tk.StringVar(master=self, value="")

        ttk.Label(
            body,
            textvariable=self.message_value,
            font=("TkDefaultFont", 11, "bold"),
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(14, 5))
        self.progress.start(12)
        ttk.Label(body, textvariable=self.percent_value, anchor="e").grid(
            row=2, column=0, sticky="e"
        )
        ttk.Label(
            body,
            textvariable=self.detail_value,
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(4, 0))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="e", pady=(14, 0))
        self.cancel_button = ttk.Button(actions, text="Batal", command=self.cancel)
        if cancellable:
            self.cancel_button.pack(side="right")

        self.grab_set()
        self.after(80, self._poll)

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def post(self, update: ProgressUpdate) -> None:
        self._events.put(update)

    def finish(self, message: str = "Selesai") -> None:
        self._events.put(("complete", message))

    def fail(self, message: str) -> None:
        self._events.put(("error", message))

    def cancel(self) -> None:
        if self._finished:
            self.destroy()
            return
        self._cancel_event.set()
        self.message_value.set("Membatalkan proses…")
        self.detail_value.set("Menunggu tahap aktif berhenti dengan aman.")
        self.cancel_button.configure(state="disabled")

    def close(self) -> None:
        if self.winfo_exists():
            self.destroy()

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                event = self._events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        if not self._finished:
            self.after(80, self._poll)

    def _handle(self, event: object) -> None:
        if isinstance(event, ProgressUpdate):
            self.message_value.set(event.message)
            self.detail_value.set(event.detail)
            if event.determinate:
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=100, value=event.percent or 0)
                self.percent_value.set(f"{event.percent or 0}%")
            else:
                self.percent_value.set("")
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            return
        if not isinstance(event, tuple) or len(event) != 2:
            return
        kind, payload = event
        self._finished = True
        self.progress.stop()
        if kind == "complete":
            self.progress.configure(mode="determinate", maximum=100, value=100)
            self.percent_value.set("100%")
            self.message_value.set(str(payload))
            self.detail_value.set("")
            if self._auto_close_ms is not None:
                self.after(self._auto_close_ms, self.close)
        else:
            self.progress.configure(mode="determinate", maximum=100, value=0)
            self.percent_value.set("")
            self.message_value.set("Proses gagal")
            self.detail_value.set(str(payload))
            self.cancel_button.configure(text="Tutup", state="normal", command=self.close)
            if not self.cancel_button.winfo_manager():
                self.cancel_button.pack(side="right")


__all__ = ["ProgressDialog", "ProgressReporter", "ProgressUpdate"]
