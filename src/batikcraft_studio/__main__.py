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

    # Optional AI packages installed from the Dependencies GUI live outside the
    # one-file executable and must be activated before AI providers are imported.
    from .dependency_bootstrap import activate_managed_ai_packages

    activate_managed_ai_packages()

    # Managed packages can contain Hugging Face Hub 0.x and previously persisted
    # cache paths. Apply compatibility before any AI dialog imports downloader symbols.
    from .runtime_compatibility import install_runtime_compatibility

    install_runtime_compatibility()

    # Keep current Diffusers releases quiet and correct: use component-level VAE
    # controls, load UNet-only LoRAs without probing absent text encoders, and fit
    # BatikBrew prompts into both SDXL CLIP tokenizers before inference.
    from .ai.diffusers_inference_compat import (
        install_diffusers_inference_compatibility,
    )

    install_diffusers_inference_compatibility()

    # Keep the model manager, persisted local-model profile, and BatikBrew
    # generation path synchronized before the application session is constructed.
    from .ai.lora_activation_persistence import install_lora_activation_persistence

    install_lora_activation_persistence()

    # This must happen before tkinter or any application shell is imported.
    # Otherwise ``python -m batikcraft_studio`` is grouped under python.exe and
    # Windows may keep the Python icon in the taskbar.
    from .windows_identity import prepare_windows_app_identity

    prepare_windows_app_identity()

    import tkinter as tk
    from tkinter import messagebox

    from .app_icon import apply_app_icon
    from .config import APP_NAME
    from .ui.canvas_selection_semantics import install_canvas_selection_semantics
    from .ui.inkscape_canvas_patch import install_inkscape_canvas_patch
    from .ui.inkscape_pointer_hotpath import install_inkscape_pointer_hotpath
    from .ui.inkscape_renderer_compat import install_inkscape_renderer_compat
    from .ui.marketplace_model_progress import install_marketplace_model_progress
    from .ui.realtime_canvas_patch import install_realtime_canvas_patch

    install_marketplace_model_progress()
    install_realtime_canvas_patch()
    install_inkscape_canvas_patch()
    install_inkscape_pointer_hotpath()
    install_inkscape_renderer_compat()
    install_canvas_selection_semantics()

    from .integrated_market_app import ContextToolApplication

    try:
        application = ContextToolApplication()
        # Apply once to the newly created HWND, then again after the window is
        # mapped. The second pass is important for TkinterDnD and python.exe
        # launches because Windows creates a native wrapper HWND lazily.
        apply_app_icon(application.root)
        application.root.after_idle(lambda: apply_app_icon(application.root))
        application.root.after(300, lambda: apply_app_icon(application.root))
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
