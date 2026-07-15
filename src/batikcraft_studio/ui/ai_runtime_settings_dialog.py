"""Global AI/GPU preferences with persistent settings and runtime diagnosis."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from batikcraft_studio.ai.runtime_settings import (
    AIRuntimeReport,
    AIRuntimeSettings,
    AIRuntimeSettingsStore,
    diagnose_ai_runtime,
)

UnloadCallback = Callable[[], object]


class AIRuntimeSettingsDialog(tk.Toplevel):
    """Edit one global runtime profile shared by all Stable Diffusion features."""

    def __init__(
        self,
        parent: tk.Misc,
        store: AIRuntimeSettingsStore,
        *,
        unload_models: UnloadCallback | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.unload_models = unload_models
        self.result: AIRuntimeSettings | None = None
        self._queue: Queue[tuple[str, object]] = Queue()
        self._working = False
        self._destroyed = False
        self._poll_after_id: str | None = None
        current = store.load()

        self.title("Preferences — AI & GPU")
        self.geometry("820x720")
        self.minsize(720, 620)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.device_value = tk.StringVar(master=self, value=current.device)
        self.precision_value = tk.StringVar(master=self, value=current.precision)
        self.cpu_offload_value = tk.BooleanVar(master=self, value=current.cpu_offload)
        self.low_vram_value = tk.BooleanVar(master=self, value=current.low_vram_mode)
        self.attention_slicing_value = tk.BooleanVar(
            master=self,
            value=current.attention_slicing,
        )
        self.vae_slicing_value = tk.BooleanVar(master=self, value=current.vae_slicing)
        self.vae_tiling_value = tk.BooleanVar(master=self, value=current.vae_tiling)
        self.cache_dir_value = tk.StringVar(master=self, value=current.cache_dir)
        self.default_model_value = tk.StringVar(master=self, value=current.default_model)
        self.local_only_value = tk.BooleanVar(master=self, value=current.local_files_only)
        self.status_value = tk.StringVar(
            master=self,
            value=store.last_error or "Pengaturan ini digunakan oleh seluruh fitur AI.",
        )

        self._build()
        self.low_vram_value.trace_add("write", self._sync_low_vram_defaults)
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        heading = ttk.Frame(body)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            heading,
            text="Global AI & GPU Settings",
            font=("TkDefaultFont", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            heading,
            text=(
                "Satu konfigurasi untuk AI Batik Background, Batifikasi AI, dan LoRA "
                "offline. Perubahan akan melepas model lama dari memori."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(3, 0))

        settings = ttk.LabelFrame(body, text="Runtime Stable Diffusion", padding=12)
        settings.grid(row=1, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)
        row = 0

        row = self._combo_row(
            settings,
            row,
            "Compute device",
            self.device_value,
            ("auto", "cuda", "cpu", "mps"),
        )
        row = self._combo_row(
            settings,
            row,
            "Precision",
            self.precision_value,
            ("auto", "float16", "bfloat16", "float32"),
        )
        row = self._entry_row(settings, row, "Default Stable Diffusion model", self.default_model_value)
        row = self._path_row(settings, row)

        for text, variable in (
            ("Gunakan file model lokal saja (tanpa download)", self.local_only_value),
            ("CPU offload — hemat VRAM tetapi dapat lebih lambat", self.cpu_offload_value),
            ("Low VRAM mode", self.low_vram_value),
            ("Attention slicing", self.attention_slicing_value),
            ("VAE slicing", self.vae_slicing_value),
            ("VAE tiling", self.vae_tiling_value),
        ):
            ttk.Checkbutton(settings, text=text, variable=variable).grid(
                row=row,
                column=0,
                columnspan=3,
                sticky="w",
                pady=3,
            )
            row += 1

        ttk.Label(
            settings,
            text=f"File konfigurasi: {self.store.path}",
            style="Muted.TLabel",
            wraplength=740,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))

        diagnosis = ttk.LabelFrame(body, text="GPU / AI Runtime Test", padding=10)
        diagnosis.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        diagnosis.columnconfigure(0, weight=1)
        diagnosis.rowconfigure(0, weight=1)
        self.report_text = tk.Text(
            diagnosis,
            height=13,
            wrap="word",
            state="disabled",
            relief=tk.FLAT,
        )
        self.report_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(diagnosis, orient="vertical", command=self.report_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.report_text.configure(yscrollcommand=scrollbar.set)
        self._set_report(
            "Klik Test GPU / AI Runtime. Tes ini tidak mengunduh model dan hanya menjalankan "
            "operasi tensor kecil."
        )

        footer = ttk.Frame(body)
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_value, wraplength=470).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=110)
        self.progress.grid(row=0, column=1, padx=5)
        self.test_button = ttk.Button(
            footer,
            text="Test GPU / AI Runtime",
            command=self.test_runtime,
        )
        self.test_button.grid(row=0, column=2, padx=3)
        ttk.Button(footer, text="Unload Model", command=self.unload).grid(
            row=0,
            column=3,
            padx=3,
        )
        ttk.Button(footer, text="Reset Default", command=self.reset_defaults).grid(
            row=0,
            column=4,
            padx=3,
        )
        ttk.Button(footer, text="Batal", command=self.cancel).grid(
            row=0,
            column=5,
            padx=3,
        )
        ttk.Button(footer, text="Simpan", command=self.save).grid(
            row=0,
            column=6,
            padx=(3, 0),
        )

    def _combo_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        return row + 1

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=3,
        )
        return row + 1

    def _path_row(self, parent: ttk.Frame, row: int) -> int:
        ttk.Label(parent, text="Model cache directory").grid(
            row=row,
            column=0,
            sticky="w",
            pady=3,
        )
        ttk.Entry(parent, textvariable=self.cache_dir_value).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=3,
        )
        ttk.Button(parent, text="Pilih…", command=self.choose_cache_directory).grid(
            row=row,
            column=2,
            padx=(6, 0),
            pady=3,
        )
        return row + 1

    def choose_cache_directory(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            initialdir=self.cache_dir_value.get() or str(Path.home()),
        )
        if selected:
            self.cache_dir_value.set(selected)

    def collect_settings(self) -> AIRuntimeSettings:
        return AIRuntimeSettings(
            device=self.device_value.get(),
            precision=self.precision_value.get(),
            cpu_offload=bool(self.cpu_offload_value.get()),
            low_vram_mode=bool(self.low_vram_value.get()),
            attention_slicing=bool(self.attention_slicing_value.get()),
            vae_slicing=bool(self.vae_slicing_value.get()),
            vae_tiling=bool(self.vae_tiling_value.get()),
            cache_dir=self.cache_dir_value.get(),
            default_model=self.default_model_value.get(),
            local_files_only=bool(self.local_only_value.get()),
        )

    def test_runtime(self) -> None:
        if self._working:
            return
        try:
            settings = self.collect_settings()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan AI tidak valid", str(exc), parent=self)
            return
        self._working = True
        self.test_button.configure(state="disabled")
        self.progress.start(12)
        self.status_value.set("Memeriksa PyTorch, CUDA/MPS, VRAM, dan tes tensor…")

        def worker() -> None:
            try:
                report = diagnose_ai_runtime(settings, run_tensor_test=True)
            except Exception as exc:  # noqa: BLE001 - report arbitrary Torch backend errors
                self._queue.put(("error", str(exc)))
            else:
                self._queue.put(("success", report))

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-ai-runtime-test",
        ).start()
        if self._poll_after_id is None:
            self._poll_after_id = self.after(80, self._poll_worker)

    def _poll_worker(self) -> None:
        self._poll_after_id = None
        if self._destroyed:
            return
        try:
            kind, payload = self._queue.get_nowait()
        except Empty:
            self._poll_after_id = self.after(80, self._poll_worker)
            return
        self._working = False
        self.progress.stop()
        self.test_button.configure(state="normal")
        if kind == "error":
            self.status_value.set(str(payload))
            self._set_report(str(payload))
            return
        if not isinstance(payload, AIRuntimeReport):
            self.status_value.set("Hasil diagnosis AI tidak dikenali.")
            return
        self._set_report(payload.format_text())
        self.status_value.set(
            "Runtime siap." if payload.error is None else "Runtime membutuhkan perbaikan."
        )

    def _set_report(self, content: str) -> None:
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", content)
        self.report_text.configure(state="disabled")

    def _sync_low_vram_defaults(self, *_args: object) -> None:
        if not self.low_vram_value.get():
            return
        self.cpu_offload_value.set(True)
        self.attention_slicing_value.set(True)
        self.vae_slicing_value.set(True)
        self.vae_tiling_value.set(True)

    def unload(self) -> None:
        if self.unload_models is None:
            self.status_value.set("Tidak ada model aktif untuk dilepas.")
            return
        try:
            self.unload_models()
        except Exception as exc:  # noqa: BLE001 - UI callback boundary
            self.status_value.set(f"Model gagal dilepas: {exc}")
            return
        self.status_value.set("Model AI dilepas dari RAM/VRAM.")

    def reset_defaults(self) -> None:
        defaults = AIRuntimeSettings()
        self.device_value.set(defaults.device)
        self.precision_value.set(defaults.precision)
        self.cpu_offload_value.set(defaults.cpu_offload)
        self.low_vram_value.set(defaults.low_vram_mode)
        self.attention_slicing_value.set(defaults.attention_slicing)
        self.vae_slicing_value.set(defaults.vae_slicing)
        self.vae_tiling_value.set(defaults.vae_tiling)
        self.cache_dir_value.set(defaults.cache_dir)
        self.default_model_value.set(defaults.default_model)
        self.local_only_value.set(defaults.local_files_only)
        self.status_value.set("Nilai default dimuat. Klik Simpan untuk menerapkan.")

    def save(self) -> None:
        try:
            settings = self.collect_settings()
            self.store.save(settings)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan AI gagal disimpan", str(exc), parent=self)
            return
        if self.unload_models is not None:
            try:
                self.unload_models()
            except Exception:  # noqa: BLE001 - settings remain valid even if unload fails
                pass
        self.result = settings
        self._close()

    def cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        self._destroyed = True
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


__all__ = ["AIRuntimeSettingsDialog"]
