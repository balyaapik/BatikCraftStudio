"""Nested layer tree, object-sized selection, asset library, and humanize UI."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from batikcraft_studio.application import (
    EditableObjectProjectSession,
    LayerLockedError,
    ObjectLockedError,
    ProjectSessionError,
)
from batikcraft_studio.domain import Layer, LayerNodeKind, LayerObject, ProjectValidationError
from batikcraft_studio.imaging import (
    ASSET_CATEGORIES,
    ISEN_LABELS,
    MOTIF_LABELS,
    BatikAssetError,
    point_hits_layer,
    point_hits_object,
    transformed_object_bounds,
)

from .icons import create_icon
from .motif_batik_editor import MotifBatikEditorWorkspaceView
from .theme import COLORS
from .widgets import icon_button


class ObjectTreeEditorWorkspaceView(MotifBatikEditorWorkspaceView):
    """Present folders, sublayers, and independently editable objects."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        parent = args[0] if args else kwargs["parent"]
        self.asset_name_value = tk.StringVar(master=parent)
        self.asset_category_value = tk.StringVar(master=parent, value="ornamen")
        self.humanize_seed_value = tk.IntVar(master=parent, value=2026)
        self.edge_wobble_value = tk.DoubleVar(master=parent, value=0.18)
        self.ink_breaks_value = tk.DoubleVar(master=parent, value=0.08)
        self.pressure_variation_value = tk.DoubleVar(master=parent, value=0.12)
        self._drag_object_id: str | None = None
        self._drag_object_start: tuple[float, float] | None = None
        self._drag_object_origin: tuple[float, float] | None = None
        self._drag_object_last: tuple[float, float] | None = None
        self._tree_icons: dict[str, tk.PhotoImage] = {}
        super().__init__(*args, **kwargs)

    def _add_dock_tabs(self, notebook: ttk.Notebook) -> None:
        super()._add_dock_tabs(notebook)
        asset_tab = ttk.Frame(notebook, style="Dock.TFrame", padding=(10, 10))
        asset_tab.columnconfigure(0, weight=1)
        self._build_asset_panel(asset_tab)
        notebook.add(asset_tab, text="Asset")

    def _build_layer_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Susunan Lapis", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self.layer_tree = ttk.Treeview(
            parent,
            show="tree",
            selectmode="browse",
            height=14,
        )
        self.layer_tree.grid(row=1, column=0, sticky="nsew", pady=(4, 5))
        self.layer_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.layer_tree.bind("<Button-3>", self._show_tree_context_menu)
        self._tree_icons = {
            "group": create_icon(self, "open", size=15, color="#C8873A"),
            "layer": create_icon(self, "editor", size=15, color="#4677A8"),
            "object": create_icon(self, "batikification", size=14, color="#7D5A9B"),
        }

        controls = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        controls.grid(row=2, column=0, sticky="ew")
        for icon, tooltip, command in (
            ("new", "Buat folder atau lapis baru", self._show_new_menu_from_button),
            ("visibility", "Tampilkan atau sembunyikan pilihan", self.toggle_visibility),
            ("lock", "Kunci atau buka pilihan", self.toggle_lock),
            ("up", "Naikkan urutan pilihan", self.move_active_up),
            ("down", "Turunkan urutan pilihan", self.move_active_down),
            ("duplicate", "Duplikat pilihan", self.duplicate_active),
            ("delete", "Hapus pilihan", self.delete_active),
        ):
            icon_button(
                controls,
                icon=icon,
                tooltip=tooltip,
                command=command,
                size=18,
            ).pack(side="left", padx=1)
        self._build_tree_menus()

    def _build_tree_menus(self) -> None:
        self._new_tree_menu = tk.Menu(self, tearoff=False)
        self._new_tree_menu.add_command(label="Folder", command=self._new_folder)
        self._new_tree_menu.add_command(label="Sublapis Objek", command=self._new_object_layer)
        self._new_tree_menu.add_command(label="Lapis Canting", command=self._new_paint_layer_in_tree)
        self._new_tree_menu.add_separator()
        motif_menu = tk.Menu(self._new_tree_menu, tearoff=False)
        for motif_type, label in MOTIF_LABELS.items():
            motif_menu.add_command(
                label=label,
                command=lambda kind=motif_type: self._new_motif_object(kind),
            )
        self._new_tree_menu.add_cascade(label="Motif Pokok", menu=motif_menu)
        isen_menu = tk.Menu(self._new_tree_menu, tearoff=False)
        for isen_type, label in ISEN_LABELS.items():
            isen_menu.add_command(
                label=label,
                command=lambda kind=isen_type: self._new_isen_object(kind),
            )
        self._new_tree_menu.add_cascade(label="Isen-Isen", menu=isen_menu)
        self._new_tree_menu.add_separator()
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
        self._tree_context_menu.add_command(label="Tampilkan/Sembunyikan", command=self.toggle_visibility)
        self._tree_context_menu.add_command(label="Kunci/Buka", command=self.toggle_lock)

    def _build_asset_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Pustaka Asset Batik", style="PanelTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Label(
            parent,
            text=(
                "Import PNG transparan atau .batikasset. Sumber asli disimpan; "
                "humanize dapat di-reset kapan saja."
            ),
            style="Muted.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 10))

        metadata = ttk.Frame(parent, style="Dock.TFrame")
        metadata.grid(row=2, column=0, sticky="ew")
        metadata.columnconfigure(1, weight=1)
        ttk.Label(metadata, text="Nama", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(metadata, textvariable=self.asset_name_value).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=3,
        )
        ttk.Label(metadata, text="Kategori", style="Muted.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
        )
        ttk.Combobox(
            metadata,
            textvariable=self.asset_category_value,
            values=ASSET_CATEGORIES,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        icon_button(
            metadata,
            icon="apply",
            tooltip="Terapkan nama dan kategori asset",
            command=self.apply_asset_metadata,
            size=18,
        ).grid(row=2, column=1, sticky="e", pady=(5, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=12,
        )
        ttk.Label(parent, text="Humanize", style="PanelTitle.TLabel").grid(
            row=4,
            column=0,
            sticky="ew",
        )
        controls = ttk.Frame(parent, style="Dock.TFrame")
        controls.grid(row=5, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        rows = (
            ("Seed", self.humanize_seed_value, 0, 999999, 1),
            ("Tepi tidak rata", self.edge_wobble_value, 0, 1, 0.01),
            ("Celah malam", self.ink_breaks_value, 0, 1, 0.01),
            ("Variasi tekanan", self.pressure_variation_value, 0, 1, 0.01),
        )
        for row, (label, variable, start, stop, increment) in enumerate(rows):
            ttk.Label(controls, text=label, style="Muted.TLabel").grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )
            ttk.Spinbox(
                controls,
                from_=start,
                to=stop,
                increment=increment,
                textvariable=variable,
                width=9,
            ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)

        actions = ttk.Frame(parent, style="Toolbar.TFrame", padding=(3, 3))
        actions.grid(row=6, column=0, sticky="e", pady=(10, 0))
        for icon, tooltip, command in (
            ("import", "Import asset", self.import_asset_dialog),
            ("save", "Export objek sebagai .batikasset", self.export_asset_dialog),
            ("batikification", "Terapkan humanize", self.apply_humanize),
            ("undo", "Reset ke asset sumber", self.reset_humanize),
        ):
            icon_button(
                actions,
                icon=icon,
                tooltip=tooltip,
                command=command,
                size=18,
            ).pack(side="left", padx=1)

    def _refresh_layer_list(self) -> None:
        if not hasattr(self, "layer_tree"):
            return
        self._updating_layer_list = True
        for item in self.layer_tree.get_children(""):
            self.layer_tree.delete(item)
        project = self.session.project
        if project is not None:
            self._insert_tree_children(None, "")
            selected = (
                f"object:{project.active_object_id}"
                if project.active_object_id is not None
                else f"layer:{project.active_layer_id}"
                if project.active_layer_id is not None
                else None
            )
            if selected and self.layer_tree.exists(selected):
                self.layer_tree.selection_set(selected)
                self.layer_tree.focus(selected)
                self.layer_tree.see(selected)
        self._updating_layer_list = False

    def _insert_tree_children(self, parent_id: str | None, tree_parent: str) -> None:
        project = self.session.require_project()
        for layer in reversed(project.children_of(parent_id)):
            layer_iid = f"layer:{layer.layer_id}"
            state = ("◉" if layer.visible else "○") + ("  🔒" if layer.locked else "")
            self.layer_tree.insert(
                tree_parent,
                tk.END,
                iid=layer_iid,
                text=f"{layer.name}  {state}",
                image=self._tree_icons[
                    "group" if layer.node_kind is LayerNodeKind.GROUP else "layer"
                ],
                open=True,
            )
            if layer.node_kind is LayerNodeKind.GROUP:
                self._insert_tree_children(layer.layer_id, layer_iid)
            else:
                for item in reversed(layer.objects):
                    object_state = ("◉" if item.visible else "○") + (
                        "  🔒" if item.locked else ""
                    )
                    self.layer_tree.insert(
                        layer_iid,
                        tk.END,
                        iid=f"object:{item.object_id}",
                        text=f"{item.name}  {object_state}",
                        image=self._tree_icons["object"],
                    )

    def _on_tree_select(self, _event: tk.Event[tk.Misc]) -> None:
        if self._updating_layer_list:
            return
        selection = self.layer_tree.selection()
        if not selection:
            return
        node_type, node_id = selection[0].split(":", 1)
        if node_type == "object":
            self._object_session.select_object(node_id)
        else:
            self.session.select_layer(node_id)
        self._refresh_transform_fields()
        self._refresh_asset_fields()
        self._draw_selection()

    def _show_tree_context_menu(self, event: tk.Event[ttk.Treeview]) -> str:
        item = self.layer_tree.identify_row(event.y)
        if item:
            self.layer_tree.selection_set(item)
            self.layer_tree.focus(item)
            self._on_tree_select(event)
        self._populate_move_folder_menu()
        try:
            self._tree_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._tree_context_menu.grab_release()
        return "break"

    def _show_new_menu_from_button(self) -> None:
        widget = self.winfo_toplevel()
        x = widget.winfo_pointerx()
        y = widget.winfo_pointery()
        self._new_tree_menu.tk_popup(x, y)

    def _populate_move_folder_menu(self) -> None:
        self._move_folder_menu.delete(0, tk.END)
        selected = self._selected_layer_for_tree_action()
        state = tk.NORMAL if selected is not None else tk.DISABLED
        self._move_folder_menu.add_command(
            label="Akar Dokumen",
            state=state,
            command=lambda: self._move_selected_to_folder(None),
        )
        project = self.session.project
        if project is None:
            return
        for layer in project.layers:
            if layer.node_kind is LayerNodeKind.GROUP and layer.layer_id != selected:
                self._move_folder_menu.add_command(
                    label=layer.name,
                    state=state,
                    command=lambda folder_id=layer.layer_id: self._move_selected_to_folder(
                        folder_id
                    ),
                )

    def _new_folder(self) -> None:
        parent_id = self._selected_folder_id()
        folder = self._object_session.create_folder(parent_id=parent_id)
        self.refresh_context()
        self.set_status(f"Folder dibuat: {folder.name}")

    def _new_object_layer(self) -> None:
        parent_id = self._selected_folder_id()
        layer = self._object_session.create_object_layer(parent_id=parent_id)
        self.refresh_context()
        self.set_status(f"Sublapis dibuat: {layer.name}")

    def _new_paint_layer_in_tree(self) -> None:
        parent_id = self._selected_folder_id()
        layer = self._object_session.create_paint_layer(parent_id=parent_id)
        self.refresh_context()
        self.set_status(f"Lapis canting dibuat: {layer.name}")

    def _new_motif_object(self, motif_type: str) -> None:
        target = self._target_layer_for_object("motif-pokok", "Motif Pokok")
        try:
            objects = self._object_session.cap_motif_di_tengah(
                motif_type,
                ukuran=float(self.motif_size_value.get()),
                warna_motif=self.motif_color_value.get(),
                warna_isen=self.motif_isen_color_value.get(),
                isen_type=self._selected_or_default_isen(motif_type),
                isi_isen_otomatis=bool(self.auto_isen_value.get()),
                susun="tunggal",
                target_layer_id=target.layer_id,
            )
        except (ProjectSessionError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Objek motif dibuat: {objects[0].name}")

    def _new_isen_object(self, isen_type: str) -> None:
        target = self._target_layer_for_object("isen-isen", "Isen-Isen")
        try:
            objects = self._object_session.cap_isen_di_tengah(
                isen_type,
                ukuran=float(self.cap_size_value.get()),
                warna=self.cap_color_value.get(),
                susun="tunggal",
                target_layer_id=target.layer_id,
            )
        except (ProjectSessionError, ValueError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Objek isen dibuat: {objects[0].name}")

    def _target_layer_for_object(self, role: str, name: str) -> Layer:
        project = self.session.require_project()
        selection = self.layer_tree.selection() if hasattr(self, "layer_tree") else ()
        if selection:
            node_type, node_id = selection[0].split(":", 1)
            if node_type == "object":
                return project.get_layer(project.object_layer_id(node_id))
            layer = project.get_layer(node_id)
            if layer.node_kind is LayerNodeKind.LAYER:
                return layer
            return self._object_session.create_object_layer(
                name,
                parent_id=layer.layer_id,
                role=role,
            )
        return self._object_session.create_object_layer(name, role=role)

    def _selected_folder_id(self) -> str | None:
        project = self.session.project
        if project is None or not hasattr(self, "layer_tree"):
            return None
        selection = self.layer_tree.selection()
        if not selection:
            return None
        node_type, node_id = selection[0].split(":", 1)
        if node_type == "object":
            owner = project.get_layer(project.object_layer_id(node_id))
            return owner.parent_id
        layer = project.get_layer(node_id)
        return layer.layer_id if layer.node_kind is LayerNodeKind.GROUP else layer.parent_id

    def _selected_layer_for_tree_action(self) -> str | None:
        project = self.session.project
        if project is None or not hasattr(self, "layer_tree"):
            return None
        selection = self.layer_tree.selection()
        if not selection:
            return None
        node_type, node_id = selection[0].split(":", 1)
        return project.object_layer_id(node_id) if node_type == "object" else node_id

    def _move_selected_to_folder(self, folder_id: str | None) -> None:
        layer_id = self._selected_layer_for_tree_action()
        if layer_id is None:
            return
        try:
            self._object_session.move_layer_to_folder(layer_id, folder_id)
        except (ProjectSessionError, ProjectValidationError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()

    def import_image_dialog(self) -> None:
        self.import_asset_dialog()

    def import_asset_dialog(self) -> None:
        if not self.session.has_project:
            self.set_status("Buat atau buka proyek sebelum mengimpor asset.")
            return
        selected = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import Asset Batik",
            filetypes=(
                ("Batik asset dan gambar", "*.batikasset *.json *.png *.jpg *.jpeg"),
                ("BatikCraft asset", "*.batikasset *.json"),
                ("Image files", "*.png *.jpg *.jpeg"),
            ),
        )
        if not selected:
            return
        path = Path(selected)
        target = self._target_layer_for_object("assets", "Pustaka Aset")
        try:
            item = self._object_session.import_batik_asset(
                path.name,
                path.read_bytes(),
                target_layer_id=target.layer_id,
                default_category=self.asset_category_value.get(),
            )
        except (OSError, ProjectSessionError, BatikAssetError) as exc:
            messagebox.showerror("Import asset gagal", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh_context()
        self.set_status(f"Asset diimpor sebagai objek: {item.name}")

    def export_asset_dialog(self) -> None:
        item = self._active_object()
        if item is None:
            self.set_status("Pilih objek asset yang akan diekspor.")
            return
        destination = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export Batik Asset",
            defaultextension=".batikasset",
            initialfile=f"{item.name}.batikasset",
            filetypes=(("BatikCraft asset", "*.batikasset"),),
        )
        if not destination:
            return
        try:
            Path(destination).write_bytes(
                self._object_session.export_batik_asset(item.object_id)
            )
        except (OSError, ProjectSessionError) as exc:
            messagebox.showerror("Export asset gagal", str(exc), parent=self.winfo_toplevel())
            return
        self.set_status(f"Asset diekspor: {destination}")

    def apply_asset_metadata(self) -> None:
        item = self._active_object()
        if item is None:
            self.set_status("Pilih objek sebelum mengubah metadata asset.")
            return
        try:
            self._object_session.update_object_metadata(
                item.object_id,
                name=self.asset_name_value.get(),
                category=self.asset_category_value.get(),
            )
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()

    def apply_humanize(self) -> None:
        item = self._active_object()
        if item is None:
            self.set_status("Pilih objek raster, motif, atau isen untuk humanize.")
            return
        try:
            self._object_session.humanize_object(
                item.object_id,
                seed=int(self.humanize_seed_value.get()),
                edge_wobble=float(self.edge_wobble_value.get()),
                ink_breaks=float(self.ink_breaks_value.get()),
                opacity_variation=float(self.pressure_variation_value.get()),
            )
        except (ProjectSessionError, ValueError, tk.TclError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"Humanize diterapkan pada {item.name}.")

    def reset_humanize(self) -> None:
        item = self._active_object()
        if item is None:
            self.set_status("Pilih objek yang akan dikembalikan ke sumber asli.")
            return
        try:
            self._object_session.reset_object_humanize(item.object_id)
        except ProjectSessionError as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"{item.name} dikembalikan ke asset sumber.")

    def _refresh_asset_fields(self) -> None:
        item = self._active_object()
        if item is None:
            self.asset_name_value.set("")
            return
        self.asset_name_value.set(item.name)
        category = str(item.properties.get("asset_category", "ornamen"))
        self.asset_category_value.set(
            category if category in ASSET_CATEGORIES else "ornamen"
        )
        self.humanize_seed_value.set(int(item.properties.get("humanize_seed", 2026)))
        self.edge_wobble_value.set(
            float(item.properties.get("humanize_edge_wobble", 0.18))
        )
        self.ink_breaks_value.set(float(item.properties.get("humanize_ink_breaks", 0.08)))
        self.pressure_variation_value.set(
            float(item.properties.get("humanize_opacity_variation", 0.12))
        )

    def _refresh_transform_fields(self) -> None:
        item = self._active_object()
        if item is None:
            super()._refresh_transform_fields()
            self._refresh_asset_fields()
            return
        values = (
            item.transform.x,
            item.transform.y,
            item.transform.rotation_degrees,
            item.transform.scale_x,
            item.transform.scale_y,
            item.opacity,
        )
        for variable, value in zip(
            (
                self.x_value,
                self.y_value,
                self.rotation_value,
                self.scale_x_value,
                self.scale_y_value,
                self.opacity_value,
            ),
            values,
            strict=True,
        ):
            variable.set(f"{value:.4f}".rstrip("0").rstrip("."))
        self._refresh_asset_fields()

    def apply_transform(self) -> None:
        item = self._active_object()
        if item is None:
            super().apply_transform()
            return
        try:
            self._object_session.update_object_transform(
                item.object_id,
                x=float(self.x_value.get()),
                y=float(self.y_value.get()),
                rotation_degrees=float(self.rotation_value.get()),
                scale_x=float(self.scale_x_value.get()),
                scale_y=float(self.scale_y_value.get()),
            )
            self._object_session.set_object_opacity(
                item.object_id,
                float(self.opacity_value.get()),
            )
        except (ValueError, ProjectSessionError, ProjectValidationError) as exc:
            messagebox.showerror("Transform objek tidak valid", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh_context()

    def duplicate_active(self) -> None:
        item = self._active_object()
        if item is not None:
            duplicate = self._object_session.duplicate_object(item.object_id)
            self.refresh_context()
            self.set_status(f"Objek diduplikat: {duplicate.name}")
            return
        super().duplicate_active()

    def delete_active(self) -> None:
        item = self._active_object()
        if item is not None:
            try:
                removed = self._object_session.delete_object(item.object_id)
            except (ObjectLockedError, ProjectSessionError) as exc:
                self.set_status(str(exc))
                return
            self.refresh_context()
            self.set_status(f"Objek dihapus: {removed.name}")
            return
        layer = self._active_layer()
        if layer is None:
            self.set_status("Pilih folder, lapis, atau objek yang akan dihapus.")
            return
        try:
            removed = self._object_session.delete_layer_tree(layer.layer_id)
        except (LayerLockedError, ProjectSessionError) as exc:
            self.set_status(str(exc))
            return
        self.refresh_context()
        self.set_status(f"{len(removed)} node lapis dihapus.")

    def toggle_visibility(self) -> None:
        item = self._active_object()
        if item is not None:
            self._object_session.set_object_visibility(item.object_id, not item.visible)
            self.refresh_context()
            return
        super().toggle_visibility()

    def toggle_lock(self) -> None:
        item = self._active_object()
        if item is not None:
            self._object_session.set_object_locked(item.object_id, not item.locked)
            self.refresh_context()
            return
        super().toggle_lock()

    def move_active_up(self) -> None:
        item = self._active_object()
        if item is not None:
            if not self._object_session.move_object_up(item.object_id):
                self.set_status("Objek sudah berada paling atas di dalam lapis.")
                return
            self.refresh_context()
            return
        super().move_active_up()

    def move_active_down(self) -> None:
        item = self._active_object()
        if item is not None:
            if not self._object_session.move_object_down(item.object_id):
                self.set_status("Objek sudah berada paling bawah di dalam lapis.")
                return
            self.refresh_context()
            return
        super().move_active_down()

    def _on_canvas_press(self, event: tk.Event[tk.Canvas]) -> None:
        if self._active_tool != "select":
            super()._on_canvas_press(event)
            return
        project = self.session.project
        if project is None or self._preview_scale <= 0:
            return
        project_x = (event.x - self._preview_left) / self._preview_scale
        project_y = (event.y - self._preview_top) / self._preview_scale
        for layer in reversed(project.layers):
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            for item in reversed(layer.objects):
                if item.visible and point_hits_object(item, project_x, project_y):
                    self._object_session.select_object(item.object_id)
                    self._refresh_layer_list()
                    self._refresh_transform_fields()
                    self._draw_selection()
                    if not item.locked and not project.is_layer_effectively_locked(
                        layer.layer_id
                    ):
                        self._drag_object_id = item.object_id
                        self._drag_object_start = (event.x, event.y)
                        self._drag_object_last = (event.x, event.y)
                        self._drag_object_origin = (
                            item.transform.x,
                            item.transform.y,
                        )
                        self.canvas.configure(cursor="fleur")
                    return
        for layer in reversed(project.layers):
            if (
                layer.node_kind is LayerNodeKind.LAYER
                and not layer.objects
                and project.is_layer_effectively_visible(layer.layer_id)
                and point_hits_layer(layer, project_x, project_y)
            ):
                self.session.select_layer(layer.layer_id)
                self._refresh_layer_list()
                self._refresh_transform_fields()
                self._draw_selection()
                return
        self.session.select_layer(None)
        self._refresh_layer_list()
        self._refresh_transform_fields()
        self._draw_selection()

    def _on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self._drag_object_id is None or self._drag_object_last is None:
            super()._on_canvas_drag(event)
            return
        delta_x = event.x - self._drag_object_last[0]
        delta_y = event.y - self._drag_object_last[1]
        self.canvas.move("selection", delta_x, delta_y)
        self._drag_object_last = (event.x, event.y)

    def _on_canvas_release(self, event: tk.Event[tk.Canvas]) -> None:
        if self._drag_object_id is None:
            super()._on_canvas_release(event)
            return
        if (
            self._drag_object_start is not None
            and self._drag_object_origin is not None
            and self._preview_scale > 0
        ):
            delta_x = (event.x - self._drag_object_start[0]) / self._preview_scale
            delta_y = (event.y - self._drag_object_start[1]) / self._preview_scale
            try:
                self._object_session.move_object(
                    self._drag_object_id,
                    x=self._drag_object_origin[0] + delta_x,
                    y=self._drag_object_origin[1] + delta_y,
                )
            except (ObjectLockedError, ProjectValidationError) as exc:
                self.set_status(str(exc))
        self._clear_object_drag()
        self.refresh_context()

    def _clear_object_drag(self) -> None:
        self._drag_object_id = None
        self._drag_object_start = None
        self._drag_object_origin = None
        self._drag_object_last = None
        self.canvas.configure(cursor="arrow")

    def _draw_selection(self) -> None:
        item = self._active_object()
        if item is None:
            super()._draw_selection()
            return
        self.canvas.delete("selection")
        left, top, right, bottom = transformed_object_bounds(
            item,
            preview_scale=self._preview_scale,
        )
        coordinates = (
            self._preview_left + left,
            self._preview_top + top,
            self._preview_left + right,
            self._preview_top + bottom,
        )
        color = COLORS["warning"] if item.locked else COLORS["accent_dark"]
        self.canvas.create_rectangle(
            *coordinates,
            outline=color,
            width=2,
            dash=(5, 3),
            tags="selection",
        )
        for x, y in (
            (coordinates[0], coordinates[1]),
            (coordinates[2], coordinates[1]),
            (coordinates[0], coordinates[3]),
            (coordinates[2], coordinates[3]),
        ):
            self.canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=color,
                outline=COLORS["white"],
                tags="selection",
            )

    def _active_object(self) -> LayerObject | None:
        project = self.session.project
        if project is None or project.active_object_id is None:
            return None
        return project.get_object(project.active_object_id)

    @property
    def _object_session(self) -> EditableObjectProjectSession:
        if not isinstance(self.session, EditableObjectProjectSession):
            raise RuntimeError("Editor memerlukan session object-tree dan asset editing.")
        return self.session


__all__ = ["ObjectTreeEditorWorkspaceView"]
