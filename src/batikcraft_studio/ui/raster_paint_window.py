"""Jendela lukis raster mandiri — pratinjau kanvas gaya MS Paint per layer.

Membungkus RasterCanvasWidget dengan dialog Dokumen Baru / Ubah Ukuran Kanvas
memakai preset. Dipasang sebagai jendela terpisah lebih dulu supaya alur baru
bisa dicoba tanpa mengganggu kanvas utama, sesuai rencana bertahap.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from batikcraft_studio.imaging.canvas_presets import (
    CANVAS_PRESETS,
    DEFAULT_PRESET_KEY,
    clamp_dimension,
    estimate_document_megabytes,
    preset_by_key,
)
from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.persistence.export_location import (
    is_cloud_synced_path,
    reveal_in_file_manager,
    safe_default_export_dir,
)
from batikcraft_studio.persistence.raster_archive import (
    PAINT_EXTENSION,
    RasterArchiveError,
    load_raster_document,
    save_raster_document,
    write_png_atomic,
)
from batikcraft_studio.ui.raster_canvas_widget import RasterCanvasWidget


class CanvasSizeDialog(tk.Toplevel):
    """Pilih ukuran kanvas: preset atau ukuran bebas."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str = "Ukuran Kanvas",
        initial: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: tuple[int, int] | None = None

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Preset").grid(row=0, column=0, sticky="w")
        self._preset_var = tk.StringVar(value=DEFAULT_PRESET_KEY)
        preset_box = ttk.Combobox(
            frame, state="readonly", textvariable=self._preset_var, width=32,
            values=[preset.label for preset in CANVAS_PRESETS],
        )
        preset_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        preset_box.bind("<<ComboboxSelected>>", self._on_preset)

        ttk.Label(frame, text="Lebar").grid(row=1, column=0, sticky="w")
        self._w_var = tk.IntVar(value=(initial or (2048, 2048))[0])
        ttk.Spinbox(frame, from_=1, to=8192, textvariable=self._w_var, width=8).grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Label(frame, text="Tinggi").grid(row=2, column=0, sticky="w")
        self._h_var = tk.IntVar(value=(initial or (2048, 2048))[1])
        ttk.Spinbox(frame, from_=1, to=8192, textvariable=self._h_var, width=8).grid(
            row=2, column=1, sticky="w", pady=2
        )

        self._memory_label = ttk.Label(frame, text="")
        self._memory_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        for var in (self._w_var, self._h_var):
            var.trace_add("write", lambda *_a: self._update_memory())

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(side="right")
        ttk.Button(actions, text="OK", command=self._ok).pack(side="right", padx=6)

        if initial is None:
            self._on_preset()
        self._update_memory()
        self.transient(master)
        self.grab_set()

    def _on_preset(self, _event: object = None) -> None:
        label = self._preset_var.get()
        for preset in CANVAS_PRESETS:
            if preset.label == label:
                self._w_var.set(preset.width)
                self._h_var.set(preset.height)
                return

    def _update_memory(self) -> None:
        try:
            width = clamp_dimension(self._w_var.get())
            height = clamp_dimension(self._h_var.get())
        except tk.TclError:
            return
        megabytes = estimate_document_megabytes(width, height, 1)
        note = f"± {megabytes:.0f} MB per layer"
        if megabytes > 100:
            note += "  (besar — hati-hati dengan banyak layer)"
        self._memory_label.configure(text=note)

    def _ok(self) -> None:
        self.result = (
            clamp_dimension(self._w_var.get()),
            clamp_dimension(self._h_var.get()),
        )
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class RasterPaintWindow(tk.Toplevel):
    """Jendela lukis raster lengkap dengan menu dokumen."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_status: Callable[[str], None] | None = None,
        document: RasterDocument | None = None,
        library_saver: "Callable[[RasterDocument], str] | None" = None,
    ) -> None:
        super().__init__(master)
        self._library_saver = library_saver
        self.title("Kanvas Lukis (Raster) — pratinjau")
        self.geometry("1180x820")
        self.minsize(900, 640)
        self._on_status = on_status
        self.document = document or RasterDocument(width=2048, height=2048)
        self._path: Path | None = None

        self._build_menu()
        self._status = ttk.Label(self, text="Siap.", anchor="w")
        self._status.pack(side="bottom", fill="x")
        self._widget = RasterCanvasWidget(self, self.document, on_status=self.set_status)
        self._widget.pack(fill="both", expand=True)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        doc_menu = tk.Menu(menu_bar, tearoff=False)
        doc_menu.add_command(label="Dokumen Baru…", command=self.new_document)
        doc_menu.add_command(label="Buka…", command=self.open_document)
        doc_menu.add_command(label="Simpan…", command=self.save_document)
        doc_menu.add_separator()
        doc_menu.add_command(label="Ubah Ukuran Kanvas…", command=self.resize_canvas)
        doc_menu.add_separator()
        doc_menu.add_command(label="Ekspor gambar rata (PNG)…", command=self.export_flat)
        doc_menu.add_separator()
        doc_menu.add_command(
            label="Simpan ke Pustaka Aset…", command=self.save_to_library
        )
        menu_bar.add_cascade(label="Dokumen", menu=doc_menu)
        self.configure(menu=menu_bar)

    def new_document(self) -> None:
        dialog = CanvasSizeDialog(self, title="Dokumen Baru")
        self.wait_window(dialog)
        if dialog.result is None:
            return
        width, height = dialog.result
        self.document = RasterDocument(width=width, height=height)
        self._path = None
        self._swap_widget()
        self.set_status(f"Dokumen baru {width}×{height}.")

    def resize_canvas(self) -> None:
        dialog = CanvasSizeDialog(
            self,
            title="Ubah Ukuran Kanvas",
            initial=(self.document.width, self.document.height),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        width, height = dialog.result
        self.document.resize_canvas(width, height, anchor="nw")
        self._widget.refresh()
        self.set_status(f"Kanvas diubah ke {width}×{height} (gambar dipertahankan).")

    def open_document(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Buka dokumen raster",
            filetypes=[("Dokumen BatikPaint", f"*{PAINT_EXTENSION}")],
        )
        if not path:
            return
        try:
            document = load_raster_document(path)
        except RasterArchiveError as exc:
            messagebox.showerror("Gagal membuka", str(exc), parent=self)
            return
        self.document = document
        self._path = Path(path)
        self._swap_widget()
        self.set_status(f"Dibuka: {Path(path).name}")

    def save_document(self) -> None:
        initial = getattr(self, "_path", None)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Simpan dokumen raster",
            defaultextension=PAINT_EXTENSION,
            initialfile=initial.name if initial else "karya" + PAINT_EXTENSION,
            filetypes=[("Dokumen BatikPaint", f"*{PAINT_EXTENSION}")],
        )
        if not path:
            return
        try:
            saved = save_raster_document(path, self.document)
        except RasterArchiveError as exc:
            messagebox.showerror("Gagal menyimpan", str(exc), parent=self)
            return
        self._path = saved
        self.set_status(f"Disimpan: {saved.name}")

    def export_flat(self) -> None:
        """Ekspor perataan seluruh dokumen sebagai PNG — dasar pustaka & cetak."""

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Ekspor gambar rata",
            defaultextension=".png",
            initialdir=str(safe_default_export_dir()),
            filetypes=[("Gambar PNG", "*.png")],
        )
        if not path:
            return
        # Peringatkan SEBELUM menulis kalau tujuannya folder tersinkron cloud:
        # OneDrive dsb. bisa mengubah berkas jadi placeholder online-only setelah
        # ditulis, sehingga terlihat di folder tapi gagal dibuka.
        if is_cloud_synced_path(path):
            lanjut = messagebox.askyesno(
                "Folder tersinkron cloud",
                "Folder tujuan tampaknya dikelola OneDrive/cloud. Berkas bisa "
                "berubah jadi placeholder online sehingga sulit dibuka.\n\n"
                "Tetap simpan di sini? (Pilih 'No' untuk memilih folder lain.)",
                parent=self,
            )
            if not lanjut:
                return
        try:
            saved = write_png_atomic(path, self.document.flatten())
        except (OSError, RasterArchiveError, ValueError) as exc:
            messagebox.showerror("Gagal mengekspor", str(exc), parent=self)
            return
        self.set_status(f"Diekspor & diverifikasi: {saved}")
        if messagebox.askyesno(
            "Ekspor selesai",
            f"Tersimpan ({saved.stat().st_size // 1024} KB):\n{saved}\n\n"
            "Buka lokasinya di File Explorer?",
            parent=self,
        ):
            reveal_in_file_manager(saved)

    def save_to_library(self) -> None:
        """Ratakan dokumen penuh dan simpan sebagai satu aset ke pustaka.

        Pustaka berasal dari dokumen PENUH, bukan objek per objek. Penyimpanan
        sesungguhnya (pemilihan pustaka tujuan) didelegasikan ke aplikasi induk
        lewat ``library_saver`` supaya jendela ini tidak perlu tahu detail
        pustaka/akun.
        """

        if self._library_saver is None:
            messagebox.showinfo(
                "Pustaka tidak tersedia",
                "Buka kanvas raster dari aplikasi utama untuk menyimpan ke pustaka.",
                parent=self,
            )
            return
        try:
            message = self._library_saver(self.document)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal menyimpan ke pustaka", str(exc), parent=self)
            return
        if message:
            self.set_status(message)

    def _swap_widget(self) -> None:
        self._widget.destroy()
        self._widget = RasterCanvasWidget(self, self.document, on_status=self.set_status)
        self._widget.pack(fill="both", expand=True)

    def insert_result_images(self, results: object) -> None:
        """Terima hasil batifikasi (dari studio SDXL) sebagai layer baru."""

        count = 0
        for result in results:  # type: ignore[union-attr]
            label = getattr(result, "label", "Batik")
            content = getattr(result, "content", None)
            if content is None:
                continue
            self._widget.insert_image_bytes(content, name=str(label))
            count += 1
        self.set_status(f"{count} hasil batifikasi disisipkan sebagai layer.")

    def set_status(self, message: str) -> None:
        self._status.configure(text=message)
        if self._on_status is not None:
            self._on_status(message)


__all__ = ["CanvasSizeDialog", "RasterPaintWindow"]
