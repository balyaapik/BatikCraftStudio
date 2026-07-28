"""Garis digambar sebagai raster supaya bisa dihapus seperti goresan kuas.

Sebelumnya garis adalah objek vektor (``ObjectKind.SHAPE``) yang dirender ulang
dari geometrinya setiap kali. Penghapus bekerja pada permukaan lapisan yang
sudah terkomposit, sehingga ia hanya menutupi garis secara visual: objek garisnya
tetap utuh, dan menggeser garis itu membuat bekas hapus tertinggal di tempatnya.

Di sini garis dirender menjadi piksel begitu selesai digambar, lalu disimpan
sebagai objek goresan biasa. Dengan begitu garis mewarisi seluruh perilaku yang
sudah ada untuk goresan: dapat dihapus sebagian, ikut terhapus permanen oleh
penghapus destruktif, dan memakai jalur render yang sama.

Yang dikorbankan: setelah menjadi raster, ketebalan dan warna garis tidak lagi
dapat diubah setelah digambar. Karena itu hanya "line" yang diraster; kotak,
elips, dan poligon sengaja tetap vektor.
"""

from __future__ import annotations

from uuid import uuid4

from batikcraft_studio.domain import LayerObject, ObjectBounds, ObjectKind, Transform
from batikcraft_studio.imaging.shape import ShapeError, build_shape_geometry
from batikcraft_studio.imaging.stroke_object import render_cropped_stroke

from .background_ai_session import AIBatikBackgroundProjectSession
from .shape_session import ShapeLayerError

# Garis lurus pada dasarnya adalah goresan kuas dua titik. Memakai perender
# goresan yang sudah ada berarti garis langsung memperoleh anti-aliasing,
# pemotongan bidang kosong, dan dukungan penghapus yang sama.
_LINE_HARDNESS = 1.0
_LINE_SMOOTHING = 0.0


class RasterLineProjectSession(AIBatikBackgroundProjectSession):
    """Alihkan pembuatan garis ke jalur raster, sisanya tetap vektor."""

    def create_shape_layer(
        self,
        shape_type: str,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        name: str | None = None,
        stroke_color: str = "#273043",
        fill_color: str = "#D9A566",
        stroke_width: float = 4.0,
        stroke_enabled: bool = True,
        fill_enabled: bool = True,
        polygon_sides: int = 6,
        constrain: bool = False,
        from_center: bool = False,
        target_layer_id: str | None = None,
    ):
        if str(shape_type).strip().lower() != "line":
            return super().create_shape_layer(
                shape_type,
                start,
                end,
                name=name,
                stroke_color=stroke_color,
                fill_color=fill_color,
                stroke_width=stroke_width,
                stroke_enabled=stroke_enabled,
                fill_enabled=fill_enabled,
                polygon_sides=polygon_sides,
                constrain=constrain,
                from_center=from_center,
                target_layer_id=target_layer_id,
            )
        return self.create_raster_line(
            start,
            end,
            name=name,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            stroke_enabled=stroke_enabled,
            constrain=constrain,
            from_center=from_center,
            target_layer_id=target_layer_id,
        )

    def create_raster_line(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        name: str | None = None,
        stroke_color: str = "#273043",
        stroke_width: float = 4.0,
        stroke_enabled: bool = True,
        constrain: bool = False,
        from_center: bool = False,
        target_layer_id: str | None = None,
    ) -> LayerObject:
        """Gambar satu garis sebagai piksel dan kembalikan objek goresannya.

        Seluruh pekerjaan dilakukan dalam satu mutasi supaya satu kali undo
        membatalkan garis sepenuhnya, bukan menyisakan garis tanpa nama.
        """

        if not stroke_enabled:
            raise ShapeLayerError("Garis tanpa goresan tidak menghasilkan apa pun.")

        project = self.require_project()

        # Pakai geometri vektor hanya untuk menghormati Shift (lurus) dan Alt
        # (dari titik tengah), serta menolak garis yang terlalu pendek.
        try:
            geometry = build_shape_geometry(
                "line",
                start,
                end,
                stroke_color=stroke_color,
                fill_color=stroke_color,
                stroke_width=stroke_width,
                stroke_enabled=True,
                fill_enabled=False,
                constrain=constrain,
                from_center=from_center,
            )
        except ShapeError as exc:
            raise ShapeLayerError(str(exc)) from exc

        line_start, line_end = _endpoints_from_geometry(geometry)
        line_width = float(geometry.properties["stroke_width"])

        # Kalau lapis aktif adalah kanvas raster, garis harus dilebur ke
        # bitmap-nya, bukan menjadi objek yang mengambang di atasnya. Penghapus
        # pada kanvas raster hanya mengenai bitmap; objek terpisah akan tampak
        # kebal terhadap penghapus, dan itulah gejala yang dilaporkan.
        raster_target = self._raster_target(target_layer_id)
        if raster_target is not None:
            return self.apply_raster_paint_stroke(
                raster_target.layer_id,
                points=[line_start, line_end],
                brush_size=line_width,
                color=stroke_color,
                erase=False,
                opacity=1.0,
                hardness=_LINE_HARDNESS,
                smoothing=_LINE_SMOOTHING,
            )

        target, add_target = self._resolve_object_layer(
            target_layer_id, name="Layer Garis"
        )
        if not add_target:
            self._require_unlocked_layer(target.layer_id)

        cropped = render_cropped_stroke(
            canvas_width=project.canvas.width,
            canvas_height=project.canvas.height,
            points=[line_start, line_end],
            brush_size=line_width,
            color=stroke_color,
            opacity=1.0,
            hardness=_LINE_HARDNESS,
            smoothing=_LINE_SMOOTHING,
            eraser=False,
        )

        line_number = (
            sum(
                other.properties.get("source_format") == "RASTER_LINE"
                for layer in project.layers
                for other in layer.objects
            )
            + 1
        )
        label = (name or f"Garis {line_number}").strip()[:120] or f"Garis {line_number}"
        asset_ref = f"assets/{uuid4()}.png"

        item = LayerObject(
            name=label,
            kind=ObjectKind.PAINT_STROKE,
            asset_ref=asset_ref,
            transform=Transform(x=cropped.center[0], y=cropped.center[1]),
            bounds=ObjectBounds(cropped.width, cropped.height),
            properties={
                "source_format": "RASTER_LINE",
                "shape_type": "line",
                "rasterized": True,
                "brush_size": line_width,
                "brush_color": stroke_color.upper(),
                "brush_opacity": 1.0,
                "brush_hardness": _LINE_HARDNESS,
                "brush_smoothing": _LINE_SMOOTHING,
                "line_start": [line_start[0], line_start[1]],
                "line_end": [line_end[0], line_end[1]],
            },
        )

        def _mutation() -> None:
            if add_target:
                project.add_layer(target)
            self._assets[asset_ref] = cropped.content
            project.add_object(target.layer_id, item, select=True)

        self._commit_mutation(_mutation)
        return item


    def _raster_target(self, target_layer_id: str | None):
        """Lapis tujuan garis, mengikuti aturan yang sama dengan kuas.

        Kuas dan penghapus memakai ensure_active_raster_paint_layer(), yang
        membuat lapis kanvas raster bila yang aktif belum raster. Alat garis
        wajib memakai resolusi yang sama; kalau tidak, garis dan penghapus bisa
        menulis ke lapis yang berbeda dan penghapus tampak tidak mempan.

        Bila pemanggil menyebut lapis tujuan secara eksplisit, pilihan itu
        dihormati: garis pada lapis objek tetap menjadi objek goresan.
        """
        if target_layer_id:
            project = self.require_project()
            try:
                candidate = project.get_layer(target_layer_id)
            except Exception:  # noqa: BLE001 - lapis hilang diperlakukan bukan raster
                return None
            return candidate if self._is_raster_paint_layer(candidate) else None
        try:
            return self.ensure_active_raster_paint_layer()
        except Exception:  # noqa: BLE001 - mis. lapis terkunci; jatuh ke jalur objek
            return None


def _endpoints_from_geometry(geometry) -> tuple[tuple[float, float], tuple[float, float]]:
    """Ambil kembali kedua ujung garis dari geometri yang sudah dinormalkan."""
    properties = geometry.properties
    width = float(properties["geometry_width"])
    height = float(properties["geometry_height"])
    left = geometry.center_x - width / 2
    top = geometry.center_y - height / 2
    right = geometry.center_x + width / 2
    bottom = geometry.center_y + height / 2
    if str(properties.get("line_orientation")) == "anti_diagonal":
        return (left, bottom), (right, top)
    return (left, top), (right, bottom)


__all__ = ["RasterLineProjectSession"]
