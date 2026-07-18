"""Shim kompatibilitas; semua perintah kini ada di ``main_window.MainWindow``."""

from .main_window import BatikProcessMainWindow  # noqa: F401

__all__ = ["BatikProcessMainWindow"]
