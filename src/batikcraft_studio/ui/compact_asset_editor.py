"""Asset-first editor with bilingual permanent panes and transient tool windows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
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
from batikcraft_studio.i18n import category_label, tr
from batikcraft_studio.imaging import ASSET_CATEGORIES, BatikAssetError, load_batik_asset

from .keyboard import run_single_key_shortcut
from .professional_object_tree_editor import ProfessionalObjectTreeEditorWorkspaceView
from .theme import COLORS
from .tool_windows import EditorToolWindows
from .widgets import icon_button

_MAX_VISIBLE_RESULTS = 5_000


class CompactAssetEditorWorkspaceView(ProfessionalObjectTreeEditorWorkspaceView):
    """Keep only library, canvas, and object tree visible in the main workspace."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.asset_library = AssetLibrary()
        self._all_packs_label = tr("library.all_packs")
        self._all_categories_label = tr("library.all_categories")
        self._category_display_to_id = {
            category_label(category): category for category in ASSET_CATEGORIES
        }
        self.library_query_value = tk.StringVar(master=parent)
        self.library_category_value = tk.StringVar(
            master=parent,
            value=self._all_categories_label,
        )
        self.library_pack_value = tk.StringVar(master=parent, value=self._all_packs_label)
        self.library_summary_value = tk.StringVar(master=parent)
        self.library_asset_name_value = tk.StringVar(
            master=parent,
            value=tr("library.choose_asset"),
        )
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
        layer_children = layers.winfo_children()
        if layer_children:
            try:
                layer_children[0].configure(text=tr("tree.title"))
            except tk.TclError:
                pass
        body.add(layers, weight=1)

    def _build_library_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Dock.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=tr("library.title"),
            style="PanelTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
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
        self.library_category_combo = ttk.Combobox(
            filters,
            textvariable=self.library_category_value,
            values=(self._all_categories_label, *self._category_display_to_id),
            state="readonly",
            width=15,
        )
        self.library_category_combo.grid(row=1, column=1, sticky="ew")

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
        self.library_list.heading("#0", text=tr("library.asset_heading"))
        self.library_list.heading("category", text=tr("library.category_heading"))
        self.library_list.heading("pack", text=tr("library.pack_heading"))
        self.library_list.column("#0", width=145, minwidth=90, stretch=True)
        self.library_list.column("category", width=80, minwidth=65, stretch=False)
        self.library_list.column("pack", width=70, minwidth=55, stretch=False)
        self.library_list.grid(row=4, column=0, sticky="nsew")
        self.library_list.bind("<<TreeviewSelect>>", self._on_library_select)
        self.library_list.bind("<Double-1>", lambda _event: self.add_selected_library_asset())

        actions = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        actions.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        for icon, tooltip_key, command in (
            ("apply", "library.add_tooltip", self.add_selected_library_asset),
            ("import", "library.install_tooltip", self.install_asset_pack_dialog),
            ("delete", "library.remove_tooltip", self.uninstall_selected_pack),
            ("redo", "library.reload_tooltip", self.reload_asset_library),
        ):
            icon_button(
                actions,
                icon=icon,
                tooltip=tr(tooltip_key),
                command=command,
                size=18,
            ).pack(side="left", padx=1)

    def _build_tree_menus(self) -> None:
        """Keep structural and import actions; drawing creation lives in the menu bar."""

        self._new_tree_menu = tk.Menu(self, tearoff=False)
        self._new_tree_menu.add_command(label=tr("tree.folder"), command=self._new_folder)
        self._new_tree_menu.add_command(
            label=tr("tree.object_sublayer"),
            command=self._new_object_layer,
        )
        self._new_tree_menu.add_command(
            label=tr("tree.canting_layer"),
            command=self._new_paint_layer_in_tree,
        )
        self._new_tree_menu.add_separator()
        self._new_tree_menu.add_command(
            label=tr("tree.add_from_library"),
            command=self.add_selected_library_asset,
        )
        self._new_tree_menu.add_command(
            label=tr("tree.import_asset"),
            command=self.import_asset_dialog,
        )

        self._tree_context_menu = tk.Menu(self, tearoff=False)
        self._tree_context_menu.add_cascade(label=tr("tree.new"), menu=self._new_tree_menu)
        self._move_folder_menu = tk.Menu(self._tree_context_menu, tearoff=False)
        self._tree_context_menu.add_cascade(
            label=tr("tree.move_to_folder"),
            menu=self._move_folder_menu,
        )
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(
            label=tr("tree.duplicate"),
            command=self.duplicate_active,
        )
        self._tree_context_menu.add_command(
            label=tr("tree.delete"),
            command=self.delete_active,
        )
        self._tree_context_menu.add_separator()
        self._tree_context_menu.add_command(
            label=tr("tree.visibility"),
            command=self.toggle_visibility,
        )
        self._tree_context_menu.add_command(label=tr("tree.lock"), command=self.toggle_lock)

    def refresh_library(self) -> None:
        if not hasattr(self, "library_list"):
            return
        pack_display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(pack_display)
        category = self._category_display_to_id.get(self.library_category_value.get())
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
                values=(
                    category_label(record.category),
                    pack_names.get(record.pack_id, record.pack_id),
                ),
            )
        total = self.asset_library.asset_count
        suffix = "+" if len(records) == _MAX_VISIBLE_RESULTS and total > len(records) else ""
        self.library_summary_value.set(
            tr(
                "library.summary",
                shown=len(records),
                suffix=suffix,
                total=total,
                packs=len(self.asset_library.packs),
            )
        )
        self._refresh_pack_combo()

    def _refresh_pack_combo(self) -> None:
        current = self.library_pack_value.get()
        self._library_pack_lookup = {pack.name: pack.pack_id for pack in self.asset_library.packs}
        values = (self._all_packs_label, *self._library_pack_lookup)
        self.library_pack_combo.configure(values=values)
        if current not in values:
            self.library_pack_value.set(self._all_packs_label)

    def reload_asset_library(self) -> None:
        self.asset_library.refresh()
        self.refresh_library()
        self.set_status(tr("library.reloaded", count=self.asset_library.asset_count))

    def install_asset_pack_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=tr("library.install_title"),
            filetypes=(("BatikCraft asset pack", f"*{ASSET_PACK_EXTENSION}"),),
        )
        if not selected:
            return
        try:
            pack = self.asset_library.install_pack(selected)
        except AssetLibraryError as exc:
            if "sudah terpasang" not in str(exc):
                messagebox.showerror(
                    tr("library.install_error"),
                    str(exc),
                    parent=self.winfo_toplevel(),
                )
                return
            replace = messagebox.askyesno(
                tr("library.replace_title"),
                tr("library.replace_question", error=exc),
                parent=self.winfo_toplevel(),
            )
            if not replace:
                return
            try:
                pack = self.asset_library.install_pack(selected, replace=True)
            except AssetLibraryError as replace_exc:
                messagebox.showerror(
                    tr("library.install_error"),
                    str(replace_exc),
                    parent=self.winfo_toplevel(),
                )
                return
        self.refresh_library()
        self.library_pack_value.set(pack.name)
        self.set_status(tr("library.installed", name=pack.name, count=len(pack.assets)))

    def uninstall_selected_pack(self) -> None:
        display = self.library_pack_value.get()
        pack_id = self._library_pack_lookup.get(display)
        if pack_id is None:
            self.set_status(tr("library.select_pack_first"))
            return
        pack = self.asset_library.get_pack(pack_id)
        if not messagebox.askyesno(
            tr("library.remove_title"),
            tr("library.remove_question", name=pack.name, count=len(pack.assets)),
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self.asset_library.uninstall_pack(pack_id)
        except AssetLibraryError as exc:
            messagebox.showerror(
                tr("library.remove_error"),
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.library_pack_value.set(self._all_packs_label)
        self.refresh_library()
        self.set_status(tr("library.removed", name=pack.name))

    def add_selected_library_asset(self) -> None:
        if not self.session.has_project:
            self.set_status(tr("library.project_required"))
            return
        selection = self.library_list.selection()
        if not selection:
            self.set_status(tr("library.select_asset_first"))
            return
        record = self._library_records.get(selection[0])
        if record is None:
            self.set_status(tr("library.asset_missing"))
            return
        try:
            content = self.asset_library.read_asset(record)
            target = self._target_layer_for_object("assets", tr("library.target_layer"))
            item = self._object_session.import_batik_asset(
                Path(record.relative_path).name,
                content,
                target_layer_id=target.layer_id,
                default_category=record.category,
            )
        except (AssetLibraryError, ProjectSessionError, BatikAssetError, OSError) as exc:
            messagebox.showerror(
                tr("library.add_error"),
                str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh_context()
        self.set_status(tr("library.added", name=item.name))

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
            else tr("common.file_size")
        )
        tags = ", ".join(record.tags[:5]) or tr("common.no_tags")
        self.library_asset_name_value.set(record.name)
        self.library_asset_meta_value.set(
            f"{category_label(record.category)} · {dimensions}\n{pack.name}\n{tags}"
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
            self.library_preview_label.configure(
                image="",
                text=tr("library.preview_unavailable"),
            )

    def focus_asset_library(self) -> None:
        self.library_list.focus_set()
        self.set_status(tr("library.focused"))

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
        bindings: tuple[tuple[str, Callable[[], object]], ...] = (
            ("<Key-v>", self.activate_select_tool),
            ("<Key-b>", self.open_brush_settings),
            ("<Key-e>", self.open_eraser_settings),
            ("<Key-l>", lambda: self.open_shape_settings("line")),
            ("<Key-r>", lambda: self.open_shape_settings("rectangle")),
            ("<Key-o>", lambda: self.open_shape_settings("ellipse")),
            ("<Key-p>", lambda: self.open_shape_settings("polygon")),
            ("<Key-m>", self.open_motif_settings),
            ("<Key-c>", self.open_isen_settings),
        )
        for sequence, command in bindings:
            self.bind_all(
                sequence,
                lambda event, action=command: run_single_key_shortcut(event, action),
            )

    def destroy(self) -> None:
        if hasattr(self, "tool_windows"):
            self.tool_windows.close_all()
        super().destroy()


__all__ = ["CompactAssetEditorWorkspaceView"]
