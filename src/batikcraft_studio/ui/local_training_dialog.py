"""Tkinter windows for dataset preparation, local LoRA training, and results."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from batikcraft_studio.ai.dataset_pack import load_batik_dataset, safe_identifier
from batikcraft_studio.ai.local_lora_training import default_training_root
from batikcraft_studio.ai.model_pack import OfflineModelLibrary
from batikcraft_studio.ai.runtime_model_installer import find_installed_batikbrew_runtime

from .dependency_manager_dialog import reveal_path
from .offline_ai_dialogs import DatasetStudioWindow


class SDXLDatasetStudioWindow(DatasetStudioWindow):
    """Dataset Studio variant configured for BatikBrew SDXL training."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.base_family_value.set("sdxl")
        self.category_value.set("ornament")
        self.style_value.set("batikcraft")
        self.title("Local AI Training — Dataset Studio")


class LocalLoraTrainingWindow(tk.Toplevel):
    """Launch the built-in SDXL LoRA worker and stream progress to the UI."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        runtime = find_installed_batikbrew_runtime()
        base_model = str(runtime.base_model) if runtime is not None else ""
        root = default_training_root()

        self.dataset_value = tk.StringVar(master=self)
        self.base_model_value = tk.StringVar(master=self, value=base_model)
        self.output_value = tk.StringVar(master=self, value=str(root))
        self.model_name_value = tk.StringVar(master=self, value="BatikCraft Ornament LoRA")
        self.model_id_value = tk.StringVar(master=self, value="batikcraft-ornament-v1")
        self.version_value = tk.StringVar(master=self, value="1.0.0")
        self.resolution_value = tk.IntVar(master=self, value=1024)
        self.steps_value = tk.IntVar(master=self, value=500)
        self.learning_rate_value = tk.StringVar(master=self, value="0.0001")
        self.rank_value = tk.IntVar(master=self, value=16)
        self.alpha_value = tk.IntVar(master=self, value=16)
        self.batch_value = tk.IntVar(master=self, value=1)
        self.accumulation_value = tk.IntVar(master=self, value=4)
        self.seed_value = tk.IntVar(master=self, value=2026)
        self.status_value = tk.StringVar(master=self, value="Siap menyiapkan training lokal.")

        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[str] = queue.Queue()
        self._result_path: Path | None = None

        self.title("Local AI Training — Train LoRA")
        self.geometry("920x760")
        self.minsize(820, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(15, weight=1)

        ttk.Label(
            body,
            text="Train SDXL LoRA di Komputer Ini",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text=(
                "Dataset dibuat dari aset manual. Training berjalan sebagai proses terpisah, "
                "kemudian hasilnya otomatis dikemas menjadi .batikmodel. GPU CUDA diperlukan."
            ),
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 12))

        self._file_row(body, 2, "Dataset", self.dataset_value, self._choose_dataset)
        self._file_row(body, 3, "Base model SDXL", self.base_model_value, self._choose_base_model)
        self._folder_row(body, 4, "Folder output", self.output_value)
        self._entry_row(body, 5, "Nama model", self.model_name_value)
        self._entry_row(body, 6, "Model ID", self.model_id_value)
        self._entry_row(body, 7, "Versi", self.version_value)

        options = ttk.LabelFrame(body, text="Training Parameters", padding=10)
        options.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        for column in (1, 3, 5):
            options.columnconfigure(column, weight=1)
        self._spin(options, 0, 0, "Resolution", self.resolution_value, (512, 640, 768, 896, 1024))
        self._spin(options, 0, 2, "Max steps", self.steps_value, None, 10, 100000, 10)
        self._entry(options, 0, 4, "Learning rate", self.learning_rate_value)
        self._spin(options, 1, 0, "LoRA rank", self.rank_value, (4, 8, 16, 32, 64, 128))
        self._spin(options, 1, 2, "LoRA alpha", self.alpha_value, None, 1, 256, 1)
        self._spin(options, 1, 4, "Batch size", self.batch_value, None, 1, 8, 1)
        self._spin(
            options,
            2,
            0,
            "Gradient accumulation",
            self.accumulation_value,
            None,
            1,
            64,
            1,
        )
        self._spin(options, 2, 2, "Seed", self.seed_value, None, 0, 999999, 1)

        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=860,
        ).grid(row=9, column=0, columnspan=3, sticky="ew", pady=(4, 4))

        progress_row = ttk.Frame(body)
        progress_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        progress_row.columnconfigure(0, weight=1)
        self.training_progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100.0)
        self.training_progress.grid(row=0, column=0, sticky="ew")
        self.training_percent_value = tk.StringVar(master=self, value="0%")
        ttk.Label(progress_row, textvariable=self.training_percent_value, width=5, anchor="e").grid(
            row=0, column=1, padx=(8, 0)
        )

        actions = ttk.Frame(body)
        actions.grid(row=10, column=0, columnspan=3, sticky="ew")
        self.start_button = ttk.Button(actions, text="Mulai Training", command=self.start_training)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(
            actions,
            text="Hentikan",
            command=self.cancel_training,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(8, 0))
        self.install_button = ttk.Button(
            actions,
            text="Instal Hasil ke Library",
            command=self.install_result,
            state="disabled",
        )
        self.install_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Buka Folder Output",
            command=lambda: reveal_path(self.output_value.get()),
        ).pack(side="left", padx=(8, 0))

        log_frame = ttk.LabelFrame(body, text="Training Log", padding=8)
        log_frame.grid(row=15, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(body)
        footer.grid(row=16, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(footer, text="Tutup", command=self._close).pack(side="right")

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        chooser: object,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(10, 8),
            pady=5,
        )
        ttk.Button(parent, text="Pilih…", command=chooser).grid(row=row, column=2, pady=5)

    def _folder_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        self._file_row(parent, row, label, variable, lambda: self._choose_folder(variable))

    @staticmethod
    def _entry_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=(10, 0),
            pady=5,
        )

    @staticmethod
    def _entry(
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.Variable,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(6, 12),
            pady=4,
        )

    @staticmethod
    def _spin(
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.Variable,
        values: tuple[int, ...] | None,
        start: int = 0,
        stop: int = 999999,
        increment: int = 1,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=4)
        if values is not None:
            widget = ttk.Combobox(
                parent,
                textvariable=variable,
                values=values,
                state="readonly",
            )
        else:
            widget = ttk.Spinbox(
                parent,
                textvariable=variable,
                from_=start,
                to=stop,
                increment=increment,
            )
        widget.grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(6, 12),
            pady=4,
        )

    def _choose_dataset(self) -> None:
        value = filedialog.askopenfilename(
            parent=self,
            filetypes=[("BatikCraft Dataset", "*.batikdataset")],
        )
        if not value:
            return
        self.dataset_value.set(value)
        try:
            bundle = load_batik_dataset(value)
        except Exception as exc:  # noqa: BLE001 - display normalized pack errors
            messagebox.showerror("Dataset tidak valid", str(exc), parent=self)
            return
        self.model_name_value.set(f"{bundle.metadata.name} LoRA")
        self.model_id_value.set(safe_identifier(bundle.metadata.dataset_id + "-lora"))
        self.status_value.set(
            f"Dataset valid: {len(bundle.samples)} sample · trigger {bundle.metadata.trigger_word}."
        )

    def _choose_base_model(self) -> None:
        value = filedialog.askdirectory(parent=self, title="Pilih folder base model SDXL")
        if value:
            self.base_model_value.set(value)

    @staticmethod
    def _choose_folder(variable: tk.StringVar) -> None:
        value = filedialog.askdirectory(initialdir=variable.get() or None)
        if value:
            variable.set(value)

    def start_training(self) -> None:
        if self._process is not None:
            return
        dataset = Path(self.dataset_value.get()).expanduser()
        if not dataset.is_file():
            messagebox.showerror("Dataset diperlukan", "Pilih file .batikdataset.", parent=self)
            return
        if not self.base_model_value.get().strip():
            messagebox.showerror(
                "Base model diperlukan",
                "Instal atau pilih base model SDXL terlebih dahulu.",
                parent=self,
            )
            return
        try:
            learning_rate = float(self.learning_rate_value.get())
            model_id = safe_identifier(self.model_id_value.get())
        except ValueError as exc:
            messagebox.showerror("Parameter tidak valid", str(exc), parent=self)
            return

        command = [
            sys.executable,
            "-m",
            "batikcraft_studio.ai.local_lora_training",
            "--dataset",
            str(dataset),
            "--base-model",
            self.base_model_value.get().strip(),
            "--output-dir",
            self.output_value.get().strip() or str(default_training_root()),
            "--model-name",
            self.model_name_value.get().strip(),
            "--model-id",
            model_id,
            "--version",
            self.version_value.get().strip() or "1.0.0",
            "--resolution",
            str(self.resolution_value.get()),
            "--max-steps",
            str(self.steps_value.get()),
            "--learning-rate",
            str(learning_rate),
            "--rank",
            str(self.rank_value.get()),
            "--alpha",
            str(self.alpha_value.get()),
            "--batch-size",
            str(self.batch_value.get()),
            "--gradient-accumulation",
            str(self.accumulation_value.get()),
            "--seed",
            str(self.seed_value.get()),
        ]
        self._result_path = None
        self.install_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_value.set("Training berjalan. Jangan tutup aplikasi secara paksa.")
        self._append_log("$ " + " ".join(command))

        def worker() -> None:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            # Prioritas proses diturunkan supaya UI dan pekerjaan user tetap
            # responsif ketika training memakan CPU/GPU.
            if os.name == "nt":
                flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
                preexec = None
            else:
                def preexec() -> None:
                    try:
                        os.nice(10)
                    except OSError:
                        pass
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=flags,
                    preexec_fn=preexec,
                )
                self._process = process
                assert process.stdout is not None
                for line in process.stdout:
                    self._messages.put(line.rstrip())
                code = process.wait()
                self._messages.put(f"__EXIT__:{code}")
            except OSError as exc:
                self._messages.put(f"ERROR: Training tidak dapat dimulai: {exc}")
                self._messages.put("__EXIT__:1")
            finally:
                self._process = None

        threading.Thread(target=worker, daemon=True, name="batikcraft-local-training").start()
        self.after(100, self._poll_messages)

    def _poll_messages(self) -> None:
        exit_code: int | None = None
        pending_lines: list[str] = []
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break
            if message.startswith("RESULT:"):
                self._result_path = Path(message.split(":", 1)[1])
                pending_lines.append(message)
            elif message.startswith("__EXIT__:"):
                exit_code = int(message.split(":", 1)[1])
            else:
                if message.startswith("STEP "):
                    self._update_training_progress(message)
                pending_lines.append(message)
        if pending_lines:
            # Satu insert per poll (bukan per baris) agar Text widget tidak
            # membuat UI tersendat saat training menulis log dengan cepat.
            self._append_log("\n".join(pending_lines))
        if exit_code is None:
            self.after(100, self._poll_messages)
            return
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if exit_code == 0 and self._result_path is not None:
            self.status_value.set(f"Training selesai: {self._result_path.name}")
            self.install_button.configure(state="normal")
        else:
            self.status_value.set("Training gagal. Periksa log untuk detail.")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        # Batasi panjang log agar widget tetap ringan pada training panjang.
        try:
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > 2000:
                self.log.delete("1.0", f"{lines - 2000}.0")
        except (tk.TclError, ValueError):
            pass
        self.log.see("end")
        self.log.configure(state="disabled")

    def _update_training_progress(self, message: str) -> None:
        """Parse baris "STEP g/t · loss=…" menjadi progress bar determinate."""

        bar = getattr(self, "training_progress", None)
        if bar is None or not bar.winfo_exists():
            return
        try:
            fraction = message.split(" ", 2)[1]
            current_text, total_text = fraction.split("/", 1)
            current = int(current_text)
            total = max(1, int(total_text.split(" ")[0].split("\u00b7")[0].strip()))
        except (IndexError, ValueError):
            return
        percent = max(0.0, min(100.0, current / total * 100.0))
        bar.configure(mode="determinate", maximum=100.0, value=percent)
        self.training_percent_value.set(f"{percent:.0f}%")

    def cancel_training(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            self.status_value.set("Menghentikan training…")

    def install_result(self) -> None:
        path = self._result_path
        if path is None or not path.is_file():
            return
        try:
            installed = OfflineModelLibrary().install(path, replace=True)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Instalasi model gagal", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Model terpasang",
            f"{installed.manifest.name} sudah masuk ke library model lokal.",
            parent=self,
        )

    def _close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            if not messagebox.askyesno(
                "Training masih berjalan",
                "Hentikan training dan tutup jendela?",
                parent=self,
            ):
                return
            self.cancel_training()
        self.destroy()


class TrainingResultsWindow(tk.Toplevel):
    """Browse and install completed local `.batikmodel` results."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.root_path = default_training_root()
        self.rows: dict[str, Path] = {}
        self.title("Local AI Training — Hasil Training")
        self.geometry("760x480")
        self.transient(parent.winfo_toplevel())
        self._build()
        self.refresh()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        ttk.Label(
            body,
            text="Hasil Training Lokal",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.tree = ttk.Treeview(
            body,
            columns=("path",),
            show="tree headings",
        )
        self.tree.heading("#0", text="Model")
        self.tree.heading("path", text="Lokasi")
        self.tree.column("#0", width=220)
        self.tree.column("path", width=480)
        self.tree.grid(row=1, column=0, sticky="nsew")
        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(actions, text="Buka Folder", command=lambda: reveal_path(self.root_path)).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Instal Model", command=self.install_selected).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Tutup", command=self.destroy).pack(side="right")

    def refresh(self) -> None:
        self.root_path.mkdir(parents=True, exist_ok=True)
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        self.rows.clear()
        for index, path in enumerate(sorted(self.root_path.rglob("*.batikmodel")), start=1):
            iid = str(index)
            self.rows[iid] = path
            self.tree.insert("", tk.END, iid=iid, text=path.stem, values=(str(path),))

    def install_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Pilih model", "Pilih hasil training terlebih dahulu.", parent=self)
            return
        path = self.rows[selection[0]]
        try:
            installed = OfflineModelLibrary().install(path, replace=True)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Instalasi gagal", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Model terpasang",
            f"{installed.manifest.name} berhasil dipasang.",
            parent=self,
        )


__all__ = [
    "LocalLoraTrainingWindow",
    "SDXLDatasetStudioWindow",
    "TrainingResultsWindow",
]
