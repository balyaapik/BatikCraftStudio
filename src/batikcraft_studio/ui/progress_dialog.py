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

    def cancelled_update(self, message: str = "Proses dibatalkan") -> None:
        self._events.put(("cancelled", message))

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
        self._cancellable = bool(cancellable)
        self._auto_close_ms = auto_close_ms

        self.title(title)
        self.geometry("640x460")
        self.minsize(560, 380)
        self.resizable(True, True)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._request_window_close)
        self.bind("<Escape>", self._request_window_close)

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
            wraplength=560,
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
            wraplength=560,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(4, 0))

        # Panel log seperti terminal: memperlihatkan proses generasi
        # (perangkat, model, langkah difusi) selagi berjalan.
        log_frame = ttk.LabelFrame(body, text="Log proses", padding=(6, 4))
        log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            height=10,
            wrap="none",
            state="disabled",
            background="#12100E",
            foreground="#E8DFD2",
            insertbackground="#E8DFD2",
            font=("Consolas", 9),
            borderwidth=0,
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)
        body.rowconfigure(4, weight=1)

        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, sticky="e", pady=(12, 0))
        self.cancel_button = ttk.Button(actions, text="Batal", command=self.cancel)
        if self._cancellable:
            self.cancel_button.pack(side="right")

        self.grab_set()
        self.after(80, self._poll)

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def post(self, update: ProgressUpdate) -> None:
        self._events.put(update)

    def log_line(self, message: str) -> None:
        """Tambahkan satu baris ke panel log (aman dipanggil dari worker)."""

        self._events.put(("log", message))

    def _append_log(self, message: str) -> None:
        from datetime import datetime

        widget = getattr(self, "log", None)
        if widget is None or not widget.winfo_exists():
            return
        widget.configure(state="normal")
        widget.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        try:
            lines = int(widget.index("end-1c").split(".")[0])
            if lines > 800:
                widget.delete("1.0", f"{lines - 800}.0")
        except (tk.TclError, ValueError):
            pass
        widget.see("end")
        widget.configure(state="disabled")

    def finish(self, message: str = "Selesai") -> None:
        self._events.put(("complete", message))

    def mark_cancelled(self, message: str = "Proses dibatalkan") -> None:
        self._events.put(("cancelled", message))

    def fail(self, message: str) -> None:
        self._events.put(("error", message))

    def _request_window_close(self, _event: object | None = None) -> None:
        """Close finished dialogs while protecting non-cancellable active work."""

        if self._finished:
            self.close()
            return
        if self._cancellable:
            self.cancel()
            return
        try:
            self.bell()
        except tk.TclError:
            pass

    def cancel(self) -> None:
        if self._finished:
            self.close()
            return
        if not self._cancellable:
            try:
                self.bell()
            except tk.TclError:
                pass
            return
        self._cancel_event.set()
        self.message_value.set("Membatalkan proses…")
        self.detail_value.set("Menghentikan stream aktif dan menyimpan data yang aman.")
        self.cancel_button.configure(state="disabled")

    def close(self) -> None:
        if not self.winfo_exists():
            return
        try:
            if self.grab_current() is self:
                self.grab_release()
        except tk.TclError:
            pass
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
        if isinstance(event, tuple) and len(event) == 2 and event[0] == "log":
            self._append_log(str(event[1]))
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
            return
        if kind == "cancelled":
            self.percent_value.set("Dibatalkan")
            self.message_value.set("Proses dibatalkan")
            self.detail_value.set(str(payload))
        else:
            self.progress.configure(mode="determinate", maximum=100, value=0)
            self.percent_value.set("")
            self.message_value.set("Proses gagal")
            self.detail_value.set(str(payload))
        self.cancel_button.configure(text="Tutup", state="normal", command=self.close)
        if not self.cancel_button.winfo_manager():
            self.cancel_button.pack(side="right")
        self.cancel_button.focus_set()


__all__ = ["ProgressDialog", "ProgressReporter", "ProgressUpdate"]
