"""Application-wide clipboard for generated raster images."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from batikcraft_studio.imaging.raster import normalize_raster_image


@dataclass(frozen=True, slots=True)
class GeneratedImageClipboardPayload:
    """One canonical PNG copied from an AI generation result."""

    name: str
    content: bytes
    width: int
    height: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


class GeneratedImageClipboard:
    """Keep generated images copyable between dialogs and the editor canvas."""

    def __init__(self) -> None:
        self._payload: GeneratedImageClipboardPayload | None = None

    @property
    def has_image(self) -> bool:
        return self._payload is not None

    def copy(
        self,
        content: bytes,
        *,
        name: str = "Hasil BatikBrew",
        metadata: Mapping[str, Any] | None = None,
    ) -> GeneratedImageClipboardPayload:
        raster = normalize_raster_image(content)
        payload = GeneratedImageClipboardPayload(
            name=str(name).strip() or "Hasil BatikBrew",
            content=raster.content,
            width=raster.width,
            height=raster.height,
            metadata=MappingProxyType(dict(metadata or {})),
        )
        self._payload = payload
        return payload

    def read(self) -> GeneratedImageClipboardPayload | None:
        return self._payload

    def clear(self) -> None:
        self._payload = None


_CLIPBOARD = GeneratedImageClipboard()


def get_generated_image_clipboard() -> GeneratedImageClipboard:
    return _CLIPBOARD


__all__ = [
    "GeneratedImageClipboard",
    "GeneratedImageClipboardPayload",
    "get_generated_image_clipboard",
]
