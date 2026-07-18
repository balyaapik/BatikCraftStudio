"""Make the Dependencies window report actual SDXL component integrity."""

from __future__ import annotations

from batikcraft_studio.ai import runtime_model_installer
from batikcraft_studio.ai.sdxl_runtime_integrity import inspect_batikbrew_runtime
from batikcraft_studio.ui import dependency_manager_dialog

_INSTALLED = False


def install_dependency_integrity_patch() -> None:
    """Patch the existing Dependencies window without duplicating its installer UI."""

    global _INSTALLED
    if _INSTALLED:
        return

    window_class = dependency_manager_dialog.DependencyManagerWindow
    original_build = window_class._build
    original_refresh = window_class.refresh

    def build(window: object) -> None:
        original_build(window)
        window.install_all_button.configure(  # type: ignore[attr-defined]
            text="Periksa & Reparasi Semua AI + BatikBrew SDXL"
        )

    def refresh(window: object) -> None:
        original_refresh(window)

        package_total = len(dependency_manager_dialog.PYTHON_AI_DEPENDENCIES)
        package_ready = sum(
            1
            for module, _requirement in dependency_manager_dialog.PYTHON_AI_DEPENDENCIES
            if dependency_manager_dialog.module_available(module)
        )

        paths = runtime_model_installer.batikbrew_runtime_model_paths()
        issues = inspect_batikbrew_runtime(paths.base_model)
        if not paths.base_model.exists():
            sdxl_status = "belum terpasang"
        elif issues:
            visible = "\n    • ".join(issues[:8])
            remaining = len(issues) - min(len(issues), 8)
            suffix = f"\n    • dan {remaining} masalah lain" if remaining else ""
            sdxl_status = f"PERLU REPARASI\n    • {visible}{suffix}"
        else:
            sdxl_status = f"siap — {paths.base_model}"

        sd15 = runtime_model_installer.find_installed_runtime_models()
        sd15_status = str(sd15.base_model) if sd15 is not None else "belum terpasang"
        window.runtime_status.set(  # type: ignore[attr-defined]
            f"Python AI Packages: {package_ready}/{package_total} terdeteksi\n"
            f"BatikBrew SDXL: {sdxl_status}\n"
            f"SD1.5 + ControlNet: {sd15_status}\n"
            "LoRA: buka pengelola model untuk instalasi paket .batikmodel."
        )

        all_ready = package_ready == package_total and not issues
        window.install_progress_text.set(  # type: ignore[attr-defined]
            "Semua komponen siap" if all_ready else "Ada komponen yang perlu diperbaiki"
        )

    def install_complete_batikbrew(window: object) -> None:
        if window._process is not None:  # type: ignore[attr-defined]
            window._installation_already_running()  # type: ignore[attr-defined]
            return
        window._continue_with_sdxl = True  # type: ignore[attr-defined]
        missing = window._missing_requirements()  # type: ignore[attr-defined]
        if missing:
            window._append_log(  # type: ignore[attr-defined]
                "Paket Python belum lengkap. Menjalankan instalasi/reparasi terlebih dahulu."
            )
            window.install_python_dependencies(  # type: ignore[attr-defined]
                continue_with_sdxl=True
            )
            return

        window._append_log(  # type: ignore[attr-defined]
            "Paket Python siap. Memeriksa file SDXL satu per satu dan memperbaiki "
            "komponen yang hilang…"
        )
        window.after(150, window.install_sdxl)  # type: ignore[attr-defined]

    window_class._build = build  # type: ignore[assignment]
    window_class.refresh = refresh  # type: ignore[assignment]
    window_class.install_complete_batikbrew = install_complete_batikbrew  # type: ignore[assignment]
    window_class._batikcraft_integrity_patch = True  # type: ignore[attr-defined]
    _INSTALLED = True


__all__ = ["install_dependency_integrity_patch"]
