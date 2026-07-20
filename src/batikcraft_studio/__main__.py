"""Command-line entry point for BatikCraft Studio."""

from __future__ import annotations

import logging
import sys


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Fitur log: file berputar + penangkap crash native + hook exception,
    # supaya "force close" meninggalkan jejak yang bisa diperiksa di folder log/.
    try:
        from .logging_setup import install_file_logging

        install_file_logging()
    except Exception:  # noqa: BLE001 - logging tidak boleh menggagalkan startup
        logging.getLogger(__name__).exception("Log file gagal diaktifkan")


def _run_private_worker_if_requested() -> int | None:
    """Dispatch hidden installer modes before importing Tkinter or the application shell.

    Frozen Windows builds launch the same ``BatikCraftStudio.exe`` for dependency and
    model downloads. Without this early dispatch the child process opens another GUI,
    exits with code zero, and the parent dialog incorrectly reports 100% even though no
    package or model file was downloaded.
    """

    # Release 0.4.2 keeps the selected CPU/CUDA variant when the frozen EXE
    # launches its private pip worker.
    from .dependency_bootstrap_v042 import maybe_run_dependency_installer

    dependency_result = maybe_run_dependency_installer()
    if dependency_result is not None:
        return dependency_result

    from .runtime_model_process import maybe_run_runtime_model_installer

    return maybe_run_runtime_model_installer()


def main() -> int:
    """Launch a private worker or the desktop application and return its exit code."""

    _configure_logging()

    worker_result = _run_private_worker_if_requested()
    if worker_result is not None:
        return worker_result

    # Optional AI packages installed from the Dependencies GUI live outside the
    # one-file executable and must be activated before AI providers are imported.
    from .dependency_bootstrap import activate_managed_ai_packages

    activate_managed_ai_packages()

    # Make all later imports (including DependencyCenterWindow's from-imports)
    # receive the deterministic release-0.4.2 installer implementation.
    from .dependency_bootstrap_v042 import install_dependency_bootstrap_v042

    install_dependency_bootstrap_v042()

    # Create cache/runtime/model-library directories before any Windows folder picker,
    # Hugging Face worker, or installer dialog tries to use them.
    from .managed_storage import ensure_managed_storage

    ensure_managed_storage()

    # Managed packages can contain Hugging Face Hub 0.x and previously persisted
    # cache paths. Apply compatibility before any AI dialog imports downloader symbols.
    from .runtime_compatibility import install_runtime_compatibility

    install_runtime_compatibility()

    # The user-visible Settings preference is authoritative for this process. Online
    # mode clears inherited Hugging Face offline variables; Offline mode sets them.
    from .ai.model_connectivity import apply_saved_model_connectivity

    apply_saved_model_connectivity()

    # A runtime is ready only when model_index, tokenizers, encoders, UNet, VAE, and
    # scheduler exist and the critical weight files have realistic byte sizes.
    from .ai.sdxl_runtime_integrity import install_sdxl_runtime_integrity

    install_sdxl_runtime_integrity()

    # Online repair must reconcile every local SDXL file against repository metadata.
    # Names or exit codes alone are never accepted as proof of a complete download.
    from .ai.sdxl_repository_repair import install_sdxl_repository_repair

    install_sdxl_repository_repair()

    # Keep current Diffusers releases quiet and correct: use component-level VAE
    # controls, load UNet-only LoRAs without probing absent text encoders, and fit
    # BatikBrew prompts into both SDXL CLIP tokenizers before inference.
    from .ai.diffusers_inference_compat import (
        install_diffusers_inference_compatibility,
    )

    install_diffusers_inference_compatibility()

    # Locally converted SDXL folders may mark tokenizer_2/text_encoder_2 as empty.
    # Repair those components before device placement and CPU-offload hooks are set.
    from .ai.sdxl_text_component_repair import install_sdxl_text_component_repair

    install_sdxl_text_component_repair()

    # When Settings is Online, mandatory SDXL text components may be restored from
    # the official cache/repository. Offline mode remains fully cache-only.
    from .ai.sdxl_online_component_repair import (
        install_sdxl_online_component_repair,
    )

    install_sdxl_online_component_repair()

    # Keep the model manager, persisted local-model profile, and BatikBrew
    # generation path synchronized before the application session is constructed.
    from .ai.lora_activation_persistence import install_lora_activation_persistence

    install_lora_activation_persistence()

    # Refuse to load SDXL on CPU when an NVIDIA GPU exists but the managed wheel
    # is CPU-only. The guard runs before from_pretrained() can exhaust RAM.
    from .ai.cuda_runtime_guard_v042 import install_cuda_runtime_guard_v042

    install_cuda_runtime_guard_v042()

    # This must happen before tkinter or any application shell is imported.
    # Otherwise ``python -m batikcraft_studio`` is grouped under python.exe and
    # Windows may keep the Python icon in the taskbar.
    from .windows_identity import prepare_windows_app_identity

    prepare_windows_app_identity()

    import tkinter as tk
    from tkinter import messagebox

    from .app_icon import apply_app_icon
    from .config import APP_NAME
    from .ui.cache_directory_guard import install_cache_directory_guard
    from .ui.canvas_selection_semantics import install_canvas_selection_semantics
    from .ui.dependency_cuda_selection_patch import (
        install_dependency_cuda_selection_patch,
    )
    from .ui.dependency_integrity_patch import install_dependency_integrity_patch
    from .ui.dependency_profiles_patch import install_dependency_profiles_patch
    from .ui.inkscape_canvas_patch import install_inkscape_canvas_patch
    from .ui.inkscape_pointer_hotpath import install_inkscape_pointer_hotpath
    from .ui.inkscape_renderer_compat import install_inkscape_renderer_compat
    from .ui.marketplace_model_progress import install_marketplace_model_progress
    from .ui.model_connectivity_settings_patch import (
        install_model_connectivity_settings_patch,
    )
    from .ui.realtime_canvas_patch import install_realtime_canvas_patch
    from .ui.runtime_installer_completion_guard import (
        install_runtime_installer_completion_guard,
    )

    install_marketplace_model_progress()
    install_dependency_integrity_patch()
    install_dependency_cuda_selection_patch()
    install_model_connectivity_settings_patch()
    install_dependency_profiles_patch()
    install_cache_directory_guard()
    install_runtime_installer_completion_guard()
    install_realtime_canvas_patch()
    install_inkscape_canvas_patch()
    install_inkscape_pointer_hotpath()
    install_inkscape_renderer_compat()
    install_canvas_selection_semantics()

    from .integrated_market_app import ContextToolApplication
    from .ui.ai_menu_consolidation_patch import install_ai_menu_consolidation

    install_ai_menu_consolidation(ContextToolApplication)

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
