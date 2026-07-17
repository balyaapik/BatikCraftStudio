"""Publish one selected library asset as an NFT marketplace listing."""

from __future__ import annotations

import hashlib
import json
import tkinter as tk
from io import BytesIO
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from batikcraft_studio.config import APP_VERSION
from batikcraft_studio.domain import LayerObject, Project
from batikcraft_studio.imaging.raster import normalize_raster_image
from batikcraft_studio.web_bridge import BatikCraftWebClient, BatikCraftWebError, WebSession


class PublishLibraryAssetNFTDialog(tk.Toplevel):
    """Sell the current object from the Studio asset library as an NFT."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        client: BatikCraftWebClient,
        session: WebSession,
        project: Project,
        item: LayerObject,
        content: bytes,
    ) -> None:
        super().__init__(parent)
        raster = normalize_raster_image(content)
        self.client = client
        self.session = session
        self.project = project
        self.item = item
        self.content = raster.content
        self.checksum = hashlib.sha256(self.content).hexdigest()

        self.title_value = tk.StringVar(master=self, value=item.name)
        self.price_value = tk.StringVar(master=self, value="50000")
        self.ends_value = tk.StringVar(master=self)
        self.license_value = tk.StringVar(master=self, value="Personal display license")
        self.status_value = tk.StringVar(
            master=self,
            value="Asset aktif akan diunggah sebagai listing NFT terpisah.",
        )
        self._photo: ImageTk.PhotoImage | None = None

        self.title("Marketplace — Jual Asset Pustaka sebagai NFT")
        self.geometry("760x650")
        self.minsize(680, 580)
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
            text="Jual Asset Pustaka sebagai NFT",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text=(
                "Objek yang sedang aktif di canvas akan menjadi item NFT tersendiri. "
                "File project penuh tidak ikut diunggah."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        preview_frame = ttk.LabelFrame(body, text="Preview Asset", padding=8)
        preview_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        with Image.open(BytesIO(self.content)) as source:
            source.load()
            preview = source.convert("RGBA")
        preview.thumbnail((360, 220), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(preview, master=self)
        ttk.Label(preview_frame, image=self._photo).pack()

        self._entry_row(body, 3, "Judul", self.title_value)
        self._entry_row(body, 4, "Harga awal", self.price_value)
        self._entry_row(body, 5, "Auction berakhir (ISO, opsional)", self.ends_value)
        self._entry_row(body, 6, "Lisensi", self.license_value)

        ttk.Label(body, text="Deskripsi / filosofi").grid(
            row=7,
            column=0,
            sticky="nw",
            pady=5,
        )
        self.description_text = tk.Text(body, height=7, wrap="word")
        self.description_text.grid(row=7, column=1, sticky="ew", padx=(10, 0), pady=5)
        self.description_text.insert(
            "1.0",
            str(self.item.properties.get("description") or self.project.metadata.description),
        )

        category = str(self.item.properties.get("asset_category") or "ornamen")
        ttk.Label(
            body,
            text=(
                f"Kategori: {category} · Object ID: {self.item.object_id}\n"
                f"SHA-256: {self.checksum[:24]}…"
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        actions = ttk.Frame(body)
        actions.grid(row=10, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Batal", command=self.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        self.publish_button = ttk.Button(
            actions,
            text="Upload & Publish NFT",
            command=self._publish,
        )
        self.publish_button.pack(side="right")

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

    def _publish(self) -> None:
        title = self.title_value.get().strip()
        if not title:
            messagebox.showerror("Judul diperlukan", "Isi judul asset NFT.", parent=self)
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

        self.publish_button.configure(state="disabled")
        self.configure(cursor="watch")
        self.status_value.set("Mengunggah asset, metadata, checksum, dan listing NFT…")
        self.update_idletasks()
        try:
            item = publish_library_asset_nft(
                self.client,
                project=self.project,
                asset=self.item,
                content=self.content,
                title=title,
                description=self.description_text.get("1.0", "end").strip(),
                starting_price=self.price_value.get(),
                auction_ends_at=self.ends_value.get(),
                license_name=self.license_value.get(),
            )
        except (BatikCraftWebError, OSError, TypeError, ValueError) as exc:
            self.publish_button.configure(state="normal")
            self.configure(cursor="")
            self.status_value.set(str(exc))
            messagebox.showerror("Publish asset NFT gagal", str(exc), parent=self)
            return

        messagebox.showinfo(
            "Asset NFT dipublikasikan",
            f"{item.get('title', title)} sekarang tampil di NFT Marketplace.",
            parent=self,
        )
        self.destroy()


def publish_library_asset_nft(
    client: BatikCraftWebClient,
    *,
    project: Project,
    asset: LayerObject,
    content: bytes,
    title: str,
    description: str,
    starting_price: str,
    auction_ends_at: str = "",
    license_name: str = "Personal display license",
) -> dict[str, object]:
    """Upload and publish one raster asset through the existing NFT API."""

    raster = normalize_raster_image(content)
    checksum = hashlib.sha256(raster.content).hexdigest()
    source_id = f"asset-{project.project_id}-{asset.object_id}-{checksum[:12]}"[:128]
    category = str(asset.properties.get("asset_category") or "ornamen")
    fields = {
        "title": title.strip() or asset.name,
        "description": description.strip(),
        "source_project_id": source_id,
        "source_app_version": APP_VERSION,
        "starting_price": str(starting_price),
        "metadata": json.dumps(
            {
                "source_type": "library_asset",
                "project_id": project.project_id,
                "object_id": asset.object_id,
                "object_kind": str(asset.kind.value),
                "asset_category": category,
                "asset_name": asset.name,
                "license": license_name.strip(),
                "sha256": checksum,
                "width": raster.width,
                "height": raster.height,
            },
            ensure_ascii=False,
        ),
    }
    if auction_ends_at.strip():
        fields["auction_ends_at"] = auction_ends_at.strip()
    created = client._request_multipart(
        "POST",
        "nfts/",
        fields=fields,
        files={
            "image": (
                f"{asset.object_id}.png",
                raster.content,
                "image/png",
            )
        },
    )
    nft_id = int(created["id"])
    return client._request_json("POST", f"nfts/{nft_id}/publish/", payload={})


__all__ = ["PublishLibraryAssetNFTDialog", "publish_library_asset_nft"]
