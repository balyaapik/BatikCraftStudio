"""Command-line entry point for BatikCraft Studio."""

from __future__ import annotations

import logging
import sys


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> int:
    """Launch the desktop application and return a process exit code."""

    _configure_logging()

    # This must happen before tkinter or any application shell is imported.
    # Otherwise ``python -m batikcraft_studio`` is grouped under python.exe and
    # Windows may keep the Python icon in the taskbar.
    from .windows_identity import prepare_windows_app_identity

    prepare_windows_app_identity()

    import tkinter as tk
    from tkinter import messagebox

    from .config import APP_NAME
    from .integrated_market_app import ContextToolApplication

    try:
        application = ContextToolApplication()
        application.run()
    except tk.TclError as exc:
        logging.exception("Tkinter could not initialize")
        try:
            messagebox.showerror(APP_NAME, f"The application could not start:\n{exc}")
        except tk.TclError:
            print(f"{APP_NAME} could not start: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - final desktop safety net
        logging.exception("Unexpected application error")
        try:
            messagebox.showerror(APP_NAME, f"Unexpected error:\n{exc}")
        except tk.TclError:
            print(f"Unexpected {APP_NAME} error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
