"""Command-line entry point for BatikCraft Studio."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from tkinter import messagebox

from .config import APP_NAME
from .direct_style_app import DirectStyleApplication


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> int:
    """Launch the desktop application and return a process exit code."""

    _configure_logging()

    try:
        application = DirectStyleApplication()
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
