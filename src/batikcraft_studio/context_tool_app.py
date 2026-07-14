"""Application shell for contextual Batik tools, destructive erasing, and panel tabs."""

from __future__ import annotations

from .direct_style_app import DirectStyleApplication


class ContextToolApplication(DirectStyleApplication):
    """Launch the contextual tool-options and destructive-eraser editor."""


__all__ = ["ContextToolApplication"]
