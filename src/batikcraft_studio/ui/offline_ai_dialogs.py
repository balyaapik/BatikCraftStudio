"""Dataset Studio and offline model manager windows for Milestone 4B."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

from batikcraft_studio.ai import (
    BATIK_DATASET_EXTENSION,
    BATIK_MODEL_EXTENSION,
    BatikDatasetError,
    BatikDatasetMetadata,
    BatikTrainingSample,
    build_batik_dataset,
)
from batikcraft_studio.application import OfflineAIProjectSession, ProjectSessionError
from batikcraft_studio.i18n import tr


class DatasetStudioWindow(tk.Toplevel):
    """Create portable `.batikdataset` archives from image pairs."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(tr("offline.dataset.title"))
        self.geometry("850x590")
        self.minsize(760, 520)
        self.transient(parent.winfo_toplevel())
        self.samples: list[BatikTrainingSample] = []
        self.target_path = tk.StringVar()
        self.source_path = tk.StringVar()
        self.conditioning_path = tk.StringVar()
        self.mask_path = tk.StringVar()
        self.category_value = tk.StringVar(value="wayang")
        self.style_value = tk.StringVar(value="klasik-jawa")
        self.dataset_name = tk.StringVar(value="BatikCraft Training Dataset")
        self.dataset_id = tk.StringVar(value="batikcraft-training-v1")
        self.author_value = tk.StringVar(value="")
        self.trigger_value = tk.StringVar(value="bcr_batik")
        self.base_family_value = tk.StringVar(value="sd15")
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        metadata = ttk.LabelFrame(
            body,
            text=tr("offline.dataset.metadata"),
            padding=10,
        )
        metadata.grid(row=0, column=0, sticky="ew")
        for column in (1, 3, 5):
            metadata.columnconfigure(column, weight=1)
        self._entry(metadata, 0, 0, "offline.dataset.id", self.dataset_id)
        self._entry(metadata, 0, 2, "offline.dataset.name", self.dataset_name)
        self._entry(metadata, 0, 4, "offline.dataset.author", self.author_value)
        self._entry(metadata, 1, 0, "offline.dataset.trigger", self.trigger_value)
        self._entry(
            metadata,
            1,
            2,
            "offline.dataset.base_family",
            self.base_family_value,
        )

        sample = ttk.LabelFrame(body, text=tr("offline.dataset.sample"), padding=10)
        sample.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        sample.columnconfigure(1, weight=1)
        row = 0
        for label_key, variable, required in (
            ("offline.dataset.target", self.target_path, True),
            ("offline.dataset.source", self.source_path, False),
            ("offline.dataset.conditioning", self.conditioning_path, False),
            ("offline.dataset.mask", self.mask_path, False),
        ):
            ttk.Label(sample, text=tr(label_key)).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            ttk.Entry(sample, textvariable=variable).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=3,
            )
            ttk.Button(
                sample,
                text=tr("common.choose"),
                command=lambda target=variable: self._choose_image(target),
            ).grid(row=row, column=2, padx=(6, 0), pady=3)
            if required:
                ttk.Label(sample, text="*").grid(row=row, column=3, sticky="w")
            row += 1

        ttk.Label(sample, text=tr("offline.dataset.category")).grid(
            row=row, column=0, sticky="w", pady=3
        )
        ttk.Entry(sample, textvariable=self.category_value).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        ttk.Label(sample, text=tr("offline.dataset.style")).grid(
            row=row, column=2, sticky="e", padx=(8, 4), pady=3
        )
        ttk.Entry(sample, textvariable=self.style_value, width=18).grid(
            row=row, column=3, sticky="ew", pady=3
        )
        row += 1

        ttk.Label(sample, text=tr("offline.dataset.caption")).grid(
            row=row, column=0, sticky="nw", pady=3
        )
        self.caption_text = tk.Text(sample, height=3, wrap="word")
        self.caption_text.grid(
            row=row,
            column=1,
            columnspan=3,
            sticky="ew",
            pady=3,
        )
        row += 1
        ttk.Button(
            sample,
            text=tr("offline.dataset.add_sample"),
            command=self._add_sample,
        ).grid(row=row, column=3, sticky="e", pady=(6, 0))

        listing = ttk.Frame(body)
        listing.grid(row=2, column=0, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            listing,
            columns=("caption", "category", "style"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("caption", text=tr("offline.dataset.caption"))
        self.tree.heading("category", text=tr("offline.dataset.category"))
        self.tree.heading("style", text=tr("offline.dataset.style"))
        self.tree.column("caption", width=430)
        self.tree.column("category", width=110)
        self.tree.column("style", width=130)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            listing,
            orient="vertical",
            command=self.tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text=tr("offline.dataset.remove_sample"),
            command=self._remove_sample,
        ).pack(side="left")
        ttk.Label(actions, text=tr("offline.dataset.note"), style="Muted.TLabel").pack(
            side="left",
            padx=12,
        )
        ttk.Button(
            actions,
            text=tr("offline.dataset.export"),
            command=self._export,
        ).pack(side="right")
        ttk.Button(
            actions,
            text=tr("common.close"),
            command=self.destroy,
        ).pack(side="right", padx=(0, 6))

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        column: int,
        label_key: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=tr(label_key)).grid(
            row=row,
            column=column,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(0, 12),
            pady=3,
        )

    def _choose_image(self, variable: tk.StringVar) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title=tr("offline.dataset.choose_image"),
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            variable.set(selected)

    def _add_sample(self) -> None:
        target = Path(self.target_path.get().strip())
        if not target.is_file():
            messagebox.showerror(
                self.title(),
                tr("offline.dataset.target_required"),
                parent=self,
            )
            return
        caption = self.caption_text.get("1.0", "end").strip()
        try:
            sample = BatikTrainingSample(
                sample_id=f"sample-{len(self.samples) + 1:06d}-{uuid4().hex[:8]}",
                caption=caption,
                target_content=target.read_bytes(),
                source_content=self._optional_bytes(self.source_path.get()),
                conditioning_content=self._optional_bytes(
                    self.conditioning_path.get()
                ),
                mask_content=self._optional_bytes(self.mask_path.get()),
                category=self.category_value.get(),
                style=self.style_value.get(),
                target_roles=("main-render", "isen", "ornament"),
                metadata={"target_original_name": target.name},
            )
        except (BatikDatasetError, OSError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self.samples.append(sample)
        self.tree.insert(
            "",
            "end",
            iid=sample.sample_id,
            values=(sample.caption, sample.category, sample.style),
        )
        self.target_path.set("")
        self.source_path.set("")
        self.conditioning_path.set("")
        self.mask_path.set("")
        self.caption_text.delete("1.0", "end")

    def _optional_bytes(self, value: str) -> bytes | None:
        text = value.strip()
        if not text:
            return None
        path = Path(text)
        if not path.is_file():
            raise BatikDatasetError(f"File tidak ditemukan: {path}")
        return path.read_bytes()

    def _remove_sample(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        sample_id = selection[0]
        self.samples = [
            sample for sample in self.samples if sample.sample_id != sample_id
        ]
        self.tree.delete(sample_id)

    def _export(self) -> None:
        if not self.samples:
            messagebox.showerror(
                self.title(),
                tr("offline.dataset.empty"),
                parent=self,
            )
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title=tr("offline.dataset.export"),
            defaultextension=BATIK_DATASET_EXTENSION,
            filetypes=[
                ("BatikCraft Dataset", f"*{BATIK_DATASET_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not destination:
            return
        try:
            metadata = BatikDatasetMetadata(
                dataset_id=self.dataset_id.get(),
                name=self.dataset_name.get(),
                author=self.author_value.get(),
                base_model_family=self.base_family_value.get(),
                trigger_word=self.trigger_value.get(),
            )
        except (BatikDatasetError, ValueError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return

        # Ekspor berjalan di background worker dengan progress bar sehingga
        # jendela tidak membeku saat menormalkan banyak gambar besar.
        from .progress_dialog import ProgressDialog, ProgressUpdate

        samples = list(self.samples)
        progress = ProgressDialog(
            self,
            title=tr("offline.dataset.export"),
            message=f"Mengekspor {len(samples)} sampel dataset…",
            cancellable=False,
            auto_close_ms=700,
        )
        progress.post(
            ProgressUpdate(
                f"Menormalkan dan mengemas {len(samples)} sampel…",
                None,
                None,
                detail=str(destination),
            )
        )

        def worker() -> None:
            try:
                output = build_batik_dataset(samples, metadata, destination)
            except (BatikDatasetError, OSError) as exc:
                message = str(exc)
                self.after(0, lambda: self._finish_export_error(progress, message))
                return
            self.after(0, lambda: self._finish_export_success(progress, output))

        threading.Thread(
            target=worker, daemon=True, name="batikcraft-dataset-export"
        ).start()

    def _finish_export_success(self, progress: object, output: object) -> None:
        try:
            progress.reporter.complete("Dataset selesai diekspor.")
        except Exception:  # noqa: BLE001
            pass
        if self.winfo_exists():
            messagebox.showinfo(
                self.title(),
                tr("offline.dataset.exported", path=output),
                parent=self,
            )

    def _finish_export_error(self, progress: object, message: str) -> None:
        try:
            progress.fail(message)
        except Exception:  # noqa: BLE001
            pass
        if self.winfo_exists():
            messagebox.showerror(self.title(), message, parent=self)


class OfflineModelManagerWindow(tk.Toplevel):
    """Install LoRA packs and bind them to local base/ControlNet folders."""

    def __init__(
        self,
        parent: tk.Misc,
        session: OfflineAIProjectSession,
        *,
        on_change: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.on_change = on_change
        self.title(tr("offline.models.title"))
        self.geometry("860x540")
        self.minsize(760, 480)
        self.transient(parent.winfo_toplevel())
        self.base_path = tk.StringVar()
        self.controlnet_path = tk.StringVar()
        self.device_value = tk.StringVar(value="auto")
        self.precision_value = tk.StringVar(value="auto")
        self.steps_value = tk.IntVar(value=28)
        self.guidance_value = tk.DoubleVar(value=7.0)
        self.control_value = tk.DoubleVar(value=0.85)
        self.lora_value = tk.DoubleVar(value=0.85)
        self.cpu_offload = tk.BooleanVar(value=False)
        self._build()
        self._sync_managed_runtime_paths()
        self.bind("<FocusIn>", lambda _e: self._sync_managed_runtime_paths(), add="+")
        self._refresh()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text=tr("offline.models.installed"), padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            left,
            columns=("version", "family", "weight"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text=tr("common.name"))
        self.tree.heading("version", text=tr("offline.models.version"))
        self.tree.heading("family", text=tr("offline.models.base_family"))
        self.tree.heading("weight", text=tr("offline.models.weight"))
        self.tree.column("#0", width=220)
        self.tree.column("version", width=70)
        self.tree.column("family", width=90)
        self.tree.column("weight", width=70)
        self.tree.grid(row=0, column=0, sticky="nsew")
        model_actions = ttk.Frame(left)
        model_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            model_actions,
            text=tr("offline.models.install"),
            command=self._install,
        ).pack(side="left")
        ttk.Button(
            model_actions,
            text=tr("offline.models.uninstall"),
            command=self._uninstall,
        ).pack(side="left", padx=(6, 0))

        right = ttk.LabelFrame(body, text=tr("offline.models.runtime"), padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        row = 0
        # Path base model & ControlNet TIDAK diisi manual: keduanya otomatis
        # mengikuti runtime terpasang dari Dependency Manager.
        self.base_path_display = tk.StringVar(master=self)
        self.controlnet_path_display = tk.StringVar(master=self)
        for label_key, display in (
            ("offline.models.base_path", self.base_path_display),
            ("offline.models.controlnet_path", self.controlnet_path_display),
        ):
            ttk.Label(right, text=tr(label_key)).grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 8)
            )
            ttk.Label(
                right,
                textvariable=display,
                style="Muted.TLabel",
                wraplength=340,
                justify="left",
            ).grid(row=row, column=1, sticky="ew", pady=4)
            row += 1
        for label_key, variable, values in (
            ("offline.models.device", self.device_value, ("auto", "cuda", "cpu", "mps")),
            (
                "offline.models.precision",
                self.precision_value,
                ("auto", "float16", "float32", "bfloat16"),
            ),
        ):
            ttk.Label(right, text=tr(label_key)).grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 8)
            )
            ttk.Combobox(
                right,
                textvariable=variable,
                values=values,
                state="readonly",
            ).grid(row=row, column=1, sticky="ew", pady=4)
            row += 1
        for label_key, variable, from_, to, increment in (
            ("offline.models.steps", self.steps_value, 1, 150, 1),
            ("offline.models.guidance", self.guidance_value, 0, 30, 0.5),
            ("offline.models.control_scale", self.control_value, 0, 2, 0.05),
            ("offline.models.lora_scale", self.lora_value, 0, 2, 0.05),
        ):
            ttk.Label(right, text=tr(label_key)).grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 8)
            )
            ttk.Spinbox(
                right,
                textvariable=variable,
                from_=from_,
                to=to,
                increment=increment,
            ).grid(row=row, column=1, sticky="ew", pady=4)
            row += 1
        ttk.Checkbutton(
            right,
            text=tr("offline.models.cpu_offload"),
            variable=self.cpu_offload,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
        row += 1
        ttk.Label(
            right,
            text=tr("offline.models.offline_note"),
            style="Muted.TLabel",
            wraplength=370,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        row += 1
        actions = ttk.Frame(right)
        actions.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(
            actions,
            text=tr("offline.models.foundation"),
            command=self._use_foundation,
        ).pack(side="left")
        ttk.Button(
            actions,
            text=tr("offline.models.activate"),
            command=self._activate,
        ).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(body)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.status = ttk.Label(bottom, style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(
            bottom,
            text=tr("common.close"),
            command=self.destroy,
        ).pack(side="right")

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label_key: str,
        variable: tk.StringVar,
    ) -> int:
        ttk.Label(parent, text=tr(label_key)).grid(
            row=row, column=0, sticky="w", pady=4, padx=(0, 8)
        )
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=4)
        holder.columnconfigure(0, weight=1)
        ttk.Entry(holder, textvariable=variable).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            holder,
            text="…",
            width=3,
            command=lambda: self._choose_directory(variable),
        ).grid(row=0, column=1, padx=(5, 0))
        return row + 1

    def _choose_directory(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(parent=self)
        if selected:
            variable.set(selected)

    def _sync_managed_runtime_paths(self) -> None:
        """Selaraskan path base/ControlNet dengan runtime dari Dependency Manager.

        Tidak ada input manual: bila runtime terpasang, path terisi otomatis;
        bila belum, tampil arahan untuk menginstal lewat menu Dependencies.
        """

        missing = "Belum terpasang — instal lewat menu Dependencies."
        try:
            from batikcraft_studio.ai.runtime_model_installer import (
                find_installed_runtime_models,
            )

            installed = find_installed_runtime_models()
        except Exception:  # noqa: BLE001 - jangan gagalkan pembukaan jendela
            installed = None
        if installed is None:
            self.base_path.set("")
            self.controlnet_path.set("")
            if hasattr(self, "base_path_display"):
                self.base_path_display.set(missing)
                self.controlnet_path_display.set(missing)
            return
        self.base_path.set(str(installed.base_model))
        self.controlnet_path.set(str(installed.controlnet))
        if hasattr(self, "base_path_display"):
            self.base_path_display.set(str(installed.base_model))
            self.controlnet_path_display.set(str(installed.controlnet))

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for installed in self.session.installed_models:
            manifest = installed.manifest
            self.tree.insert(
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
        runtime = self.session.runtime_selection
        if runtime is None:
            self.status.configure(text=tr("offline.models.foundation_active"))
        else:
            self.status.configure(
                text=tr("offline.models.active", model=runtime.model_id)
            )
            if self.tree.exists(runtime.model_id):
                self.tree.selection_set(runtime.model_id)

    def _selected_model_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _install(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title=tr("offline.models.install"),
            filetypes=[
                ("BatikCraft Model", f"*{BATIK_MODEL_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        try:
            self.session.install_model_pack(selected, replace=True)
        except ProjectSessionError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh()

    def _uninstall(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            return
        if not messagebox.askyesno(
            self.title(),
            tr("offline.models.uninstall_confirm", model=model_id),
            parent=self,
        ):
            return
        try:
            self.session.uninstall_model_pack(model_id)
        except ProjectSessionError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh()
        self._changed()

    def _activate(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            messagebox.showerror(
                self.title(),
                tr("offline.models.select_required"),
                parent=self,
            )
            return
        control_text = self.controlnet_path.get().strip()
        try:
            self.session.configure_offline_model(
                model_id,
                base_model_path=self.base_path.get().strip(),
                controlnet_path=control_text or None,
                device=self.device_value.get(),
                precision=self.precision_value.get(),
                inference_steps=int(self.steps_value.get()),
                guidance_scale=float(self.guidance_value.get()),
                controlnet_scale=float(self.control_value.get()),
                lora_scale=float(self.lora_value.get()),
                cpu_offload=self.cpu_offload.get(),
            )
        except (ProjectSessionError, ValueError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self._refresh()
        self._changed()

    def _use_foundation(self) -> None:
        self.session.use_foundation_renderer()
        self._refresh()
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


__all__ = [
    "DatasetStudioWindow",
    "OfflineModelManagerWindow",
]
