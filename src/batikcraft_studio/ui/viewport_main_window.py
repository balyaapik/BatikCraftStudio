"""Shim kompatibilitas; semua perintah kini ada di ``main_window.MainWindow``."""

from .main_window import ViewportMainWindow  # noqa: F401

__all__ = ["ViewportMainWindow"]
