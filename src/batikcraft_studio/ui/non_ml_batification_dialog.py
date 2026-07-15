"""Modal preview workflow for non-ML Batification of one canvas object."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from batikcraft_studio.application import (
    NonMLBatificationPreview,
    ProjectSessionError,
)
from batikcraft_studio.assets import (
    AssetLibrary,
    AssetLibraryError,
    AssetRecord,
    PersonalAssetStore,
)
from batikcraft_studio.imaging.batik_asset import BatikAssetError, load_batik_asset
from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationError,
    NonMLBatificationMode,
    NonMLBatificationOptions,
)

from .external_image_io import image_dialog_filetypes

PreviewRenderer = Callable[
    [bytes, str, str | None, NonMLBatificationOptions],
    NonMLBatificationPreview,
]

_MODE_BY_LABEL = {
    "Isi + Garis": NonMLBatificationMode.FILL_OUTLINE,
    "Isi Motif": NonMLBatificationMode.FILL,
    "Garis Motif": NonMLBatificationMode.OUTLINE,
}


class NonMLBatificationDialog(tk.Toplevel):
    """Preview source, motif, and output before committing an in-place replacement."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        source_name: str,
        source_content: bytes,
        asset_library: AssetLibrary,
        personal_store: PersonalAssetStore,
        render_preview: PreviewRenderer,
    ) -> None:
        super().__init__(parent)
        self.title("Proses Batifikasi Non-AI")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.result: NonMLBatificationPreview | None = None
        self._source_content = bytes(source_content)
        self._asset_library = asset_library
        self._personal_store = personal_store
        self._render_preview = render_preview
        self._motif_content: bytes | None = None
        self._motif_name = ""
        self._motif_library_key: str | None = None
        self._records_by_iid: dict[str, AssetRecord] = {}
        self._photos: dict[str, ImageTk.PhotoImage] = {}

        self.search_value = tk.StringVar(master=self, value="")
        self.mode_value = tk.StringVar(master=self, value="Isi + Garis")
        self.pattern_scale_value = tk.DoubleVar(master=self, value=0.65)
        self.rotation_value = tk.DoubleVar(master=self, value=0.0)
        self.opacity_value = tk.DoubleVar(master=self, value=1.0)
        self.outline_strength_value = tk.DoubleVar(master=self, value=1.0)
        self.outline_width_value = tk.IntVar(master=self, value=2)
        self.shading_value = tk.DoubleVar(master=self, value=0.42)
        self.tolerance_value = tk.IntVar(master=self, value=24)
        self.status_value = tk.StringVar(
            master=self,
            value="Pilih motif dari pustaka atau upload motif baru.",
        )

        self._build_layout(source_name)
        self._set_preview("source", self._source_content)
        self._refresh_library_records()
        self.search_value.trace_add("write", lambda *_args: self._refresh_library_records())
        self.grab_set()
        self.focus_set()

    def _build_layout(self, source_name: str) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.columnconfigure(2, weight=1)
        root.rowconfigure(0, weight=2)
        root.rowconfigure(1, weight=3)

        self.source_preview = self._preview_panel(root, "Objek Sumber", 0)
        self.motif_preview = self._preview_panel(root, "Motif Batik", 1)
        self.result_preview = self._preview_panel(root, "Preview Hasil", 2)
        self.source_preview.configure(text=f"Objek Sumber — {source_name}")

        library_frame = ttk.LabelFrame(root, text="Pilih Motif dari Pustaka", padding=10)
        library_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=8)
        library_frame.columnconfigure(0, weight=1)
        library_frame.rowconfigure(1, weight=1)

        search_row = ttk.Frame(library_frame)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        search_row.columnconfigure(0, weight=1)
        ttk.Entry(search_row, textvariable=self.search_value).grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Button(
            search_row,
            text="Upload Motif…",
            command=self._upload_motif,
        ).grid(row=0, column=1, padx=(8, 0))

        columns = ("name", "category", "pack")
        self.library_tree = ttk.Treeview(
            library_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.library_tree.heading("name", text="Nama")
        self.library_tree.heading("category", text="Kategori")
        self.library_tree.heading("pack", text="Pustaka")
        self.library_tree.column("name", width=260, anchor="w")
        self.library_tree.column("category", width=120, anchor="w")
        self.library_tree.column("pack", width=150, anchor="w")
        self.library_tree.grid(row=1, column=0, sticky="nsew")
        self.library_tree.bind("<<TreeviewSelect>>", self._on_library_select)
        scrollbar = ttk.Scrollbar(
            library_frame,
            orient="vertical",
            command=self.library_tree.yview,
        )
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.library_tree.configure(yscrollcommand=scrollbar.set)

        options = ttk.LabelFrame(root, text="Pengaturan Batifikasi", padding=10)
        options.grid(row=1, column=2, sticky="nsew", padx=(8, 0), pady=8)
        options.columnconfigure(1, weight=1)
        self._option_combo(options, 0, "Mode", self.mode_value, tuple(_MODE_BY_LABEL))
        self._option_spin(options, 1, "Skala motif", self.pattern_scale_value, 0.08, 8.0, 0.05)
        self._option_spin(options, 2, "Rotasi motif", self.rotation_value, 0.0, 359.0, 1.0)
        self._option_spin(options, 3, "Opacity motif", self.opacity_value, 0.0, 1.0, 0.05)
        self._option_spin(
            options,
            4,
            "Kekuatan garis",
            self.outline_strength_value,
            0.0,
            1.0,
            0.05,
        )
        self._option_spin(options, 5, "Lebar garis", self.outline_width_value, 1, 64, 1)
        self._option_spin(options, 6, "Pertahankan shading", self.shading_value, 0.0, 1.0, 0.05)
        self._option_spin(options, 7, "Toleransi background", self.tolerance_value, 1, 128, 1)
        ttk.Button(
            options,
            text="Proses Batifikasi",
            command=self._process_preview,
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(14, 0), ipady=4)

        footer = ttk.Frame(root)
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            textvariable=self.status_value,
            anchor="w",
            wraplength=760,
        ).grid(row=0, column=0, sticky="ew")
        self.ok_button = ttk.Button(footer, text="OK", command=self._accept, state="disabled")
        self.ok_button.grid(row=0, column=1, padx=(8, 4))
        ttk.Button(footer, text="Cancel", command=self._cancel).grid(row=0, column=2)

    def _preview_panel(self, parent: ttk.Frame, title: str, column: int) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 6, 0 if column == 2 else 6),
        )
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        label = ttk.Label(frame, anchor="center", text="Belum tersedia")
        label.grid(row=0, column=0, sticky="nsew")
        setattr(self, f"_{column}_preview_label", label)
        return frame

    @staticmethod
    def _option_combo(
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)

    @staticmethod
    def _option_spin(
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.Variable,
        minimum: float,
        maximum: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=minimum,
            to=maximum,
            increment=increment,
            width=10,
        ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)

    def _refresh_library_records(self) -> None:
        query = self.search_value.get().strip()
        self._asset_library.refresh()
        records = self._asset_library.search(query, limit=600)
        current_key = self._motif_library_key
        self.library_tree.delete(*self.library_tree.get_children())
        self._records_by_iid.clear()
        selected_iid: str | None = None
        for index, record in enumerate(records):
            iid = f"asset-{index}"
            pack_name = self._asset_library.get_pack(record.pack_id).name
            self.library_tree.insert(
                "",
                "end",
                iid=iid,
                values=(record.name, record.category, pack_name),
            )
            self._records_by_iid[iid] = record
            if record.key == current_key:
                selected_iid = iid
        if selected_iid is not None:
            self.library_tree.selection_set(selected_iid)
            self.library_tree.see(selected_iid)

    def _on_library_select(self, _event: tk.Event[tk.Misc]) -> None:
        selection = self.library_tree.selection()
        if not selection:
            return
        record = self._records_by_iid.get(selection[0])
        if record is None:
            return
        try:
            raw = self._asset_library.read_asset(record)
            asset = load_batik_asset(
                raw,
                filename=record.relative_path,
                default_category=record.category,
            )
        except (AssetLibraryError, BatikAssetError) as exc:
            self.status_value.set(str(exc))
            return
        self._set_motif(asset.content, record.name, record.key)

    def _upload_motif(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Upload Motif Batik",
            filetypes=image_dialog_filetypes(),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            content = path.read_bytes()
            record = self._personal_store.import_image(
                path.name,
                content,
                category="motif-pokok",
            )
            motif_content = self._asset_library.read_asset(record)
        except (OSError, AssetLibraryError) as exc:
            messagebox.showerror("Upload motif gagal", str(exc), parent=self)
            return
        self._set_motif(motif_content, record.name, record.key)
        self._refresh_library_records()
        self.status_value.set(
            f"Motif {record.name} diupload dan disimpan ke pustaka Gambar Impor Saya."
        )

    def _set_motif(self, content: bytes, name: str, library_key: str | None) -> None:
        self._motif_content = bytes(content)
        self._motif_name = name
        self._motif_library_key = library_key
        self._set_preview("motif", self._motif_content)
        self.result = None
        self.ok_button.configure(state="disabled")
        self._clear_preview("result", "Klik Proses Batifikasi untuk melihat hasil.")
        self.status_value.set(f"Motif dipilih: {name}")

    def _options(self) -> NonMLBatificationOptions:
        return NonMLBatificationOptions(
            mode=_MODE_BY_LABEL[self.mode_value.get()],
            pattern_scale=float(self.pattern_scale_value.get()),
            pattern_rotation=float(self.rotation_value.get()),
            pattern_opacity=float(self.opacity_value.get()),
            outline_strength=float(self.outline_strength_value.get()),
            outline_width=int(self.outline_width_value.get()),
            preserve_shading=float(self.shading_value.get()),
            background_tolerance=int(self.tolerance_value.get()),
        )

    def _process_preview(self) -> None:
        if self._motif_content is None:
            self.status_value.set("Pilih atau upload motif batik terlebih dahulu.")
            return
        self.configure(cursor="watch")
        self.status_value.set("Memproses preview Batifikasi Non-AI…")
        self.update_idletasks()
        try:
            options = self._options()
            preview = self._render_preview(
                self._motif_content,
                self._motif_name,
                self._motif_library_key,
                options,
            )
        except (ProjectSessionError, NonMLBatificationError, ValueError, tk.TclError) as exc:
            self.status_value.set(str(exc))
            self.result = None
            self.ok_button.configure(state="disabled")
            return
        finally:
            self.configure(cursor="")
        self.result = preview
        self._set_preview("result", preview.result.content)
        self.ok_button.configure(state="normal")
        self.status_value.set("Preview selesai. Klik OK untuk mengganti objek pada canvas.")

    def _set_preview(self, target: str, content: bytes) -> None:
        photo = _preview_photo(content)
        self._photos[target] = photo
        label = self._preview_label(target)
        label.configure(image=photo, text="")

    def _clear_preview(self, target: str, text: str) -> None:
        self._photos.pop(target, None)
        self._preview_label(target).configure(image="", text=text)

    def _preview_label(self, target: str) -> ttk.Label:
        index = {"source": 0, "motif": 1, "result": 2}[target]
        return getattr(self, f"_{index}_preview_label")

    def _accept(self) -> None:
        if self.result is None:
            self.status_value.set("Proses preview terlebih dahulu sebelum menekan OK.")
            return
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def _preview_photo(content: bytes, size: tuple[int, int] = (330, 235)) -> ImageTk.PhotoImage:
    with Image.open(BytesIO(content)) as source:
        source.load()
        image = source.convert("RGBA")
    image.thumbnail((size[0] - 18, size[1] - 18), Image.Resampling.LANCZOS)
    backdrop = Image.new("RGBA", size, (244, 241, 234, 255))
    draw = ImageDraw.Draw(backdrop)
    tile = 12
    for top in range(0, size[1], tile):
        for left in range(0, size[0], tile):
            if (left // tile + top // tile) % 2:
                draw.rectangle(
                    (left, top, left + tile - 1, top + tile - 1),
                    fill=(226, 221, 211, 255),
                )
    position = ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
    backdrop.alpha_composite(image, dest=position)
    return ImageTk.PhotoImage(backdrop)


__all__ = ["NonMLBatificationDialog", "PreviewRenderer"]
