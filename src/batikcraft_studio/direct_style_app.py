"""Application shell for direct styling and drag/drop layer editing."""

from __future__ import annotations

from .viewport_app import ViewportApplication


class DirectStyleApplication(ViewportApplication):
    """Launch the direct palette, fill, stroke, and layer-tree editor."""


__all__ = ["DirectStyleApplication"]
