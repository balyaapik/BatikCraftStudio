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

from PIL import ImageTk

from batikcraft_studio.imaging.brush_engine import BrushEngine, BrushSettings
from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.raster_viewport import (
    RasterViewportRenderer,
    ViewportRequest,
)

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
        self._photo: ImageTk.PhotoImage | None = None
        self._render_after: str | None = None

        self._build()
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

        self.canvas = tk.Canvas(self, background="#3A3A3A", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", lambda _e: self._schedule_render())
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom)

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
        proj = self._project_point(event.x, event.y)
        self._last_point = proj
        self._engine().stroke(self.document.active_layer, [proj])
        self._schedule_render(fast=True)

    def _on_drag(self, event: tk.Event) -> None:
        if self._last_point is None:
            return
        proj = self._project_point(event.x, event.y)
        self._engine().stroke(self.document.active_layer, [self._last_point, proj])
        self._last_point = proj
        self._schedule_render(fast=True)

    def _on_release(self, _event: tk.Event) -> None:
        self._last_point = None
        # Layer aktif berubah -> cache latar tetap valid, cukup render biasa.
        self._schedule_render()

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

    def refresh(self) -> None:
        self.renderer.invalidate()
        self._render()

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
