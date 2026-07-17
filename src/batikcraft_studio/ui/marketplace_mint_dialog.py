"""Create, seal, and publish the current project as an NFT marketplace item."""

from __future__ import annotations

import tempfile
import tkinter as tk
from collections.abc import Mapping
from pathlib import Path
from tkinter import messagebox, ttk

from batikcraft_studio.domain import Project
from batikcraft_studio.imaging import ProjectRenderError
from batikcraft_studio.persistence import BatikNFTError, NFTExportMetadata, export_batikcraft_nft
from batikcraft_studio.project_export import (
    discover_project_colors,
    discover_project_motifs,
    render_project_jpeg,
)
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError, WebSession


class MintCurrentProjectDialog(tk.Toplevel):
    """Mint an immutable package internally and publish it without exporting a file."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        client: BatikCraftWebClient,
        session: WebSession,
        project: Project,
        assets: Mapping[str, bytes],
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.session = session
        self.project = project
        self.assets = dict(assets)

        self.price_value = tk.StringVar(master=self, value="100000")
        self.ends_value = tk.StringVar(master=self)
        self.motifs_value = tk.StringVar(
            master=self,
            value=", ".join(discover_project_motifs(project)),
        )
        self.colors_value = tk.StringVar(
            master=self,
            value=", ".join(discover_project_colors(project)),
        )
        self.license_value = tk.StringVar(master=self, value="All rights reserved")
        self.status_value = tk.StringVar(
            master=self,
            value="Project akan diberi package ID dan checksum sebelum dipublikasikan.",
        )

        self.title("Marketplace — Mint & Publish NFT")
        self.geometry("760x600")
        self.minsize(680, 540)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Mint Motif Batik sebagai NFT",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text=(
                "BatikCraft Studio membuat paket NFT bersegel dari project aktif lalu "
                "mengunggah preview dan metadata ke BatikCraftWeb. Tidak ada file paket "
                "yang perlu diekspor manual dari menu File."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 14))

        self._readonly_row(body, 2, "Project", self.project.metadata.title)
        self._readonly_row(body, 3, "Creator", self.session.account.public_name)
        self._entry_row(body, 4, "Motif", self.motifs_value)
        self._entry_row(body, 5, "Warna dominan", self.colors_value)
        self._entry_row(body, 6, "Lisensi", self.license_value)
        self._entry_row(body, 7, "Harga awal", self.price_value)
        self._entry_row(body, 8, "Auction berakhir (ISO, opsional)", self.ends_value)

        ttk.Label(body, text="Filosofi / deskripsi").grid(
            row=9,
            column=0,
            sticky="nw",
            pady=5,
        )
        self.philosophy_text = tk.Text(body, height=8, wrap="word")
        self.philosophy_text.grid(row=9, column=1, sticky="ew", pady=5)
        self.philosophy_text.insert("1.0", self.project.metadata.description)

        ttk.Label(
            body,
            text=(
                "Catatan: aksi ini membuat identitas NFT marketplace dan listing auction. "
                "Transaksi minting blockchain on-chain memerlukan gateway wallet/contract "
                "yang terpisah dari package seal BatikCraft."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        actions = ttk.Frame(body)
        actions.grid(row=12, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Batal", command=self.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        self.mint_button = ttk.Button(
            actions,
            text="Mint & Publish",
            command=self._mint,
        )
        self.mint_button.pack(side="right")

    @staticmethod
    def _readonly_row(parent: ttk.Frame, row: int, label: str, value: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Label(parent, text=value).grid(row=row, column=1, sticky="w", pady=5)

    @staticmethod
    def _entry_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=5,
        )

    def _mint(self) -> None:
        philosophy = self.philosophy_text.get("1.0", "end").strip()
        if not philosophy:
            messagebox.showerror(
                "Filosofi diperlukan",
                "Isi filosofi atau deskripsi motif sebelum minting.",
                parent=self,
            )
            return
        try:
            price = float(self.price_value.get())
        except ValueError:
            messagebox.showerror("Harga tidak valid", "Harga awal harus berupa angka.", parent=self)
            return
        if price <= 0:
            messagebox.showerror(
                "Harga tidak valid",
                "Harga awal harus lebih dari nol.",
                parent=self,
            )
            return

        self.mint_button.configure(state="disabled")
        self.configure(cursor="watch")
        self.status_value.set("Membuat package ID, checksum, preview, dan listing NFT…")
        self.update_idletasks()
        try:
            metadata = NFTExportMetadata(
                creator_user_id=str(self.session.account.user_id),
                philosophy=philosophy,
                motifs=_csv(self.motifs_value.get()),
                colors=_csv(self.colors_value.get()),
                license_name=self.license_value.get(),
            )
            preview = render_project_jpeg(self.project, self.assets)
            with tempfile.TemporaryDirectory(prefix="batikcraft-mint-") as temp:
                package = export_batikcraft_nft(
                    Path(temp) / "mint.batikcraftnft",
                    self.project,
                    self.assets,
                    preview,
                    metadata,
                )
                item = self.client.publish_nft_package(
                    package,
                    starting_price=self.price_value.get(),
                    auction_ends_at=self.ends_value.get(),
                )
        except (
            BatikNFTError,
            BatikCraftWebError,
            OSError,
            ProjectRenderError,
            ValueError,
        ) as exc:
            self.mint_button.configure(state="normal")
            self.configure(cursor="")
            self.status_value.set(str(exc))
            messagebox.showerror("Mint NFT gagal", str(exc), parent=self)
            return
        messagebox.showinfo(
            "NFT dipublikasikan",
            f"{item.get('title', self.project.metadata.title)} sekarang tampil di NFT Market.",
            parent=self,
        )
        self.destroy()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


__all__ = ["MintCurrentProjectDialog"]
