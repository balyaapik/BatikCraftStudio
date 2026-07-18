"""Standalone dependency status and installer window for BatikCraft Studio."""

from __future__ import annotations

import importlib.util
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.ai import default_ai_cache_dir
from batikcraft_studio.ai.runtime_model_installer import (
    find_installed_batikbrew_runtime,
    find_installed_runtime_models,
)
from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    default_managed_ai_package_dir,
    managed_ai_install_command,
)

PYTHON_AI_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("torch", "torch>=2.4"),
    ("diffusers", "diffusers>=0.39,<0.40"),
    ("transformers", "transformers>=4.48,<5"),
    ("accelerate", "accelerate>=1.2"),
    ("huggingface_hub", "huggingface-hub>=0.27"),
    ("peft", "peft>=0.17"),
    ("safetensors", "safetensors>=0.4"),
    ("numpy", "numpy>=1.26,<3"),
    ("openai", "openai>=1.0,<3"),
    ("google.genai", "google-genai>=1.0,<2"),
    ("keyring", "keyring>=25,<27"),
)


class DependencyManagerWindow(tk.Toplevel):
    """Show and install every optional AI component from one GUI window."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        install_sdxl: Callable[[], object],
        install_sd15: Callable[[], object],
        manage_lora: Callable[[], object],
    ) -> None:
        super().__init__(parent)
        self.install_sdxl = install_sdxl
        self.install_sd15 = install_sd15
        self.manage_lora = manage_lora
        self._process: subprocess.Popen[object] | None = None
        self._messages: queue.Queue[str] = queue.Queue()
        self._install_succeeded = False
        self._continue_with_sdxl = False

        self.title("Dependencies")
        self.geometry("900x680")
        self.minsize(780, 580)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self.refresh()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(
            body,
            text="BatikCraft AI Setup",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Paket Python AI, pengunduh model, dan BatikBrew dapat dipasang langsung "
                "dari aplikasi. Pengguna tidak perlu mencari Python, pip, atau dependency "
                "melalui terminal."
            ),
            style="Muted.TLabel",
            wraplength=840,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        quick_setup = ttk.LabelFrame(body, text="Instalasi Sekali Klik", padding=12)
        quick_setup.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        quick_setup.columnconfigure(0, weight=1)
        ttk.Label(
            quick_setup,
            text=(
                "Memasang atau memperbaiki seluruh paket AI ke folder runtime BatikCraft, "
                "lalu otomatis membuka unduhan model BatikBrew SDXL."
            ),
            wraplength=660,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self.install_all_button = ttk.Button(
            quick_setup,
            text="Instal Semua AI + BatikBrew SDXL",
            command=self.install_complete_batikbrew,
        )
        self.install_all_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        content = ttk.PanedWindow(body, orient=tk.VERTICAL)
        content.grid(row=3, column=0, sticky="nsew")

        packages = ttk.LabelFrame(content, text="Python AI Packages", padding=10)
        packages.columnconfigure(0, weight=1)
        packages.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            packages,
            columns=("requirement", "status"),
            show="headings",
            height=9,
        )
        self.tree.heading("requirement", text="Dependency")
        self.tree.heading("status", text="Status")
        self.tree.column("requirement", width=500)
        self.tree.column("status", width=180)
        self.tree.grid(row=0, column=0, sticky="nsew")
        package_actions = ttk.Frame(packages)
        package_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.install_packages_button = ttk.Button(
            package_actions,
            text="Instal / Reparasi Paket AI",
            command=self.install_python_dependencies,
        )
        self.install_packages_button.pack(side="left")
        ttk.Button(package_actions, text="Refresh", command=self.refresh).pack(
            side="left",
            padx=(8, 0),
        )
        self.package_location = tk.StringVar(master=self)
        ttk.Label(
            packages,
            textvariable=self.package_location,
            style="Muted.TLabel",
            wraplength=820,
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        content.add(packages, weight=1)

        runtime = ttk.LabelFrame(content, text="Runtime, Base Model & LoRA", padding=10)
        runtime.columnconfigure(0, weight=1)
        self.runtime_status = tk.StringVar(master=self)
        ttk.Label(
            runtime,
            textvariable=self.runtime_status,
            justify="left",
            wraplength=820,
        ).grid(row=0, column=0, sticky="ew")
        runtime_actions = ttk.Frame(runtime)
        runtime_actions.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(
            runtime_actions,
            text="Unduh / Instal BatikBrew SDXL…",
            command=self.install_sdxl,
        ).pack(side="left")
        ttk.Button(
            runtime_actions,
            text="Unduh / Instal SD1.5 + ControlNet…",
            command=self.install_sd15,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            runtime_actions,
            text="Instal / Kelola LoRA…",
            command=self.manage_lora,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            runtime_actions,
            text="Buka Folder Unduhan AI",
            command=lambda: reveal_path(default_ai_cache_dir()),
        ).pack(side="left", padx=(8, 0))
        content.add(runtime, weight=0)

        log_frame = ttk.LabelFrame(content, text="Log Instalasi", padding=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=9, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        content.add(log_frame, weight=1)

        footer = ttk.Frame(body)
        footer.grid(row=4, column=0, sticky="e", pady=(12, 0))
        self.cancel_button = ttk.Button(
            footer,
            text="Hentikan Instalasi",
            command=self.cancel_installation,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Tutup", command=self._close).pack(side="right")

    def refresh(self) -> None:
        activate_managed_ai_packages()
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        for module, requirement in PYTHON_AI_DEPENDENCIES:
            installed = module_available(module)
            self.tree.insert(
                "",
                tk.END,
                values=(requirement, "Terpasang" if installed else "Belum terpasang"),
            )
        package_dir = default_managed_ai_package_dir()
        self.package_location.set(f"Folder runtime terkelola: {package_dir}")
        sdxl = find_installed_batikbrew_runtime()
        sd15 = find_installed_runtime_models()
        self.runtime_status.set(
            "BatikBrew SDXL: "
            + (str(sdxl.base_model) if sdxl is not None else "belum terpasang")
            + "\nSD1.5 + ControlNet: "
            + (str(sd15.base_model) if sd15 is not None else "belum terpasang")
            + "\nLoRA: buka pengelola model untuk instalasi paket .batikmodel."
        )

    def install_complete_batikbrew(self) -> None:
        """Install Python dependencies and continue into the SDXL model installer."""

        if self._process is not None:
            self._installation_already_running()
            return
        self._continue_with_sdxl = True
        missing = self._missing_requirements()
        if not missing:
            self._append_log("Semua paket AI sudah tersedia. Membuka installer BatikBrew SDXL…")
            self.after(150, self.install_sdxl)
            return
        self.install_python_dependencies(continue_with_sdxl=True)

    def install_python_dependencies(self, *, continue_with_sdxl: bool = False) -> None:
        if self._process is not None:
            self._installation_already_running()
            return

        self._continue_with_sdxl = continue_with_sdxl
        requirements = [requirement for _module, requirement in PYTHON_AI_DEPENDENCIES]
        target = default_managed_ai_package_dir()
        target.parent.mkdir(parents=True, exist_ok=True)
        frozen = bool(getattr(sys, "frozen", False))
        log_path = target.parent / "dependency-install.log"
        if log_path.exists():
            log_path.unlink()
        command = managed_ai_install_command(
            requirements,
            target=target,
            frozen=frozen,
            log_file=log_path if frozen else None,
        )
        self._append_log(f"Menyiapkan runtime AI terkelola di {target}")
        self._append_log("Seluruh paket dipasang otomatis; jendela terminal tidak diperlukan.")
        self._set_installing(True)
        self._install_succeeded = False

        def worker() -> None:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                if frozen:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=flags,
                    )
                    self._process = process
                    self._stream_log_file(process, log_path)
                else:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=flags,
                    )
                    self._process = process
                    assert process.stdout is not None
                    for line in process.stdout:
                        self._messages.put(line.rstrip())
                code = process.wait()
                self._install_succeeded = code == 0
                self._messages.put(
                    "Paket AI berhasil dipasang ke runtime BatikCraft."
                    if code == 0
                    else f"Instalasi paket AI gagal (kode {code}). Tekan instal lagi untuk reparasi."
                )
            except OSError as exc:
                self._messages.put(f"Instalasi tidak dapat dimulai: {exc}")
            finally:
                self._process = None
                self._messages.put("__DONE__")

        threading.Thread(target=worker, daemon=True, name="batikcraft-dependencies").start()
        self.after(100, self._poll_messages)

    def _stream_log_file(self, process: subprocess.Popen[object], log_path: Path) -> None:
        offset = 0
        pending = ""
        while process.poll() is None:
            offset, pending = self._read_new_log(log_path, offset, pending)
            time.sleep(0.15)
        _offset, pending = self._read_new_log(log_path, offset, pending)
        if pending.strip():
            self._messages.put(pending.strip())

    def _read_new_log(self, path: Path, offset: int, pending: str) -> tuple[int, str]:
        if not path.is_file():
            return offset, pending
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
        except OSError:
            return offset, pending
        if not chunk:
            return offset, pending
        pending += chunk
        lines = pending.splitlines(keepends=True)
        pending = ""
        for line in lines:
            if line.endswith(("\n", "\r")):
                text = line.rstrip("\r\n")
                if text:
                    self._messages.put(text)
            else:
                pending = line
        return offset, pending

    def _poll_messages(self) -> None:
        done = False
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break
            if message == "__DONE__":
                done = True
            else:
                self._append_log(message)
        if done:
            self._set_installing(False)
            if self._install_succeeded:
                activate_managed_ai_packages()
            self.refresh()
            continue_with_sdxl = self._continue_with_sdxl and self._install_succeeded
            self._continue_with_sdxl = False
            if continue_with_sdxl:
                self._append_log("Dependency siap. Membuka unduhan BatikBrew SDXL…")
                self.after(250, self.install_sdxl)
            return
        self.after(100, self._poll_messages)

    def _missing_requirements(self) -> list[str]:
        return [
            requirement
            for module, requirement in PYTHON_AI_DEPENDENCIES
            if not module_available(module)
        ]

    def _installation_already_running(self) -> None:
        messagebox.showinfo(
            "Instalasi berjalan",
            "Tunggu atau hentikan instalasi yang sedang berjalan.",
            parent=self,
        )

    def _set_installing(self, installing: bool) -> None:
        state = "disabled" if installing else "normal"
        self.install_all_button.configure(state=state)
        self.install_packages_button.configure(state=state)
        self.cancel_button.configure(state="normal" if installing else "disabled")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def cancel_installation(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            self._append_log("Permintaan penghentian dikirim. File yang sudah ada dipertahankan.")

    def _close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            if not messagebox.askyesno(
                "Instalasi masih berjalan",
                "Tutup jendela dan hentikan instalasi?",
                parent=self,
            ):
                return
            self.cancel_installation()
        self.destroy()


def module_available(module: str) -> bool:
    """Check import availability without importing heavyweight AI packages."""

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def reveal_path(path: str | Path) -> None:
    """Open one folder with the native file manager."""

    target = Path(path).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError as exc:
        raise RuntimeError(f"Folder tidak dapat dibuka: {target}") from exc


__all__ = [
    "DependencyManagerWindow",
    "PYTHON_AI_DEPENDENCIES",
    "module_available",
    "reveal_path",
]
