"""Standalone dependency status and installer window for BatikCraft Studio."""

from __future__ import annotations

import importlib.util
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.ai.runtime_model_installer import (
    find_installed_batikbrew_runtime,
    find_installed_runtime_models,
)
from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    default_managed_ai_package_dir,
    default_managed_dependency_log,
    default_managed_dependency_root,
    default_managed_pip_cache_dir,
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
        self._cancel_requested = False

        self.title("Dependencies")
        self.geometry("920x720")
        self.minsize(800, 620)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self.refresh()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(
            body,
            text="BatikCraft AI Setup",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Dua tab: instalasi (dependensi + model) dan log — sesuai kebutuhan
        # user agar jendela tidak panjang dan log tidak mengganggu.
        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        tab_host = ttk.Frame(self.notebook)
        tab_log = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab_host, text="Dependensi AI Lokal")
        self.notebook.add(tab_log, text="Log Instalasi")

        # Konten tab instalasi dapat digulir sehingga muat di layar pendek
        # (sebelumnya bagian bawah jendela terpotong/"rusak").
        tab_host.columnconfigure(0, weight=1)
        tab_host.rowconfigure(0, weight=1)
        tab_canvas = tk.Canvas(tab_host, highlightthickness=0, borderwidth=0)
        tab_canvas.grid(row=0, column=0, sticky="nsew")
        tab_scroll = ttk.Scrollbar(tab_host, orient="vertical", command=tab_canvas.yview)
        tab_scroll.grid(row=0, column=1, sticky="ns")
        tab_canvas.configure(yscrollcommand=tab_scroll.set)
        tab_main = ttk.Frame(tab_canvas, padding=10)
        _tab_window = tab_canvas.create_window((0, 0), window=tab_main, anchor="nw")

        def _sync_tab_scroll(_event: object = None) -> None:
            try:
                tab_canvas.configure(scrollregion=tab_canvas.bbox("all"))
                tab_canvas.itemconfigure(_tab_window, width=tab_canvas.winfo_width())
            except tk.TclError:
                pass

        tab_main.bind("<Configure>", _sync_tab_scroll)
        tab_canvas.bind("<Configure>", _sync_tab_scroll)

        def _tab_wheel(event: tk.Event) -> None:
            tab_canvas.yview_scroll(-1 if getattr(event, "delta", 0) > 0 else 1, "units")

        for widget in (tab_canvas, tab_main):
            widget.bind("<MouseWheel>", _tab_wheel)
        tab_canvas.bind("<Button-4>", lambda _e: tab_canvas.yview_scroll(-1, "units"))
        tab_canvas.bind("<Button-5>", lambda _e: tab_canvas.yview_scroll(1, "units"))

        tab_main.columnconfigure(0, weight=1)

        # --- Instalasi sekali klik -----------------------------------------
        quick_setup = ttk.LabelFrame(tab_main, text="Instalasi Sekali Klik", padding=12)
        quick_setup.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        quick_setup.columnconfigure(0, weight=1)
        ttk.Label(
            quick_setup,
            text=(
                "Satu tombol untuk memasang seluruh paket AI lokal beserta model "
                "BatikBrew SDXL, lengkap dengan progres byte dan persentase."
            ),
            wraplength=680,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self.install_all_button = ttk.Button(
            quick_setup,
            text="Instal Semua AI + BatikBrew SDXL",
            command=self.install_complete_batikbrew,
        )
        self.install_all_button.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.install_progress = ttk.Progressbar(quick_setup, mode="indeterminate")
        self.install_progress.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        self.install_progress_text = tk.StringVar(master=self, value="Siap")
        ttk.Label(
            quick_setup,
            textvariable=self.install_progress_text,
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        # --- Komponen unduhan + perkiraan ukuran ---------------------------
        components = ttk.LabelFrame(
            tab_main, text="Komponen yang Diunduh", padding=10
        )
        components.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        components.columnconfigure(0, weight=1)
        self.component_tree = ttk.Treeview(
            components,
            columns=("size", "status"),
            show="tree headings",
            height=4,
            selectmode="none",
        )
        self.component_tree.heading("#0", text="Komponen")
        self.component_tree.heading("size", text="Perkiraan Ukuran")
        self.component_tree.heading("status", text="Status")
        self.component_tree.column("#0", width=340)
        self.component_tree.column("size", width=150, anchor="e")
        self.component_tree.column("status", width=190)
        self.component_tree.grid(row=0, column=0, sticky="ew")
        runtime_actions = ttk.Frame(components)
        runtime_actions.grid(row=1, column=0, sticky="w", pady=(8, 0))
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
            text="Buka Folder Dependencies",
            command=lambda: reveal_path(default_managed_dependency_root()),
        ).pack(side="left", padx=(8, 0))
        self.runtime_status = tk.StringVar(master=self)
        ttk.Label(
            components,
            textvariable=self.runtime_status,
            justify="left",
            wraplength=840,
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # --- Rincian paket Python ------------------------------------------
        packages = ttk.LabelFrame(tab_main, text="Python AI Packages", padding=10)
        packages.grid(row=2, column=0, sticky="nsew")
        packages.columnconfigure(0, weight=1)
        packages.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            packages,
            columns=("requirement", "status"),
            show="headings",
            height=7,
        )
        self.tree.heading("requirement", text="Dependency")
        self.tree.heading("status", text="Status")
        self.tree.column("requirement", width=520)
        self.tree.column("status", width=180)
        self.tree.grid(row=0, column=0, sticky="nsew")
        package_scroll = ttk.Scrollbar(packages, orient="vertical", command=self.tree.yview)
        package_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=package_scroll.set)
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
            wraplength=840,
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        # --- Tab log --------------------------------------------------------
        tab_log.columnconfigure(0, weight=1)
        tab_log.rowconfigure(0, weight=1)
        self.log = tk.Text(tab_log, height=18, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(tab_log, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

        footer = ttk.Frame(body)
        footer.grid(row=2, column=0, sticky="e", pady=(10, 0))
        # Ukuran wajar untuk layout tab; patch _fit_window_to_screen hanya
        # membatasi terhadap layar, jadi tetapkan tinggi yang pas di sini agar
        # tidak ada area kosong memanjang di bawah konten.
        self.geometry("1000x640")
        self.minsize(880, 560)
        self.cancel_button = ttk.Button(
            footer,
            text="Hentikan Instalasi",
            command=self.cancel_installation,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Tutup", command=self._close).pack(side="right")

    def _refresh_component_overview(self) -> None:
        """Isi daftar komponen unduhan beserta perkiraan ukuran dan status."""

        tree = getattr(self, "component_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        for item in tree.get_children(""):
            tree.delete(item)

        missing = len(self._missing_requirements())
        packages_status = (
            "Terpasang lengkap" if missing == 0 else f"{missing} paket belum terpasang"
        )
        sdxl = find_installed_batikbrew_runtime()
        sd15 = find_installed_runtime_models()
        rows = (
            ("Paket Python AI Lokal (torch, diffusers, dll.)", "± 2–3 GB", packages_status),
            (
                "BatikBrew SDXL (base model)",
                "± 13 GB",
                "Terpasang" if sdxl is not None else "Belum diunduh",
            ),
            (
                "Stable Diffusion 1.5 + ControlNet",
                "± 6,6 GB",
                "Terpasang" if sd15 is not None else "Belum diunduh",
            ),
            ("LoRA Batik (opsional, per paket)", "± 50–500 MB", "Kelola lewat tombol LoRA"),
        )
        for name, size, status in rows:
            tree.insert("", "end", text=name, values=(size, status))


    def refresh(self) -> None:
        activate_managed_ai_packages()
        self._refresh_component_overview()
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        for module, requirement in PYTHON_AI_DEPENDENCIES:
            installed = module_available(module)
            self.tree.insert(
                "",
                tk.END,
                values=(requirement, "Terpasang" if installed else "Belum terpasang"),
            )
        dependency_root = default_managed_dependency_root()
        self.package_location.set(f"Folder dependencies: {dependency_root}")
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
        """Install Python dependencies and continue into the SDXL installer."""

        if self._process is not None:
            self._installation_already_running()
            return
        self._continue_with_sdxl = True
        missing = self._missing_requirements()
        if not missing:
            self._append_log(
                "Semua paket AI tersedia. Membuka installer BatikBrew SDXL…"
            )
            self.after(150, self.install_sdxl)
            return
        self.install_python_dependencies(continue_with_sdxl=True)

    def install_python_dependencies(self, *, continue_with_sdxl: bool = False) -> None:
        if self._process is not None:
            self._installation_already_running()
            return

        self._continue_with_sdxl = continue_with_sdxl
        self._cancel_requested = False
        requirements = [requirement for _module, requirement in PYTHON_AI_DEPENDENCIES]
        dependency_root = default_managed_dependency_root()
        target = default_managed_ai_package_dir()
        cache_dir = default_managed_pip_cache_dir()
        log_path = default_managed_dependency_log()
        dependency_root.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        frozen = bool(getattr(sys, "frozen", False))
        if log_path.exists():
            log_path.unlink()
        command = managed_ai_install_command(
            requirements,
            target=target,
            cache_dir=cache_dir,
            frozen=frozen,
            log_file=log_path if frozen else None,
        )
        self._append_log(f"Menyiapkan dependencies di {dependency_root}")
        self._append_log("Seluruh paket dipasang otomatis tanpa jendela terminal.")
        self._set_installing(True)
        self._install_succeeded = False

        def worker() -> None:
            creation_flags = 0
            start_new_session = False
            if os.name == "nt":
                creation_flags = subprocess.CREATE_NO_WINDOW
                creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                start_new_session = True
            try:
                if frozen:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creation_flags,
                        start_new_session=start_new_session,
                    )
                    self._process = process
                    if self._cancel_requested:
                        self._terminate_process_tree(process)
                    self._stream_log_file(process, log_path)
                else:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=creation_flags,
                        start_new_session=start_new_session,
                    )
                    self._process = process
                    if self._cancel_requested:
                        self._terminate_process_tree(process)
                    assert process.stdout is not None
                    for line in process.stdout:
                        self._messages.put(line.rstrip())
                code = process.wait()
                cancelled = self._cancel_requested
                self._install_succeeded = code == 0 and not cancelled
                if cancelled:
                    self._messages.put(
                        "Instalasi dependency dihentikan. Cache unduhan dipertahankan."
                    )
                elif code == 0:
                    self._messages.put(
                        "Paket AI berhasil dipasang ke folder dependencies."
                    )
                else:
                    self._messages.put(
                        f"Instalasi paket AI gagal (kode {code}). "
                        "Tekan instal lagi untuk reparasi."
                    )
            except OSError as exc:
                self._messages.put(f"Instalasi tidak dapat dimulai: {exc}")
            finally:
                self._process = None
                self._messages.put("__DONE__")

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-dependencies",
        ).start()
        self.after(100, self._poll_messages)

    def _stream_log_file(
        self,
        process: subprocess.Popen[object],
        log_path: Path,
    ) -> None:
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
        if not self.winfo_exists():
            return
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
            cancelled = self._cancel_requested
            self._set_installing(False)
            self.install_progress_text.set(
                "Dibatalkan" if cancelled else "Selesai"
            )
            if self._install_succeeded:
                activate_managed_ai_packages()
            self.refresh()
            continue_with_sdxl = (
                self._continue_with_sdxl
                and self._install_succeeded
                and not cancelled
            )
            self._continue_with_sdxl = False
            self._cancel_requested = False
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
        if installing:
            self.install_progress.configure(mode="indeterminate")
            self.install_progress.start(12)
            self.install_progress_text.set("Mengunduh dan memasang paket AI…")
        else:
            self.install_progress.stop()
            self.install_progress.configure(mode="determinate", maximum=1, value=0)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def cancel_installation(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        if self._cancel_requested:
            return
        self._cancel_requested = True
        self._continue_with_sdxl = False
        self.cancel_button.configure(state="disabled")
        self.install_progress_text.set("Menghentikan proses dependency…")
        self._append_log(
            "Menghentikan proses dependency dan seluruh proses turunannya…"
        )
        threading.Thread(
            target=self._terminate_process_tree,
            args=(process,),
            daemon=True,
            name="batikcraft-stop-dependencies",
        ).start()

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
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                process.terminate()
            except OSError:
                return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass

    def _close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            if not messagebox.askyesno(
                "Instalasi masih berjalan",
                "Tutup jendela dan hentikan instalasi sekarang?",
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
