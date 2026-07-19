"""Studio Pustaka Aset — alur: buat wadah pustaka dulu, isi, baru jual.

Wadah pustaka dibuat lebih dahulu dengan metadata lengkap (nama, author,
filosofi, tipe: motif-pokok / isen-isen / ornamen / tekstur / lainnya).
Setelah wadah ada, user mengisinya dengan objek dari canvas (menu Asset →
Simpan Objek Terpilih) atau gambar dari luar aplikasi. Pustaka yang sudah
berisi barulah bisa diekspor sebagai ``.batikpack`` atau dijual ke
BatikCraftWeb.
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
    LIBRARY_TYPES,
    SUPPORTED_IMAGE_EXTENSIONS,
    PersonalAssetStore,
    create_user_library,
    list_user_libraries,
    parse_library_description,
)
from batikcraft_studio.config import APP_VERSION
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError


class CreateLibraryDialog(tk.Toplevel):
    """Form pembuatan wadah pustaka: nama, author, filosofi, tipe."""

    def __init__(
        self,
        parent: tk.Misc,
        library: AssetLibrary,
        *,
        on_created: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Buat Pustaka Aset Baru")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.library = library
        self.on_created = on_created
        self.result: str | None = None

        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        self.name_value = tk.StringVar(master=self)
        self.author_value = tk.StringVar(master=self)
        self.type_value = tk.StringVar(master=self, value="ornamen")

        ttk.Label(body, text="Nama pustaka:").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.name_value, width=42).grid(
            row=0, column=1, sticky="ew", padx=(6, 0), pady=1
        )
        ttk.Label(body, text="Author pustaka:").grid(row=1, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.author_value).grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=1
        )
        ttk.Label(body, text="Tipe pustaka:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            body,
            textvariable=self.type_value,
            values=list(LIBRARY_TYPES),
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=1)
        ttk.Label(body, text="Filosofi pustaka:").grid(row=3, column=0, sticky="nw", pady=(4, 0))
        self.philosophy_text = tk.Text(body, width=42, height=4, wrap="word")
        self.philosophy_text.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Batal", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(
            buttons, text="Buat Pustaka", style="Accent.TButton", command=self._create
        ).pack(side="right")

    def _create(self) -> None:
        try:
            pack_id = create_user_library(
                self.library,
                name=self.name_value.get(),
                author=self.author_value.get(),
                philosophy=self.philosophy_text.get("1.0", "end").strip(),
                library_type=self.type_value.get(),
            )
        except AssetLibraryError as exc:
            messagebox.showerror("Pustaka tidak dapat dibuat", str(exc), parent=self)
            return
        self.result = pack_id
        if self.on_created is not None:
            self.on_created(pack_id)
        self.destroy()


class LibraryPickerDialog(tk.Toplevel):
    """Pilih satu pustaka user sebagai tujuan penyimpanan objek."""

    def __init__(self, parent: tk.Misc, packs: list[Any]) -> None:
        super().__init__(parent)
        self.title("Pilih Pustaka Tujuan")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: str | None = None
        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0)
        self.listbox = tk.Listbox(body, height=min(8, max(3, len(packs))), width=48)
        for pack in packs:
            library_type, _ = parse_library_description(pack.description)
            self.listbox.insert("end", f"{pack.name}  ({library_type}, {pack.author})")
        self.listbox.selection_set(0)
        self.listbox.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._packs = packs
        ttk.Button(body, text="Batal", command=self.destroy).grid(
            row=1, column=0, sticky="e", pady=(8, 0), padx=(0, 6)
        )
        ttk.Button(body, text="Pilih", style="Accent.TButton", command=self._pick).grid(
            row=1, column=1, sticky="e", pady=(8, 0)
        )
        self.listbox.bind("<Double-Button-1>", lambda _e: self._pick())

    def _pick(self) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.result = self._packs[int(selection[0])].pack_id
        self.destroy()


class AssetPackStudioWindow(tk.Toplevel):
    """Kelola pustaka user: lihat isi, impor gambar, ekspor, dan jual."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        library: AssetLibrary,
        client_provider: Callable[[], BatikCraftWebClient | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Studio Pustaka Aset")
        self.library = library
        self.store = PersonalAssetStore(library)
        self.client_provider = client_provider
        self._packs: list[Any] = []
        self._records: list[Any] = []

        body = ttk.Frame(self, padding=(12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(body, text="Pustaka:").grid(row=0, column=0, sticky="w")
        self.pack_value = tk.StringVar(master=self)
        self.pack_combo = ttk.Combobox(
            body, textvariable=self.pack_value, state="readonly", width=42
        )
        self.pack_combo.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        self.pack_combo.bind("<<ComboboxSelected>>", lambda _e: self._show_pack())
        ttk.Button(
            body, text="Buat Pustaka Baru…", command=self.create_library
        ).grid(row=0, column=2, sticky="e")

        self.info_value = tk.StringVar(master=self, value="")
        ttk.Label(
            body, textvariable=self.info_value, style="Muted.TLabel",
            wraplength=600, justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 6))

        self.tree = ttk.Treeview(
            body,
            columns=("category",),
            show="tree headings",
            selectmode="extended",
            height=11,
        )
        self.tree.heading("#0", text="Isi pustaka")
        self.tree.heading("category", text="Kategori")
        self.tree.column("#0", width=380)
        self.tree.column("category", width=130)
        self.tree.grid(row=2, column=0, columnspan=3, sticky="nsew")

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(2, weight=1)
        self.import_button = ttk.Button(
            buttons, text="Impor Gambar ke Pustaka…", command=self.import_images
        )
        self.import_button.grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Muat Ulang", command=self.refresh_packs).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )
        self.export_button = ttk.Button(
            buttons, text="Ekspor .batikpack…", command=self.export_pack
        )
        self.export_button.grid(row=0, column=3, sticky="e", padx=(0, 6))
        self.sell_button = ttk.Button(
            buttons,
            text="Jual Pustaka Ini…",
            style="Accent.TButton",
            command=self.sell_pack,
        )
        self.sell_button.grid(row=0, column=4, sticky="e")

        price_row = ttk.Frame(body)
        price_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(price_row, text="Harga awal saat dijual:").pack(side="left")
        self.price_value = tk.StringVar(master=self, value="100000")
        ttk.Entry(price_row, textvariable=self.price_value, width=14).pack(
            side="left", padx=(6, 0)
        )

        self.status_value = tk.StringVar(master=self, value="")
        ttk.Label(body, textvariable=self.status_value, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        self.refresh_packs()

    # ------------------------------------------------------------------
    def refresh_packs(self, select_pack_id: str | None = None) -> None:
        self.library.refresh()
        self._packs = list(list_user_libraries(self.library))
        labels = []
        for pack in self._packs:
            library_type, _ = parse_library_description(pack.description)
            labels.append(f"{pack.name}  ({library_type}, {len(pack.assets)} aset)")
        self.pack_combo.configure(values=labels)
        if not self._packs:
            self.pack_value.set("")
            self.info_value.set(
                "Belum ada pustaka. Buat wadah pustaka dulu (nama, author, "
                "filosofi, tipe), baru isi dengan objek canvas atau gambar impor."
            )
            self._records = []
            self._render_records()
            self._update_action_states()
            return
        index = 0
        if select_pack_id is not None:
            for position, pack in enumerate(self._packs):
                if pack.pack_id == select_pack_id:
                    index = position
                    break
        self.pack_combo.current(index)
        self._show_pack()

    def _selected_pack(self) -> Any | None:
        index = self.pack_combo.current()
        if 0 <= index < len(self._packs):
            return self._packs[index]
        return None

    def _show_pack(self) -> None:
        pack = self._selected_pack()
        if pack is None:
            return
        library_type, philosophy = parse_library_description(pack.description)
        self.info_value.set(
            f"Author: {pack.author or '-'}  •  Tipe: {library_type}  •  "
            f"{len(pack.assets)} aset\nFilosofi: {philosophy or '-'}"
        )
        self._records = list(pack.assets)
        self._render_records()
        self._update_action_states()

    def _render_records(self) -> None:
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        for index, record in enumerate(self._records):
            self.tree.insert(
                "", "end", iid=str(index), text=record.name, values=(record.category,)
            )

    def _update_action_states(self) -> None:
        has_pack = self._selected_pack() is not None
        has_assets = bool(self._records)
        self.import_button.configure(state="normal" if has_pack else "disabled")
        self.export_button.configure(
            state="normal" if has_pack and has_assets else "disabled"
        )
        sellable = has_pack and has_assets and self.client_provider is not None
        self.sell_button.configure(state="normal" if sellable else "disabled")

    # ------------------------------------------------------------------
    def create_library(self) -> None:
        dialog = CreateLibraryDialog(
            self,
            self.library,
            on_created=lambda pack_id: self.refresh_packs(select_pack_id=pack_id),
        )
        dialog.focus_set()

    def import_images(self) -> None:
        pack = self._selected_pack()
        if pack is None:
            messagebox.showinfo(
                "Buat pustaka dulu",
                "Buat wadah pustaka terlebih dahulu sebelum mengisi gambar.",
                parent=self,
            )
            return
        library_type, _ = parse_library_description(pack.description)
        category = library_type if library_type in LIBRARY_TYPES else "ornamen"
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_IMAGE_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            parent=self,
            title=f"Impor gambar ke pustaka {pack.name!r}",
            filetypes=[("Gambar", patterns), ("Semua file", "*.*")],
        )
        imported = 0
        for raw in paths:
            path = Path(raw)
            try:
                self.store.import_image(
                    path.name,
                    path.read_bytes(),
                    category=category,
                    pack_id=pack.pack_id,
                )
                imported += 1
            except (AssetLibraryError, OSError) as exc:
                messagebox.showwarning("Impor gagal", f"{path.name}: {exc}", parent=self)
        if imported:
            self.refresh_packs(select_pack_id=pack.pack_id)
            self.status_value.set(f"{imported} gambar masuk ke pustaka {pack.name!r}.")

    # ------------------------------------------------------------------
    def _candidates(self) -> list[AssetCandidate]:
        return [
            AssetCandidate(
                asset_id=record.asset_id,
                name=record.name,
                category=record.category,
                content=self.library.read_asset(record),
            )
            for record in self._records
        ]

    def export_pack(self, destination: str | None = None) -> Path | None:
        pack = self._selected_pack()
        if pack is None or not self._records:
            messagebox.showinfo(
                "Pustaka belum siap",
                "Pilih pustaka yang sudah berisi aset.",
                parent=self,
            )
            return None
        try:
            if destination is None:
                destination = filedialog.asksaveasfilename(
                    parent=self,
                    title="Simpan pustaka sebagai paket",
                    defaultextension=".batikpack",
                    initialfile=f"{pack.name}.batikpack",
                    filetypes=[("BatikCraft Asset Pack", "*.batikpack")],
                )
            if not destination:
                return None
            metadata = AssetPackMetadata(
                pack_id=pack.pack_id,
                name=pack.name,
                author=pack.author or "BatikCraft User",
                description=pack.description,
            )
            output = build_asset_pack(self._candidates(), metadata, destination)
        except (AssetPackBuildError, AssetLibraryError, OSError) as exc:
            messagebox.showerror("Ekspor pustaka gagal", str(exc), parent=self)
            return None
        self.status_value.set(f"Pustaka tersimpan sebagai paket: {output}")
        return output

    def sell_pack(self) -> None:
        pack = self._selected_pack()
        if pack is None or not self._records:
            messagebox.showinfo(
                "Pustaka belum siap",
                "Pustaka harus dibuat dan berisi aset sebelum dijual.",
                parent=self,
            )
            return
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
            candidates = self._candidates()
        except (AssetLibraryError, OSError) as exc:
            messagebox.showerror("Baca aset gagal", str(exc), parent=self)
            return

        import tempfile

        library_type, philosophy = parse_library_description(pack.description)
        with tempfile.TemporaryDirectory() as tmp:
            pack_path = self.export_pack(str(Path(tmp) / "pustaka.batikpack"))
            if pack_path is None:
                return
            archive = pack_path.read_bytes()

        checksum = hashlib.sha256(archive).hexdigest()
        preview = candidates[0].content
        self.status_value.set("Mengunggah pustaka ke BatikCraftWeb…")
        self.sell_button.configure(state="disabled")

        def worker() -> None:
            try:
                item = client._request_multipart(  # noqa: SLF001 - API internal satu paket
                    "POST",
                    "nfts/",
                    fields={
                        "title": pack.name,
                        "description": philosophy or pack.description,
                        "source_project_id": f"asset-library-{pack.pack_id}"[:128],
                        "source_app_version": APP_VERSION,
                        "starting_price": str(self.price_value.get()),
                        "metadata": json.dumps(
                            {
                                "source_type": "asset_library",
                                "library_name": pack.name,
                                "library_author": pack.author,
                                "library_type": library_type,
                                "philosophy": philosophy,
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
                            f"{pack.pack_id}.batikpack",
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
            self.after(0, lambda: self._sell_done(pack.name))

        threading.Thread(target=worker, daemon=True).start()

    def _sell_failed(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self._update_action_states()
        self.status_value.set(message)
        messagebox.showerror("Penjualan pustaka gagal", message, parent=self)

    def _sell_done(self, name: str) -> None:
        if not self.winfo_exists():
            return
        self._update_action_states()
        self.status_value.set(f"Pustaka {name!r} tampil di NFT Marketplace.")
        messagebox.showinfo(
            "Pustaka dijual",
            f"{name} berhasil diunggah dan dipublikasikan.",
            parent=self,
        )


__all__ = ["AssetPackStudioWindow", "CreateLibraryDialog", "LibraryPickerDialog"]
