"""Responsive Tk dialog for installing managed AI runtimes."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import ttk

from batikcraft_studio.ai.runtime_model_installer import (
    BatikBrewRuntimePaths,
    RuntimeModelInstallProgress,
    RuntimeModelPaths,
    batikbrew_runtime_model_paths,
    default_runtime_model_root,
    runtime_model_paths,
)
from batikcraft_studio.dependency_bootstrap import default_managed_dependency_root
from batikcraft_studio.runtime_model_process import runtime_model_install_command

_DOWNLOAD_STAGES = {"base", "controlnet", "sdxl"}
_TERMINAL_EVENT_KINDS = {"complete", "cancelled", "error"}


class RuntimeModelInstallDialog(tk.Toplevel):
    """Download either the legacy SD1.5 stack or BatikBrew SDXL runtime."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        install_root: str | Path | None = None,
        family: str = "sd15",
    ) -> None:
        super().__init__(parent)
        normalized = str(family).strip().casefold()
        if normalized not in {"sd15", "sdxl"}:
            raise ValueError("family harus sd15 atau sdxl")
        self.family = normalized
        self.result: RuntimeModelPaths | BatikBrewRuntimePaths | None = None
        self.install_root = (
            Path(install_root).expanduser()
            if install_root is not None
            else default_runtime_model_root()
        )
        self._events: queue.Queue[object] = queue.Queue()
        self._process: subprocess.Popen[object] | None = None
        self._monitor: threading.Thread | None = None
        self._cancel_requested = False
        self._finished = False
        self._size_note = ""
        event_directory = default_managed_dependency_root() / "logs"
        self._event_file = event_directory / (
            f"runtime-download-{self.family}-{uuid.uuid4().hex}.jsonl"
        )

        self.title("Instal Runtime AI BatikCraft")
        self.geometry("680x370")
        self.minsize(620, 340)
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

        if self.family == "sdxl":
            heading = "Instal BatikBrew — Stable Diffusion XL"
            description = (
                "Runtime ini sama dengan base model pada notebook BatikCraft. "
                "SDXL dan LoRA BatikBrew digunakan untuk menghasilkan motif baru dari "
                "analisis objek inspirasi, bukan untuk menempelkan tekstur pada objek."
            )
            self._size_note = "Unduhan SDXL sekitar 7 GB. File parsial dapat dilanjutkan."
        else:
            heading = "Instal Stable Diffusion 1.5 + ControlNet"
            description = (
                "Runtime legacy untuk workflow img2img/ControlNet. Internet hanya "
                "diperlukan saat instalasi pertama."
            )
            self._size_note = (
                "Jika koneksi terputus, instalasi dapat dilanjutkan tanpa mengulang."
            )

        ttk.Label(
            body,
            text=heading,
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=description,
            wraplength=635,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 4))

        ttk.Label(body, text="Lokasi penyimpanan:").grid(
            row=2,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        path_entry = ttk.Entry(body)
        path_entry.insert(0, str(self.install_root))
        path_entry.configure(state="readonly")
        path_entry.grid(row=3, column=0, sticky="ew", pady=(2, 10))

        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=4, column=0, sticky="ew")
        self.percent = ttk.Label(
            body,
            text="",
            anchor="e",
            style="Muted.TLabel",
        )
        self.percent.grid(row=5, column=0, sticky="e", pady=(3, 0))
        self.status = ttk.Label(
            body,
            text="Menyiapkan instalasi…",
            wraplength=635,
            justify="left",
        )
        self.status.grid(row=6, column=0, sticky="ew", pady=(8, 4))
        self.detail = ttk.Label(
            body,
            text=self._size_note,
            style="Muted.TLabel",
            wraplength=635,
            justify="left",
        )
        self.detail.grid(row=7, column=0, sticky="ew")

        actions = ttk.Frame(body)
        actions.grid(row=8, column=0, sticky="e", pady=(14, 0))
        self.action_button = ttk.Button(
            actions,
            text="Batal",
            command=self._cancel_or_close,
        )
        self.action_button.pack(side="right")

    def _start_install(self) -> None:
        if self._process is not None or self._finished:
            return
        self._event_file.parent.mkdir(parents=True, exist_ok=True)
        self._event_file.unlink(missing_ok=True)
        command = runtime_model_install_command(
            self.family,
            root=self.install_root,
            event_file=self._event_file,
        )
        creation_flags = 0
        start_new_session = False
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NO_WINDOW
            creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                start_new_session=start_new_session,
            )
        except OSError as exc:
            self._finish(f"Proses unduhan tidak dapat dimulai: {exc}", success=False)
            return

        self.progress.start(12)
        self._monitor = threading.Thread(
            target=self._monitor_process,
            args=(self._process,),
            name=f"batikcraft-runtime-monitor-{self.family}",
            daemon=True,
        )
        self._monitor.start()
        self.after(100, self._poll_events)

    def _monitor_process(self, process: subprocess.Popen[object]) -> None:
        offset = 0
        pending = ""
        saw_terminal_event = False
        while process.poll() is None:
            offset, pending, terminal = self._read_new_events(offset, pending)
            saw_terminal_event = saw_terminal_event or terminal
            time.sleep(0.10)
        offset, pending, terminal = self._read_new_events(offset, pending)
        saw_terminal_event = saw_terminal_event or terminal
        if pending.strip():
            saw_terminal_event = self._enqueue_event_line(pending.strip()) or saw_terminal_event
        code = process.wait()
        cancelled = self._cancel_requested
        if not cancelled and not saw_terminal_event:
            if code == 0:
                self._events.put(("complete", self.family))
            else:
                self._events.put(
                    ("error", f"Proses unduhan model berhenti dengan kode {code}.")
                )
        self._process = None
        try:
            self._event_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _read_new_events(
        self,
        offset: int,
        pending: str,
    ) -> tuple[int, str, bool]:
        if not self._event_file.is_file():
            return offset, pending, False
        try:
            with self._event_file.open(
                "r",
                encoding="utf-8",
                errors="replace",
            ) as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
        except OSError:
            return offset, pending, False
        if not chunk:
            return offset, pending, False
        pending += chunk
        lines = pending.splitlines(keepends=True)
        pending = ""
        terminal = False
        for line in lines:
            if line.endswith(("\n", "\r")):
                terminal = self._enqueue_event_line(line.rstrip("\r\n")) or terminal
            else:
                pending = line
        return offset, pending, terminal

    def _enqueue_event_line(self, line: str) -> bool:
        if not line.strip():
            return False
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
        kind = str(payload.get("kind", ""))
        if kind == "progress":
            try:
                event = RuntimeModelInstallProgress(
                    stage=str(payload.get("stage", "")),
                    message=str(payload.get("message", "")),
                    completed=int(payload.get("completed", 0)),
                    total=int(payload.get("total", 4)),
                    downloaded_bytes=int(payload.get("downloaded_bytes", 0)),
                    total_bytes=int(payload.get("total_bytes", 0)),
                    current_file=str(payload.get("current_file", "")),
                )
            except (TypeError, ValueError):
                return False
            self._events.put(event)
            return False
        if kind == "complete":
            self._events.put(("complete", str(payload.get("family", self.family))))
        elif kind in {"cancelled", "error"}:
            self._events.put((kind, str(payload.get("message", ""))))
        return kind in _TERMINAL_EVENT_KINDS

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
            self._show_progress(event)
            return
        if not isinstance(event, tuple) or len(event) != 2:
            return
        kind, payload = event
        if kind == "complete":
            self.result = (
                batikbrew_runtime_model_paths(self.install_root)
                if self.family == "sdxl"
                else runtime_model_paths(self.install_root)
            )
            label = (
                "Runtime BatikBrew SDXL" if self.family == "sdxl" else "Runtime AI"
            )
            self._finish(
                f"{label} berhasil dipasang. Tekan Selesai untuk kembali.",
                success=True,
            )
        elif kind == "cancelled":
            self._finish(str(payload), success=False, cancelled=True)
        elif kind == "error":
            self._finish(str(payload), success=False)

    def _show_progress(self, event: RuntimeModelInstallProgress) -> None:
        stage_number = max(0, min(event.completed, event.total))
        self.status.configure(
            text=f"Tahap {stage_number}/{event.total} — {event.message}"
        )

        if event.stage in _DOWNLOAD_STAGES and event.total_bytes > 0:
            percent = event.download_percent or 0.0
            self.progress.stop()
            self.progress.configure(
                mode="determinate",
                maximum=100,
                value=percent,
            )
            self.percent.configure(
                text=(
                    f"{percent:.1f}% · "
                    f"{_format_bytes(event.downloaded_bytes)} / "
                    f"{_format_bytes(event.total_bytes)}"
                )
            )
            detail = self._size_note
            if event.current_file:
                detail = f"File aktif: {event.current_file}"
            self.detail.configure(text=detail)
            return

        if event.stage in _DOWNLOAD_STAGES:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.percent.configure(text="Menghitung ukuran unduhan…")
            self.detail.configure(text=self._size_note)
            return

        self.progress.stop()
        self.progress.configure(
            mode="determinate",
            maximum=event.total,
            value=event.completed,
        )
        percent = round(event.completed / event.total * 100) if event.total else 0
        self.percent.configure(text=f"{percent}%")
        self.detail.configure(text=self._size_note)

    def _finish(
        self,
        message: str,
        *,
        success: bool,
        cancelled: bool = False,
    ) -> None:
        self._finished = True
        self.progress.stop()
        if success:
            self.progress.configure(mode="determinate", maximum=1, value=1)
            self.percent.configure(text="100%")
        elif cancelled:
            self.progress.configure(mode="determinate", maximum=1, value=0)
            self.percent.configure(text="Dibatalkan")
        else:
            self.percent.configure(text="")
        self.status.configure(text=message)
        if success:
            detail = "Model tersimpan di folder dependencies dan ditemukan otomatis."
        elif cancelled:
            detail = (
                "Proses unduhan dihentikan. File parsial tetap disimpan; jendela dapat "
                "ditutup sekarang."
            )
        else:
            detail = "File parsial tetap disimpan dan dapat dilanjutkan nanti."
        self.detail.configure(text=detail)
        self.action_button.configure(
            text="Selesai" if success else "Tutup",
            command=self.destroy,
            state="normal",
        )

    def _cancel_or_close(self) -> None:
        if self._finished:
            self.destroy()
            return
        if self._cancel_requested:
            self.destroy()
            return
        self._cancel_requested = True
        process = self._process
        if process is not None and process.poll() is None:
            threading.Thread(
                target=self._terminate_process_tree,
                args=(process,),
                daemon=True,
                name=f"batikcraft-stop-runtime-{self.family}",
            ).start()
        self._finish(
            "Unduhan dibatalkan dan proses transfer sedang dihentikan.",
            success=False,
            cancelled=True,
        )

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[object]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                    timeout=5,
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            try:
                process.terminate()
            except OSError:
                return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            except (OSError, ProcessLookupError):
                pass


def _format_bytes(value: int) -> str:
    size = max(0, int(value))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(size)
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            precision = 0 if unit == "B" else 2
            return f"{amount:.{precision}f} {unit}"
        amount /= 1024.0
    return f"{size} B"


__all__ = ["RuntimeModelInstallDialog"]
