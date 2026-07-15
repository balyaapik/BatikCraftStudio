"""Responsive progress window for background `.batikpack` installation."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from batikcraft_studio.assets.progressive_install import AssetInstallProgress


class AssetPackProgressDialog(tk.Toplevel):
    """Show live install progress while keeping the main editor responsive."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        archive_path: Path,
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._cancel_requested = False
        self.title("Memasang Paket Asset")
        self.geometry("520x220")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.request_cancel)

        self.status_value = tk.StringVar(
            master=self,
            value="Menyiapkan pemasangan paket asset…",
        )
        self.detail_value = tk.StringVar(
            master=self,
            value=archive_path.name,
        )
        self.percent_value = tk.DoubleVar(master=self, value=0.0)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(
            body,
            text="Pemasangan Paket Asset",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=archive_path.name,
            wraplength=470,
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))
        ttk.Label(
            body,
            textvariable=self.status_value,
            wraplength=470,
        ).grid(row=2, column=0, sticky="w")
        ttk.Progressbar(
            body,
            variable=self.percent_value,
            maximum=100.0,
            mode="determinate",
        ).grid(row=3, column=0, sticky="ew", pady=(10, 5), ipady=3)
        ttk.Label(
            body,
            textvariable=self.detail_value,
            foreground="#6D655D",
            wraplength=470,
        ).grid(row=4, column=0, sticky="w")

        footer = ttk.Frame(body)
        footer.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            text="Aplikasi tetap dapat digunakan selama proses berlangsung.",
            foreground="#6D655D",
        ).grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(
            footer,
            text="Batal",
            command=self.request_cancel,
        )
        self.cancel_button.grid(row=0, column=1, sticky="e")

    def apply_progress(self, update: AssetInstallProgress) -> None:
        """Apply one worker progress event on the Tk main thread."""

        self.percent_value.set(update.percent)
        self.status_value.set(update.message)
        if update.total > 0:
            if update.stage == "extracting":
                current_mb = update.current / (1024 * 1024)
                total_mb = update.total / (1024 * 1024)
                self.detail_value.set(
                    f"{update.percent:.1f}% · {current_mb:.1f} MB / {total_mb:.1f} MB"
                )
            else:
                self.detail_value.set(
                    f"{update.percent:.1f}% · {update.current}/{update.total}"
                )
        else:
            self.detail_value.set(f"{update.percent:.1f}%")
        if not update.cancellable:
            self.cancel_button.configure(state="disabled")

    def request_cancel(self) -> None:
        """Request cancellation without destroying the live worker window."""

        if self._cancel_requested:
            return
        self._cancel_requested = True
        self.status_value.set("Membatalkan pemasangan dengan aman…")
        self.detail_value.set("Paket yang sudah terpasang tidak akan dirusak.")
        self.cancel_button.configure(state="disabled")
        self._on_cancel()

    def close(self) -> None:
        """Destroy the dialog safely from the Tk main thread."""

        try:
            self.destroy()
        except tk.TclError:
            pass


__all__ = ["AssetPackProgressDialog"]
