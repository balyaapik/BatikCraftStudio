"""Pusat Dependensi: tabel bercentang untuk unduh, instal, dan uninstall.

Tidak ada lagi tombol "instal semua" atau tombol per komponen yang tersebar.
Pengguna mencentang komponen yang diinginkan pada tabel, lalu menekan
"Unduh & Instal Terpilih" atau "Uninstall Terpilih". Tab kedua memuat
pengelola Model AI Offline & LoRA, tab ketiga menyimpan log instalasi.
"""

from __future__ import annotations

import queue
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


def _progress_bar(fraction: float) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * _BAR_SEGMENTS))
    return "█" * filled + "░" * (_BAR_SEGMENTS - filled)


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
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        session = self.session
        if session is None:
            ttk.Label(
                parent,
                text=(
                    "Pengelola model memerlukan proyek aktif. Buka jendela ini dari "
                    "menu Dependencies saat editor sedang terbuka."
                ),
                style="Muted.TLabel",
                wraplength=900,
            ).grid(row=0, column=0, sticky="nw")
            return
        try:
            from .offline_ai_dialogs_global import GlobalOfflineModelManagerWindow

            holder = GlobalOfflineModelManagerWindow(self, session)
            # Tanam isi jendela pengelola model ke dalam tab ini.
            body = None
            for child in holder.winfo_children():
                body = child
                break
            if body is not None:
                body.pack_forget()
                body.grid_forget()
                body.master = parent  # type: ignore[attr-defined]
                body.grid(row=0, column=0, sticky="nsew")
            holder.withdraw()
            self._model_window = holder
        except Exception as exc:  # noqa: BLE001 - jangan gagalkan seluruh jendela
            ttk.Label(
                parent,
                text=f"Pengelola model tidak dapat dimuat: {exc}",
                style="Muted.TLabel",
                wraplength=900,
            ).grid(row=0, column=0, sticky="nw")

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
        for line in process.stdout:
            stripped = line.rstrip()
            if stripped:
                self._messages.put(("log", stripped))
        code = process.wait()
        if code != 0:
            raise RuntimeError(f"pip keluar dengan kode {code}")

    def _install_model(self, item: DependencyItem) -> None:
        from batikcraft_studio.ai.runtime_model_installer import (
            install_batikbrew_runtime,
            install_default_runtime_models,
        )

        def progress(stage: str, message: str, completed: float, total: float) -> None:
            del stage
            fraction = (completed / total) if total else 0.0
            self._messages.put(("progress", (item.key, fraction)))
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

    def _update_row_progress(self, key: str, fraction: float) -> None:
        if not self.tree.exists(key):
            return
        self.tree.set(key, "percent", f"{fraction * 100:.0f}%")
        self.tree.set(key, "progress", _progress_bar(fraction))
        self.overall_progress.configure(value=fraction * 100)

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
