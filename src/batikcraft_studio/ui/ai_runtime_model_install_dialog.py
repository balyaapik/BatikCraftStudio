"""Responsive Tk dialog for installing the managed offline AI runtime."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from batikcraft_studio.ai.runtime_model_installer import (
    RuntimeModelInstallCancelled,
    RuntimeModelInstallError,
    RuntimeModelInstallProgress,
    RuntimeModelPaths,
    default_runtime_model_root,
    install_default_runtime_models,
)


class RuntimeModelInstallDialog(tk.Toplevel):
    """Download SD 1.5 and ControlNet on a worker thread with resumable state."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        install_root: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.result: RuntimeModelPaths | None = None
        self.install_root = (
            Path(install_root).expanduser()
            if install_root is not None
            else default_runtime_model_root()
        )
        self._events: queue.Queue[object] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._finished = False

        self.title("Instal Runtime AI BatikCraft")
        self.geometry("610x285")
        self.minsize(560, 260)
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel_or_close)
        self._build()
        self.grab_set()
        self.after(80, self._start_install)

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(
            body,
            text="Instal Stable Diffusion 1.5 + ControlNet",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "BatikCraft akan mengunduh model resmi ke folder aplikasi. "
                "Internet hanya diperlukan saat instalasi pertama; setelah selesai "
                "runtime dapat dipakai secara offline."
            ),
            wraplength=565,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 4))

        ttk.Label(body, text="Lokasi penyimpanan:").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        path_entry = ttk.Entry(body)
        path_entry.insert(0, str(self.install_root))
        path_entry.configure(state="readonly")
        path_entry.grid(row=3, column=0, sticky="ew", pady=(2, 10))

        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=4, column=0, sticky="ew")
        self.status = ttk.Label(
            body,
            text="Menyiapkan instalasi…",
            wraplength=565,
            justify="left",
        )
        self.status.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self.detail = ttk.Label(
            body,
            text=(
                "Jika koneksi terputus, tekan instal lagi. File yang sudah selesai "
                "tidak akan diunduh ulang."
            ),
            style="Muted.TLabel",
            wraplength=565,
            justify="left",
        )
        self.detail.grid(row=6, column=0, sticky="ew")

        actions = ttk.Frame(body)
        actions.grid(row=7, column=0, sticky="e", pady=(14, 0))
        self.action_button = ttk.Button(
            actions,
            text="Batal",
            command=self._cancel_or_close,
        )
        self.action_button.pack(side="right")

    def _start_install(self) -> None:
        if self._worker is not None:
            return
        self.progress.start(12)
        self._worker = threading.Thread(
            target=self._run_install,
            name="batikcraft-runtime-installer",
            daemon=True,
        )
        self._worker.start()
        self.after(100, self._poll_events)

    def _run_install(self) -> None:
        try:
            paths = install_default_runtime_models(
                self.install_root,
                progress=self._events.put,
                cancel_event=self._cancel_event,
            )
        except RuntimeModelInstallCancelled as exc:
            self._events.put(("cancelled", str(exc)))
        except RuntimeModelInstallError as exc:
            self._events.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 - keep worker failures visible in UI
            self._events.put(("error", f"Instalasi gagal: {exc}"))
        else:
            self._events.put(("complete", paths))

    def _poll_events(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                event = self._events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        if not self._finished:
            self.after(100, self._poll_events)

    def _handle_event(self, event: object) -> None:
        if isinstance(event, RuntimeModelInstallProgress):
            self.status.configure(text=event.message)
            if event.stage in {"base", "controlnet"}:
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            else:
                self.progress.stop()
                self.progress.configure(
                    mode="determinate",
                    maximum=event.total,
                    value=event.completed,
                )
            return

        if not isinstance(event, tuple) or len(event) != 2:
            return
        kind, payload = event
        if kind == "complete" and isinstance(payload, RuntimeModelPaths):
            self.result = payload
            self._finish(
                "Runtime AI berhasil dipasang. Tekan Selesai untuk kembali ke pengelola model.",
                success=True,
            )
        elif kind == "cancelled":
            self._finish(str(payload), success=False)
        elif kind == "error":
            self._finish(str(payload), success=False)

    def _finish(self, message: str, *, success: bool) -> None:
        self._finished = True
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=1 if success else 0)
        self.status.configure(text=message)
        self.detail.configure(
            text=(
                "Model tersimpan di folder aplikasi dan akan ditemukan otomatis."
                if success
                else "File parsial tetap disimpan dan instalasi dapat dilanjutkan nanti."
            )
        )
        self.action_button.configure(text="Selesai" if success else "Tutup", command=self.destroy)

    def _cancel_or_close(self) -> None:
        if self._finished:
            self.destroy()
            return
        self._cancel_event.set()
        self.status.configure(
            text="Membatalkan setelah tahap unduhan yang sedang aktif selesai…"
        )
        self.action_button.configure(state="disabled")


__all__ = ["RuntimeModelInstallDialog"]
