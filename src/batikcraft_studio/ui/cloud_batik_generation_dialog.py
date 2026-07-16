"""Generation controls for watsonx.ai, Gemini, and OpenAI Batik providers."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from batikcraft_studio.ai.generation_providers import (
    CloudGenerationSettingsStore,
    get_cloud_generation_settings_store,
    provider_label,
)
from batikcraft_studio.ai.hybrid_batik_generation import CloudBatikBrewOptions
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.imaging.structured_batification import BatificationError

from .cloud_ai_settings_dialog import CloudAISettingsDialog


class CloudBatikGenerationDialog(tk.Toplevel):
    """Collect provider model, prompt, seed hints, and variation count."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        provider_id: str,
        output_mode: str,
        defaults: PretrainedAIBatificationOptions,
        settings_store: CloudGenerationSettingsStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.provider_id = provider_id
        self.output_mode = output_mode
        self.defaults = defaults
        self.settings_store = settings_store or get_cloud_generation_settings_store()
        settings = self.settings_store.load()
        self.result: CloudBatikBrewOptions | None = None

        mode_label = "Ornamen Tunggal" if output_mode == "ornament" else "Pola"
        self.title(f"{provider_label(provider_id)} — {mode_label}")
        self.geometry("760x650")
        self.minsize(680, 580)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.model_value = tk.StringVar(master=self, value=settings.model_for(provider_id))
        self.seed_value = tk.StringVar(master=self, value=str(defaults.seed))
        self.variations_value = tk.IntVar(master=self, value=4)
        self.tileable_value = tk.BooleanVar(
            master=self,
            value=output_mode == "pattern",
        )
        self.resolution_value = tk.IntVar(master=self, value=max(512, defaults.resolution))
        self.status_value = tk.StringVar(
            master=self,
            value=(
                "Provider API menggunakan analisis warna, garis, tema, dan komposisi dari objek "
                "yang dipilih. API key tidak disimpan dalam hasil."
            ),
        )

        self._build()
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(6, weight=1)

        ttk.Label(
            body,
            text=f"Generate dengan {provider_label(self.provider_id)}",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            textvariable=self.status_value,
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 12))

        ttk.Label(body, text="Model API").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(body, textvariable=self.model_value).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Button(
            body,
            text="Pengaturan API…",
            command=self._open_api_settings,
        ).grid(row=2, column=2, padx=(8, 0), pady=4)

        numeric = ttk.Frame(body)
        numeric.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        for index in range(3):
            numeric.columnconfigure(index, weight=1)
        self._spinbox(numeric, 0, "Seed hint", self.seed_value, 0, 2_147_483_647, 1)
        self._spinbox(numeric, 1, "Variasi", self.variations_value, 1, 4, 1)
        self._spinbox(numeric, 2, "Resolusi target", self.resolution_value, 512, 1024, 128)

        tile = ttk.Checkbutton(
            body,
            text="Buat pola seamless/tileable setelah hasil API diterima",
            variable=self.tileable_value,
        )
        tile.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 8))
        if self.output_mode == "ornament":
            self.tileable_value.set(False)
            tile.configure(state="disabled")

        ttk.Label(body, text="Creative direction").grid(
            row=5, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.prompt_text = tk.Text(body, height=7, wrap="word")
        self.prompt_text.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=4)
        self.prompt_text.insert("1.0", self.defaults.prompt)

        ttk.Label(body, text="Negative prompt tambahan").grid(
            row=6, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.negative_text = tk.Text(body, height=6, wrap="word")
        self.negative_text.grid(row=6, column=1, columnspan=2, sticky="nsew", pady=4)
        self.negative_text.insert("1.0", self.defaults.negative_prompt)

        note = (
            "Provider API tidak menjamin seed deterministik. Seed dipakai sebagai composition hint "
            "agar setiap variasi tetap berbeda. Untuk Ornamen Tunggal, background dibersihkan dan "
            "hasil disimpan sebagai PNG transparan."
        )
        ttk.Label(
            body,
            text=note,
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 12))

        actions = ttk.Frame(body)
        actions.grid(row=8, column=0, columnspan=3, sticky="e")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="Generate Variasi", command=self._accept).pack(side="right")

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
        holder.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
        ttk.Label(holder, text=label, style="Muted.TLabel").pack(anchor="w")
        ttk.Spinbox(
            holder,
            textvariable=variable,
            from_=start,
            to=stop,
            increment=increment,
        ).pack(fill="x")

    def _open_api_settings(self) -> None:
        dialog = CloudAISettingsDialog(self, settings_store=self.settings_store)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.model_value.set(dialog.result.model_for(self.provider_id))

    def _accept(self) -> None:
        try:
            self.result = CloudBatikBrewOptions(
                model_id_or_path=self.defaults.model_id_or_path,
                prompt=self.prompt_text.get("1.0", "end").strip(),
                negative_prompt=self.negative_text.get("1.0", "end").strip(),
                strength=self.defaults.strength,
                ai_blend=self.defaults.ai_blend,
                pattern_scale=self.defaults.pattern_scale,
                preserve_shading=self.defaults.preserve_shading,
                inference_steps=self.defaults.inference_steps,
                guidance_scale=self.defaults.guidance_scale,
                seed=int(self.seed_value.get().strip()),
                device=self.defaults.device,
                precision=self.defaults.precision,
                local_files_only=False,
                cpu_offload=False,
                cache_dir=self.defaults.cache_dir,
                resolution=int(self.resolution_value.get()),
                lora_path="",
                lora_weight=0.0,
                lora_trigger_words=("traditional Indonesian batik",),
                variation_count=int(self.variations_value.get()),
                tileable=bool(self.tileable_value.get()),
                generation_provider=self.provider_id,
                provider_model=self.model_value.get(),
                output_mode=self.output_mode,
            )
        except (BatificationError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan API tidak valid", str(exc), parent=self)
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["CloudBatikGenerationDialog"]
