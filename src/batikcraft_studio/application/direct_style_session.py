"""Direct styling and drag/drop tree commands for the Batik editor."""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageColor, ImageDraw, UnidentifiedImageError

from batikcraft_studio.domain import LayerNodeKind, LayerObject, ObjectBounds, ObjectKind

from .gradient_session import GradientProjectSession
from .session import LayerLockedError, ProjectSessionError

_STYLE_TARGETS = frozenset({"auto", "fill", "stroke"})
_TINTABLE_KINDS = frozenset(
    {ObjectKind.PAINT_STROKE, ObjectKind.MOTIF, ObjectKind.ISEN, ObjectKind.RASTER}
)


class DirectStyleProjectSession(GradientProjectSession):
    """Apply palette choices immediately and move tree nodes with one Undo step."""

    def apply_color_to_selected(
        self,
        color: str,
        *,
        target: str = "auto",
    ) -> tuple[LayerObject, ...]:
        """Apply a palette color to selected shapes or monochrome raster objects."""

        normalized = _normalize_color(color)
        if target not in _STYLE_TARGETS:
            raise ProjectSessionError(f"Target warna tidak dikenal: {target!r}.")
        selected = self.selected_objects
        if not selected:
            project = self.require_project()
            if project.active_object_id is not None:
                selected = (project.get_object(project.active_object_id),)
        if not selected:
            raise ProjectSessionError("Pilih minimal satu objek sebelum menerapkan warna.")

        project = self.require_project()
        shape_updates: dict[str, tuple[dict[str, object], ObjectBounds]] = {}
        raster_updates: dict[str, tuple[str, bytes, dict[str, object], str | None]] = {}
        for item in selected:
            self._require_unlocked_object(item.object_id)
            if item.kind is ObjectKind.SHAPE:
                closed = self.is_closed_shape(item)
                if target == "auto":
                    resolved = "fill" if closed else "stroke"
                else:
                    resolved = target
                if resolved == "fill" and not closed:
                    continue
                properties = self._updated_shape_object_properties(
                    item,
                    **(
                        {"fill_color": normalized, "fill_enabled": True}
                        if resolved == "fill"
                        else {"stroke_color": normalized, "stroke_enabled": True}
                    ),
                )
                shape_updates[item.object_id] = (
                    properties,
                    ObjectBounds(
                        float(properties["pixel_width"]),
                        float(properties["pixel_height"]),
                    ),
                )
                continue

            if target == "fill" and item.kind is ObjectKind.PAINT_STROKE:
                # A closed freehand line receives its fill as a separate editable object.
                continue
            if target == "fill" or item.kind not in _TINTABLE_KINDS or item.asset_ref is None:
                continue
            content = self._assets.get(item.asset_ref)
            if content is None:
                continue
            asset_ref = f"assets/{uuid4()}.png"
            properties = dict(item.properties)
            if item.kind is ObjectKind.PAINT_STROKE:
                properties["brush_color"] = normalized
            elif item.kind is ObjectKind.MOTIF:
                properties["warna_motif"] = normalized
            elif item.kind is ObjectKind.ISEN:
                properties["warna_isen"] = normalized
            else:
                properties["color"] = normalized
            raster_updates[item.object_id] = (
                asset_ref,
                _tint_png(content, normalized),
                properties,
                item.asset_ref,
            )

        if not shape_updates and not raster_updates:
            message = (
                "Objek yang dipilih tidak mendukung fill. Gunakan polygon/shape tertutup "
                "atau satu goresan tertutup dengan Fill tool."
                if target == "fill"
                else "Objek yang dipilih tidak mendukung perubahan warna langsung."
            )
            raise ProjectSessionError(message)

        def mutation() -> None:
            previous_refs: list[str | None] = []
            for object_id, (properties, bounds) in shape_updates.items():
                project.update_object(object_id, properties=properties, bounds=bounds)
            for (
                object_id,
                (asset_ref, content, properties, previous_ref),
            ) in raster_updates.items():
                self._assets[asset_ref] = content
                project.update_object(
                    object_id,
                    asset_ref=asset_ref,
                    properties=properties,
                )
                previous_refs.append(previous_ref)
            for previous_ref in previous_refs:
                self._remove_asset_if_unreferenced(previous_ref)

        self._commit_mutation(mutation)
        ids = (*shape_updates, *raster_updates)
        self.set_selected_objects(list(ids))
        return tuple(project.get_object(object_id) for object_id in ids)

    def fill_closed_object(self, object_id: str, color: str) -> tuple[LayerObject, ...]:
        """Fill a closed vector shape or one closed raster stroke."""

        normalized = _normalize_color(color)
        project = self.require_project()
        item = self._require_unlocked_object(object_id)
        if item.kind is ObjectKind.SHAPE:
            if not self.is_closed_shape(item):
                raise ProjectSessionError("Fill hanya berlaku untuk bentuk vector tertutup.")
            properties = self._updated_shape_object_properties(
                item,
                fill_color=normalized,
                fill_enabled=True,
            )
            bounds = ObjectBounds(
                float(properties["pixel_width"]),
                float(properties["pixel_height"]),
            )
            self._commit_mutation(
                lambda: project.update_object(
                    item.object_id,
                    properties=properties,
                    bounds=bounds,
                )
            )
            self.set_selected_objects([item.object_id])
            return (project.get_object(item.object_id),)

        if item.kind is not ObjectKind.PAINT_STROKE or item.asset_ref is None:
            raise ProjectSessionError(
                "Fill tool memerlukan shape tertutup atau satu goresan tertutup."
            )
        content = self._assets.get(item.asset_ref)
        if content is None:
            raise ProjectSessionError("Asset goresan tidak tersedia.")
        filled = _fill_enclosed_png(content, normalized)
        asset_ref = f"assets/{uuid4()}.png"
        layer_id = project.object_layer_id(item.object_id)
        layer = project.get_layer(layer_id)
        index = next(
            position
            for position, candidate in enumerate(layer.objects)
            if candidate.object_id == item.object_id
        )
        fill_object = LayerObject(
            name=f"Isi {item.name}"[:120],
            kind=ObjectKind.RASTER,
            asset_ref=asset_ref,
            transform=item.transform,
            bounds=item.bounds,
            properties={
                "source_format": "ENCLOSED_STROKE_FILL",
                "fill_color": normalized,
                "fill_source_object_id": item.object_id,
            },
        )

        def mutation() -> None:
            self._assets[asset_ref] = filled
            project.add_object(layer_id, fill_object, index=index, select=False)

        self._commit_mutation(mutation)
        self.set_selected_objects([fill_object.object_id, item.object_id])
        return (fill_object, project.get_object(item.object_id))

    def set_selected_shape_stroke_enabled(self, enabled: bool) -> tuple[LayerObject, ...]:
        """Show or hide outlines on every selected vector shape."""

        if not isinstance(enabled, bool):
            raise ProjectSessionError("Status garis tepi harus berupa boolean.")
        return self._update_selected_shape_style(stroke_enabled=enabled)

    def set_selected_shape_stroke_width(self, width: float) -> tuple[LayerObject, ...]:
        """Update outline width on selected vector shapes."""

        try:
            numeric = float(width)
        except (TypeError, ValueError) as exc:
            raise ProjectSessionError("Ukuran stroke harus berupa angka.") from exc
        if not 0.1 <= numeric <= 512:
            raise ProjectSessionError("Ukuran stroke shape harus antara 0.1 dan 512 px.")
        return self._update_selected_shape_style(stroke_width=numeric)

    def move_tree_node(self, source_iid: str, target_iid: str) -> str:
        """Move an object, layer, or folder by dropping it on another tree node."""

        source_type, source_id = _parse_tree_iid(source_iid)
        target_type, target_id = _parse_tree_iid(target_iid)
        if source_iid == target_iid:
            return source_iid
        project = self.require_project()

        if source_type == "object":
            source = self._require_unlocked_object(source_id)
            if target_type == "object":
                target_layer_id = project.object_layer_id(target_id)
                target_layer = project.get_layer(target_layer_id)
                target_index = next(
                    index
                    for index, item in enumerate(target_layer.objects)
                    if item.object_id == target_id
                )
            else:
                target_layer = project.get_layer(target_id)
                if target_layer.node_kind is LayerNodeKind.GROUP:
                    raise ProjectSessionError(
                        "Objek harus dijatuhkan pada layer, bukan folder."
                    )
                target_layer_id = target_layer.layer_id
                target_index = len(target_layer.objects)
            if project.is_layer_effectively_locked(target_layer_id):
                raise LayerLockedError(f"Layer {target_layer.name!r} sedang dikunci.")
            self._commit_mutation(
                lambda: project.move_object(
                    source.object_id,
                    target_layer_id,
                    index=target_index,
                )
            )
            self.set_selected_objects([source.object_id])
            return f"object:{source.object_id}"

        source_layer = project.get_layer(source_id)
        if project.is_layer_effectively_locked(source_layer.layer_id):
            raise LayerLockedError(f"Layer {source_layer.name!r} sedang dikunci.")
        if target_type == "object":
            target_layer = project.get_layer(project.object_layer_id(target_id))
            parent_id = target_layer.parent_id
            target_index = project.layers.index(target_layer)
        else:
            target_layer = project.get_layer(target_id)
            if target_layer.node_kind is LayerNodeKind.GROUP:
                parent_id = target_layer.layer_id
                descendants = project.descendants_of(target_layer.layer_id)
                last_descendant = max(
                    (
                        project.layers.index(layer)
                        for layer in descendants
                    ),
                    default=project.layers.index(target_layer),
                )
                target_index = last_descendant + 1
            else:
                parent_id = target_layer.parent_id
                target_index = project.layers.index(target_layer)

        def mutation() -> None:
            project.set_layer_parent(source_layer.layer_id, parent_id)
            current = project.get_layer(source_layer.layer_id)
            current_index = project.layers.index(current)
            adjusted = target_index - 1 if current_index < target_index else target_index
            adjusted = max(0, min(adjusted, len(project.layers) - 1))
            project.reorder_layer(source_layer.layer_id, adjusted)

        self._commit_mutation(mutation)
        project.set_active_layer(source_layer.layer_id)
        self.clear_object_selection()
        return f"layer:{source_layer.layer_id}"

    def _update_selected_shape_style(self, **changes: object) -> tuple[LayerObject, ...]:
        project = self.require_project()
        targets = tuple(
            item for item in self.selected_objects if item.kind is ObjectKind.SHAPE
        )
        if not targets and project.active_object_id is not None:
            candidate = project.get_object(project.active_object_id)
            if candidate.kind is ObjectKind.SHAPE:
                targets = (candidate,)
        if not targets:
            raise ProjectSessionError("Pilih minimal satu objek shape.")
        replacements: dict[str, tuple[dict[str, object], ObjectBounds]] = {}
        for item in targets:
            self._require_unlocked_object(item.object_id)
            properties = self._updated_shape_object_properties(item, **changes)
            replacements[item.object_id] = (
                properties,
                ObjectBounds(
                    float(properties["pixel_width"]),
                    float(properties["pixel_height"]),
                ),
            )

        def mutation() -> None:
            for object_id, (properties, bounds) in replacements.items():
                project.update_object(object_id, properties=properties, bounds=bounds)

        self._commit_mutation(mutation)
        self.set_selected_objects(list(replacements))
        return tuple(project.get_object(object_id) for object_id in replacements)


def _normalize_color(value: str) -> str:
    try:
        rgb = ImageColor.getrgb(value)
    except (TypeError, ValueError) as exc:
        raise ProjectSessionError(
            "Warna harus berupa warna CSS atau #RRGGBB yang valid."
        ) from exc
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def _tint_png(content: bytes, color: str) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectSessionError("Asset objek tidak dapat diwarnai.") from exc
    rgb = ImageColor.getrgb(color)[:3]
    tinted = Image.new("RGBA", image.size, (*rgb, 0))
    tinted.putalpha(image.getchannel("A"))
    output = BytesIO()
    tinted.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _fill_enclosed_png(content: bytes, color: str) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProjectSessionError("Goresan tidak dapat dibaca untuk proses fill.") from exc
    alpha = image.getchannel("A")
    barrier = alpha.point(lambda value: 0 if value >= 28 else 255)
    padded = Image.new("L", (barrier.width + 2, barrier.height + 2), 255)
    padded.paste(barrier, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    regions = padded.crop((1, 1, barrier.width + 1, barrier.height + 1))
    interior = regions.point(lambda value: 255 if value == 255 else 0)
    if interior.getbbox() is None:
        raise ProjectSessionError(
            "Garis belum membentuk bidang tertutup. Sambungkan ujung garis lalu coba Fill lagi."
        )
    rgb = ImageColor.getrgb(color)[:3]
    filled = Image.new("RGBA", image.size, (*rgb, 0))
    filled.putalpha(interior)
    output = BytesIO()
    filled.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _parse_tree_iid(iid: str) -> tuple[str, str]:
    if not isinstance(iid, str) or ":" not in iid:
        raise ProjectSessionError("Node layer drag-and-drop tidak valid.")
    node_type, node_id = iid.split(":", 1)
    if node_type not in {"layer", "object"} or not node_id:
        raise ProjectSessionError("Node layer drag-and-drop tidak valid.")
    return node_type, node_id


__all__ = ["DirectStyleProjectSession", "GradientProjectSession"]
