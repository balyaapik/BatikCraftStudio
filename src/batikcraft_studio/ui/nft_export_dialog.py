"""Modal form for BatikCraft marketplace metadata."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from batikcraft_studio.i18n import tr
from batikcraft_studio.persistence.nft_package import BatikNFTError, NFTExportMetadata


class NFTExportDialog(simpledialog.Dialog):
    """Collect identity and story fields before sealing an NFT package."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        creator_name: str,
        creator_user_id: str,
        philosophy: str = "",
        motifs: tuple[str, ...] = (),
        colors: tuple[str, ...] = (),
        license_name: str = "All rights reserved",
    ) -> None:
        self.result: NFTExportMetadata | None = None
        self.creator_name = creator_name
        self.creator_id_var = tk.StringVar(value=creator_user_id)
        self.motifs_var = tk.StringVar(value=", ".join(motifs))
        self.colors_var = tk.StringVar(value=", ".join(colors))
        self.license_var = tk.StringVar(value=license_name)
        self._initial_philosophy = philosophy
        self.philosophy_text: tk.Text | None = None
        super().__init__(parent, title=tr("dialog.export_nft.title"))

    def body(self, master: tk.Misc) -> tk.Widget:
        form = ttk.Frame(master, padding=(10, 10))
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text=tr("dialog.export_nft.creator_name")).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )
        ttk.Label(form, text=self.creator_name).grid(
            row=0,
            column=1,
            sticky="w",
            pady=5,
        )

        ttk.Label(form, text=tr("dialog.export_nft.creator_id")).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )
        creator_entry = ttk.Entry(form, textvariable=self.creator_id_var, width=46)
        creator_entry.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(form, text=tr("dialog.export_nft.philosophy")).grid(
            row=2,
            column=0,
            sticky="nw",
            padx=(0, 12),
            pady=5,
        )
        self.philosophy_text = tk.Text(form, height=7, width=52, wrap="word")
        self.philosophy_text.grid(row=2, column=1, sticky="nsew", pady=5)
        self.philosophy_text.insert("1.0", self._initial_philosophy)

        for row, label_key, variable in (
            (3, "dialog.export_nft.motifs", self.motifs_var),
            (4, "dialog.export_nft.colors", self.colors_var),
            (5, "dialog.export_nft.license", self.license_var),
        ):
            ttk.Label(form, text=tr(label_key)).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=5,
            )
            ttk.Entry(form, textvariable=variable).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=5,
            )

        ttk.Label(
            form,
            text=tr("dialog.export_nft.hint_list"),
            style="Muted.TLabel",
        ).grid(row=6, column=1, sticky="w", pady=(0, 8))
        ttk.Label(
            form,
            text=tr("dialog.export_nft.integrity_note"),
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        return creator_entry

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(
            box,
            text=tr("common.ok"),
            width=12,
            command=self.ok,
            default=tk.ACTIVE,
        ).pack(side=tk.LEFT, padx=5, pady=8)
        ttk.Button(
            box,
            text=tr("common.cancel"),
            width=12,
            command=self.cancel,
        ).pack(side=tk.LEFT, padx=5, pady=8)
        self.bind("<Control-Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def validate(self) -> bool:
        philosophy = ""
        if self.philosophy_text is not None:
            philosophy = self.philosophy_text.get("1.0", "end").strip()
        try:
            self.result = NFTExportMetadata(
                creator_user_id=self.creator_id_var.get(),
                philosophy=philosophy,
                motifs=_csv(self.motifs_var.get()),
                colors=_csv(self.colors_var.get()),
                license_name=self.license_var.get(),
            )
        except BatikNFTError as exc:
            messagebox.showerror(
                tr("dialog.export_nft.error"),
                str(exc),
                parent=self,
            )
            return False
        return True

    def apply(self) -> None:
        return None


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


__all__ = ["NFTExportDialog"]
