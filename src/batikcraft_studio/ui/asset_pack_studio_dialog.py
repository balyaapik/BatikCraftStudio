"""Studio Paket Aset: buat pustaka, isi dari canvas/luar aplikasi, lalu jual.

Alur sesuai kebutuhan: user membuat paket aset dulu, mengisinya dengan
ornamen/gambar batik (dari canvas lewat menu konteks editor, atau impor file
dari komputer), lalu mengekspornya sebagai ``.batikpack`` dan/atau menjualnya
ke BatikCraftWeb melalui NFT marketplace.
"""

from __future__ import annotations

import hashlib
import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from batikcraft_studio.assets import AssetLibrary, AssetLibraryError
from batikcraft_studio.assets.builder import (
    AssetCandidate,
    AssetPackBuildError,
    AssetPackMetadata,
    build_asset_pack,
)
from batikcraft_studio.assets.personal_store import (
    PERSONAL_PACK_ID,
    PersonalAssetStore,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from batikcraft_studio.config import APP_VERSION
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError


class AssetPackStudioWindow(tk.Toplevel):
    """Kurasi aset pustaka pribadi menjadi paket yang siap dipasang/dijual."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        library: AssetLibrary,
        client_provider: Callable[[], BatikCraftWebClient | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Studio Paket Aset — Buat, Isi, Jual")
        self.library = library
        self.store = PersonalAssetStore(library)
        self.client_provider = client_provider
        self._records: list[Any] = []

        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(
            body,
            text=(
                "1) Isi pustaka: dari canvas (klik kanan objek → Simpan ke Pustaka Aset) "
                "atau impor gambar dari komputer.  2) Centang aset.  3) Ekspor / jual."
            ),
            wraplength=620,
            justify="left",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.tree = ttk.Treeview(
            body,
            columns=("category",),
            show="tree headings",
            selectmode="extended",
            height=12,
        )
        self.tree.heading("#0", text="Aset (pilih beberapa dengan Ctrl/Shift)")
        self.tree.heading("category", text="Kategori")
        self.tree.column("#0", width=380)
        self.tree.column("category", width=140)
        self.tree.grid(row=1, column=0, sticky="nsew")

        form = ttk.LabelFrame(body, text="Metadata Paket", padding=(8, 6))
        form.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        form.columnconfigure(1, weight=1)
        self.name_value = tk.StringVar(master=self, value="Paket Ornamen Batik Saya")
        self.creator_value = tk.StringVar(master=self, value="")
        self.price_value = tk.StringVar(master=self, value="100000")
        for row, (label, variable) in enumerate(
            (
                ("Nama paket", self.name_value),
                ("Pembuat", self.creator_value),
                ("Harga awal (jual)", self.price_value),
            )
        ):
            ttk.Label(form, text=f"{label}:").grid(row=row, column=0, sticky="w")
            ttk.Entry(form, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=(6, 0), pady=1
            )

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(2, weight=1)
        ttk.Button(
            buttons, text="Impor Gambar…", command=self.import_images
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Muat Ulang", command=self.refresh_assets).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )
        ttk.Button(
            buttons, text="Ekspor .batikpack…", command=self.export_pack
        ).grid(row=0, column=3, sticky="e", padx=(0, 6))
        self.sell_button = ttk.Button(
            buttons,
            text="Jual ke BatikCraftWeb…",
            style="Accent.TButton",
            command=self.sell_pack,
        )
        self.sell_button.grid(row=0, column=4, sticky="e")
        if client_provider is None:
            self.sell_button.configure(state="disabled")

        self.status_value = tk.StringVar(master=self, value="")
        ttk.Label(body, textvariable=self.status_value, style="Muted.TLabel").grid(
            row=4, column=0, sticky="w", pady=(6, 0)
        )
        self.refresh_assets()

    # ------------------------------------------------------------------
    def refresh_assets(self) -> None:
        self.library.refresh()
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        try:
            self._records = list(self.library.search(pack_id=PERSONAL_PACK_ID))
        except AssetLibraryError:
            self._records = []  # pustaka pribadi belum pernah diisi
        for index, record in enumerate(self._records):
            self.tree.insert(
                "", "end", iid=str(index), text=record.name, values=(record.category,)
            )
        self.status_value.set(f"{len(self._records)} aset di pustaka pribadi.")

    def import_images(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_IMAGE_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Impor gambar/ornamen batik ke pustaka",
            filetypes=[("Gambar", patterns), ("Semua file", "*.*")],
        )
        imported = 0
        for raw in paths:
            path = Path(raw)
            try:
                self.store.import_image(path.name, path.read_bytes())
                imported += 1
            except (AssetLibraryError, OSError) as exc:
                messagebox.showwarning("Impor gagal", f"{path.name}: {exc}", parent=self)
        if imported:
            self.refresh_assets()
            self.status_value.set(f"{imported} gambar masuk ke pustaka pribadi.")

    # ------------------------------------------------------------------
    def _selected_candidates(self) -> list[AssetCandidate]:
        selection = self.tree.selection()
        records = (
            [self._records[int(iid)] for iid in selection]
            if selection
            else list(self._records)
        )
        candidates: list[AssetCandidate] = []
        for record in records:
            content = self.library.read_asset(record)
            candidates.append(
                AssetCandidate(
                    asset_id=record.asset_id,
                    name=record.name,
                    category=record.category,
                    content=content,
                )
            )
        return candidates

    def _metadata(self) -> AssetPackMetadata:
        return AssetPackMetadata(
            pack_id=f"user-pack-{abs(hash(self.name_value.get())) % 99999:05d}",
            name=self.name_value.get().strip() or "Paket Aset Batik",
            author=self.creator_value.get().strip() or "BatikCraft User",
            description="Paket aset dibuat dari Studio Paket Aset BatikCraft.",
        )

    def export_pack(self, destination: str | None = None) -> Path | None:
        try:
            candidates = self._selected_candidates()
            if not candidates:
                messagebox.showinfo(
                    "Pustaka kosong",
                    "Isi pustaka dulu dari canvas atau impor gambar.",
                    parent=self,
                )
                return None
            if destination is None:
                destination = filedialog.asksaveasfilename(
                    parent=self,
                    title="Simpan paket aset",
                    defaultextension=".batikpack",
                    filetypes=[("BatikCraft Asset Pack", "*.batikpack")],
                )
            if not destination:
                return None
            output = build_asset_pack(candidates, self._metadata(), destination)
        except (AssetPackBuildError, AssetLibraryError, OSError) as exc:
            messagebox.showerror("Ekspor paket gagal", str(exc), parent=self)
            return None
        self.status_value.set(f"Paket tersimpan: {output}")
        return output

    def sell_pack(self) -> None:
        provider = self.client_provider
        client = provider() if provider is not None else None
        if client is None:
            messagebox.showinfo(
                "Perlu login",
                "Login BatikCraftWeb dulu melalui menu Marketplace.",
                parent=self,
            )
            return
        try:
            candidates = self._selected_candidates()
        except (AssetLibraryError, OSError) as exc:
            messagebox.showerror("Baca aset gagal", str(exc), parent=self)
            return
        if not candidates:
            messagebox.showinfo(
                "Pustaka kosong",
                "Isi pustaka dulu dari canvas atau impor gambar.",
                parent=self,
            )
            return

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            pack_path = self.export_pack(str(Path(tmp) / "paket.batikpack"))
            if pack_path is None:
                return
            archive = pack_path.read_bytes()

        preview = candidates[0].content
        metadata = self._metadata()
        checksum = hashlib.sha256(archive).hexdigest()
        self.status_value.set("Mengunggah paket aset ke BatikCraftWeb…")
        self.sell_button.configure(state="disabled")

        def worker() -> None:
            try:
                item = client._request_multipart(  # noqa: SLF001 - API internal satu paket
                    "POST",
                    "nfts/",
                    fields={
                        "title": metadata.name,
                        "description": metadata.description,
                        "source_project_id": f"asset-pack-{checksum[:16]}",
                        "source_app_version": APP_VERSION,
                        "starting_price": str(self.price_value.get()),
                        "metadata": json.dumps(
                            {
                                "source_type": "asset_pack",
                                "asset_count": len(candidates),
                                "asset_names": [c.name for c in candidates][:50],
                                "sha256": checksum,
                            },
                            ensure_ascii=False,
                        ),
                    },
                    files={
                        "image": ("preview.png", preview, "image/png"),
                        "package_file": (
                            f"{metadata.pack_id}.batikpack",
                            archive,
                            "application/zip",
                        ),
                    },
                )
                nft_id = int(item["id"])
                client._request_json("POST", f"nfts/{nft_id}/publish/", payload={})
            except (BatikCraftWebError, OSError, KeyError, ValueError, TypeError) as exc:
                self.after(0, lambda: self._sell_failed(str(exc)))
                return
            self.after(0, lambda: self._sell_done(metadata.name))

        threading.Thread(target=worker, daemon=True).start()

    def _sell_failed(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self.sell_button.configure(state="normal")
        self.status_value.set(message)
        messagebox.showerror("Penjualan paket gagal", message, parent=self)

    def _sell_done(self, name: str) -> None:
        if not self.winfo_exists():
            return
        self.sell_button.configure(state="normal")
        self.status_value.set(f"Paket {name!r} tampil di NFT Marketplace.")
        messagebox.showinfo(
            "Paket aset dijual",
            f"{name} berhasil diunggah dan dipublikasikan.",
            parent=self,
        )


__all__ = ["AssetPackStudioWindow"]
