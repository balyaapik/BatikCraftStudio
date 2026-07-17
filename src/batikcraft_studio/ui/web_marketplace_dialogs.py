"""Tkinter dialogs for BatikCraftWeb login, NFT market, and model market."""

from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from batikcraft_studio.ai.model_pack import OfflineModelLibrary
from batikcraft_studio.web_bridge import (
    BatikCraftWebClient,
    BatikCraftWebError,
    WebSession,
)


class WebLoginDialog(tk.Toplevel):
    """Authenticate the desktop app against BatikCraftWeb."""

    def __init__(self, parent: tk.Misc, client: BatikCraftWebClient) -> None:
        super().__init__(parent)
        self.client = client
        self.result: WebSession | None = None
        self.url_value = tk.StringVar(master=self, value=client.base_url)
        self.username_value = tk.StringVar(master=self)
        self.password_value = tk.StringVar(master=self)
        self.status_value = tk.StringVar(master=self, value="Masuk dengan akun BatikCraftWeb.")

        self.title("Login BatikCraftWeb")
        self.geometry("560x330")
        self.minsize(500, 300)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Hubungkan BatikCraft Studio",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text=(
                "Login ini menghubungkan profil, NFT, model, pembelian, dan library "
                "desktop dengan BatikCraftWeb."
            ),
            style="Muted.TLabel",
            wraplength=510,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 14))

        self._entry(body, 2, "URL Web", self.url_value)
        username_entry = self._entry(body, 3, "Username", self.username_value)
        password_entry = self._entry(
            body,
            4,
            "Password",
            self.password_value,
            show="•",
        )
        password_entry.bind("<Return>", lambda _event: self._login())

        ttk.Label(
            body,
            textvariable=self.status_value,
            style="Muted.TLabel",
            wraplength=510,
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        actions = ttk.Frame(body)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Batal", command=self._cancel).pack(
            side="right",
            padx=(8, 0),
        )
        self.login_button = ttk.Button(
            actions,
            text="Login",
            command=self._login,
        )
        self.login_button.pack(side="right")

        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()
        username_entry.focus_set()

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        *,
        show: str = "",
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=5,
        )
        entry = ttk.Entry(parent, textvariable=variable, show=show)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        return entry

    def _login(self) -> None:
        username = self.username_value.get().strip()
        password = self.password_value.get()
        if not username or not password:
            messagebox.showerror(
                "Login tidak lengkap",
                "Username dan password wajib diisi.",
                parent=self,
            )
            return
        self.client.base_url = self.url_value.get().strip().rstrip("/")
        self.login_button.configure(state="disabled")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            self.result = self.client.login(username, password)
        except BatikCraftWebError as exc:
            self.status_value.set(str(exc))
            messagebox.showerror("Login gagal", str(exc), parent=self)
            self.login_button.configure(state="normal")
            self.configure(cursor="")
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class WebAccountWindow(tk.Toplevel):
    """Show the connected account and allow logout."""

    def __init__(
        self,
        parent: tk.Misc,
        client: BatikCraftWebClient,
        session: WebSession,
        *,
        on_logout: callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.session = session
        self.on_logout = on_logout
        self.title("Akun BatikCraftWeb")
        self.geometry("520x300")
        self.transient(parent.winfo_toplevel())

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=session.account.public_name,
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=f"@{session.account.username} · {session.account.role}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 14))
        ttk.Label(body, text=f"Email: {session.account.email or '-'}").pack(anchor="w")
        ttk.Label(body, text=f"Web: {session.base_url}").pack(anchor="w", pady=(4, 0))
        ttk.Label(
            body,
            text=(
                "Akun ini dipakai untuk upload NFT, menjual model, bidding, membeli "
                "model, dan menyinkronkan library."
            ),
            wraplength=470,
            justify="left",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(16, 16))
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Tutup", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Logout", command=self._logout).pack(
            side="right",
            padx=(0, 8),
        )

    def _logout(self) -> None:
        if not messagebox.askyesno(
            "Logout",
            "Putuskan BatikCraft Studio dari akun web ini?",
            parent=self,
        ):
            return
        self.client.logout()
        if self.on_logout is not None:
            self.on_logout()
        self.destroy()


class WebMarketplaceWindow(tk.Toplevel):
    """Browse NFT auctions, buy models, and install purchased model packs."""

    def __init__(
        self,
        parent: tk.Misc,
        client: BatikCraftWebClient,
        *,
        initial_tab: str = "nfts",
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.nft_rows: dict[str, dict[str, object]] = {}
        self.model_rows: dict[str, dict[str, object]] = {}
        self.library_rows: dict[str, dict[str, object]] = {}

        self.title("BatikCraft Marketplace")
        self.geometry("980x620")
        self.minsize(820, 520)
        self.transient(parent.winfo_toplevel())

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        account = client.me()
        ttk.Label(
            body,
            text=f"Terhubung sebagai {account.public_name} · {account.role}",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        notebook = ttk.Notebook(body)
        notebook.grid(row=1, column=0, sticky="nsew")
        self.nft_tab = self._build_nft_tab(notebook)
        self.model_tab = self._build_model_tab(notebook)
        self.library_tab = self._build_library_tab(notebook)
        notebook.add(self.nft_tab, text="NFT Market")
        notebook.add(self.model_tab, text="Model Market")
        notebook.add(self.library_tab, text="Library Model")
        tab_map = {
            "nfts": self.nft_tab,
            "models": self.model_tab,
            "library": self.library_tab,
        }
        notebook.select(tab_map.get(initial_tab, self.nft_tab))

        self.refresh_all()

    def _build_nft_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(notebook, padding=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.nft_tree = ttk.Treeview(
            frame,
            columns=("creator", "price", "bids", "status"),
            show="tree headings",
        )
        self.nft_tree.heading("#0", text="Motif NFT")
        self.nft_tree.heading("creator", text="Creator")
        self.nft_tree.heading("price", text="Harga saat ini")
        self.nft_tree.heading("bids", text="Bid")
        self.nft_tree.heading("status", text="Auction")
        self.nft_tree.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_nfts).pack(side="left")
        ttk.Button(actions, text="Bid NFT…", command=self._bid_selected).pack(
            side="left",
            padx=(8, 0),
        )
        return frame

    def _build_model_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(notebook, padding=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.model_tree = ttk.Treeview(
            frame,
            columns=("seller", "base", "version", "price", "owned"),
            show="tree headings",
        )
        self.model_tree.heading("#0", text="Model")
        self.model_tree.heading("seller", text="Seller")
        self.model_tree.heading("base", text="Base")
        self.model_tree.heading("version", text="Versi")
        self.model_tree.heading("price", text="Harga")
        self.model_tree.heading("owned", text="Milik")
        self.model_tree.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_models).pack(side="left")
        ttk.Button(actions, text="Beli Model", command=self._purchase_selected).pack(
            side="left",
            padx=(8, 0),
        )
        return frame

    def _build_library_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(notebook, padding=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.library_tree = ttk.Treeview(
            frame,
            columns=("seller", "base", "version", "downloads"),
            show="tree headings",
        )
        self.library_tree.heading("#0", text="Model Dibeli")
        self.library_tree.heading("seller", text="Seller")
        self.library_tree.heading("base", text="Base")
        self.library_tree.heading("version", text="Versi")
        self.library_tree.heading("downloads", text="Download")
        self.library_tree.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_library).pack(side="left")
        ttk.Button(
            actions,
            text="Download & Install",
            command=self._install_selected,
        ).pack(side="left", padx=(8, 0))
        return frame

    def refresh_all(self) -> None:
        self.refresh_nfts()
        self.refresh_models()
        self.refresh_library()

    def refresh_nfts(self) -> None:
        try:
            items = self.client.list_nfts()
        except BatikCraftWebError as exc:
            self._show_error(exc)
            return
        self._clear(self.nft_tree)
        self.nft_rows.clear()
        for item in items:
            iid = str(item["id"])
            self.nft_rows[iid] = item
            self.nft_tree.insert(
                "",
                "end",
                iid=iid,
                text=str(item.get("title") or f"NFT {iid}"),
                values=(
                    item.get("owner_name", ""),
                    _rupiah(item.get("current_price", "0")),
                    item.get("bid_count", 0),
                    "Buka" if item.get("is_auction_open") else "Tutup",
                ),
            )

    def refresh_models(self) -> None:
        try:
            items = self.client.list_models()
        except BatikCraftWebError as exc:
            self._show_error(exc)
            return
        self._clear(self.model_tree)
        self.model_rows.clear()
        for item in items:
            iid = str(item["id"])
            self.model_rows[iid] = item
            self.model_tree.insert(
                "",
                "end",
                iid=iid,
                text=str(item.get("name") or f"Model {iid}"),
                values=(
                    item.get("seller_name", ""),
                    item.get("base_model_family", ""),
                    item.get("version", ""),
                    _rupiah(item.get("price", "0")),
                    "Ya" if item.get("owned") else "Belum",
                ),
            )

    def refresh_library(self) -> None:
        try:
            items = self.client.model_library()
        except BatikCraftWebError as exc:
            self._show_error(exc)
            return
        self._clear(self.library_tree)
        self.library_rows.clear()
        for item in items:
            iid = str(item["id"])
            self.library_rows[iid] = item
            self.library_tree.insert(
                "",
                "end",
                iid=iid,
                text=str(item.get("model_name") or f"Model {iid}"),
                values=(
                    item.get("seller_name", ""),
                    item.get("base_model_family", ""),
                    item.get("version", ""),
                    item.get("download_count", 0),
                ),
            )

    def _bid_selected(self) -> None:
        item = self._selected(self.nft_tree, self.nft_rows)
        if item is None:
            return
        amount = simpledialog.askstring(
            "Bid NFT",
            f"Masukkan bid untuk {item.get('title', 'NFT')}:\n"
            f"Harga saat ini {_rupiah(item.get('current_price', '0'))}",
            parent=self,
        )
        if amount is None:
            return
        try:
            self.client.place_bid(int(item["id"]), amount)
        except (BatikCraftWebError, ValueError) as exc:
            self._show_error(exc)
            return
        messagebox.showinfo("Bid NFT", "Bid berhasil dikirim.", parent=self)
        self.refresh_nfts()

    def _purchase_selected(self) -> None:
        item = self._selected(self.model_tree, self.model_rows)
        if item is None:
            return
        if item.get("owned"):
            messagebox.showinfo(
                "Model sudah dimiliki",
                "Model ini sudah ada di library akunmu.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Beli model",
            f"Beli {item.get('name')} seharga {_rupiah(item.get('price', '0'))}?",
            parent=self,
        ):
            return
        try:
            self.client.purchase_model(int(item["id"]))
        except BatikCraftWebError as exc:
            self._show_error(exc)
            return
        messagebox.showinfo(
            "Pembelian berhasil",
            "Model telah ditambahkan ke library akunmu.",
            parent=self,
        )
        self.refresh_models()
        self.refresh_library()

    def _install_selected(self) -> None:
        purchase = self._selected(self.library_tree, self.library_rows)
        if purchase is None:
            return
        model_id = int(purchase["model"])
        try:
            with tempfile.TemporaryDirectory(prefix="batikcraft-model-") as temp:
                target = self.client.download_model(model_id, Path(temp))
                installed = OfflineModelLibrary().install(target, replace=True)
        except (BatikCraftWebError, OSError, RuntimeError) as exc:
            self._show_error(exc)
            return
        messagebox.showinfo(
            "Model terpasang",
            f"{installed.manifest.name} berhasil dipasang ke library lokal.",
            parent=self,
        )
        self.refresh_library()

    def _selected(
        self,
        tree: ttk.Treeview,
        rows: dict[str, dict[str, object]],
    ) -> dict[str, object] | None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(
                "Pilih item",
                "Pilih satu item terlebih dahulu.",
                parent=self,
            )
            return None
        return rows.get(selection[0])

    def _show_error(self, error: object) -> None:
        messagebox.showerror("BatikCraftWeb", str(error), parent=self)

    @staticmethod
    def _clear(tree: ttk.Treeview) -> None:
        for iid in tree.get_children(""):
            tree.delete(iid)


class PublishNFTDialog(tk.Toplevel):
    """Upload a verified .batikcraftnft package and publish its auction."""

    def __init__(self, parent: tk.Misc, client: BatikCraftWebClient) -> None:
        super().__init__(parent)
        self.client = client
        self.path_value = tk.StringVar(master=self)
        self.price_value = tk.StringVar(master=self, value="100000")
        self.ends_value = tk.StringVar(master=self)
        self.title("Publish Motif sebagai NFT")
        self.geometry("680x330")
        self.transient(parent.winfo_toplevel())
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(
            body,
            text="Upload Motif NFT ke BatikCraftWeb",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text=(
                "Gunakan paket .batikcraftnft yang sudah berisi preview, metadata, "
                "project ID, checksum, dan lisensi."
            ),
            style="Muted.TLabel",
            wraplength=630,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 14))
        ttk.Label(body, text="Paket NFT").grid(row=2, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.path_value).grid(
            row=2,
            column=1,
            sticky="ew",
            padx=(8, 8),
        )
        ttk.Button(body, text="Pilih…", command=self._choose).grid(row=2, column=2)
        ttk.Label(body, text="Harga awal").grid(row=3, column=0, sticky="w", pady=8)
        ttk.Entry(body, textvariable=self.price_value).grid(
            row=3,
            column=1,
            sticky="ew",
            padx=(8, 8),
            pady=8,
        )
        ttk.Label(body, text="Auction berakhir (ISO, opsional)").grid(
            row=4,
            column=0,
            sticky="w",
        )
        ttk.Entry(body, textvariable=self.ends_value).grid(
            row=4,
            column=1,
            sticky="ew",
            padx=(8, 8),
        )
        actions = ttk.Frame(body)
        actions.grid(row=5, column=0, columnspan=3, sticky="e", pady=(18, 0))
        ttk.Button(actions, text="Batal", command=self.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Upload & Publish", command=self._publish).pack(
            side="right"
        )

    def _choose(self) -> None:
        value = filedialog.askopenfilename(
            parent=self,
            filetypes=[("BatikCraft NFT", "*.batikcraftnft")],
        )
        if value:
            self.path_value.set(value)

    def _publish(self) -> None:
        try:
            item = self.client.publish_nft_package(
                self.path_value.get(),
                starting_price=self.price_value.get(),
                auction_ends_at=self.ends_value.get(),
            )
        except (BatikCraftWebError, OSError, ValueError) as exc:
            messagebox.showerror("Publish NFT gagal", str(exc), parent=self)
            return
        messagebox.showinfo(
            "NFT dipublikasikan",
            f"{item.get('title', 'Motif')} sekarang tampil di NFT Market.",
            parent=self,
        )
        self.destroy()


class PublishModelDialog(tk.Toplevel):
    """Upload one .batikmodel pack, set its price, and publish it."""

    def __init__(self, parent: tk.Misc, client: BatikCraftWebClient) -> None:
        super().__init__(parent)
        self.client = client
        self.model_value = tk.StringVar(master=self)
        self.preview_value = tk.StringVar(master=self)
        self.price_value = tk.StringVar(master=self, value="75000")
        self.category_value = tk.StringVar(master=self, value="ornament")
        self.license_value = tk.StringVar(master=self, value="personal")
        self.commercial_value = tk.BooleanVar(master=self, value=False)
        self.title("Publish Model ke Marketplace")
        self.geometry("720x440")
        self.transient(parent.winfo_toplevel())
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(
            body,
            text="Jual Model BatikCraft",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            body,
            text="Metadata nama, versi, base model, trigger words, dan capability dibaca dari manifest .batikmodel.",
            style="Muted.TLabel",
            wraplength=670,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 14))
        self._file_row(body, 2, "Model", self.model_value, "*.batikmodel")
        self._file_row(body, 3, "Preview", self.preview_value, "*.png *.jpg *.jpeg *.webp")
        self._entry_row(body, 4, "Harga", self.price_value)
        self._entry_row(body, 5, "Kategori", self.category_value)
        ttk.Label(body, text="Lisensi").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Combobox(
            body,
            textvariable=self.license_value,
            values=("personal", "commercial", "extended"),
            state="readonly",
        ).grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(
            body,
            text="Izinkan penggunaan komersial",
            variable=self.commercial_value,
        ).grid(row=7, column=1, sticky="w", pady=5)
        ttk.Label(body, text="Deskripsi").grid(row=8, column=0, sticky="nw", pady=5)
        self.description_text = tk.Text(body, height=5, wrap="word")
        self.description_text.grid(row=8, column=1, columnspan=2, sticky="ew", pady=5)
        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="Batal", command=self.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        ttk.Button(actions, text="Upload & Publish", command=self._publish).pack(
            side="right"
        )

    def _entry_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=5,
        )

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        pattern: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=5,
        )
        ttk.Button(
            parent,
            text="Pilih…",
            command=lambda: self._choose(variable, pattern),
        ).grid(row=row, column=2, pady=5)

    def _choose(self, variable: tk.StringVar, pattern: str) -> None:
        value = filedialog.askopenfilename(
            parent=self,
            filetypes=[("File", pattern), ("Semua file", "*.*")],
        )
        if value:
            variable.set(value)

    def _publish(self) -> None:
        try:
            item = self.client.publish_model_pack(
                self.model_value.get(),
                preview_path=self.preview_value.get() or None,
                price=self.price_value.get(),
                description=self.description_text.get("1.0", "end").strip(),
                category=self.category_value.get(),
                license_type=self.license_value.get(),
                commercial_use=bool(self.commercial_value.get()),
            )
        except (BatikCraftWebError, OSError, ValueError) as exc:
            messagebox.showerror("Publish model gagal", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Model dipublikasikan",
            f"{item.get('name', 'Model')} sekarang tampil di Model Market.",
            parent=self,
        )
        self.destroy()


def _rupiah(value: object) -> str:
    try:
        amount = float(str(value))
    except (TypeError, ValueError):
        return f"Rp{value}"
    return f"Rp{amount:,.0f}".replace(",", ".")


__all__ = [
    "PublishModelDialog",
    "PublishNFTDialog",
    "WebAccountWindow",
    "WebLoginDialog",
    "WebMarketplaceWindow",
]
