"""Creative-only request dialog for centrally configured BatikBrew models."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk


@dataclass(frozen=True, slots=True)
class BatikBrewRequest:
    prompt: str
    negative_prompt: str
    seed: int
    variation_count: int
    tileable: bool


class BatikBrewRequestDialog(tk.Toplevel):
    """Collect creative direction without exposing provider or model settings."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        output_mode: str,
        provider_summary: str,
        prompt: str,
        negative_prompt: str,
        seed: int,
        default_variation_count: int = 1,
        request_notice: str = "",
    ) -> None:
        super().__init__(parent)
        self.output_mode = output_mode
        self.result: BatikBrewRequest | None = None
        self.seed_value = tk.StringVar(master=self, value=str(seed))
        initial_variations = max(1, min(4, int(default_variation_count)))
        self.variations_value = tk.IntVar(master=self, value=initial_variations)
        self.tileable_value = tk.BooleanVar(master=self, value=output_mode == "pattern")

        mode_label = "Ornamen Tunggal" if output_mode == "ornament" else "Pola"
        self.title(f"Generate BatikBrew — {mode_label}")
        self.geometry("720x580")
        self.minsize(640, 520)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        summary = (
            f"Konfigurasi aktif: {provider_summary}. Provider, model API, runtime, GPU, "
            "dan LoRA dikelola dari menu Settings → Pengaturan AI, Model & LoRA."
        )
        notice = str(request_notice).strip()
        if notice:
            summary = f"{summary}\n\n{notice}"

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(4, weight=1)

        ttk.Label(
            body,
            text=f"Generate {mode_label}",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text=summary,
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 14))

        numeric = ttk.Frame(body)
        numeric.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        numeric.columnconfigure(0, weight=1)
        numeric.columnconfigure(1, weight=1)
        self._spinbox(numeric, 0, "Seed", self.seed_value, 0, 2_147_483_647, 1)
        self._spinbox(numeric, 1, "Jumlah variasi", self.variations_value, 1, 4, 1)

        tile = ttk.Checkbutton(
            body,
            text="Buat hasil seamless/tileable",
            variable=self.tileable_value,
        )
        tile.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))
        if output_mode == "ornament":
            self.tileable_value.set(False)
            tile.configure(state="disabled")

        prompts = ttk.Frame(body)
        prompts.grid(row=4, column=0, columnspan=2, sticky="nsew")
        prompts.columnconfigure(1, weight=1)
        prompts.rowconfigure(0, weight=1)
        prompts.rowconfigure(1, weight=1)

        ttk.Label(prompts, text="Creative direction").grid(
            row=0, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.prompt_text = tk.Text(prompts, height=7, wrap="word")
        self.prompt_text.grid(row=0, column=1, sticky="nsew", pady=4)
        self.prompt_text.insert("1.0", prompt)

        ttk.Label(prompts, text="Negative prompt tambahan").grid(
            row=1, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.negative_text = tk.Text(prompts, height=6, wrap="word")
        self.negative_text.grid(row=1, column=1, sticky="nsew", pady=4)
        self.negative_text.insert("1.0", negative_prompt)

        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="Generate Variasi", command=self._accept).pack(side="right")

        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Control-Return>", lambda _event: self._accept())
        self.grab_set()
        self.prompt_text.focus_set()

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
        holder.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(holder, text=label, style="Muted.TLabel").pack(anchor="w")
        ttk.Spinbox(
            holder,
            textvariable=variable,
            from_=start,
            to=stop,
            increment=increment,
        ).pack(fill="x")

    def _accept(self) -> None:
        try:
            seed = int(self.seed_value.get().strip())
            variations = int(self.variations_value.get())
            if not 0 <= seed <= 2_147_483_647:
                raise ValueError("Seed harus berada antara 0 dan 2147483647.")
            if not 1 <= variations <= 4:
                raise ValueError("Jumlah variasi harus berada antara 1 dan 4.")
            self.result = BatikBrewRequest(
                prompt=self.prompt_text.get("1.0", "end").strip(),
                negative_prompt=self.negative_text.get("1.0", "end").strip(),
                seed=seed,
                variation_count=variations,
                tileable=bool(self.tileable_value.get()),
            )
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Permintaan generasi tidak valid", str(exc), parent=self)
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewRequest", "BatikBrewRequestDialog"]