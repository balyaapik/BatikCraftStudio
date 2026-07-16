"""Settings dialog for notebook-compatible BatikBrew SDXL generation."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from batikcraft_studio.ai.batikbrew_generation import (
    SDXL_BASE_MODEL_ID,
    BatikBrewGenerationOptions,
)
from batikcraft_studio.ai.model_pack import InstalledBatikModel
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.ai.runtime_model_installer import (
    BatikBrewRuntimePaths,
    find_installed_batikbrew_runtime,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

from .ai_runtime_model_install_dialog import RuntimeModelInstallDialog


class BatikBrewGenerationDialog(tk.Toplevel):
    """Collect SDXL LoRA generation controls and install the runtime in-app."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        defaults: PretrainedAIBatificationOptions,
        installed_models: tuple[InstalledBatikModel, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.result: BatikBrewGenerationOptions | None = None
        self.defaults = defaults
        self._managed_runtime = find_installed_batikbrew_runtime()
        self._model_by_label = self._compatible_models(installed_models)
        labels = tuple(self._model_by_label)

        self.title("BatikBrew Generatif — SDXL LoRA")
        self.geometry("820x760")
        self.minsize(740, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.model_value = tk.StringVar(master=self, value=labels[0] if labels else "")
        self.base_model_value = tk.StringVar(master=self, value=self._initial_base_model())
        self.lora_path_value = tk.StringVar(master=self)
        self.lora_weight_value = tk.DoubleVar(master=self, value=1.0)
        self.trigger_value = tk.StringVar(master=self, value="batikbrew")
        self.steps_value = tk.IntVar(master=self, value=max(30, defaults.inference_steps))
        self.guidance_value = tk.DoubleVar(master=self, value=7.5)
        self.seed_value = tk.StringVar(master=self, value=str(defaults.seed))
        self.resolution_value = tk.IntVar(master=self, value=max(512, defaults.resolution))
        self.variations_value = tk.IntVar(master=self, value=4)
        self.tileable_value = tk.BooleanVar(master=self, value=True)

        self._build(labels)
        if labels:
            self._select_installed_model()
        self.grab_set()
        self.focus_set()

    @staticmethod
    def _compatible_models(
        models: tuple[InstalledBatikModel, ...],
    ) -> dict[str, InstalledBatikModel]:
        compatible: dict[str, InstalledBatikModel] = {}
        for model in models:
            family = model.manifest.base_model_family.casefold()
            engine = str((model.manifest.metadata or {}).get("generation_engine", "")).casefold()
            if "sdxl" in family or "batikbrew" in engine:
                label = f"{model.manifest.name} · v{model.manifest.version} · SDXL"
                compatible[label] = model
        return compatible

    def _initial_base_model(self) -> str:
        if self._managed_runtime is not None:
            return str(self._managed_runtime.base_model)
        current = str(self.defaults.model_id_or_path)
        return current if "xl" in current.casefold() else SDXL_BASE_MODEL_ID

    def _build(self, model_labels: tuple[str, ...]) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Generate Motif BatikBrew dari Objek Inspirasi",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text=(
                "Sesuai notebook BatikCraft: objek dianalisis untuk warna, kepadatan garis, "
                "tema, dan komposisi. SDXL + LoRA membuat motif baru; tidak ada img2img fill."
            ),
            wraplength=770,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(3, 12))

        row = 2
        row = self._path_row(
            body,
            row,
            "Runtime SDXL",
            self.base_model_value,
            "Unduh SDXL…",
            self._install_sdxl,
        )

        ttk.Label(body, text="LoRA BatikBrew terpasang").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        combo = ttk.Combobox(
            body,
            textvariable=self.model_value,
            values=model_labels,
            state="readonly" if model_labels else "disabled",
        )
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._select_installed_model())
        ttk.Button(body, text="Gunakan", command=self._select_installed_model).grid(
            row=row, column=2, sticky="e", padx=(6, 0), pady=4
        )
        row += 1

        row = self._path_row(
            body,
            row,
            "File LoRA SDXL",
            self.lora_path_value,
            "Pilih…",
            self._browse_lora,
        )
        row = self._entry_row(body, row, "Trigger words", self.trigger_value)
        row = self._scale_row(
            body, row, "Bobot LoRA", self.lora_weight_value, 0.0, 2.0, 0.05
        )

        numeric = ttk.Frame(body)
        numeric.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 4))
        for index in range(5):
            numeric.columnconfigure(index, weight=1)
        self._spinbox(numeric, 0, "Steps", self.steps_value, 10, 80, 1)
        self._spinbox(numeric, 1, "Guidance", self.guidance_value, 1, 20, 0.5)
        self._spinbox(numeric, 2, "Seed", self.seed_value, 0, 2_147_483_647, 1)
        self._spinbox(numeric, 3, "Resolusi", self.resolution_value, 512, 1024, 128)
        self._spinbox(numeric, 4, "Variasi", self.variations_value, 1, 4, 1)
        row += 1

        ttk.Checkbutton(
            body,
            text="Buat hasil seamless/tileable seperti notebook",
            variable=self.tileable_value,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 8))
        row += 1

        self.prompt_text, row = self._text_row(
            body,
            row,
            "Creative direction",
            self.defaults.prompt,
            height=5,
        )
        self.negative_text, row = self._text_row(
            body,
            row,
            "Negative prompt tambahan",
            self.defaults.negative_prompt,
            height=4,
        )

        note = (
            "Pilih satu objek sebagai inspirasi; Shift-pilih objek kedua untuk menggabungkan "
            "dua sumber. Setelah generasi, pilih satu dari maksimal empat variasi."
        )
        if not model_labels:
            note += " Pilih file LoRA hasil notebook atau instal paket .batikmodel SDXL."
        ttk.Label(
            body,
            text=note,
            style="Muted.TLabel",
            wraplength=770,
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 12))
        row += 1

        actions = ttk.Frame(body)
        actions.grid(row=row, column=0, columnspan=3, sticky="e")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(actions, text="Generate Variasi", command=self._accept).pack(side="right")

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        button_text: str,
        command: object,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=4
        )
        ttk.Button(parent, text=button_text, command=command).grid(
            row=row, column=2, sticky="e", padx=(6, 0), pady=4
        )
        return row + 1

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4
        )
        return row + 1

    def _scale_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        start: float,
        stop: float,
        resolution: float,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=3
        )
        tk.Scale(
            parent,
            variable=variable,
            from_=start,
            to=stop,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            showvalue=True,
        ).grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        return row + 1

    def _text_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value: str,
        *,
        height: int,
    ) -> tuple[tk.Text, int]:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        widget = tk.Text(parent, height=height, wrap="word")
        widget.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        widget.insert("1.0", value)
        return widget, row + 1

    def _spinbox(
        self,
        parent: ttk.Frame,
        column: int,
        label: str,
        variable: tk.Variable,
        start: float,
        stop: float,
        increment: float,
    ) -> None:
        holder = ttk.Frame(parent)
        holder.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
        ttk.Label(holder, text=label, style="Muted.TLabel").pack(anchor="w")
        ttk.Spinbox(
            holder,
            textvariable=variable,
            from_=start,
            to=stop,
            increment=increment,
            width=10,
        ).pack(fill="x")

    def _select_installed_model(self) -> None:
        model = self._model_by_label.get(self.model_value.get())
        if model is None:
            return
        self.lora_path_value.set(str(model.lora_path))
        self.lora_weight_value.set(model.manifest.recommended_weight)
        self.trigger_value.set(", ".join(model.manifest.trigger_words))
        self.resolution_value.set(min(1024, max(512, model.manifest.resolution)))
        if model.manifest.negative_prompt:
            self.negative_text.delete("1.0", "end")
            self.negative_text.insert("1.0", model.manifest.negative_prompt)
        metadata = dict(model.manifest.metadata or {})
        base_model = str(metadata.get("base_model_id", "")).strip()
        if self._managed_runtime is not None:
            base_model = str(self._managed_runtime.base_model)
        if base_model:
            self.base_model_value.set(base_model)

    def _browse_lora(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Pilih LoRA BatikBrew SDXL",
            filetypes=(
                ("LoRA safetensors", "*.safetensors"),
                ("LoRA binary", "*.bin"),
                ("Semua file", "*.*"),
            ),
        )
        if selected:
            self.lora_path_value.set(selected)

    def _install_sdxl(self) -> None:
        dialog = RuntimeModelInstallDialog(self, family="sdxl")
        self.wait_window(dialog)
        result = dialog.result
        if isinstance(result, BatikBrewRuntimePaths):
            self._managed_runtime = result
            self.base_model_value.set(str(result.base_model))

    def _accept(self) -> None:
        try:
            triggers = tuple(
                part.strip()
                for part in self.trigger_value.get().replace(";", ",").split(",")
                if part.strip()
            )
            model_source = self.base_model_value.get().strip() or SDXL_BASE_MODEL_ID
            self.result = BatikBrewGenerationOptions(
                model_id_or_path=model_source,
                prompt=self.prompt_text.get("1.0", "end").strip(),
                negative_prompt=self.negative_text.get("1.0", "end").strip(),
                inference_steps=int(self.steps_value.get()),
                guidance_scale=float(self.guidance_value.get()),
                seed=int(self.seed_value.get().strip()),
                device=self.defaults.device,
                precision=self.defaults.precision,
                local_files_only=Path(model_source).expanduser().exists(),
                cpu_offload=self.defaults.cpu_offload,
                cache_dir=self.defaults.cache_dir,
                resolution=int(self.resolution_value.get()),
                lora_path=self.lora_path_value.get().strip(),
                lora_weight=float(self.lora_weight_value.get()),
                lora_trigger_words=triggers,
                variation_count=int(self.variations_value.get()),
                tileable=bool(self.tileable_value.get()),
            )
        except (BatificationError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan BatikBrew tidak valid", str(exc), parent=self)
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewGenerationDialog"]
