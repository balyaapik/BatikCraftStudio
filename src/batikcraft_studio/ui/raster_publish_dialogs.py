"""Dialog pustaka & publish NFT untuk dokumen raster.

Menggantikan rantai simpledialog yang minim: pemilihan pustaka lewat DAFTAR
(tanpa mengetik nama — nama aset dibuat otomatis), dan publish NFT lewat jendela
tersendiri berisi pratinjau + semua field sekaligus.

Bagian logika murni (nama otomatis, validasi harga) dipisah agar bisa diuji
tanpa Tk.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Sequence

from PIL import Image, ImageTk


def auto_asset_name(prefix: str = "Motif", now: datetime | None = None) -> str:
    """Nama aset otomatis berbasis waktu, jadi pengguna tak perlu mengetik."""

    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{prefix} {stamp}"


def normalize_price(raw: str) -> str:
    """Validasi & normalkan harga awal NFT. Kembalikan string angka.

    Menerima koma atau titik desimal. Menolak negatif / bukan angka.
    """

    text = str(raw).strip().replace(",", ".")
    if not text:
        return "0"
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError("Harga harus berupa angka.") from exc
    if value < 0:
        raise ValueError("Harga tidak boleh negatif.")
    return f"{value:g}"


def _thumbnail(image: Image.Image, size: tuple[int, int] = (220, 220)) -> Image.Image:
    preview = image.convert("RGB").copy()
    preview.thumbnail(size, Image.Resampling.LANCZOS)
    return preview


class LibrarySaveDialog(tk.Toplevel):
    """Pilih pustaka tujuan dari daftar; nama aset otomatis (bisa diubah)."""

    def __init__(
        self,
        master: tk.Misc,
        libraries: Sequence[object],
        *,
        preview: Image.Image | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Simpan ke Pustaka Aset")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._libraries = list(libraries)
        self._photo: ImageTk.PhotoImage | None = None

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        if preview is not None:
            thumb = _thumbnail(preview)
            self._photo = ImageTk.PhotoImage(thumb)
            tk.Label(outer, image=self._photo, borderwidth=1, relief="solid").grid(
                row=0, column=0, rowspan=4, padx=(0, 14), sticky="n"
            )

        ttk.Label(outer, text="Pilih pustaka:").grid(row=0, column=1, sticky="w")
        self._list = tk.Listbox(outer, height=8, width=34, exportselection=False)
        self._list.grid(row=1, column=1, sticky="ew")
        for pack in self._libraries:
            self._list.insert(tk.END, getattr(pack, "name", getattr(pack, "pack_id", "?")))
        if self._libraries:
            self._list.selection_set(0)

        ttk.Label(outer, text="Nama karya (otomatis):").grid(
            row=2, column=1, sticky="w", pady=(10, 0)
        )
        self._name_var = tk.StringVar(value=auto_asset_name())
        ttk.Entry(outer, textvariable=self._name_var, width=34).grid(
            row=3, column=1, sticky="ew"
        )

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(side="right")
        ttk.Button(actions, text="Simpan", command=self._ok).pack(side="right", padx=6)

        self.transient(master)
        self.grab_set()

    def _ok(self) -> None:
        selection = self._list.curselection()
        if not selection:
            return
        pack = self._libraries[selection[0]]
        name = self._name_var.get().strip() or auto_asset_name()
        self.result = (getattr(pack, "pack_id"), name)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class NFTPublishDialog(tk.Toplevel):
    """Jendela publish NFT: pratinjau + judul, deskripsi, harga sekaligus."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        preview: Image.Image | None = None,
        default_title: str = "",
    ) -> None:
        super().__init__(master)
        self.title("Jual sebagai NFT")
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self._photo: ImageTk.PhotoImage | None = None

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        if preview is not None:
            thumb = _thumbnail(preview, (260, 260))
            self._photo = ImageTk.PhotoImage(thumb)
            tk.Label(outer, image=self._photo, borderwidth=1, relief="solid").grid(
                row=0, column=0, rowspan=6, padx=(0, 16), sticky="n"
            )

        ttk.Label(outer, text="Judul motif").grid(row=0, column=1, sticky="w")
        self._title_var = tk.StringVar(value=default_title)
        ttk.Entry(outer, textvariable=self._title_var, width=40).grid(
            row=1, column=1, sticky="ew"
        )

        ttk.Label(outer, text="Deskripsi / filosofi").grid(
            row=2, column=1, sticky="w", pady=(10, 0)
        )
        self._desc = tk.Text(outer, width=40, height=6, wrap="word")
        self._desc.grid(row=3, column=1, sticky="ew")

        ttk.Label(outer, text="Harga awal").grid(row=4, column=1, sticky="w", pady=(10, 0))
        self._price_var = tk.StringVar(value="0")
        ttk.Entry(outer, textvariable=self._price_var, width=16).grid(
            row=5, column=1, sticky="w"
        )

        self._error = ttk.Label(outer, text="", foreground="#B00020")
        self._error.grid(row=6, column=1, sticky="w", pady=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(side="right")
        ttk.Button(actions, text="Publikasikan", command=self._ok).pack(
            side="right", padx=6
        )

        self.transient(master)
        self.grab_set()

    def _ok(self) -> None:
        title = self._title_var.get().strip()
        if not title:
            self._error.configure(text="Judul tidak boleh kosong.")
            return
        try:
            price = normalize_price(self._price_var.get())
        except ValueError as exc:
            self._error.configure(text=str(exc))
            return
        self.result = {
            "title": title,
            "description": self._desc.get("1.0", "end").strip(),
            "price": price,
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = [
    "LibrarySaveDialog",
    "NFTPublishDialog",
    "auto_asset_name",
    "normalize_price",
]
