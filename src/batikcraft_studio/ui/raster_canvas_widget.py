"""Widget kanvas raster (Tk) — menggambar gaya MS Paint per layer.

Menghubungkan RasterDocument + RasterViewportRenderer + BrushEngine ke sebuah
Tk Canvas. Menggambar menulis langsung ke bitmap layer aktif, jadi tetap ringan
pada kanvas seramai apa pun. Panel layer di sisi kanan mengatur urutan dan
layer aktif.

Logika penempatan/koordinat dipisah ke fungsi murni ``view_to_project`` dan
``project_to_view`` supaya bisa diuji tanpa Tk.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, simpledialog, ttk
from typing import Callable

from PIL import Image, ImageTk

from batikcraft_studio.imaging.brush_engine import BrushEngine, BrushSettings
from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_viewport import (
    RasterViewportRenderer,
    ViewportRequest,
)
from batikcraft_studio.imaging.raster_insert import (
    centered_position,
    commit_floating_to_layer,
    point_in_floating,
    prepare_floating_image,
)
from batikcraft_studio.imaging.undo_history import UndoStack

_MIN_ZOOM = 0.1
_MAX_ZOOM = 1.5


def view_to_project(
    view_x: float, view_y: float, offset_x: float, offset_y: float, zoom: float
) -> tuple[float, float]:
    """Koordinat kanvas layar -> koordinat proyek (piksel dokumen)."""

    z = max(zoom, 1e-6)
    return (view_x - offset_x) / z, (view_y - offset_y) / z


def project_to_view(
    proj_x: float, proj_y: float, offset_x: float, offset_y: float, zoom: float
) -> tuple[float, float]:
    return proj_x * zoom + offset_x, proj_y * zoom + offset_y


def _stem(path: str) -> str:
    from pathlib import Path

    return Path(path).stem or "Gambar"


def fit_zoom(doc_w: int, doc_h: int, view_w: int, view_h: int, padding: int = 20) -> float:
    """Zoom agar seluruh dokumen muat di viewport."""

    if doc_w <= 0 or doc_h <= 0:
        return 1.0
    scale = min((view_w - padding * 2) / doc_w, (view_h - padding * 2) / doc_h, 1.0)
    return max(_MIN_ZOOM, min(_MAX_ZOOM, scale))


class RasterCanvasWidget(ttk.Frame):
    """Kanvas raster berlapis dengan alat kuas/penghapus dan panel layer."""

    def __init__(
        self,
        master: tk.Misc,
        document: RasterDocument,
        *,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.document = document
        self.renderer = RasterViewportRenderer()
        self._on_status = on_status
        self._zoom = 1.0
        self._offset = (0.0, 0.0)
        self._tool = "brush"
        self._brush = BrushSettings()
        self._last_point: tuple[float, float] | None = None
        self._last_view_point: tuple[float, float] | None = None
        self._active_engine: BrushEngine | None = None
        self._undo = UndoStack()
        self._stroke_before: "Image.Image | None" = None
        # Gambar mengambang: bisa digeser dulu sebelum dileburkan ke layer.
        self._floating: Image.Image | None = None
        self._floating_pos: tuple[int, int] = (0, 0)
        self._floating_photo: ImageTk.PhotoImage | None = None
        self._floating_drag_offset: tuple[float, float] | None = None
        self._floating_name: str = "Gambar"
        self._photo: ImageTk.PhotoImage | None = None
        self._render_after: str | None = None

        self._build()
        self._register_drop_target()
        self.after(50, self._fit_and_render)

    # ------------------------------------------------------------------
    # Tata letak
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(toolbar, text="Kuas", command=lambda: self.set_tool("brush")).pack(side="left")
        ttk.Button(toolbar, text="Penghapus", command=lambda: self.set_tool("eraser")).pack(
            side="left", padx=4
        )
        ttk.Label(toolbar, text="Ukuran").pack(side="left", padx=(12, 2))
        self._size_var = tk.IntVar(value=int(self._brush.size))
        ttk.Spinbox(
            toolbar, from_=1, to=200, width=4, textvariable=self._size_var,
            command=self._apply_brush,
        ).pack(side="left")
        ttk.Button(toolbar, text="Warna", command=self.choose_color).pack(side="left", padx=8)
        self._color_swatch = tk.Label(toolbar, width=3, bg=self._brush.color)
        self._color_swatch.pack(side="left")
        ttk.Button(toolbar, text="↶ Undo", command=self.undo).pack(side="left", padx=(12, 2))
        ttk.Button(toolbar, text="↷ Redo", command=self.redo).pack(side="left")
        ttk.Button(toolbar, text="Sisipkan Gambar…", command=self.insert_image_dialog).pack(
            side="left", padx=(12, 0)
        )

        self.canvas = tk.Canvas(self, background="#3A3A3A", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", lambda _e: self._schedule_render())
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom)
        # Undo/redo di-bind di level widget agar aktif walau fokus di kanvas.
        self.bind_all("<Control-z>", lambda _e: self.undo())
        self.bind_all("<Control-y>", lambda _e: self.redo())
        self.bind_all("<Control-Z>", lambda _e: self.redo())  # Ctrl+Shift+Z

        self._layer_panel = _LayerPanel(self, self)
        self._layer_panel.grid(row=1, column=1, sticky="ns", padx=(6, 0))

    # ------------------------------------------------------------------
    # Alat & kuas
    # ------------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self._status(f"Alat: {'penghapus' if tool == 'eraser' else 'kuas'}")

    def choose_color(self) -> None:
        chosen = colorchooser.askcolor(color=self._brush.color, parent=self)
        if chosen and chosen[1]:
            self._brush = BrushSettings(
                size=float(self._size_var.get()),
                color=chosen[1],
                hardness=self._brush.hardness,
                opacity=self._brush.opacity,
            )
            self._color_swatch.configure(bg=chosen[1])

    def _apply_brush(self) -> None:
        self._brush = BrushSettings(
            size=float(self._size_var.get()),
            color=self._brush.color,
            hardness=self._brush.hardness,
            opacity=self._brush.opacity,
        )

    def _engine(self) -> BrushEngine:
        settings = BrushSettings(
            size=self._brush.size,
            color=self._brush.color,
            hardness=self._brush.hardness,
            opacity=self._brush.opacity,
            erase=self._tool == "eraser",
        )
        return BrushEngine(settings)

    # ------------------------------------------------------------------
    # Interaksi menggambar
    # ------------------------------------------------------------------

    def _on_press(self, event: tk.Event) -> None:
        if self._floating is not None:
            proj = self._project_point(event.x, event.y)
            if point_in_floating(proj[0], proj[1], self._floating, self._floating_pos):
                self._floating_drag_offset = (
                    proj[0] - self._floating_pos[0],
                    proj[1] - self._floating_pos[1],
                )
            else:
                self._floating_drag_offset = None
            return
        # Engine dibangun SEKALI per goresan. Membangunnya tiap gerakan mouse
        # (termasuk blur tepi) adalah salah satu sumber lag versi sebelumnya.
        self._active_engine = self._engine()
        # Salinan penuh sementara untuk membandingkan wilayah yang berubah saat
        # goresan selesai. Hidup hanya selama satu goresan.
        self._stroke_before = self.document.active_layer.image.copy()
        proj = self._project_point(event.x, event.y)
        self._last_point = proj
        self._last_view_point = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self._active_engine.stroke(self.document.active_layer, [proj])
        self._draw_preview_dot(self._last_view_point)

    def _on_drag(self, event: tk.Event) -> None:
        if self._floating is not None:
            if self._floating_drag_offset is None:
                return
            proj = self._project_point(event.x, event.y)
            self._floating_pos = (
                int(proj[0] - self._floating_drag_offset[0]),
                int(proj[1] - self._floating_drag_offset[1]),
            )
            self._position_floating_overlay()
            return
        if self._last_point is None or self._active_engine is None:
            return
        proj = self._project_point(event.x, event.y)
        view_point = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        # Cap ke bitmap layer (murah), TAPI jangan render ulang seluruh viewport
        # tiap gerakan -- itu yang bikin patah-patah. Umpan balik instan memakai
        # garis native Tk; piksel asli muncul saat dilepas.
        self._active_engine.stroke(self.document.active_layer, [self._last_point, proj])
        if self._last_view_point is not None:
            self._draw_preview_segment(self._last_view_point, view_point)
        self._last_point = proj
        self._last_view_point = view_point

    def _on_release(self, _event: tk.Event) -> None:
        if self._floating is not None:
            self._floating_drag_offset = None
            return
        self._last_point = None
        self._last_view_point = None
        self._active_engine = None
        if self._stroke_before is not None:
            self._undo.record_layer_change(
                self.document.active_layer.layer_id,
                self._stroke_before,
                self.document.active_layer.image,
            )
            self._stroke_before = None
        # Render penuh sekali: gambar pratinjau native diganti piksel asli.
        self._render()
        self.canvas.delete("stroke-preview")

    def undo(self) -> None:
        if self._undo.undo(self.document) is not None:
            self.refresh()
            self._status("Undo.")

    def redo(self) -> None:
        if self._undo.redo(self.document) is not None:
            self.refresh()
            self._status("Redo.")

    def _preview_style(self) -> tuple[str, float]:
        color = "#FFFFFF" if self._tool == "eraser" else self._brush.color
        width = max(1.0, self._brush.size * self._zoom)
        return color, width

    def _draw_preview_dot(self, view_point: tuple[float, float]) -> None:
        color, width = self._preview_style()
        radius = max(0.5, width / 2)
        x, y = view_point
        self.canvas.create_oval(
            x - radius, y - radius, x + radius, y + radius,
            fill=color, outline=color, tags="stroke-preview",
        )

    def _draw_preview_segment(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> None:
        color, width = self._preview_style()
        self.canvas.create_line(
            start[0], start[1], end[0], end[1],
            fill=color, width=width, capstyle="round", joinstyle="round",
            tags="stroke-preview",
        )

    def _project_point(self, view_x: float, view_y: float) -> tuple[float, float]:
        return view_to_project(
            self.canvas.canvasx(view_x),
            self.canvas.canvasy(view_y),
            self._offset[0],
            self._offset[1],
            self._zoom,
        )

    # ------------------------------------------------------------------
    # Zoom & render
    # ------------------------------------------------------------------

    def _on_zoom(self, event: tk.Event) -> None:
        factor = 1.1 if getattr(event, "delta", 0) > 0 else 1 / 1.1
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        self._schedule_render()

    def _fit_and_render(self) -> None:
        view_w = max(self.canvas.winfo_width(), 100)
        view_h = max(self.canvas.winfo_height(), 100)
        self._zoom = fit_zoom(self.document.width, self.document.height, view_w, view_h)
        self._render()

    def _schedule_render(self, *, fast: bool = False) -> None:
        if fast:
            # Saat menggambar, render segera untuk umpan balik responsif.
            self._render()
            return
        if self._render_after is not None:
            self.after_cancel(self._render_after)
        self._render_after = self.after(16, self._render)

    def _render(self) -> None:
        self._render_after = None
        view_w = max(self.canvas.winfo_width(), 100)
        view_h = max(self.canvas.winfo_height(), 100)
        display_w = self.document.width * self._zoom
        display_h = self.document.height * self._zoom
        self._offset = (
            max(20.0, (view_w - display_w) / 2),
            max(20.0, (view_h - display_h) / 2),
        )
        proj_left, proj_top = view_to_project(
            0, 0, self._offset[0], self._offset[1], self._zoom
        )
        request = ViewportRequest(
            proj_left=max(0.0, proj_left),
            proj_top=max(0.0, proj_top),
            view_width=view_w,
            view_height=view_h,
            zoom=self._zoom,
        )
        image = self.renderer.render(self.document, request)
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("raster")
        draw_x = max(self._offset[0], 0.0)
        draw_y = max(self._offset[1], 0.0)
        self.canvas.create_image(draw_x, draw_y, image=self._photo, anchor="nw", tags="raster")
        self._draw_floating_overlay()

    def _draw_floating_overlay(self) -> None:
        self.canvas.delete("floating")
        if self._floating is None:
            return
        scaled = self._floating
        target_w = max(1, round(self._floating.width * self._zoom))
        target_h = max(1, round(self._floating.height * self._zoom))
        if (target_w, target_h) != self._floating.size:
            resample = (
                Image.Resampling.NEAREST if self._zoom >= 1.0 else Image.Resampling.BILINEAR
            )
            scaled = self._floating.resize((target_w, target_h), resample)
        self._floating_photo = ImageTk.PhotoImage(scaled)
        cx, cy = self._floating_canvas_xy()
        self.canvas.create_image(cx, cy, image=self._floating_photo, anchor="nw", tags="floating")
        # Bingkai putus-putus menandai gambar masih mengambang.
        self.canvas.create_rectangle(
            cx, cy, cx + target_w, cy + target_h,
            outline="#2A7DE1", dash=(4, 3), width=1, tags="floating",
        )

    def _floating_canvas_xy(self) -> tuple[float, float]:
        return (
            self._offset[0] + self._floating_pos[0] * self._zoom,
            self._offset[1] + self._floating_pos[1] * self._zoom,
        )

    def _position_floating_overlay(self) -> None:
        """Geser overlay tanpa render ulang penuh — mulus saat menyeret."""

        cx, cy = self._floating_canvas_xy()
        items = self.canvas.find_withtag("floating")
        if not items or self._floating is None:
            self._draw_floating_overlay()
            return
        target_w = max(1, round(self._floating.width * self._zoom))
        target_h = max(1, round(self._floating.height * self._zoom))
        self.canvas.coords(items[0], cx, cy)
        if len(items) > 1:
            self.canvas.coords(items[1], cx, cy, cx + target_w, cy + target_h)

    def refresh(self) -> None:
        self.renderer.invalidate()
        self._render()

    def insert_image_dialog(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self,
            title="Sisipkan gambar sebagai layer",
            filetypes=[
                ("Gambar", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("Semua berkas", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                content = handle.read()
            self.insert_image_bytes(content, name=_stem(path))
        except OSError as exc:
            self._status(f"Gagal membaca gambar: {exc}")

    def insert_image_bytes(self, content: bytes, *, name: str = "Gambar") -> None:
        """Sisipkan gambar sebagai objek MENGAMBANG yang bisa digeser dulu.

        Gambar belum melebur ke layer: pengguna bisa memindahkannya, lalu
        menekan 'Terapkan' (atau Enter) untuk meleburkannya, atau 'Batal'
        (Escape) untuk membuangnya. Kalau ada gambar mengambang sebelumnya,
        gambar itu dileburkan dulu.
        """

        from batikcraft_studio.imaging.raster_layer import RasterLayerError

        try:
            floating = prepare_floating_image(
                content, self.document.width, self.document.height
            )
        except RasterLayerError as exc:
            self._status(str(exc))
            return
        self.commit_floating()  # leburkan yang lama bila ada
        self._floating = floating
        self._floating_pos = centered_position(
            floating, self.document.width, self.document.height
        )
        self._floating_name = name
        self._show_float_controls()
        self._render()
        self._status(
            f"Gambar '{name}' mengambang — geser lalu Terapkan (Enter), "
            "atau Batal (Esc)."
        )

    def commit_floating(self) -> None:
        """Leburkan gambar mengambang ke layer aktif, dengan undo."""

        if self._floating is None:
            return
        layer = self.document.active_layer
        before = layer.image.copy()
        commit_floating_to_layer(layer, self._floating, self._floating_pos)
        self._undo.record_layer_change(layer.layer_id, before, layer.image)
        self._floating = None
        self._floating_photo = None
        self._hide_float_controls()
        self.refresh()
        self._status("Gambar diterapkan ke layer.")

    def cancel_floating(self) -> None:
        if self._floating is None:
            return
        self._floating = None
        self._floating_photo = None
        self._hide_float_controls()
        self._render()
        self._status("Gambar mengambang dibatalkan.")

    def _show_float_controls(self) -> None:
        bar = getattr(self, "_float_bar", None)
        if bar is not None and bar.winfo_exists():
            return
        self._float_bar = ttk.Frame(self)
        ttk.Label(self._float_bar, text="Gambar mengambang:").pack(side="left", padx=4)
        ttk.Button(self._float_bar, text="Terapkan (Enter)", command=self.commit_floating).pack(side="left")
        ttk.Button(self._float_bar, text="Batal (Esc)", command=self.cancel_floating).pack(side="left", padx=4)
        self._float_bar.place(relx=0.5, rely=0.02, anchor="n")
        self.bind_all("<Return>", lambda _e: self.commit_floating())
        self.bind_all("<Escape>", lambda _e: self.cancel_floating())

    def _hide_float_controls(self) -> None:
        bar = getattr(self, "_float_bar", None)
        if bar is not None and bar.winfo_exists():
            bar.destroy()
        self.unbind_all("<Return>")
        self.unbind_all("<Escape>")

    def _register_drop_target(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return False
        register = getattr(self.canvas, "drop_target_register", None)
        bind = getattr(self.canvas, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            return False
        try:
            register(DND_FILES)
            bind("<<Drop>>", self._on_drop)
        except tk.TclError:
            return False
        return True

    def _on_drop(self, event: tk.Event) -> str:
        from batikcraft_studio.ui.batikbrew_studio_window import (
            is_supported_image,
            parse_dropped_paths,
        )

        for path in parse_dropped_paths(getattr(event, "data", "")):
            if not is_supported_image(path):
                continue
            try:
                self.insert_image_bytes(path.read_bytes(), name=path.stem)
            except OSError:
                continue
        return "copy"

    def add_layer(self) -> None:
        self.document.add_layer()
        self.refresh()
        panel = getattr(self, "_layer_panel", None)
        if panel is not None:
            panel.refresh()
        self._status("Layer baru ditambahkan.")

    def move_active_layer(self, delta: int) -> None:
        """Pindah layer aktif naik (+1) atau turun (-1) di tumpukan."""

        self.document.move_active(delta)
        self.refresh()
        panel = getattr(self, "_layer_panel", None)
        if panel is not None:
            panel.refresh()
        self._status("Layer dipindah " + ("naik." if delta > 0 else "turun."))

    def remove_active_layer(self) -> None:
        try:
            self.document.remove_active()
        except Exception as exc:  # noqa: BLE001
            self._status(str(exc))
            return
        self.refresh()
        panel = getattr(self, "_layer_panel", None)
        if panel is not None:
            panel.refresh()
        self._status("Layer dihapus.")

    def _status(self, message: str) -> None:
        if self._on_status is not None:
            self._on_status(message)


class _LayerPanel(ttk.Frame):
    """Daftar layer: tambah, hapus, pindah, ganti aktif."""

    def __init__(self, master: tk.Misc, widget: RasterCanvasWidget) -> None:
        super().__init__(master, width=180)
        self._widget = widget
        ttk.Label(self, text="Layer").pack(anchor="w")
        self._list = tk.Listbox(self, height=12, exportselection=False)
        self._list.pack(fill="both", expand=True)
        self._list.bind("<<ListboxSelect>>", self._on_select)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=4)
        ttk.Button(buttons, text="+", width=3, command=self._add).pack(side="left")
        ttk.Button(buttons, text="−", width=3, command=self._remove).pack(side="left", padx=2)
        ttk.Button(buttons, text="▲", width=3, command=lambda: self._move(1)).pack(side="left")
        ttk.Button(buttons, text="▼", width=3, command=lambda: self._move(-1)).pack(side="left", padx=2)
        self.refresh()

    def refresh(self) -> None:
        self._list.delete(0, tk.END)
        doc = self._widget.document
        # Tampilkan dari atas ke bawah (atas = paling akhir di list dokumen).
        for layer in reversed(doc.layers):
            mark = "○" if not layer.visible else "●"
            self._list.insert(tk.END, f"{mark} {layer.name}")
        active_row = len(doc.layers) - 1 - doc.active_index
        self._list.selection_clear(0, tk.END)
        self._list.selection_set(active_row)

    def _on_select(self, _event: tk.Event) -> None:
        selection = self._list.curselection()
        if not selection:
            return
        doc = self._widget.document
        doc.active_index = len(doc.layers) - 1 - selection[0]
        self._widget.refresh()

    def _add(self) -> None:
        self._widget.document.add_layer()
        self._widget.refresh()
        self.refresh()

    def _remove(self) -> None:
        try:
            self._widget.document.remove_active()
        except Exception as exc:  # noqa: BLE001
            self._widget._status(str(exc))
            return
        self._widget.refresh()
        self.refresh()

    def _move(self, delta: int) -> None:
        self._widget.document.move_active(delta)
        self._widget.refresh()
        self.refresh()


__all__ = ["RasterCanvasWidget", "fit_zoom", "project_to_view", "view_to_project"]
