"""Shim kompatibilitas; semua perintah kini ada di ``main_window.MainWindow``."""

from .main_window import MultiObjectMainWindow  # noqa: F401

__all__ = ["MultiObjectMainWindow"]
