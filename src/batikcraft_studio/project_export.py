"""Shared helpers for flattened image and marketplace package exports."""

from __future__ import annotations

import re
from collections.abc import Mapping
from io import BytesIO

from PIL import Image

from batikcraft_studio.domain import ObjectKind, Project
from batikcraft_studio.imaging import render_project_preview

_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def render_project_jpeg(
    project: Project,
    assets: Mapping[str, bytes],
    *,
    quality: int = 95,
) -> bytes:
    """Render the complete canvas and encode a high-quality flattened JPEG."""

    if isinstance(quality, bool) or not isinstance(quality, int) or not 1 <= quality <= 100:
        raise ValueError("quality JPEG harus berada di antara 1 dan 100.")
    rendered = render_project_preview(
        project,
        assets,
        max_width=project.canvas.width,
        max_height=project.canvas.height,
    )
    image = rendered.image.convert("RGB")
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        subsampling=0,
    )
    return output.getvalue()


def discover_project_colors(project: Project) -> tuple[str, ...]:
    """Collect unique HEX colors from canvas, layer, object, and gradient metadata."""

    colors: list[str] = []
    seen: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, str):
            candidate = value.strip().upper()
            if _COLOR_PATTERN.fullmatch(candidate) and candidate not in seen:
                colors.append(candidate)
                seen.add(candidate)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                collect(item)
            return
        if isinstance(value, (tuple, list)):
            for item in value:
                collect(item)

    collect(project.canvas.background_color)
    for layer in project.layers:
        collect(layer.properties)
        for item in layer.objects:
            collect(item.properties)
    return tuple(colors[:64])


def discover_project_motifs(project: Project) -> tuple[str, ...]:
    """Infer motif names from motif objects and common style metadata."""

    motifs: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        normalized = value.strip()
        if not normalized:
            return
        key = normalized.casefold()
        if key not in seen:
            motifs.append(normalized[:80])
            seen.add(key)

    for layer in project.layers:
        for key in ("motif", "motif_type", "style", "batik_style"):
            add(layer.properties.get(key))
        for item in layer.objects:
            if item.kind is ObjectKind.MOTIF:
                add(item.name)
            for key in ("motif", "motif_type", "style", "batik_style"):
                add(item.properties.get(key))
    return tuple(motifs[:50])


def creator_id_suggestion(creator_name: str) -> str:
    """Create a conservative website-username suggestion from the project creator."""

    value = re.sub(r"[^A-Za-z0-9._-]+", "-", creator_name.strip()).strip("-._")
    return (value or "creator")[:120]


__all__ = [
    "creator_id_suggestion",
    "discover_project_colors",
    "discover_project_motifs",
    "render_project_jpeg",
]
