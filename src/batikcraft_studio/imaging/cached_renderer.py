"""Cached tile+object renderer for viewport display.

``CachedViewportRenderer`` ties together:

* ``ObjectRenderCache`` — per-object image cache keyed by content hash
* ``TileCache`` — per-tile composed image cache keyed by project state
* ``render_project_region`` — region-level renderer with viewport culling

Usage::

    renderer = CachedViewportRenderer()

    # On each viewport paint:
    tile_image = renderer.get_or_render_tile(
        project, assets,
        project_revision=session.revision,
        visibility_revision=session.visibility_revision,
        zoom_scale=1.5,
        tile_x=0, tile_y=0,
    )

Call ``renderer.clear_project()`` when a project is closed.
Call ``renderer.invalidate_object(object_id)`` when a single object changes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageEnhance

from batikcraft_studio.domain import (
    Layer,
    LayerKind,
    LayerNodeKind,
    LayerObject,
    ObjectKind,
    Project,
)
from batikcraft_studio.imaging.affine_object import object_axis_aligned_bounds, object_shear
from batikcraft_studio.imaging.gradient import apply_gradient_to_image
from batikcraft_studio.imaging.renderer import (
    MissingRasterAssetError,
    ProjectRenderError,
    _apply_centered_shear,  # type: ignore[attr-defined]
    _effective_layer_opacity,  # type: ignore[attr-defined]
    _open_rgba,  # type: ignore[attr-defined]
    _positive_property,  # type: ignore[attr-defined]
)
from batikcraft_studio.imaging.shape import ShapeError, render_shape_image
from batikcraft_studio.imaging.tile_cache import (
    TILE_SIZE,
    tile_project_size,
    ObjectRenderCache,
    ObjectRenderCacheKey,
    TileCache,
    TileCacheKey,
    _asset_digest,
    _gradient_hash,
    clear_decoded_asset_cache,
    decoded_asset_cache_stats,
    display_source,
    tile_project_bounds,
    zoom_scale_bucket,
)
from batikcraft_studio.imaging.viewport_renderer import bounds_intersect


_MAX_OBJECT_RENDER_PX = 4096
_MAX_OBJECT_RENDER_PIXELS = 16_000_000


_INDEX_CELL = 512
_MAX_CELLS_PER_OBJECT = 64


def _object_signature(item: LayerObject) -> tuple[Any, ...]:
    """Ringkasan sifat objek yang memengaruhi hasil gambarnya.

    Dipakai untuk menyusun kunci cache per tile. ``asset_ref`` sudah cukup
    mewakili isi rasternya: aset di aplikasi ini tidak pernah ditimpa, konten
    baru selalu mendapat ref baru — asumsi yang sama yang dipakai memoisasi
    ``_asset_digest``.
    """

    transform = item.transform
    gradient = item.properties.get("gradient")
    return (
        item.object_id,
        item.kind,
        item.visible,
        item.opacity,
        item.asset_ref,
        item.bounds.width,
        item.bounds.height,
        transform.x,
        transform.y,
        transform.scale_x,
        transform.scale_y,
        transform.rotation_degrees,
        object_shear(item),
        str(item.properties.get("fill_mode", "solid")),
        _gradient_hash(dict(gradient) if gradient else None),
    )


class _LayerSpatialIndex:
    """Indeks spasial sederhana atas objek satu layer.

    Tanpa ini, setiap tile harus menelusuri SELURUH objek di layer hanya untuk
    membuang sebagian besar darinya — dan ``object_axis_aligned_bounds`` bukan
    operasi murah karena ikut menghitung rotasi/shear. Dengan 1000 objek dan 24
    tile itu 24.000 perhitungan bounds untuk setiap kali render; inilah sebabnya
    kanvas terasa berat begitu objeknya banyak, terlepas objek itu hasil AI atau
    bukan.

    Bounds dihitung sekali per revisi proyek, lalu objek dimasukkan ke sel grid.
    Setiap tile hanya memeriksa objek di sel yang bersinggungan dengannya.
    """

    __slots__ = ("bounds", "buckets", "oversized", "signatures")

    def __init__(self, layer: Layer) -> None:
        self.bounds: list[tuple[float, float, float, float]] = []
        self.buckets: dict[tuple[int, int], list[int]] = {}
        # Tanda tangan isi per objek, dipakai untuk kunci cache tile.
        self.signatures: list[tuple[Any, ...]] = []
        # Objek yang membentang sangat luas akan memenuhi terlalu banyak sel;
        # menyimpannya terpisah lebih murah daripada meledakkan indeks.
        self.oversized: list[int] = []

        for index, item in enumerate(layer.objects):
            box = object_axis_aligned_bounds(item)
            self.bounds.append(box)
            self.signatures.append(_object_signature(item))
            if not item.visible:
                continue
            gx0 = int(math.floor(box[0] / _INDEX_CELL))
            gy0 = int(math.floor(box[1] / _INDEX_CELL))
            gx1 = int(math.floor(box[2] / _INDEX_CELL))
            gy1 = int(math.floor(box[3] / _INDEX_CELL))
            if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) > _MAX_CELLS_PER_OBJECT:
                self.oversized.append(index)
                continue
            for gy in range(gy0, gy1 + 1):
                for gx in range(gx0, gx1 + 1):
                    self.buckets.setdefault((gx, gy), []).append(index)

    def candidates(self, proj_bounds: tuple[float, float, float, float]) -> list[int]:
        """Indeks objek yang mungkin bersinggungan, dalam urutan gambar."""

        left, top, right, bottom = proj_bounds
        gx0 = int(math.floor(left / _INDEX_CELL))
        gy0 = int(math.floor(top / _INDEX_CELL))
        gx1 = int(math.floor(right / _INDEX_CELL))
        gy1 = int(math.floor(bottom / _INDEX_CELL))
        found: set[int] = set(self.oversized)
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                bucket = self.buckets.get((gx, gy))
                if bucket:
                    found.update(bucket)
        # Urutan gambar (painter's algorithm) wajib dipertahankan.
        return sorted(found)


def _clamp_render_size(width: int, height: int) -> tuple[int, int]:
    """Batasi ukuran render satu objek agar alokasinya tidak pernah meledak."""

    if (
        width <= _MAX_OBJECT_RENDER_PX
        and height <= _MAX_OBJECT_RENDER_PX
        and width * height <= _MAX_OBJECT_RENDER_PIXELS
    ):
        return width, height
    ratio = min(
        _MAX_OBJECT_RENDER_PX / max(width, 1),
        _MAX_OBJECT_RENDER_PX / max(height, 1),
        (_MAX_OBJECT_RENDER_PIXELS / max(width * height, 1)) ** 0.5,
    )
    return max(1, int(width * ratio)), max(1, int(height * ratio))


def _resize_for_display(image: Image.Image, width: int, height: int) -> Image.Image:
    """Skalakan sumber yang sudah dipilih ke ukuran layar.

    Pemilihan level mipmap dikerjakan ``display_source``; di sini hanya tersisa
    faktor kecil. LANCZOS dipakai untuk perkecilan (kualitas), BICUBIC untuk
    perbesaran -- LANCZOS tidak menambah detail apa pun saat upscale, hanya
    biaya.
    """

    if image.width == width and image.height == height:
        return image
    if width >= image.width and height >= image.height:
        return image.resize((width, height), Image.Resampling.BICUBIC)
    return image.resize((width, height), Image.Resampling.LANCZOS)


class CachedViewportRenderer:
    """Stateful tile + object renderer with LRU caching.

    Parameters
    ----------
    tile_max_bytes
        Maximum bytes for the tile cache.  Default 128 MiB.
    object_max_bytes
        Maximum bytes for the object render cache.  Default 64 MiB.
    debug
        Enable hit/miss statistics.
    """

    def __init__(
        self,
        tile_max_bytes: int = 128 * 1024 * 1024,
        object_max_bytes: int = 64 * 1024 * 1024,
        *,
        debug: bool = False,
    ) -> None:
        self._tile_cache = TileCache(tile_max_bytes, debug=debug)
        self._obj_cache = ObjectRenderCache(object_max_bytes, debug=debug)
        self._debug = debug
        self._rendered_objects = 0
        self._culled_objects = 0
        self._layer_index: dict[str, tuple[int, _LayerSpatialIndex]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_render_tile(
        self,
        project: Project,
        assets: Mapping[str, bytes],
        *,
        project_revision: int,
        visibility_revision: int,
        zoom_scale: float,
        tile_x: int,
        tile_y: int,
    ) -> Image.Image:
        """Return a cached tile or render it now.

        The tile covers one ``tile_size × tile_size`` block of project space
        rendered at *zoom_scale*. ``tile_size`` mengecil saat zoom membesar
        supaya sisi tile di layar — dan karenanya biaya render serta memori —
        tetap terbatas.
        """
        bucket = zoom_scale_bucket(zoom_scale)
        tile_size = tile_project_size(zoom_scale)
        # Kunci berdasarkan ISI tile, bukan revisi global proyek. Dengan revisi
        # global, satu goresan pena mengubah revisi dan SELURUH tile kehilangan
        # cache-nya — itulah kenapa kanvas terasa dirender ulang dari nol setiap
        # kali menggambar. Dengan tanda tangan isi, hanya tile yang benar-benar
        # memuat objek yang berubah yang perlu digambar ulang.
        content_revision = self._tile_content_revision(
            project, tile_x, tile_y, tile_size, project_revision
        )
        key = TileCacheKey(
            project_revision=content_revision,
            zoom_bucket=bucket,
            tile_size=tile_size,
            tile_x=tile_x,
            tile_y=tile_y,
            canvas_background=project.canvas.background_color,
            visibility_revision=visibility_revision,
        )
        cached = self._tile_cache.get(key)
        if cached is not None:
            return cached

        # Render HARUS memakai skala yang sama dengan yang ada di kunci cache.
        # Kalau tidak, tile pertama pada satu bucket menentukan skala semua
        # tile berikutnya di bucket itu.
        tile_image = self._render_tile(
            project,
            assets,
            zoom_scale=bucket,
            tile_x=tile_x,
            tile_y=tile_y,
            tile_size=tile_size,
            project_revision=project_revision,
        )
        self._tile_cache.put(key, tile_image)
        return tile_image

    def _tile_content_revision(
        self,
        project: Project,
        tile_x: int,
        tile_y: int,
        tile_size: int,
        project_revision: int,
    ) -> int:
        """Hash isi satu tile: objek apa saja yang tampil di sana, dan bagaimana.

        Biayanya kecil karena hanya menyentuh objek yang benar-benar bersinggungan
        dengan tile (lewat indeks spasial), dan tanda tangannya sudah dihitung
        sekali saat indeks dibangun.
        """

        proj_bounds = tile_project_bounds(tile_x, tile_y, tile_size)
        parts: list[Any] = [project.canvas.background_color]
        for layer in project.layers:
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue
            if not layer.objects:
                # Layer legacy: jatuh kembali ke revisi global agar tetap aman.
                parts.append(("legacy", layer.layer_id, project_revision))
                continue
            index = self._get_layer_index(layer, project_revision)
            parts.append(("layer", layer.layer_id, _effective_layer_opacity(project, layer)))
            for position in index.candidates(proj_bounds):
                if not bounds_intersect(index.bounds[position], proj_bounds):
                    continue
                parts.append(index.signatures[position])
        return hash(tuple(parts)) & 0x7FFF_FFFF

    def _get_layer_index(self, layer: Layer, project_revision: int) -> _LayerSpatialIndex:
        """Indeks spasial layer, dibangun ulang hanya saat proyek berubah."""

        cached = self._layer_index.get(layer.layer_id)
        if cached is not None and cached[0] == project_revision:
            return cached[1]
        index = _LayerSpatialIndex(layer)
        self._layer_index[layer.layer_id] = (project_revision, index)
        return index

    def invalidate_object(self, object_id: str) -> None:
        """Invalidate all cached images for a single object."""
        self._obj_cache.invalidate_object(object_id)

    def clear_project(self) -> None:
        """Clear all caches (call on project close/open)."""
        self._tile_cache.clear()
        self._obj_cache.clear()
        self._layer_index.clear()
        # Piramida mipmap memegang gambar berukuran penuh; lepaskan juga supaya
        # menutup proyek benar-benar mengembalikan memorinya.
        clear_decoded_asset_cache()

    def invalidate_tile_cache(self) -> None:
        """Invalidate all tile cache entries (e.g. background color change)."""
        self._tile_cache.clear()

    def debug_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = dict(decoded_asset_cache_stats())
        stats.update(self._tile_cache.debug_stats())
        stats.update(self._obj_cache.debug_stats())
        stats["rendered_objects"] = self._rendered_objects
        stats["culled_objects"] = self._culled_objects
        return stats

    # ------------------------------------------------------------------
    # Internal tile rendering
    # ------------------------------------------------------------------

    def _render_tile(
        self,
        project: Project,
        assets: Mapping[str, bytes],
        zoom_scale: float,
        tile_x: int,
        tile_y: int,
        tile_size: int = TILE_SIZE,
        project_revision: int = 0,
    ) -> Image.Image:
        proj_bounds = tile_project_bounds(tile_x, tile_y, tile_size)
        tile_px = max(1, round(tile_size * zoom_scale))
        out_size = (tile_px, tile_px)

        bg_color = (*ImageColor.getrgb(project.canvas.background_color), 255)
        result = Image.new("RGBA", out_size, bg_color)

        region_left = proj_bounds[0]
        region_top = proj_bounds[1]

        for layer in project.layers:
            if layer.node_kind is LayerNodeKind.GROUP:
                continue
            if not project.is_layer_effectively_visible(layer.layer_id):
                continue

            if layer.objects:
                layer_surface = self._render_object_layer_tile(
                    layer,
                    assets,
                    proj_bounds=proj_bounds,
                    zoom_scale=zoom_scale,
                    region_left=region_left,
                    region_top=region_top,
                    out_size=out_size,
                    project_revision=project_revision,
                )
                eff_opacity = _effective_layer_opacity(project, layer)
                if eff_opacity < 1.0:
                    alpha = layer_surface.getchannel("A")
                    layer_surface.putalpha(ImageEnhance.Brightness(alpha).enhance(eff_opacity))
                result.alpha_composite(layer_surface)
                continue

            # Legacy non-object layers
            if layer.kind is not LayerKind.SHAPE:
                if layer.asset_ref is None:
                    continue
                content = assets.get(layer.asset_ref)
                if content is None:
                    raise MissingRasterAssetError(
                        f"Layer {layer.name!r} references missing asset {layer.asset_ref!r}."
                    )
            else:
                content = None

            layer_bounds = self._layer_project_bounds(layer)
            if not bounds_intersect(layer_bounds, proj_bounds):
                if self._debug:
                    self._culled_objects += 1
                continue

            prepared = self._prepare_layer_image(layer, content, zoom_scale=zoom_scale)
            eff_opacity = _effective_layer_opacity(project, layer)
            if eff_opacity != layer.opacity:
                alpha = prepared.getchannel("A")
                inherited = eff_opacity / layer.opacity if layer.opacity else 0.0
                prepared.putalpha(ImageEnhance.Brightness(alpha).enhance(inherited))
            cx = (layer.transform.x - region_left) * zoom_scale
            cy = (layer.transform.y - region_top) * zoom_scale
            dest = (round(cx - prepared.width / 2), round(cy - prepared.height / 2))
            result.alpha_composite(prepared, dest=dest)

        return result

    def _render_object_layer_tile(
        self,
        layer: Layer,
        assets: Mapping[str, bytes],
        proj_bounds: tuple[float, float, float, float],
        zoom_scale: float,
        region_left: float,
        region_top: float,
        out_size: tuple[int, int],
        project_revision: int = 0,
    ) -> Image.Image:
        surface = Image.new("RGBA", out_size, (0, 0, 0, 0))
        index = self._get_layer_index(layer, project_revision)
        objects = layer.objects
        for position in index.candidates(proj_bounds):
            item = objects[position]
            if not item.visible:
                continue
            if not bounds_intersect(index.bounds[position], proj_bounds):
                if self._debug:
                    self._culled_objects += 1
                continue

            prepared = self._get_or_render_object(item, assets, zoom_scale=zoom_scale)
            if self._debug:
                self._rendered_objects += 1
            cx = (item.transform.x - region_left) * zoom_scale
            cy = (item.transform.y - region_top) * zoom_scale
            dest_left = round(cx - prepared.width / 2)
            dest_top = round(cy - prepared.height / 2)
            if item.kind is ObjectKind.ERASER_STROKE:
                self._erase_from_surface(surface, prepared, dest_left, dest_top)
            else:
                surface.alpha_composite(prepared, dest=(dest_left, dest_top))
        return surface

    def _get_or_render_object(
        self,
        item: LayerObject,
        assets: Mapping[str, bytes],
        zoom_scale: float,
    ) -> Image.Image:
        bucket = zoom_scale_bucket(zoom_scale)
        content = assets.get(item.asset_ref) if item.asset_ref else None
        shear_x, shear_y = object_shear(item)
        gradient = item.properties.get("gradient")
        fill_mode = item.properties.get("fill_mode", "solid")

        key = ObjectRenderCacheKey(
            object_id=item.object_id,
            asset_ref=item.asset_ref,
            asset_digest=_asset_digest(content),
            bounds_w=item.bounds.width,
            bounds_h=item.bounds.height,
            scale_x=item.transform.scale_x,
            scale_y=item.transform.scale_y,
            rotation_degrees=item.transform.rotation_degrees,
            shear_x=shear_x,
            shear_y=shear_y,
            fill_mode=str(fill_mode),
            gradient_hash=_gradient_hash(dict(gradient) if gradient else None),
            opacity=item.opacity,
            render_scale_bucket=bucket,
        )
        cached = self._obj_cache.get(key)
        if cached is not None:
            return cached

        image = self._render_object(item, assets, zoom_scale=bucket)
        self._obj_cache.put(key, image)
        return image

    def _render_object(
        self,
        item: LayerObject,
        assets: Mapping[str, bytes],
        zoom_scale: float,
    ) -> Image.Image:
        width = max(1, round(item.bounds.width * abs(item.transform.scale_x) * zoom_scale))
        height = max(1, round(item.bounds.height * abs(item.transform.scale_y) * zoom_scale))
        # Pengaman keras: pada 800% sebuah hasil BatikBrew 1024 px diminta
        # dirender 8192x8192 = 256 MB. Alokasi sebesar itu gagal (dan dulu
        # kegagalannya ditelan diam-diam sehingga kanvas jadi kosong). Tile
        # hanya butuh potongan seluas layar, jadi batasi di sini.
        width, height = _clamp_render_size(width, height)

        if item.kind is ObjectKind.SHAPE:
            from batikcraft_studio.domain import LayerKind as LK
            from batikcraft_studio.domain import Transform as T

            legacy_shape = Layer(
                name=item.name,
                kind=LK.SHAPE,
                transform=T(),
                properties={
                    **dict(item.properties),
                    "pixel_width": item.bounds.width,
                    "pixel_height": item.bounds.height,
                },
            )
            try:
                image = render_shape_image(legacy_shape, width, height)
            except ShapeError as exc:
                raise ProjectRenderError(
                    f"Object {item.name!r} contains invalid shape data."
                ) from exc
        else:
            if item.asset_ref is None:
                raise MissingRasterAssetError(f"Object {item.name!r} has no raster asset.")
            content = assets.get(item.asset_ref)
            if content is None:
                raise MissingRasterAssetError(
                    f"Object {item.name!r} references missing asset {item.asset_ref!r}."
                )
            image = display_source(
                content,
                lambda: _open_rgba(content, f"Object {item.name!r}"),
                width,
                height,
            )
            image = _resize_for_display(image, width, height)

        if item.transform.scale_x < 0:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if item.transform.scale_y < 0:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        shear_x, shear_y = object_shear(item)
        if shear_x or shear_y:
            image = _apply_centered_shear(image, shear_x, shear_y)
        if item.transform.rotation_degrees:
            image = image.rotate(
                -item.transform.rotation_degrees,
                resample=Image.Resampling.BICUBIC,
                expand=True,
            )
        fill_mode = item.properties.get("fill_mode", "solid")
        gradient = item.properties.get("gradient")
        if fill_mode in ("linear_gradient", "radial_gradient") and gradient is not None:
            image = apply_gradient_to_image(image, dict(gradient), fill_mode)
        if item.opacity < 1.0:
            alpha = image.getchannel("A")
            image.putalpha(ImageEnhance.Brightness(alpha).enhance(item.opacity))
        return image

    @staticmethod
    def _prepare_layer_image(
        layer: Layer,
        content: bytes | None,
        zoom_scale: float,
    ) -> Image.Image:
        pixel_width = _positive_property(layer, "pixel_width")
        pixel_height = _positive_property(layer, "pixel_height")
        width = max(1, round(pixel_width * abs(layer.transform.scale_x) * zoom_scale))
        height = max(1, round(pixel_height * abs(layer.transform.scale_y) * zoom_scale))
        if layer.kind is LayerKind.SHAPE:
            try:
                image = render_shape_image(layer, width, height)
            except ShapeError as exc:
                raise ProjectRenderError(
                    f"Layer {layer.name!r} contains invalid shape data."
                ) from exc
        else:
            if content is None:
                raise MissingRasterAssetError(f"Layer {layer.name!r} has no raster content.")
            image = display_source(
                content,
                lambda: _open_rgba(content, f"Layer {layer.name!r}"),
                width,
                height,
            )
            image = _resize_for_display(image, width, height)
        if layer.transform.scale_x < 0:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if layer.transform.scale_y < 0:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if layer.transform.rotation_degrees:
            image = image.rotate(
                -layer.transform.rotation_degrees,
                resample=Image.Resampling.BICUBIC,
                expand=True,
            )
        if layer.opacity < 1.0:
            alpha = image.getchannel("A")
            image.putalpha(ImageEnhance.Brightness(alpha).enhance(layer.opacity))
        return image

    @staticmethod
    def _layer_project_bounds(layer: Layer) -> tuple[float, float, float, float]:
        try:
            pixel_width = _positive_property(layer, "pixel_width")
            pixel_height = _positive_property(layer, "pixel_height")
        except ProjectRenderError:
            return (-1e9, -1e9, 1e9, 1e9)
        sw = pixel_width * abs(layer.transform.scale_x)
        sh = pixel_height * abs(layer.transform.scale_y)
        angle = math.radians(layer.transform.rotation_degrees)
        bw = abs(sw * math.cos(angle)) + abs(sh * math.sin(angle))
        bh = abs(sw * math.sin(angle)) + abs(sh * math.cos(angle))
        cx, cy = layer.transform.x, layer.transform.y
        return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)

    @staticmethod
    def _erase_from_surface(
        surface: Image.Image,
        eraser: Image.Image,
        left: int,
        top: int,
    ) -> None:
        mask = Image.new("L", surface.size, 0)
        mask.paste(eraser.getchannel("A"), (left, top))
        surface.putalpha(ImageChops.subtract(surface.getchannel("A"), mask))


__all__ = ["CachedViewportRenderer"]
