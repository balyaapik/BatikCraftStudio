"""Choose one centrally configured AI model for a Batik generation request."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from batikcraft_studio.ai.batikbrew_model_settings import (
    get_batikbrew_model_settings_store,
)
from batikcraft_studio.ai.generation_providers import (
    PROVIDER_IDS,
    PROVIDER_LOCAL,
    CloudGenerationSettingsStore,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_label,
)


class BatikAIProviderDialog(tk.Toplevel):
    """Require the user to choose a configured local or cloud model per request."""

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
        self._provider_by_label = self._model_choices(current)
        labels = tuple(self._provider_by_label)
        default_label = next(
            (
                label
                for label, provider_id in self._provider_by_label.items()
                if provider_id == default_provider
            ),
            labels[0],
        )

        self.title("Pilih Model Generasi AI")
        self.geometry("680x360")
        self.minsize(600, 330)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.model_value = tk.StringVar(master=self, value=default_label)
        self.status_value = tk.StringVar(master=self)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        mode_label = "Ornamen Tunggal" if output_mode == "ornament" else "Pola"
        ttk.Label(
            body,
            text=f"Pilih model untuk {mode_label}",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Model, API key, runtime, dan LoRA tetap dikelola dari menu Settings. "
                "Pilihan ini hanya menentukan model yang dipakai untuk proses generasi sekarang."
            ),
            wraplength=630,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 14))

        combo = ttk.Combobox(
            body,
            textvariable=self.model_value,
            values=labels,
            state="readonly",
        )
        combo.grid(row=2, column=0, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_status())

        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=630,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(12, 16))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="Gunakan Model Ini", command=self._accept).pack(side="right")

        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<KP_Enter>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self._cancel())
        self._refresh_status()
        combo.focus_set()
        self.grab_set()

    def _model_choices(self, settings: object) -> dict[str, str]:
        choices: dict[str, str] = {}
        local = get_batikbrew_model_settings_store().load()
        local_name = local.model_id if local.configured else "belum diatur"
        choices[f"{provider_label(PROVIDER_LOCAL)} · {local_name}"] = PROVIDER_LOCAL
        for provider_id in PROVIDER_IDS:
            if provider_id == PROVIDER_LOCAL:
                continue
            model = settings.model_for(provider_id)
            choices[f"{provider_label(provider_id)} · {model}"] = provider_id
        return choices

    def _selected_provider(self) -> str:
        return self._provider_by_label.get(self.model_value.get(), PROVIDER_LOCAL)

    def _refresh_status(self) -> None:
        provider = self._selected_provider()
        if provider == PROVIDER_LOCAL:
            active = get_batikbrew_model_settings_store().load()
            if active.configured:
                self.status_value.set(
                    f"Model lokal aktif: {active.model_id}. Runtime dan LoRA diambil dari Settings."
                )
            else:
                self.status_value.set(
                    "Model lokal belum diatur. Buka Settings → Model Lokal, Runtime & LoRA."
                )
            return
        settings = self.settings_store.load()
        model = settings.model_for(provider)
        has_key = get_api_secret_store().has(provider)
        key_status = "API key tersedia" if has_key else "API key belum diisi"
        self.status_value.set(f"{provider_label(provider)} · model {model} · {key_status}.")

    def _accept(self) -> None:
        provider = self._selected_provider()
        if provider == PROVIDER_LOCAL:
            if not get_batikbrew_model_settings_store().load().configured:
                messagebox.showerror(
                    "Model lokal belum diatur",
                    "Atur dan aktifkan model lokal dari menu Settings terlebih dahulu.",
                    parent=self,
                )
                return
        elif not get_api_secret_store().has(provider):
            messagebox.showerror(
                "API key belum diisi",
                f"API key {provider_label(provider)} belum tersedia. Isi dari menu Settings.",
                parent=self,
            )
            return
        self.result = provider
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikAIProviderDialog"]