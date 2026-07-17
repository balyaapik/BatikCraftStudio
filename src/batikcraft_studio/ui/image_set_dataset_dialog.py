"""Build SDXL training datasets from sets of ordinary image files."""

from __future__ import annotations

import hashlib
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from batikcraft_studio.ai import (
    BATIK_DATASET_EXTENSION,
    BatikDatasetError,
    BatikDatasetMetadata,
    BatikTrainingSample,
    build_batik_dataset,
)

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})


@dataclass(slots=True)
class ImageSetEntry:
    path: Path
    caption: str


class ImageSetDatasetStudioWindow(tk.Toplevel):
    """Create one `.batikdataset` from multiple normal image files."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.entries: list[ImageSetEntry] = []
        self.dataset_name = tk.StringVar(master=self, value="BatikCraft Image Set")
        self.dataset_id = tk.StringVar(master=self, value="batikcraft-image-set-v1")
        self.author_value = tk.StringVar(master=self)
        self.trigger_value = tk.StringVar(master=self, value="bcr_ornament")
        self.category_value = tk.StringVar(master=self, value="ornament")
        self.style_value = tk.StringVar(master=self, value="batikcraft")
        self.recursive_value = tk.BooleanVar(master=self, value=True)
        self.status_value = tk.StringVar(
            master=self,
            value="Tambahkan sedikitnya dua gambar PNG/JPG/WebP atau satu folder gambar.",
        )

        self.title("Training AI Lokal — Set Gambar SDXL")
        self.geometry("980x720")
        self.minsize(860, 620)
        self.transient(parent.winfo_toplevel())
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(
            body,
            text="Dataset Training dari Set Gambar",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Masukkan banyak file gambar biasa. Fitur ini tidak menerima .batikasset. "
                "Caption dibaca dari file .txt dengan nama yang sama atau dibuat dari nama file."
            ),
            style="Muted.TLabel",
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        metadata = ttk.LabelFrame(body, text="Metadata Dataset", padding=10)
        metadata.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for column in (1, 3, 5):
            metadata.columnconfigure(column, weight=1)
        self._entry(metadata, 0, 0, "Dataset ID", self.dataset_id)
        self._entry(metadata, 0, 2, "Nama dataset", self.dataset_name)
        self._entry(metadata, 0, 4, "Author", self.author_value)
        self._entry(metadata, 1, 0, "Trigger word", self.trigger_value)
        self._entry(metadata, 1, 2, "Kategori", self.category_value)
        self._entry(metadata, 1, 4, "Style", self.style_value)

        content = ttk.PanedWindow(body, orient=tk.HORIZONTAL)
        content.grid(row=3, column=0, sticky="nsew")

        listing = ttk.LabelFrame(content, text="Set Gambar", padding=8)
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(1, weight=1)
        controls = ttk.Frame(listing)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(controls, text="Tambah Gambar…", command=self.add_images).pack(side="left")
        ttk.Button(controls, text="Tambah Folder…", command=self.add_folder).pack(
            side="left",
            padx=(6, 0),
        )
        ttk.Checkbutton(
            controls,
            text="Sertakan subfolder",
            variable=self.recursive_value,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(controls, text="Hapus", command=self.remove_selected).pack(
            side="right",
            padx=(6, 0),
        )
        ttk.Button(controls, text="Kosongkan", command=self.clear).pack(side="right")

        self.tree = ttk.Treeview(
            listing,
            columns=("file", "caption"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("file", text="File gambar")
        self.tree.heading("caption", text="Caption")
        self.tree.column("file", width=300)
        self.tree.column("caption", width=420)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._load_selected_caption)
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        content.add(listing, weight=3)

        editor = ttk.LabelFrame(content, text="Caption Gambar Terpilih", padding=10)
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(1, weight=1)
        ttk.Label(
            editor,
            text=(
                "Gunakan caption yang menjelaskan bentuk motif, gaya garis, komposisi, "
                "dan ciri batiknya. Trigger word ditambahkan otomatis saat training."
            ),
            style="Muted.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.caption_text = tk.Text(editor, height=12, wrap="word")
        self.caption_text.grid(row=1, column=0, sticky="nsew")
        ttk.Button(
            editor,
            text="Terapkan Caption",
            command=self.apply_caption,
        ).grid(row=2, column=0, sticky="e", pady=(8, 0))
        content.add(editor, weight=1)

        footer = ttk.Frame(body)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            footer,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=650,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Tutup", command=self.destroy).pack(side="right")
        ttk.Button(
            footer,
            text="Ekspor .batikdataset",
            command=self.export_dataset,
        ).pack(side="right", padx=(0, 8))

    @staticmethod
    def _entry(
        parent: ttk.Frame,
        row: int,
        column: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=column,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(0, 12),
            pady=3,
        )

    def add_images(self) -> None:
        values = filedialog.askopenfilenames(
            parent=self,
            title="Pilih Set Gambar Training",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        self._add_paths(Path(value) for value in values)

    def add_folder(self) -> None:
        value = filedialog.askdirectory(parent=self, title="Pilih Folder Set Gambar")
        if not value:
            return
        paths = discover_image_files(Path(value), recursive=bool(self.recursive_value.get()))
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        existing = {entry.path.resolve() for entry in self.entries}
        added = 0
        for path in paths:
            candidate = Path(path).expanduser()
            if not candidate.is_file() or candidate.suffix.casefold() not in _IMAGE_SUFFIXES:
                continue
            resolved = candidate.resolve()
            if resolved in existing:
                continue
            self.entries.append(
                ImageSetEntry(path=resolved, caption=caption_for_image(resolved))
            )
            existing.add(resolved)
            added += 1
        self.entries.sort(key=lambda entry: str(entry.path).casefold())
        self._refresh_tree()
        self.status_value.set(
            f"{added} gambar ditambahkan. Total set: {len(self.entries)} gambar."
        )

    def _refresh_tree(self) -> None:
        selected_path = self._selected_path()
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        for index, entry in enumerate(self.entries):
            iid = str(index)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(entry.path.name, entry.caption),
            )
            if selected_path is not None and entry.path == selected_path:
                self.tree.selection_set(iid)
        if self.entries and not self.tree.selection():
            self.tree.selection_set("0")
            self._load_selected_caption()

    def _selected_index(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            index = int(selection[0])
        except ValueError:
            return None
        return index if 0 <= index < len(self.entries) else None

    def _selected_path(self) -> Path | None:
        index = self._selected_index()
        return self.entries[index].path if index is not None else None

    def _load_selected_caption(self, _event: object = None) -> None:
        index = self._selected_index()
        self.caption_text.delete("1.0", "end")
        if index is not None:
            self.caption_text.insert("1.0", self.entries[index].caption)

    def apply_caption(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        caption = self.caption_text.get("1.0", "end").strip()
        if not caption:
            messagebox.showerror("Caption diperlukan", "Caption tidak boleh kosong.", parent=self)
            return
        self.entries[index].caption = caption[:1000]
        self._refresh_tree()
        self.tree.selection_set(str(index))

    def remove_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self.entries.pop(index)
        self._refresh_tree()
        self.status_value.set(f"Total set: {len(self.entries)} gambar.")

    def clear(self) -> None:
        self.entries.clear()
        self._refresh_tree()
        self.caption_text.delete("1.0", "end")
        self.status_value.set("Set gambar dikosongkan.")

    def export_dataset(self) -> None:
        if len(self.entries) < 2:
            messagebox.showerror(
                "Set gambar belum cukup",
                "Tambahkan sedikitnya dua gambar untuk membuat dataset training.",
                parent=self,
            )
            return
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Ekspor Dataset Set Gambar",
            defaultextension=BATIK_DATASET_EXTENSION,
            initialfile=f"{self.dataset_id.get().strip() or 'batikcraft-image-set'}{BATIK_DATASET_EXTENSION}",
            filetypes=[
                ("BatikCraft Dataset", f"*{BATIK_DATASET_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not destination:
            return

        try:
            samples = [
                BatikTrainingSample(
                    sample_id=_sample_id(entry.path, index),
                    caption=entry.caption,
                    target_content=entry.path.read_bytes(),
                    category=self.category_value.get().strip() or "ornament",
                    style=self.style_value.get().strip(),
                    target_roles=("main-render", "ornament"),
                    metadata={
                        "source_type": "image-set",
                        "original_name": entry.path.name,
                    },
                )
                for index, entry in enumerate(self.entries, start=1)
            ]
            metadata = BatikDatasetMetadata(
                dataset_id=self.dataset_id.get(),
                name=self.dataset_name.get(),
                author=self.author_value.get(),
                base_model_family="sdxl",
                trigger_word=self.trigger_value.get(),
                description=(
                    f"SDXL image-set dataset containing {len(samples)} ordinary image files."
                ),
            )
            output = build_batik_dataset(samples, metadata, destination)
        except (BatikDatasetError, OSError, ValueError) as exc:
            messagebox.showerror("Ekspor dataset gagal", str(exc), parent=self)
            return

        self.status_value.set(f"Dataset berhasil dibuat: {output}")
        messagebox.showinfo(
            "Dataset selesai",
            f"{len(samples)} gambar dikemas ke:\n{output}",
            parent=self,
        )


def discover_image_files(folder: Path, *, recursive: bool = True) -> tuple[Path, ...]:
    """Return supported ordinary images from one folder in stable order."""

    root = Path(folder).expanduser()
    if not root.is_dir():
        return ()
    iterator = root.rglob("*") if recursive else root.glob("*")
    return tuple(
        sorted(
            (
                path.resolve()
                for path in iterator
                if path.is_file() and path.suffix.casefold() in _IMAGE_SUFFIXES
            ),
            key=lambda path: str(path).casefold(),
        )
    )


def caption_for_image(path: Path) -> str:
    """Read a sidecar caption or derive a useful caption from the filename."""

    image = Path(path)
    sidecar = image.with_suffix(".txt")
    if sidecar.is_file():
        try:
            value = sidecar.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            value = ""
        if value:
            return value[:1000]
    stem = image.stem.replace("_", " ").replace("-", " ")
    normalized = " ".join(stem.split())
    return normalized or "Indonesian batik ornament"


def _sample_id(path: Path, index: int) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    return f"image-{index:06d}-{digest}"


__all__ = [
    "ImageSetDatasetStudioWindow",
    "ImageSetEntry",
    "caption_for_image",
    "discover_image_files",
]
