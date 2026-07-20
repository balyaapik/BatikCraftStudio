"""Log file aplikasi + penangkap crash untuk diagnosis "force close".

Semua kejadian penting ditulis ke folder ``log/`` di data aplikasi per-user:

* ``batikcraft.log``      — log berjalan (INFO+), berputar 5×2 MB.
* ``crash-native.log``    — jejak faulthandler bila proses mati di kode native
                            (segfault/driver GPU), penyebab umum force close.

Exception yang tidak tertangani — di thread utama, thread worker, dan callback
Tk — dicatat lengkap dengan traceback alih-alih menghilang bersama jendelanya.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

_LOGGER = logging.getLogger("batikcraft_studio")
_CRASH_FILE_HANDLE = None  # dipegang selamanya agar faulthandler tetap hidup
_INSTALLED = False


def default_log_dir() -> Path:
    """Folder ``log/`` di samping folder dependencies (data per-user/app)."""

    from batikcraft_studio.dependency_bootstrap import (
        default_managed_dependency_root,
    )

    return default_managed_dependency_root().parent / "log"


def install_file_logging() -> Path:
    """Pasang log file + faulthandler + hook exception. Idempoten."""

    global _CRASH_FILE_HANDLE, _INSTALLED
    log_dir = default_log_dir()
    if _INSTALLED:
        return log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "batikcraft.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)
    if logging.getLogger().level > logging.INFO:
        logging.getLogger().setLevel(logging.INFO)

    # Crash native (akses memori ilegal, driver GPU, OOM keras) tidak melewati
    # logging Python — faulthandler menulis traceback semua thread ke file.
    try:
        _CRASH_FILE_HANDLE = open(  # noqa: SIM115 - harus tetap terbuka
            log_dir / "crash-native.log", "a", encoding="utf-8"
        )
        faulthandler.enable(file=_CRASH_FILE_HANDLE, all_threads=True)
    except OSError:
        _CRASH_FILE_HANDLE = None

    _install_exception_hooks()
    _INSTALLED = True
    _LOGGER.info("Log file aktif di %s", log_dir)
    return log_dir


def _install_exception_hooks() -> None:
    previous_excepthook = sys.excepthook

    def log_uncaught(exc_type, exc, tb):  # noqa: ANN001
        _LOGGER.critical(
            "Exception tidak tertangani:\n%s",
            "".join(traceback.format_exception(exc_type, exc, tb)),
        )
        previous_excepthook(exc_type, exc, tb)

    sys.excepthook = log_uncaught

    previous_thread_hook = threading.excepthook

    def log_thread_exception(args) -> None:  # noqa: ANN001
        _LOGGER.critical(
            "Exception di thread %r:\n%s",
            getattr(args.thread, "name", "?"),
            "".join(
                traceback.format_exception(
                    args.exc_type, args.exc_value, args.exc_traceback
                )
            ),
        )
        previous_thread_hook(args)

    threading.excepthook = log_thread_exception


def install_tk_exception_logging(root) -> None:  # noqa: ANN001
    """Callback Tk yang meledak dicatat ke log, tidak diam-diam."""

    def report_callback_exception(exc_type, exc, tb):  # noqa: ANN001
        _LOGGER.error(
            "Exception pada callback Tk:\n%s",
            "".join(traceback.format_exception(exc_type, exc, tb)),
        )

    root.report_callback_exception = report_callback_exception


__all__ = [
    "default_log_dir",
    "install_file_logging",
    "install_tk_exception_logging",
]
