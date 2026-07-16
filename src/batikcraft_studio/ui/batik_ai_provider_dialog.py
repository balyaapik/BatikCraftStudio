"""Choose the generation engine for one Batik ornament or pattern request."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from batikcraft_studio.ai.generation_providers import (
    PROVIDER_LABELS,
    PROVIDER_LOCAL,
    CloudGenerationSettingsStore,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_id_from_label,
    provider_label,
)

from .cloud_ai_settings_dialog import CloudAISettingsDialog


class BatikAIProviderDialog(tk.Toplevel):
    """Select local SDXL, watsonx.ai, Gemini, or OpenAI for the current mode."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        output_mode: str,
        settings_store: CloudGenerationSettingsStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.output_mode = output_mode
        self.settings_store = settings_store or get_cloud_generation_settings_store()
        self.result: str | None = None
        current = self.settings_store.load()
        default_provider = current.provider_for_mode(output_mode)

        self.title("Pilih Mesin Generasi AI")
        self.geometry("620x350")
        self.minsize(560, 320)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.provider_value = tk.StringVar(master=self, value=provider_label(default_provider))
        self.status_value = tk.StringVar(master=self)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        mode_label = "Ornamen Tunggal" if output_mode == "ornament" else "Pola"
        ttk.Label(
            body,
            text=f"Provider untuk {mode_label}",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "SDXL lokal memakai runtime dan LoRA di komputer. Provider API mengirim prompt "
                "BatikBrew ke layanan yang dipilih; API key tidak masuk ke project atau NFT."
            ),
            wraplength=570,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        chooser = ttk.Frame(body)
        chooser.grid(row=2, column=0, sticky="ew")
        chooser.columnconfigure(0, weight=1)
        combo = ttk.Combobox(
            chooser,
            textvariable=self.provider_value,
            values=tuple(PROVIDER_LABELS.values()),
            state="readonly",
        )
        combo.grid(row=0, column=0, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_status())
        ttk.Button(
            chooser,
            text="Pengaturan API…",
            command=self._open_settings,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=570,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(12, 16))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="OK / Lanjutkan", command=self._accept).pack(side="right")

        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<KP_Enter>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self._cancel())
        self._refresh_status()
        combo.focus_set()
        self.grab_set()

    def _refresh_status(self) -> None:
        provider = provider_id_from_label(self.provider_value.get())
        if provider == PROVIDER_LOCAL:
            self.status_value.set(
                "Lokal: Stable Diffusion XL + LoRA BatikBrew. Tidak memakai API key atau internet."
            )
            return
        settings = self.settings_store.load()
        model = settings.model_for(provider)
        has_key = get_api_secret_store().has(provider)
        key_status = "API key tersedia" if has_key else "API key belum diisi"
        self.status_value.set(f"{provider_label(provider)} · model {model} · {key_status}.")

    def _open_settings(self) -> None:
        dialog = CloudAISettingsDialog(self, settings_store=self.settings_store)
        self.wait_window(dialog)
        settings = dialog.result
        if settings is not None:
            selected = settings.provider_for_mode(self.output_mode)
            self.provider_value.set(provider_label(selected))
        self._refresh_status()

    def _accept(self) -> None:
        provider = provider_id_from_label(self.provider_value.get())
        if provider != PROVIDER_LOCAL and not get_api_secret_store().has(provider):
            answer = messagebox.askyesno(
                "API key belum diisi",
                "API key provider ini belum ditemukan. Buka Pengaturan API sekarang?",
                parent=self,
            )
            if answer:
                self._open_settings()
            return
        settings = self.settings_store.load().with_provider_for_mode(self.output_mode, provider)
        try:
            self.settings_store.save(settings)
        except OSError as exc:
            messagebox.showerror("Provider tidak dapat disimpan", str(exc), parent=self)
            return
        self.result = provider
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikAIProviderDialog"]
