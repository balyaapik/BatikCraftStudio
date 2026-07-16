"""Configure OpenAI, Gemini, and IBM watsonx.ai image providers."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from batikcraft_studio.ai.generation_providers import (
    APISecretStore,
    CloudGenerationSettings,
    CloudGenerationSettingsStore,
    PROVIDER_GEMINI,
    PROVIDER_LABELS,
    PROVIDER_OPENAI,
    PROVIDER_WATSONX,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_id_from_label,
    provider_label,
)


class CloudAISettingsDialog(tk.Toplevel):
    """Persist per-mode provider defaults while keeping API keys in the OS vault."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings_store: CloudGenerationSettingsStore | None = None,
        secret_store: APISecretStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_store = settings_store or get_cloud_generation_settings_store()
        self.secret_store = secret_store or get_api_secret_store()
        self.result: CloudGenerationSettings | None = None
        current = self.settings_store.load()

        self.title("Pengaturan API Batifikasi")
        self.geometry("790x720")
        self.minsize(700, 620)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        labels = tuple(PROVIDER_LABELS.values())
        self.ornament_provider_value = tk.StringVar(
            master=self,
            value=provider_label(current.ornament_provider),
        )
        self.pattern_provider_value = tk.StringVar(
            master=self,
            value=provider_label(current.pattern_provider),
        )
        self.openai_model_value = tk.StringVar(master=self, value=current.openai_model)
        self.openai_base_url_value = tk.StringVar(master=self, value=current.openai_base_url)
        self.gemini_model_value = tk.StringVar(master=self, value=current.gemini_model)
        self.watsonx_model_value = tk.StringVar(master=self, value=current.watsonx_model)
        self.watsonx_url_value = tk.StringVar(master=self, value=current.watsonx_url)
        self.watsonx_project_value = tk.StringVar(master=self, value=current.watsonx_project_id)
        self.watsonx_version_value = tk.StringVar(master=self, value=current.watsonx_api_version)
        self.timeout_value = tk.IntVar(master=self, value=current.request_timeout_seconds)

        self.openai_key_value = tk.StringVar(master=self)
        self.gemini_key_value = tk.StringVar(master=self)
        self.watsonx_key_value = tk.StringVar(master=self)
        self.delete_openai_value = tk.BooleanVar(master=self, value=False)
        self.delete_gemini_value = tk.BooleanVar(master=self, value=False)
        self.delete_watsonx_value = tk.BooleanVar(master=self, value=False)
        self.status_value = tk.StringVar(
            master=self,
            value=self.settings_store.last_error or "API key tidak disimpan di project atau metadata NFT.",
        )

        self._build(labels)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()

    def _build(self, provider_labels: tuple[str, ...]) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(
            body,
            text="Provider API untuk Batifikasi",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Pilih provider default secara terpisah untuk Ornamen Tunggal dan Pola. "
                "API key disimpan melalui credential vault sistem operasi dan tidak ikut "
                "tersimpan di file project, clipboard, maupun paket .batikcraftnft."
            ),
            wraplength=750,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        notebook = ttk.Notebook(body)
        notebook.grid(row=2, column=0, sticky="nsew")

        defaults = ttk.Frame(notebook, padding=14)
        defaults.columnconfigure(1, weight=1)
        notebook.add(defaults, text="Default Mode")
        self._combo_row(
            defaults,
            0,
            "Provider Ornamen Tunggal",
            self.ornament_provider_value,
            provider_labels,
        )
        self._combo_row(
            defaults,
            1,
            "Provider Pola",
            self.pattern_provider_value,
            provider_labels,
        )
        ttk.Label(defaults, text="Timeout request (detik)").grid(
            row=2, column=0, sticky="w", pady=5, padx=(0, 10)
        )
        ttk.Spinbox(
            defaults,
            textvariable=self.timeout_value,
            from_=30,
            to=900,
            increment=30,
        ).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(
            defaults,
            text=(
                "Pilihan masih dapat diganti pada setiap proses generasi. Default ini hanya "
                "menentukan provider yang langsung terpilih setelah memilih Ornamen atau Pola."
            ),
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        openai = ttk.Frame(notebook, padding=14)
        openai.columnconfigure(1, weight=1)
        notebook.add(openai, text="OpenAI")
        self._secret_row(
            openai,
            0,
            PROVIDER_OPENAI,
            self.openai_key_value,
            self.delete_openai_value,
        )
        self._entry_row(openai, 1, "Model", self.openai_model_value)
        self._entry_row(openai, 2, "Base URL", self.openai_base_url_value)
        ttk.Label(
            openai,
            text="Contoh model: gpt-image-1. Mode ornamen meminta PNG transparan jika didukung model.",
            style="Muted.TLabel",
            wraplength=680,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        gemini = ttk.Frame(notebook, padding=14)
        gemini.columnconfigure(1, weight=1)
        notebook.add(gemini, text="Gemini")
        self._secret_row(
            gemini,
            0,
            PROVIDER_GEMINI,
            self.gemini_key_value,
            self.delete_gemini_value,
        )
        self._entry_row(gemini, 1, "Model", self.gemini_model_value)
        ttk.Label(
            gemini,
            text=(
                "Contoh model: gemini-3.1-flash-image. Background ornamen dibersihkan "
                "otomatis setelah gambar diterima."
            ),
            style="Muted.TLabel",
            wraplength=680,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        watsonx = ttk.Frame(notebook, padding=14)
        watsonx.columnconfigure(1, weight=1)
        notebook.add(watsonx, text="IBM watsonx.ai")
        self._secret_row(
            watsonx,
            0,
            PROVIDER_WATSONX,
            self.watsonx_key_value,
            self.delete_watsonx_value,
        )
        self._entry_row(watsonx, 1, "Project ID", self.watsonx_project_value)
        self._entry_row(watsonx, 2, "Region / Base URL", self.watsonx_url_value)
        self._entry_row(watsonx, 3, "Model ID", self.watsonx_model_value)
        self._entry_row(watsonx, 4, "API version", self.watsonx_version_value)
        ttk.Label(
            watsonx,
            text=(
                "Contoh URL: https://us-south.ml.cloud.ibm.com. Project ID wajib diisi. "
                "Default model: stable-diffusion-xl-1024-v1-0."
            ),
            style="Muted.TLabel",
            wraplength=680,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        footer = ttk.Frame(body)
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            textvariable=self.status_value,
            wraplength=500,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Batal", command=self._cancel).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(footer, text="Simpan", command=self._save).grid(
            row=0, column=2, padx=(8, 0)
        )

    def _combo_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", pady=5)

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 10))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)

    def _secret_row(
        self,
        parent: ttk.Frame,
        row: int,
        provider_id: str,
        variable: tk.StringVar,
        delete_variable: tk.BooleanVar,
    ) -> None:
        available = self.secret_store.has(provider_id)
        ttk.Label(parent, text="API key baru").grid(
            row=row, column=0, sticky="w", pady=5, padx=(0, 10)
        )
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=5)
        holder.columnconfigure(0, weight=1)
        ttk.Entry(holder, textvariable=variable, show="•").grid(row=0, column=0, sticky="ew")
        ttk.Label(
            holder,
            text="Tersedia" if available else "Belum diisi",
            style="Muted.TLabel",
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Checkbutton(
            parent,
            text="Hapus API key tersimpan",
            variable=delete_variable,
        ).grid(row=row + 1, column=1, sticky="w", pady=(0, 7))

    def _save(self) -> None:
        try:
            settings = CloudGenerationSettings(
                ornament_provider=provider_id_from_label(self.ornament_provider_value.get()),
                pattern_provider=provider_id_from_label(self.pattern_provider_value.get()),
                openai_model=self.openai_model_value.get(),
                openai_base_url=self.openai_base_url_value.get(),
                gemini_model=self.gemini_model_value.get(),
                watsonx_model=self.watsonx_model_value.get(),
                watsonx_url=self.watsonx_url_value.get(),
                watsonx_project_id=self.watsonx_project_value.get(),
                watsonx_api_version=self.watsonx_version_value.get(),
                request_timeout_seconds=int(self.timeout_value.get()),
            )
            self.settings_store.save(settings)
            self._save_secret(
                PROVIDER_OPENAI,
                self.openai_key_value.get(),
                bool(self.delete_openai_value.get()),
            )
            self._save_secret(
                PROVIDER_GEMINI,
                self.gemini_key_value.get(),
                bool(self.delete_gemini_value.get()),
            )
            self._save_secret(
                PROVIDER_WATSONX,
                self.watsonx_key_value.get(),
                bool(self.delete_watsonx_value.get()),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan API tidak dapat disimpan", str(exc), parent=self)
            return
        self.result = settings
        self.destroy()

    def _save_secret(self, provider_id: str, value: str, delete: bool) -> None:
        if delete:
            self.secret_store.set(provider_id, "")
        elif value.strip():
            self.secret_store.set(provider_id, value)

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["CloudAISettingsDialog"]
