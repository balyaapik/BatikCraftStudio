"""Create, seal, and publish the current project as an NFT marketplace item."""

from __future__ import annotations

import re
import tempfile
import tkinter as tk
import webbrowser
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from batikcraft_studio.auction_time import (
    SYSTEM_LOCAL_TIMEZONE,
    available_timezones_sorted,
    system_timezone_name,
    timezone_database_missing,
)
from batikcraft_studio.domain import Project
from batikcraft_studio.imaging import ProjectRenderError
from batikcraft_studio.persistence import BatikNFTError, NFTExportMetadata, export_batikcraft_nft
from batikcraft_studio.project_export import (
    discover_project_colors,
    discover_project_motifs,
    render_project_jpeg,
)
from batikcraft_studio.ui.listing_fee_prompt import handle_listing_fee_required
from batikcraft_studio.web_bridge import (
    BatikCraftWebClient,
    BatikCraftWebError,
    ListingFeeRequiredError,
    WebSession,
    normalize_auction_deadline,
)


def _preferred_timezone() -> str:
    from batikcraft_studio.auction_time import TimezonePreference

    try:
        return TimezonePreference().load()
    except OSError:
        return system_timezone_name()


def _default_deadline(timezone_name: str) -> str:
    for candidate in (timezone_name, "Asia/Jakarta"):
        try:
            zone = ZoneInfo(candidate)
        except (KeyError, ValueError):
            continue
        return (datetime.now(zone) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    # Instalasi lama mungkin belum memiliki tzdata. Jam lokal sistem tetap
    # menyediakan offset yang cukup untuk membuat deadline ISO-8601 yang tegas.
    return (datetime.now().astimezone() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")


def _listing_fee_nft_id(error: ListingFeeRequiredError) -> int | None:
    """Ambil draft NFT dari payload baru atau checkout URL server lama."""
    raw = error.fee.get("nft_id")
    try:
        nft_id = int(raw)
    except (TypeError, ValueError):
        nft_id = 0
    if nft_id > 0:
        return nft_id
    match = re.search(r"/nfts/(\d+)/listing-fee(?:/|$)", error.checkout_url)
    return int(match.group(1)) if match else None


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
        self._pending_nft_id: int | None = None

        preferred_timezone = _preferred_timezone()
        self.price_value = tk.StringVar(master=self, value="100000")
        self.reserve_value = tk.StringVar(master=self, value="")
        self.ends_value = tk.StringVar(
            master=self,
            value=_default_deadline(preferred_timezone),
        )
        self.timezone_value = tk.StringVar(master=self, value=preferred_timezone)
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
        self.geometry("780x700")
        self.minsize(700, 640)
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
                "mengunggah preview dan metadata ke BatikCraftWeb. Atur harga, reserve "
                "price, dan batas akhir agar lelang selalu dapat diselesaikan."
            ),
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 14))

        self._readonly_row(body, 2, "Project", self.project.metadata.title)
        self._readonly_row(body, 3, "Creator", self.session.account.public_name)
        self._entry_row(body, 4, "Motif", self.motifs_value)
        self._entry_row(body, 5, "Warna dominan", self.colors_value)
        self._entry_row(body, 6, "Lisensi", self.license_value)
        self._entry_row(body, 7, "Harga awal", self.price_value)
        self._entry_row(body, 8, "Reserve price (opsional)", self.reserve_value)
        self._entry_row(
            body,
            9,
            "Auction berakhir (mis. 2026-08-01 17:00)",
            self.ends_value,
        )
        self._timezone_row(body, 10, self.timezone_value)

        ttk.Label(body, text="Filosofi / deskripsi").grid(
            row=11,
            column=0,
            sticky="nw",
            pady=5,
        )
        self.philosophy_text = tk.Text(body, height=8, wrap="word")
        self.philosophy_text.grid(row=11, column=1, sticky="ew", pady=5)
        self.philosophy_text.insert("1.0", self.project.metadata.description)

        ttk.Label(
            body,
            text=(
                "Catatan: package seal mengikat preview dan project. Kepemilikan "
                "marketplace diterbitkan setelah buyer membayar dan transaksi diverifikasi."
            ),
            style="Muted.TLabel",
            wraplength=720,
            justify="left",
        ).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=720,
        ).grid(row=13, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        actions = ttk.Frame(body)
        actions.grid(row=14, column=0, columnspan=2, sticky="e", pady=(12, 0))
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
    def _timezone_row(parent: ttk.Frame, row: int, variable: tk.StringVar) -> None:
        timezones = available_timezones_sorted()
        missing_database = timezone_database_missing() or not timezones
        if missing_database:
            variable.set(SYSTEM_LOCAL_TIMEZONE)
            timezones = [SYSTEM_LOCAL_TIMEZONE]
        label = (
            "Zona waktu batas lelang (jam lokal sistem)"
            if missing_database
            else "Zona waktu batas lelang"
        )
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=timezones,
            state="readonly",
        )
        combo.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=5)

    def _remember_timezone(self) -> None:
        from batikcraft_studio.auction_time import AuctionTimeError, TimezonePreference

        try:
            TimezonePreference().save(self.timezone_value.get())
        except (AuctionTimeError, OSError):
            pass

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

    def _restore_button(self) -> None:
        self.mint_button.configure(state="normal")
        self.configure(cursor="")

    def _mint(self) -> None:
        self.mint_button.configure(state="disabled")
        self.configure(cursor="watch")

        if self._pending_nft_id is not None:
            self.status_value.set(
                f"Mencoba mempublikasikan kembali draft NFT #{self._pending_nft_id}…"
            )
            self.update_idletasks()
            try:
                item = self.client._request_json(  # noqa: SLF001 - retry draft API
                    "POST",
                    f"nfts/{self._pending_nft_id}/publish/",
                    payload={},
                )
            except ListingFeeRequiredError as exc:
                self._restore_button()
                self.status_value.set(exc.detail)
                handle_listing_fee_required(self, exc)
                return
            except BatikCraftWebError as exc:
                self._restore_button()
                self.status_value.set(str(exc))
                messagebox.showerror("Mint NFT gagal", str(exc), parent=self)
                return
            self._pending_nft_id = None
            self._mint_done(item)
            return

        philosophy = self.philosophy_text.get("1.0", "end").strip()
        if not philosophy:
            self._restore_button()
            messagebox.showerror(
                "Filosofi diperlukan",
                "Isi filosofi atau deskripsi motif sebelum minting.",
                parent=self,
            )
            return
        try:
            price = float(self.price_value.get())
        except ValueError:
            self._restore_button()
            messagebox.showerror(
                "Harga tidak valid",
                "Harga awal harus berupa angka.",
                parent=self,
            )
            return
        if price <= 0:
            self._restore_button()
            messagebox.showerror(
                "Harga tidak valid",
                "Harga awal harus lebih dari nol.",
                parent=self,
            )
            return

        reserve_text = self.reserve_value.get().strip()
        try:
            reserve = float(reserve_text) if reserve_text else None
        except ValueError:
            self._restore_button()
            messagebox.showerror(
                "Reserve price tidak valid",
                "Reserve price harus berupa angka atau dikosongkan.",
                parent=self,
            )
            return
        if reserve is not None and reserve < price:
            self._restore_button()
            messagebox.showerror(
                "Reserve price tidak valid",
                "Reserve price tidak boleh lebih rendah dari harga awal.",
                parent=self,
            )
            return
        if not self.ends_value.get().strip():
            self._restore_button()
            messagebox.showerror(
                "Batas lelang diperlukan",
                "Isi waktu berakhir lelang agar pemenang dapat ditagih.",
                parent=self,
            )
            return

        self.status_value.set("Membuat package ID, checksum, preview, dan listing NFT…")
        self.update_idletasks()
        try:
            deadline = normalize_auction_deadline(
                self.ends_value.get(), self.timezone_value.get()
            )
            if not deadline:
                raise BatikCraftWebError("Batas akhir lelang wajib diisi.")
            self._remember_timezone()
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
                    reserve_price=reserve_text,
                    auction_ends_at=deadline,
                )
        except ListingFeeRequiredError as exc:
            pending_nft_id = _listing_fee_nft_id(exc)
            if pending_nft_id is not None:
                self._pending_nft_id = pending_nft_id
                self.mint_button.configure(text="Cek Pembayaran & Publish")
            self._restore_button()
            self.status_value.set(exc.detail)
            handle_listing_fee_required(self, exc)
            return
        except (
            BatikNFTError,
            BatikCraftWebError,
            OSError,
            ProjectRenderError,
            ValueError,
        ) as exc:
            self._restore_button()
            self.status_value.set(str(exc))
            messagebox.showerror("Mint NFT gagal", str(exc), parent=self)
            return
        self._mint_done(item)

    def _mint_done(self, item: Mapping[str, object]) -> None:
        open_dashboard = messagebox.askyesno(
            "NFT dipublikasikan",
            (
                f"{item.get('title', self.project.metadata.title)} sekarang tampil di "
                "NFT Market.\n\nBuka Dashboard Creator untuk memantau bid dan payout?"
            ),
            parent=self,
        )
        if open_dashboard:
            webbrowser.open(f"{self.session.base_url.rstrip('/')}/dashboard/creator/", new=2)
        self.destroy()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


__all__ = ["MintCurrentProjectDialog"]
