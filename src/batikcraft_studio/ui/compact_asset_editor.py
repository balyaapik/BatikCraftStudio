"""Asset-first editor with permanent library/tree panes and transient tool windows."""

from __future__ import annotations

import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk, UnidentifiedImageError

from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.assets import (
    ASSET_PACK_EXTENSION,
    AssetLibrary,
    AssetLibraryError,
    AssetRecord,
)
from batikcraft_studio.imaging import ASSET_CATEGORIES, BatikAssetError, load_batik_asset

from .professional_object_tree_editor import ProfessionalObjectTreeEditorWorkspaceView
from .theme import COLORS
from .tool_windows import EditorToolWindows
from .widgets import icon_button

_ALL_PACKS = "Semua paket"
_ALL_CATEGORIES = "Semua kategori"
_MAX_VISIBLE_RESULTS = 5_000


class CompactAssetEditorWorkspaceView(ProfessionalObjectTreeEditorWorkspaceView):
    """Keep only library, canvas, and object tree visible in the main workspace."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.asset_library = AssetLibrary()
        self.library_query_value = tk.StringVar(master=parent)
        self.library_category_value = tk.StringVar(master=parent, value=_ALL_CATEGORIES)
        self.library_pack_value = tk.StringVar(master=parent, value=_ALL_PACKS)
        self.library_summary_value = tk.StringVar(master=parent)
        self.library_asset_name_value = tk.StringVar(master=parent, value="Pilih asset")
        self.library_asset_meta_value = tk.StringVar(master=parent, value="")
        self._library_records: dict[str, AssetRecord] = {}
        self._library_pack_lookup: dict[str, str] = {}
        self._library_preview_photo: ImageTk.PhotoImage | None = None
        super().__init__(*args, **kwargs)
        self.tool_windows = EditorToolWindows(self)
        self.library_query_value.trace_add("write", lambda *_args: self.refresh_library())
        self.library_category_value.trace_add("write", lambda *_args: self.refresh_library())
        self.library_pack_value.trace_add("write", lambda *_args: self.refresh_library())
        self._bind_compact_shortcuts()
        self.refresh_library()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=0, column=0, sticky="nsew")

        library = ttk.Frame(body, style="Dock.TFrame", width=310, padding=(8, 8))
        library.grid_propagate(False)
        library.columnconfigure(0, weight=1)
        library.rowconfigure(4, weight=1)
        self._build_library_panel(library)
        body.add(library, weight=1)

        canvas_shell = ttk.Frame(body, style="App.TFrame")
        canvas_shell.columnconfigure(0, weight=1)
        canvas_shell.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            canvas_shell,
            background=COLORS["canvas"],
            highlightthickness=0,
            borderwidth=0,
            cursor="arrow",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._schedule_render())
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        ttk.Label(
            canvas_shell,
            textvariable=self.canvas_caption,
            style="Status.TLabel",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew")
        body.add(canvas_shell, weight=5)

        layers = ttk.Frame(body, style="Dock.TFrame", width=300, padding=(8, 8))
        layers.grid_propagate(False)
        layers.columnconfigure(0, weight=1)
        layers.rowconfigure(1, weight=1)
        self._build_layer_panel(layers)
        body.add(layers, weight=1)

    def _build_library_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Dock.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Pustaka Asset", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(
            header,
            textvariable=self.library_summary_value,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(1, 0))

        filters = ttk.Frame(parent, style="Dock.TFrame")
        filters.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        filters.columnconfigure(0, weight=1)
        ttk.Entry(filters, textvariable=self.library_query_value).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.library_pack_combo = ttk.Combobox(
            filters,
            textvariable=self.library_pack_value,
            state="readonly",
        )
        self.library_pack_combo.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Combobox(
            filters,
            textvariable=self.library_category_value,
            values=(_ALL_CATEGORIES, *ASSET_CATEGORIES),
            state="readonly",
            width=15,
        ).grid(row=1, column=1, sticky="ew")

        preview = ttk.Frame(parent, style="Surface.TFrame", padding=(7, 7))
        preview.grid(row=2, column=0, sticky="ew", pady=(4, 5))
        preview.columnconfigure(1, weight=1)
        self.library_preview_label = ttk.Label(preview, style="Muted.TLabel", anchor="center")
        self.library_preview_label.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        ttk.Label(
            preview,
            textvariable=self.library_asset_name_value,
            style="ProjectTitle.TLabel",
            wraplength=160,
            justify="left",
        ).grid(row=0, column=1, sticky="sw")
        ttk.Label(
            preview,
            textvariable=self.library_asset_meta_value,
            style="Muted.TLabel",
            wraplength=160,
            justify="left",
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(2, 5),
        )
        self.library_list = ttk.Treeview(
            parent,
            columns=("category", "pack"),
            show="tree headings",
            selectmode="browse",
            height=18,
        )
        self.library_list.heading("#0", text="Asset")
        self.library_list.heading("category", text="Kategori")
        self.library_list.heading("pack", text="Paket")
        self.library_list.column("#0", width=145, minwidth=90, stretch=True)
        self.library_list.column("category", width=80, minwidth=65, stretch=False)
        self.library_list.column("pack", width=70, minwidth=55, stretch=False)
        self.library_list.grid(row=4, column=0, sticky="nsew")
        self.library_list.bind("<<TreeviewSelect>>", self._on_library_select)
        self.library_list.bind("<Double-1>", lambda _event: self.add_selected_library_asset())

        actions = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        actions.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        for icon, tooltip, command in (
            ("apply", "Tambahkan asset terpilih ke canvas", self.add_selected_library_asset),
            ("import", "Install asset pack", self.install_asset_pack_dialog),
            ("delete", "Hapus asset pack terpilih", self.uninstall_selected_pack),
            ("redo", "Muat ulang pustaka", self.reload_asset_library),
        ):
            icon_button(
                actions,
                icon=icon,
                tooltip=tooltip,
                command=command,
                size=18,
            ).pack(side="left", padx=1)

    def _build_tree_menus(self) -> None:
        """Keep structural and import actions; drawing creation lives in the menu bar."""

        self._new_tree_menu = tk.Menu(self, tearoff=False)
        self._new_tree_menu.add_command(label="Folder", command=self._new_folder)
        self._new_tree_menu.add_command(label="Sublapis Objek", command=self._new_object_layer)
        self._new_tree_menu.add_command(label="Lapis Canting", command=self._new_paint_layer_in_tree)
        self._new_tree_menu.add_separator()
        self._new_tree_menu.add_command(
            label="Tambah dari Pustaka",
            command=self.add_selected_library_asset,
        )
        self._new_tree_menu.add_command(label="Import Asset…", command=self.import_asset_dialog)

        self._tree_context_menu = tk.Menu(self, tearoff=False)
        self._tree_context_menu.add_cascade(label="Baru", menu=self._new_tree_menu)
        self._move_folder_menu = tk.Menu(self._tree_context_menu, tearoff=False)
        self._tree_context_menu.add_cascade(
            label="Pindah ke Folder",
            menu=self._move_folder_menu,
        )
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(label="Duplikat", command=self.duplicate_active)
        self._tree_context_menu.add_command(label="Hapus", command=self.delete_active)
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(
            label="Tampilkan/Sembunyikan",
            command=self.toggle_visibility,
        )
        self._tree_context_menu.add_command(label="Kunci/Buka", command=self.toggle_lock)

    def refresh_library(self) -> None:
        if not hasattr(self, "library_list"):
            return
        pack_display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(pack_display)
        category_display = self.library_category_value.get()
        category = None if category_display == _ALL_CATEGORIES else category_display
        try:
            records = self.asset_library.search(
                self.library_query_value.get(),
                category=category,
                pack_id=pack_id,
                limit=_MAX_VISIBLE_RESULTS,
            )
        except AssetLibraryError as exc:
            self.set_status(str(exc))
            return
        for item in self.library_list.get_children(""):
            self.library_list.delete(item)
        self._library_records.clear()
        pack_names = {pack.pack_id: pack.name for pack in self.asset_library.packs}
        for record in records:
            iid = record.key
            self._library_records[iid] = record
            self.library_list.insert(
                "",
                tk.END,
                iid=iid,
                text=record.name,
                values=(record.category, pack_names.get(record.pack_id, record.pack_id)),
            )
        total = self.asset_library.asset_count
        suffix = "+" if len(records) == _MAX_VISIBLE_RESULTS and total > len(records) else ""
        self.library_summary_value.set(
            f"{len(records)}{suffix} tampil · {total} asset · {len(self.asset_library.packs)} paket"
        )
        self._refresh_pack_combo()

    def _refresh_pack_combo(self) -> None:
        current = self.library_pack_value.get()
        self._library_pack_lookup = {pack.name: pack.pack_id for pack in self.asset_library.packs}
        values = (_ALL_PACKS, *self._library_pack_lookup)
        self.library_pack_combo.configure(values=values)
        if current not in values:
            self.library_pack_value.set(_ALL_PACKS)

    def reload_asset_library(self) -> None:
        self.asset_library.refresh()
        self.refresh_library()
        self.set_status(
            f"Pustaka dimuat ulang: {self.asset_library.asset_count} asset tersedia."
        )

    def install_asset_pack_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Install BatikCraft Asset Pack",
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if not selected:
            return
        replace = False
        try:
            pack = self.asset_library.install_pack(selected)
        except AssetLibraryError as exc:
            if "sudah terpasang" not in str(exc):
                messagebox.showerror(
                    "Install asset pack gagal",
                    str(exc),
                    parent=self.winfo_toplevel(),
                )
                return
            replace = messagebox.askyesno(
                "Ganti asset pack",
                f"{exc}\n\nGanti paket yang sudah terpasang?",
                parent=self.winfo_toplevel(),
            )
            if not replace:
                return
            try:
                pack = self.asset_library.install_pack(selected, replace=True)
            except AssetLibraryError as replace_exc:
                messagebox.showerror(
                    "Install asset pack gagal",
                    str(replace_exc),
                    parent=self.winfo_toplevel(),
                )
                return
        self.refresh_library()
        self.library_pack_value.set(pack.name)
        self.set_status(f"Asset pack terpasang: {pack.name} ({len(pack.assets)} asset).")

    def uninstall_selected_pack(self) -> None:
        display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(display)
        if pack_id is None:
            self.set_status("Pilih satu asset pack pada filter sebelum menghapusnya.")
            return
        pack = self.asset_library.get_pack(pack_id)
        if not messagebox.askyesno(
            "Hapus asset pack",
            f"Hapus '{pack.name}' beserta {len(pack.assets)} asset dari pustaka lokal?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self.asset_library.uninstall_pack(pack_id)
        except AssetLibraryError as exc:
            messagebox.showerror(
                "Hapus asset pack gagal",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.library_pack_value.set(_ALL_PACKS)
        self.refresh_library()
        self.set_status(f"Asset pack dihapus: {pack.name}.")

    def add_selected_library_asset(self) -> None:
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum menambahkan asset.")
            return
        selection = self.library_list.selection()
        if not selection:
            self.set_status("Pilih asset pada Pustaka Asset terlebih dahulu.")
            return
        record = self._library_records.get(selection[0])
        if record is None:
            self.set_status("Asset terpilih tidak lagi tersedia; muat ulang pustaka.")
            return
        try:
            content = self.asset_library.read_asset(record)
            target = self._target_layer_for_object("assets", "Pustaka Aset")
            item = self._object_session.import_batik_asset(
                Path(record.relative_path).name,
                content,
                target_layer_id=target.layer_id,
                default_category=record.category,
            )
        except (AssetLibraryError, ProjectSessionError, BatikAssetError, OSError) as exc:
            messagebox.showerror(
                "Tambah asset gagal",
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()
        self.set_status(f"Asset ditambahkan sebagai objek: {item.name}.")

    def _on_library_select(self, _event: tk.Event[ttk.Treeview]) -> None:
        selection = self.library_list.selection()
        if not selection:
            return
        record = self._library_records.get(selection[0])
        if record is None:
            return
        pack = self.asset_library.get_pack(record.pack_id)
        dimensions = (
            f"{record.width}×{record.height}px"
            if record.width and record.height
            else "ukuran dari file"
        )
        tags = ", ".join(record.tags[:5]) or "tanpa tag"
        self.library_asset_name_value.set(record.name)
        self.library_asset_meta_value.set(
            f"{record.category} · {dimensions}\n{pack.name}\n{tags}"
        )
        self._show_library_preview(record)

    def _show_library_preview(self, record: AssetRecord) -> None:
        try:
            content = self.asset_library.read_thumbnail(record)
            if content is None:
                asset = load_batik_asset(
                    self.asset_library.read_asset(record),
                    filename=record.relative_path,
                    default_category=record.category,
                )
                content = asset.content
            with Image.open(BytesIO(content)) as source:
                source.load()
                image = source.convert("RGBA")
            image.thumbnail((92, 92), Image.Resampling.LANCZOS)
            self._library_preview_photo = ImageTk.PhotoImage(image)
            self.library_preview_label.configure(image=self._library_preview_photo, text="")
        except (
            AssetLibraryError,
            BatikAssetError,
            OSError,
            UnidentifiedImageError,
            ValueError,
        ):
            self._library_preview_photo = None
            self.library_preview_label.configure(image="", text="Preview\ntidak tersedia")

    def focus_asset_library(self) -> None:
        self.library_list.focus_set()
        self.set_status("Pustaka Asset aktif.")

    def open_brush_settings(self) -> None:
        self.tool_windows.open_brush("brush")

    def open_eraser_settings(self) -> None:
        self.tool_windows.open_brush("eraser")

    def open_shape_settings(self, shape_type: str) -> None:
        self.tool_windows.open_shape(shape_type)

    def open_motif_settings(self) -> None:
        self.tool_windows.open_motif()

    def open_isen_settings(self) -> None:
        self.tool_windows.open_isen()

    def open_transform_settings(self) -> None:
        self.tool_windows.open_transform()

    def open_asset_metadata_settings(self) -> None:
        self.tool_windows.open_asset_metadata()

    def open_humanize_settings(self) -> None:
        self.tool_windows.open_humanize()

    def new_folder(self) -> None:
        self._new_folder()

    def new_object_layer(self) -> None:
        self._new_object_layer()

    def new_paint_layer(self) -> None:
        self._new_paint_layer_in_tree()

    def _bind_compact_shortcuts(self) -> None:
        bindings = (
            ("<Key-v>", lambda _event: self.activate_select_tool()),
            ("<Key-b>", lambda _event: self.open_brush_settings()),
            ("<Key-e>", lambda _event: self.open_eraser_settings()),
            ("<Key-l>", lambda _event: self.open_shape_settings("line")),
            ("<Key-r>", lambda _event: self.open_shape_settings("rectangle")),
            ("<Key-o>", lambda _event: self.open_shape_settings("ellipse")),
            ("<Key-p>", lambda _event: self.open_shape_settings("polygon")),
            ("<Key-m>", lambda _event: self.open_motif_settings()),
            ("<Key-c>", lambda _event: self.open_isen_settings()),
        )
        for sequence, command in bindings:
            self.bind_all(sequence, command)


__all__ = ["CompactAssetEditorWorkspaceView"]
