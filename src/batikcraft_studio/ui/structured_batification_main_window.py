"""Shim kompatibilitas; semua perintah kini ada di ``main_window.MainWindow``."""

from .main_window import StructuredBatificationMainWindow  # noqa: F401

__all__ = ["StructuredBatificationMainWindow"]
