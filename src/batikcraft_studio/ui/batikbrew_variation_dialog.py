"""Visual picker for BatikBrew SDXL seed variations."""

from __future__ import annotations

import tkinter as tk
from io import BytesIO
from tkinter import ttk

from PIL import Image, ImageTk

from batikcraft_studio.ai.batikbrew_generation import create_tile_preview
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationResult


class BatikBrewVariationDialog(tk.Toplevel):
    """Show up to four generated motifs and return the selected variation."""

    def __init__(
        self,
        parent: tk.Misc,
        results: tuple[PretrainedAIBatificationResult, ...],
    ) -> None:
        super().__init__(parent)
        if not results:
            raise ValueError("results tidak boleh kosong")
        self.results = results[:4]
        self.result: PretrainedAIBatificationResult | None = None
        self.selected_index = tk.IntVar(master=self, value=0)
        self.tile_preview_value = tk.BooleanVar(master=self, value=False)
        self._images: list[Image.Image] = []
        self._photos: list[ImageTk.PhotoImage] = []
        self._image_labels: list[ttk.Label] = []

        self.title("Pilih Variasi BatikBrew")
        self.geometry("980x780")
        self.minsize(820, 650)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(
            body,
            text="Pilih hasil generasi BatikBrew",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=(
                "Setiap gambar dibuat oleh SDXL + LoRA dengan seed berbeda. "
                "Objek canvas hanya menjadi sumber inspirasi warna, tema, dan kepadatan garis."
            ),
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 10))

        gallery = ttk.Frame(body)
        gallery.grid(row=2, column=0, sticky="nsew")
        for column in range(2):
            gallery.columnconfigure(column, weight=1)
        for row in range(2):
            gallery.rowconfigure(row, weight=1)

        for index, result in enumerate(self.results):
            row, column = divmod(index, 2)
            card = ttk.LabelFrame(gallery, padding=8)
            card.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 6 if column == 0 else 0),
                pady=(0 if row == 0 else 6, 6 if row == 0 else 0),
            )
            card.columnconfigure(0, weight=1)
            card.rowconfigure(0, weight=1)
            with Image.open(BytesIO(result.content)) as source:
                source.load()
                image = source.convert("RGB")
            self._images.append(image)
            photo = self._photo_for(image)
            self._photos.append(photo)
            image_label = ttk.Label(card, image=photo, anchor="center")
            image_label.grid(row=0, column=0, sticky="nsew")
            self._image_labels.append(image_label)

            metadata = result.metadata
            seed = metadata.get("seed", "-")
            palette = ", ".join(str(value) for value in metadata.get("palette_names", [])[:4])
            themes = ", ".join(str(value) for value in metadata.get("theme_keywords", [])[:3])
            ttk.Radiobutton(
                card,
                text=f"Variasi {index + 1} · seed {seed}",
                variable=self.selected_index,
                value=index,
                command=self._refresh_selection,
            ).grid(row=1, column=0, sticky="w", pady=(7, 0))
            ttk.Label(
                card,
                text=f"Palet: {palette or '-'}\nTema: {themes or '-'}",
                style="Muted.TLabel",
                wraplength=400,
                justify="left",
            ).grid(row=2, column=0, sticky="ew", pady=(3, 0))
            image_label.bind(
                "<Button-1>",
                lambda _event, value=index: self._select(value),
            )

        footer = ttk.Frame(body)
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Checkbutton(
            footer,
            text="Tampilkan preview pengulangan 3 × 3",
            variable=self.tile_preview_value,
            command=self._refresh_previews,
        ).pack(side="left")
        actions = ttk.Frame(footer)
        actions.pack(side="right")
        ttk.Button(actions, text="Batal", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Gunakan Variasi", command=self._accept).pack(side="right")
        self._refresh_selection()

    def _photo_for(self, image: Image.Image) -> ImageTk.PhotoImage:
        preview = image.copy()
        preview.thumbnail((405, 285), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(preview, master=self)

    def _select(self, index: int) -> None:
        self.selected_index.set(index)
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        selected = int(self.selected_index.get())
        for index, label in enumerate(self._image_labels):
            label.configure(cursor="hand2" if index != selected else "arrow")

    def _refresh_previews(self) -> None:
        show_tiles = bool(self.tile_preview_value.get())
        self._photos.clear()
        for image, label in zip(self._images, self._image_labels, strict=True):
            preview = create_tile_preview(image, (3, 3)) if show_tiles else image
            photo = self._photo_for(preview)
            self._photos.append(photo)
            label.configure(image=photo)

    def _accept(self) -> None:
        index = max(0, min(int(self.selected_index.get()), len(self.results) - 1))
        self.result = self.results[index]
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["BatikBrewVariationDialog"]
