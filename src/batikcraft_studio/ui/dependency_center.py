"""Pusat Dependensi: tabel bercentang untuk unduh, instal, dan uninstall.

Tidak ada lagi tombol "instal semua" atau tombol per komponen yang tersebar.
Pengguna mencentang komponen yang diinginkan pada tabel, lalu menekan
"Unduh & Instal Terpilih" atau "Uninstall Terpilih". Tab kedua memuat
pengelola Model AI Offline & LoRA, tab ketiga menyimpan log instalasi.
"""

from __future__ import annotations

import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.dependency_bootstrap import (
    activate_managed_ai_packages,
    default_managed_ai_package_dir,
    default_managed_dependency_log,
    default_managed_dependency_root,
    default_managed_pip_cache_dir,
    managed_ai_install_command,
)

from .dependency_catalog import (
    CATALOG,
    KIND_MODEL,
    DependencyItem,
    eligibility,
    installed_fraction,
    integrity_status,
    is_installed,
    managed_runtime_root,
    refresh_installed_state,
    requirements_for,
)

_CHECKED = "☑"
_UNCHECKED = "☐"
_BAR_SEGMENTS = 12


def _progress_bar(fraction: float, pulse: int | None = None) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * _BAR_SEGMENTS))
    bar = ["█"] * filled + ["░"] * (_BAR_SEGMENTS - filled)
    if pulse is not None and filled < _BAR_SEGMENTS:
        # Denyut halus di ujung isian menandakan proses masih berjalan.
        bar[filled] = "▓" if pulse % 2 == 0 else "▒"
    return "".join(bar)


def _pulse_bar(phase: int) -> str:
    """Indikator bergerak untuk tahap tanpa persentase (resolusi/ekstraksi)."""

    position = phase % _BAR_SEGMENTS
    bar = ["░"] * _BAR_SEGMENTS
    for offset in range(3):
        bar[(position + offset) % _BAR_SEGMENTS] = "█"
    return "".join(bar)


class DependencyCenterWindow(tk.Toplevel):
    """Satu jendela untuk seluruh siklus hidup dependensi AI."""

    def __init__(self, parent: tk.Misc, *, session: object | None = None) -> None:
        super().__init__(parent)
        self.title("Pusat Dependensi AI — BatikCraft Studio")
        self.geometry("1040x660")
        self.minsize(900, 560)
        self.transient(parent.winfo_toplevel())
        self.session = session
        self._checked: set[str] = set()
        self._live_fraction: dict[str, float] = {}
        self._integrity_notes: dict[str, str] = {}
        self._active_key: str | None = None
        self._pulse_phase = 0
        self._messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._busy = False

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.notebook = notebook

        self.tab_dependencies = ttk.Frame(notebook, padding=10)
        notebook.add(self.tab_dependencies, text="Dependensi")
        self._build_dependency_tab(self.tab_dependencies)

        self.tab_models = ttk.Frame(notebook, padding=10)
        notebook.add(self.tab_models, text="Model AI Offline & LoRA")
        self._build_model_tab(self.tab_models)

        self.tab_log = ttk.Frame(notebook, padding=8)
        notebook.add(self.tab_log, text="Log Instalasi")
        self._build_log_tab(self.tab_log)

        self.refresh()
        self.after(150, self._poll_messages)
        self.after(180, self._tick_animation)

    # ------------------------------------------------------------------
    # Tab 1 — tabel dependensi
    # ------------------------------------------------------------------
    def _build_dependency_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(
            parent,
            text=(
                "Centang komponen yang ingin dipasang, lalu tekan Unduh & Instal "
                "Terpilih. Klik pada kolom centang untuk memilih."
            ),
            style="Muted.TLabel",
            wraplength=960,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("size", "percent", "progress", "eligibility", "status")
        self.tree = ttk.Treeview(
            parent, columns=columns, show="tree headings", height=12, selectmode="none"
        )
        self.tree.heading("#0", text="  Dependensi")
        self.tree.heading("size", text="Ukuran")
        self.tree.heading("percent", text="Terunduh")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("eligibility", text="Eligibility")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=330, stretch=True)
        self.tree.column("size", width=90, anchor="e")
        self.tree.column("percent", width=85, anchor="e")
        self.tree.column("progress", width=140, anchor="center")
        self.tree.column("eligibility", width=110, anchor="center")
        self.tree.column("status", width=140, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("ineligible", foreground="#B91C1C")
        self.tree.bind("<Button-1>", self._on_tree_click)

        self.detail_value = tk.StringVar(master=self, value="")
        ttk.Label(
            parent,
            textvariable=self.detail_value,
            style="Muted.TLabel",
            wraplength=960,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(parent)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="Pilih Semua", command=self.select_all).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(actions, text="Kosongkan", command=self.select_none).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )
        self.install_button = ttk.Button(
            actions,
            text="Unduh & Instal Terpilih",
            style="Accent.TButton",
            command=self.install_selected,
        )
        self.install_button.grid(row=0, column=3, sticky="e")
        self.uninstall_button = ttk.Button(
            actions, text="Uninstall Terpilih", command=self.uninstall_selected
        )
        self.uninstall_button.grid(row=0, column=4, sticky="e", padx=(6, 0))
        ttk.Button(actions, text="Muat Ulang", command=self.refresh).grid(
            row=0, column=5, sticky="e", padx=(6, 0)
        )

        self.status_value = tk.StringVar(master=self, value="Siap.")
        ttk.Label(parent, textvariable=self.status_value).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self.overall_progress = ttk.Progressbar(parent, mode="determinate", maximum=100)
        self.overall_progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # ------------------------------------------------------------------
    # Tab 2 — model offline & LoRA (tanpa tombol instalasi runtime)
    # ------------------------------------------------------------------
    def _build_model_tab(self, parent: ttk.Frame) -> None:
        """Model LoRA aktif + pengaturan runtime, tanpa tombol instalasi.

        Widget Tk tidak dapat dipindah antar-jendela, jadi panel ini dibangun
        langsung di dalam tab (bukan menanam jendela lain).
        """

        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        session = self.session
        if session is None or not hasattr(session, "installed_models"):
            ttk.Label(
                parent,
                text=(
                    "Pengelola model memerlukan proyek aktif. Buka Pusat Dependensi "
                    "dari menu Dependencies saat editor sedang terbuka."
                ),
                style="Muted.TLabel",
                wraplength=900,
                justify="left",
            ).grid(row=0, column=0, sticky="nw")
            return

        left = ttk.LabelFrame(parent, text="LoRA Terpasang", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.model_tree = ttk.Treeview(
            left,
            columns=("version", "family", "weight"),
            show="tree headings",
            selectmode="browse",
        )
        self.model_tree.heading("#0", text="Nama")
        self.model_tree.heading("version", text="Versi")
        self.model_tree.heading("family", text="Base")
        self.model_tree.heading("weight", text="Bobot")
        self.model_tree.column("#0", width=210)
        self.model_tree.column("version", width=70, anchor="center")
        self.model_tree.column("family", width=80, anchor="center")
        self.model_tree.column("weight", width=70, anchor="e")
        self.model_tree.grid(row=0, column=0, sticky="nsew")
        model_actions = ttk.Frame(left)
        model_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            model_actions, text="Pasang .batikmodel…", command=self._install_lora_pack
        ).pack(side="left")
        ttk.Button(
            model_actions, text="Hapus", command=self._uninstall_lora_pack
        ).pack(side="left", padx=(6, 0))

        right = ttk.LabelFrame(parent, text="Runtime Lokal & Model Aktif", padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        self.base_path = tk.StringVar(master=self)
        self.controlnet_path = tk.StringVar(master=self)
        row = 0
        for label, variable in (
            ("Folder base model", self.base_path),
            ("Folder ControlNet", self.controlnet_path),
        ):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Label(
                right,
                textvariable=variable,
                style="Muted.TLabel",
                wraplength=320,
                justify="left",
            ).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        self.device_value = tk.StringVar(master=self, value="auto")
        self.precision_value = tk.StringVar(master=self, value="auto")
        for label, variable, values in (
            ("Perangkat", self.device_value, ("auto", "cpu", "cuda", "mps")),
            ("Presisi", self.precision_value, ("auto", "float16", "float32", "bfloat16")),
        ):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(
                right, textvariable=variable, values=values, state="readonly"
            ).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        self.steps_value = tk.IntVar(master=self, value=28)
        self.guidance_value = tk.DoubleVar(master=self, value=7.0)
        self.control_value = tk.DoubleVar(master=self, value=0.85)
        self.lora_value = tk.DoubleVar(master=self, value=0.85)
        for label, variable, low, high, step in (
            ("Inference steps", self.steps_value, 1, 150, 1),
            ("Guidance scale", self.guidance_value, 0, 30, 0.5),
            ("Kekuatan ControlNet", self.control_value, 0, 2, 0.05),
            ("Kekuatan LoRA", self.lora_value, 0, 2, 0.05),
        ):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Spinbox(
                right,
                textvariable=variable,
                from_=low,
                to=high,
                increment=step,
            ).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        self.cpu_offload = tk.BooleanVar(master=self, value=False)
        ttk.Checkbutton(
            right, text="CPU offload untuk menghemat VRAM", variable=self.cpu_offload
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        ttk.Label(
            right,
            text=(
                "Folder model mengikuti Pusat Dependensi secara otomatis. "
                "Unduhan runtime dilakukan di tab Dependensi."
            ),
            style="Muted.TLabel",
            wraplength=340,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 6))
        row += 1

        model_buttons = ttk.Frame(right)
        model_buttons.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(
            model_buttons, text="Pakai Renderer Fondasi", command=self._use_foundation
        ).pack(side="left")
        ttk.Button(
            model_buttons,
            text="Aktifkan Model",
            style="Accent.TButton",
            command=self._activate_model,
        ).pack(side="left", padx=(6, 0))

        self.model_status = tk.StringVar(master=self, value="")
        ttk.Label(
            parent,
            textvariable=self.model_status,
            style="Muted.TLabel",
            wraplength=960,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._refresh_models()

    # ------------------------------------------------------------------
    # Aksi model LoRA
    # ------------------------------------------------------------------
    def _refresh_models(self) -> None:
        tree = getattr(self, "model_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        for row in tree.get_children(""):
            tree.delete(row)
        try:
            installed = list(self.session.installed_models)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            self.model_status.set(f"Daftar model tidak dapat dibaca: {exc}")
            return
        for entry in installed:
            manifest = entry.manifest
            tree.insert(
                "",
                "end",
                iid=manifest.model_id,
                text=manifest.name,
                values=(
                    manifest.version,
                    manifest.base_model_family,
                    f"{manifest.recommended_weight:.2f}",
                ),
            )
        # Path runtime selalu mengikuti hasil unduhan Pusat Dependensi.
        try:
            from batikcraft_studio.ai.runtime_model_installer import (
                find_installed_runtime_models,
            )

            paths = find_installed_runtime_models()
        except Exception:  # noqa: BLE001
            paths = None
        missing = "Belum terpasang — unduh di tab Dependensi."
        self.base_path.set(str(paths.base_model) if paths else missing)
        self.controlnet_path.set(str(paths.controlnet) if paths else missing)
        try:
            runtime = self.session.runtime_selection  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            runtime = None
        if runtime is None:
            self.model_status.set("Provider aktif: renderer fondasi lokal.")
        else:
            self.model_status.set(f"Model aktif: {runtime.model_id}")
            if tree.exists(runtime.model_id):
                tree.selection_set(runtime.model_id)

    def _selected_model_id(self) -> str | None:
        tree = getattr(self, "model_tree", None)
        if tree is None:
            return None
        selection = tree.selection()
        return str(selection[0]) if selection else None

    def _install_lora_pack(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self,
            title="Pasang paket model .batikmodel",
            filetypes=[("BatikCraft model", "*.batikmodel"), ("Semua file", "*.*")],
        )
        if not path:
            return
        try:
            self.session.install_model_pack(path, replace=True)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh_models()

    def _uninstall_lora_pack(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            messagebox.showinfo(self.title(), "Pilih model LoRA dulu.", parent=self)
            return
        try:
            self.session.uninstall_model_pack(model_id)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh_models()

    def _activate_model(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            messagebox.showinfo(self.title(), "Pilih model LoRA dulu.", parent=self)
            return
        base = self.base_path.get().strip()
        control = self.controlnet_path.get().strip()
        if base.startswith("Belum terpasang"):
            messagebox.showerror(
                self.title(),
                "Base model belum terpasang. Unduh di tab Dependensi terlebih dahulu.",
                parent=self,
            )
            return
        try:
            self.session.configure_offline_model(  # type: ignore[union-attr]
                model_id,
                base_model_path=base,
                controlnet_path=None if control.startswith("Belum") else control,
                device=self.device_value.get(),
                precision=self.precision_value.get(),
                inference_steps=int(self.steps_value.get()),
                guidance_scale=float(self.guidance_value.get()),
                controlnet_scale=float(self.control_value.get()),
                lora_scale=float(self.lora_value.get()),
                cpu_offload=bool(self.cpu_offload.get()),
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh_models()

    def _use_foundation(self) -> None:
        try:
            self.session.use_foundation_renderer()  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh_models()

    # ------------------------------------------------------------------
    # Tab 3 — log
    # ------------------------------------------------------------------
    def _build_log_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log = tk.Text(parent, wrap="word", state="disabled", height=20)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        ttk.Button(
            parent, text="Buka Folder Log", command=self._open_log_folder
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # Data & tampilan
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        refresh_installed_state()
        self._integrity_notes.clear()
        for row in self.tree.get_children(""):
            self.tree.delete(row)
        for item in CATALOG:
            eligible, reason = eligibility(item)
            installed = is_installed(item)
            fraction = self._live_fraction.get(
                item.key, 1.0 if installed else installed_fraction(item)
            )
            checked = item.key in self._checked
            status_text, status_detail = integrity_status(item)
            if status_detail:
                self._integrity_notes[item.key] = status_detail
            self.tree.insert(
                "",
                "end",
                iid=item.key,
                text=f" {_CHECKED if checked else _UNCHECKED}  {item.name}",
                values=(
                    item.size_text,
                    f"{fraction * 100:.0f}%",
                    _progress_bar(fraction),
                    "OK" if eligible else "✗ NO",
                    status_text,
                ),
                tags=()
                if eligible and status_text != "PERLU REPARASI"
                else ("ineligible",),
            )
            if not eligible:
                self._checked.discard(item.key)
        self._update_detail()

    def _update_detail(self) -> None:
        lines = []
        for item in CATALOG:
            if item.key in self._checked:
                eligible, reason = eligibility(item)
                note = item.note or reason
                lines.append(f"• {item.name} — {item.size_text}. {note}")
        for key, note in self._integrity_notes.items():
            item = next((entry for entry in CATALOG if entry.key == key), None)
            if item is not None:
                lines.append(
                    f"⚠ {item.name}: PERLU REPARASI — {note}. Centang lalu tekan "
                    "Unduh & Instal Terpilih untuk memperbaiki."
                )
        if not lines:
            self.detail_value.set(
                "Belum ada komponen dicentang. Folder instalasi: "
                f"{default_managed_dependency_root()}"
            )
            return
        total = sum(item.size_bytes for item in CATALOG if item.key in self._checked)
        lines.append(f"Total unduhan diperkirakan: {total / 1024**3:.1f} GB")
        self.detail_value.set("\n".join(lines))

    def _on_tree_click(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        item = next((entry for entry in CATALOG if entry.key == row), None)
        if item is None:
            return
        eligible, reason = eligibility(item)
        if not eligible:
            self.status_value.set(f"{item.name}: {reason}")
            return
        if row in self._checked:
            self._checked.discard(row)
        else:
            self._checked.add(row)
        self.refresh()

    def select_all(self) -> None:
        self._checked = {
            item.key for item in CATALOG if eligibility(item)[0]
        }
        self.refresh()

    def select_none(self) -> None:
        self._checked.clear()
        self.refresh()

    def _selected_items(self) -> list[DependencyItem]:
        return [item for item in CATALOG if item.key in self._checked]

    # ------------------------------------------------------------------
    # Instalasi
    # ------------------------------------------------------------------
    def install_selected(self) -> None:
        if self._busy:
            messagebox.showinfo(
                self.title(), "Proses sedang berjalan. Tunggu hingga selesai.", parent=self
            )
            return
        items = self._selected_items()
        if not items:
            messagebox.showinfo(
                self.title(), "Centang minimal satu komponen terlebih dahulu.", parent=self
            )
            return
        self._set_busy(True)
        self.notebook.select(self.tab_log)
        self._append_log(f"Memulai instalasi {len(items)} komponen…")
        self._worker = threading.Thread(
            target=self._install_worker, args=(items,), daemon=True
        )
        self._worker.start()

    def _install_worker(self, items: list[DependencyItem]) -> None:
        for index, item in enumerate(items, start=1):
            self._messages.put(("active", item.key))
            self._messages.put(
                ("status", f"[{index}/{len(items)}] Memasang {item.name}…")
            )
            try:
                if item.kind == KIND_MODEL:
                    self._install_model(item)
                else:
                    self._install_packages(item)
            except Exception as exc:  # noqa: BLE001 - laporkan ke GUI
                self._messages.put(("log", f"GAGAL {item.name}: {exc}"))
                self._messages.put(("error", f"{item.name} gagal dipasang: {exc}"))
                continue
            self._messages.put(("log", f"Selesai: {item.name}"))
            self._messages.put(("progress", (item.key, 1.0)))
        self._messages.put(("active", None))
        self._messages.put(("done", None))

    def _install_packages(self, item: DependencyItem) -> None:
        target = default_managed_ai_package_dir()
        cache_dir = default_managed_pip_cache_dir()
        target.parent.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        frozen = bool(getattr(sys, "frozen", False))
        log_path = default_managed_dependency_log()
        command = managed_ai_install_command(
            requirements_for(item),
            target=target,
            cache_dir=cache_dir,
            frozen=frozen,
            log_file=log_path if frozen else None,
            torch_variant=item.variant or None,
        )
        self._messages.put(("log", "$ " + " ".join(command)))
        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(  # noqa: S603 - perintah dibentuk internal
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creation,
        )
        assert process.stdout is not None
        # pip --progress-bar raw menulis "Progress <selesai> of <total>" per file;
        # angka itu dipakai untuk menggerakkan bar pada baris tabel.
        progress_pattern = re.compile(r"Progress (\d+) of (\d+)")
        for line in process.stdout:
            stripped = line.rstrip()
            if not stripped:
                continue
            match = progress_pattern.search(stripped)
            if match:
                done, total = int(match.group(1)), int(match.group(2))
                if total > 0:
                    self._messages.put(("progress", (item.key, done / total)))
                continue
            if stripped.startswith(("Downloading", "Collecting", "Installing")):
                self._messages.put(("status", f"{item.name}: {stripped[:70]}"))
            self._messages.put(("log", stripped))
        code = process.wait()
        if code != 0:
            raise RuntimeError(f"pip keluar dengan kode {code}")

    def _install_model(self, item: DependencyItem) -> None:
        from batikcraft_studio.ai.runtime_model_installer import (
            install_batikbrew_runtime,
            install_default_runtime_models,
        )

        def progress(update: object) -> None:
            """Installer mengirim satu objek RuntimeModelInstallProgress."""

            percent = getattr(update, "download_percent", None)
            if percent is None:
                completed = float(getattr(update, "completed", 0) or 0)
                total = float(getattr(update, "total", 0) or 0)
                fraction = (completed / total) if total else 0.0
            else:
                fraction = float(percent) / 100.0
            self._messages.put(("progress", (item.key, fraction)))
            message = str(getattr(update, "message", "") or "")
            if message:
                self._messages.put(("status", f"{item.name}: {message}"))

        root = managed_runtime_root()
        root.mkdir(parents=True, exist_ok=True)
        if item.key == "sdxl":
            install_batikbrew_runtime(root, progress=progress)
        else:
            install_default_runtime_models(root, progress=progress)

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------
    def uninstall_selected(self) -> None:
        if self._busy:
            return
        items = self._selected_items()
        if not items:
            messagebox.showinfo(
                self.title(), "Centang komponen yang ingin dihapus.", parent=self
            )
            return
        names = "\n".join(f"• {item.name}" for item in items)
        if not messagebox.askyesno(
            "Uninstall dependensi",
            f"Hapus komponen berikut dari komputer?\n\n{names}",
            parent=self,
        ):
            return
        removed = 0
        for item in items:
            try:
                if item.kind == KIND_MODEL:
                    folder = managed_runtime_root() / item.folder
                    if folder.is_dir():
                        shutil.rmtree(folder, ignore_errors=True)
                        removed += 1
                else:
                    removed += self._remove_package_files(item)
            except OSError as exc:
                self._append_log(f"Gagal menghapus {item.name}: {exc}")
        self._append_log(f"{removed} komponen dihapus.")
        self.status_value.set(f"{removed} komponen dihapus.")
        self._live_fraction.clear()
        self.refresh()

    def _remove_package_files(self, item: DependencyItem) -> int:
        packages = default_managed_ai_package_dir()
        if not packages.is_dir():
            return 0
        removed = 0
        module_root = item.module.split(".")[0]
        for path in list(packages.glob(f"{module_root}*")):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            elif path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    # ------------------------------------------------------------------
    # Utilitas
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.install_button.configure(state=state)
        self.uninstall_button.configure(state=state)
        if busy:
            self.overall_progress.configure(mode="indeterminate")
            self.overall_progress.start(60)
        else:
            self.overall_progress.stop()
            self.overall_progress.configure(mode="determinate")
            self._active_key = None

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self._messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_value.set(str(payload))
                elif kind == "progress" and isinstance(payload, tuple):
                    key, fraction = payload
                    self._live_fraction[str(key)] = float(fraction)
                    self._update_row_progress(str(key), float(fraction))
                elif kind == "active":
                    self._active_key = str(payload) if payload else None
                elif kind == "error":
                    messagebox.showerror(self.title(), str(payload), parent=self)
                elif kind == "done":
                    self._set_busy(False)
                    self.status_value.set("Selesai. Periksa tab Log untuk detail.")
                    self.overall_progress.configure(value=100)
                    activate_managed_ai_packages()
                    self.refresh()
        except queue.Empty:
            pass
        try:
            self.after(150, self._poll_messages)
        except tk.TclError:
            pass

    def _tick_animation(self) -> None:
        """Gerakkan indikator baris aktif supaya tidak terlihat mati.

        Fase pip (resolusi dependensi, ekstraksi wheel) tidak memberi angka;
        tanpa denyut ini bar tampak diam padahal proses berjalan.
        """

        key = self._active_key
        if key and self.tree.exists(key):
            self._pulse_phase = (self._pulse_phase + 1) % _BAR_SEGMENTS
            fraction = self._live_fraction.get(key)
            if fraction is None or fraction <= 0.0 or fraction >= 1.0:
                self.tree.set(key, "progress", _pulse_bar(self._pulse_phase))
                self.tree.set(key, "percent", "…")
            else:
                # Ada angka nyata: bar terisi, ujungnya berdenyut halus.
                self.tree.set(
                    key, "progress", _progress_bar(fraction, pulse=self._pulse_phase)
                )
            self.overall_progress.step(3)
        try:
            self.after(180, self._tick_animation)
        except tk.TclError:
            pass

    def _update_row_progress(self, key: str, fraction: float) -> None:
        if not self.tree.exists(key):
            return
        self.tree.set(key, "percent", f"{fraction * 100:.0f}%")
        self.tree.set(key, "progress", _progress_bar(fraction, pulse=self._pulse_phase))

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_log_folder(self) -> None:
        from batikcraft_studio.logging_setup import install_file_logging

        path = install_file_logging()
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)])  # noqa: S603,S607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except OSError as exc:
            messagebox.showinfo(self.title(), f"Folder log: {path} ({exc})", parent=self)


__all__ = ["DependencyCenterWindow"]
