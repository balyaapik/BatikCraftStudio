"""Modal settings window for Stable Diffusion plus LoRA object Batification."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from batikcraft_studio.ai.lora_object_batification import LoraObjectBatificationOptions
from batikcraft_studio.ai.model_pack import InstalledBatikModel
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.imaging.structured_batification import BatificationError


class AIObjectBatificationDialog(tk.Toplevel):
    """Collect creative settings while compute settings remain global."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        defaults: PretrainedAIBatificationOptions,
        installed_models: tuple[InstalledBatikModel, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.result: LoraObjectBatificationOptions | None = None
        self.defaults = defaults
        self._model_by_label: dict[str, InstalledBatikModel] = {}

        self.title("Batifikasi Objek — Stable Diffusion + LoRA")
        self.geometry("780x760")
        self.minsize(700, 660)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        for model in installed_models:
            label = f"{model.manifest.name} · v{model.manifest.version}"
            self._model_by_label[label] = model
        labels = tuple(self._model_by_label)
        self.model_value = tk.StringVar(master=self, value=labels[0] if labels else "")
        self.lora_path_value = tk.StringVar(master=self)
        self.lora_weight_value = tk.DoubleVar(master=self, value=0.85)
        self.trigger_value = tk.StringVar(master=self, value="bcr_batik")
        self.strength_value = tk.DoubleVar(master=self, value=defaults.strength * 100)
        self.blend_value = tk.DoubleVar(master=self, value=defaults.ai_blend * 100)
        self.pattern_scale_value = tk.DoubleVar(master=self, value=defaults.pattern_scale)
        self.shading_value = tk.DoubleVar(master=self, value=defaults.preserve_shading * 100)
        self.steps_value = tk.IntVar(master=self, value=defaults.inference_steps)
        self.guidance_value = tk.DoubleVar(master=self, value=defaults.guidance_scale)
        self.seed_value = tk.StringVar(master=self, value=str(defaults.seed))
        self.resolution_value = tk.IntVar(master=self, value=defaults.resolution)

        self._build(labels)
        if labels:
            self._select_installed_model()
        self.grab_set()
        self.focus_set()

    def _build(self, model_labels: tuple[str, ...]) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Batifikasi Objek dengan AI",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text=(
                "Bentuk objek dijaga oleh img2img, mask/alpha, dan outline sumber. "
                "Gaya Batik berasal dari LoRA yang dipasang di atas Stable Diffusion."
            ),
            wraplength=730,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(3, 12))

        row = 2
        runtime_text = (
            f"Base model: {self.defaults.model_id_or_path}\n"
            f"Runtime global: {self.defaults.device} / {self.defaults.precision}"
        )
        ttk.Label(body, text="Runtime").grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 10),
        )
        ttk.Label(
            body,
            text=runtime_text,
            style="Muted.TLabel",
            justify="left",
        ).grid(row=row, column=1, columnspan=2, sticky="w")
        row += 1

        ttk.Label(body, text="LoRA Batik terpasang").grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        model_combo = ttk.Combobox(
            body,
            textvariable=self.model_value,
            values=model_labels,
            state="readonly" if model_labels else "disabled",
        )
        model_combo.grid(row=row, column=1, sticky="ew", pady=4)
        model_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._select_installed_model(),
        )
        ttk.Button(body, text="Gunakan", command=self._select_installed_model).grid(
            row=row,
            column=2,
            sticky="e",
            padx=(6, 0),
            pady=4,
        )
        row += 1

        ttk.Label(body, text="File LoRA").grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        ttk.Entry(body, textvariable=self.lora_path_value).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=4,
        )
        ttk.Button(body, text="Pilih…", command=self._browse_lora).grid(
            row=row,
            column=2,
            sticky="e",
            padx=(6, 0),
            pady=4,
        )
        row += 1

        row = self._entry_row(body, row, "Trigger words", self.trigger_value)
        row = self._scale_row(
            body,
            row,
            "Bobot LoRA",
            self.lora_weight_value,
            0,
            2,
            0.05,
        )
        row = self._scale_row(
            body,
            row,
            "Kekuatan perubahan",
            self.strength_value,
            5,
            80,
            1,
        )
        row = self._scale_row(
            body,
            row,
            "Campuran hasil AI",
            self.blend_value,
            0,
            100,
            1,
        )
        row = self._scale_row(
            body,
            row,
            "Skala motif referensi",
            self.pattern_scale_value,
            0.08,
            4,
            0.05,
        )
        row = self._scale_row(
            body,
            row,
            "Pertahankan shading",
            self.shading_value,
            0,
            100,
            1,
        )

        numeric = ttk.Frame(body)
        numeric.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 4))
        for index in range(4):
            numeric.columnconfigure(index, weight=1)
        self._spinbox(numeric, 0, "Steps", self.steps_value, 1, 100, 1)
        self._spinbox(numeric, 1, "Guidance", self.guidance_value, 0, 30, 0.5)
        self._spinbox(numeric, 2, "Seed", self.seed_value, 0, 2_147_483_647, 1)
        self._spinbox(numeric, 3, "Resolusi", self.resolution_value, 256, 1024, 64)
        row += 1

        ttk.Label(body, text="Prompt").grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=4,
        )
        self.prompt_text = tk.Text(body, height=4, wrap="word")
        self.prompt_text.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        self.prompt_text.insert("1.0", self.defaults.prompt)
        row += 1

        ttk.Label(body, text="Negative prompt").grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=4,
        )
        self.negative_text = tk.Text(body, height=3, wrap="word")
        self.negative_text.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        self.negative_text.insert("1.0", self.defaults.negative_prompt)
        row += 1

        ttk.Label(
            body,
            text=(
                "Pilih objek sumber terlebih dahulu lalu Shift-pilih motif referensi. "
                "Klik kanan pada objek dan pilih Batifikasi Objek dengan AI & LoRA."
            ),
            style="Muted.TLabel",
            wraplength=730,
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 12))
        row += 1

        actions = ttk.Frame(body)
        actions.grid(row=row, column=0, columnspan=3, sticky="e")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right",
            padx=(6, 0),
        )
        ttk.Button(actions, text="Generate Batik", command=self._accept).pack(
            side="right"
        )

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
    ) -> int:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=4,
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
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=3,
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
        holder.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0 if column == 0 else 5, 0),
        )
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
        if model.manifest.negative_prompt:
            self.negative_text.delete("1.0", "end")
            self.negative_text.insert("1.0", model.manifest.negative_prompt)
        self.resolution_value.set(min(1024, max(256, model.manifest.resolution)))

    def _browse_lora(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Pilih LoRA Batik",
            filetypes=(
                ("LoRA safetensors", "*.safetensors"),
                ("LoRA binary", "*.bin"),
                ("Semua file", "*.*"),
            ),
        )
        if selected:
            self.lora_path_value.set(selected)

    def _accept(self) -> None:
        try:
            triggers = tuple(
                part.strip()
                for part in self.trigger_value.get().replace(";", ",").split(",")
                if part.strip()
            )
            self.result = LoraObjectBatificationOptions(
                model_id_or_path=self.defaults.model_id_or_path,
                prompt=self.prompt_text.get("1.0", "end").strip(),
                negative_prompt=self.negative_text.get("1.0", "end").strip(),
                strength=float(self.strength_value.get()) / 100,
                ai_blend=float(self.blend_value.get()) / 100,
                pattern_scale=float(self.pattern_scale_value.get()),
                preserve_shading=float(self.shading_value.get()) / 100,
                inference_steps=int(self.steps_value.get()),
                guidance_scale=float(self.guidance_value.get()),
                seed=int(self.seed_value.get()),
                device=self.defaults.device,
                precision=self.defaults.precision,
                local_files_only=self.defaults.local_files_only,
                cpu_offload=self.defaults.cpu_offload,
                cache_dir=self.defaults.cache_dir,
                resolution=int(self.resolution_value.get()),
                lora_path=self.lora_path_value.get(),
                lora_weight=float(self.lora_weight_value.get()),
                lora_trigger_words=triggers,
            )
        except (BatificationError, OSError, TypeError, ValueError, tk.TclError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["AIObjectBatificationDialog"]
