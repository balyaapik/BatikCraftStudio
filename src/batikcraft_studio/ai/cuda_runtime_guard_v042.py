"""Release 0.4.2 preflight guard for BatikBrew SDXL generation.

A machine with an NVIDIA GPU but a CPU-only Torch wheel must not silently load
SDXL on CPU. Loading the model can exhaust system RAM before the existing render-
time memory guard runs, causing Windows to terminate the whole application.
"""

from __future__ import annotations

_PATCHED = False


def install_cuda_runtime_guard_v042() -> None:
    """Install a pre-load CUDA and CPU-memory guard for BatikBrew SDXL."""

    global _PATCHED
    if _PATCHED:
        return

    from batikcraft_studio.ai import batikbrew_generation
    from batikcraft_studio.ai.torch_runtime_integrity import installed_torch_version
    from batikcraft_studio.ai.torch_wheel_index import nvidia_gpu_present
    from batikcraft_studio.dependency_bootstrap import (
        activate_managed_ai_packages,
        default_managed_ai_package_dir,
    )
    from batikcraft_studio.imaging.structured_batification import BatificationError

    original_factory = batikbrew_generation._default_sdxl_pipeline_factory

    def guarded_factory(settings):  # type: ignore[no-untyped-def]
        activate_managed_ai_packages()
        try:
            import torch
        except ImportError:
            return original_factory(settings)

        cuda_available = bool(
            getattr(torch, "cuda", None) is not None and torch.cuda.is_available()
        )
        requested = str(getattr(settings, "device", "auto") or "auto").casefold()
        has_nvidia = nvidia_gpu_present()
        if (has_nvidia and not cuda_available) or (requested == "cuda" and not cuda_available):
            version = installed_torch_version(default_managed_ai_package_dir()) or str(
                getattr(torch, "__version__", "tidak diketahui")
            )
            raise BatificationError(
                "GPU NVIDIA terdeteksi, tetapi runtime PyTorch tidak menyediakan CUDA "
                f"(PyTorch {version}). Buka Dependencies → Pusat Dependensi AI, pasang "
                "hanya 'PyTorch GPU (CUDA)', tunggu verifikasi berhasil, lalu tutup dan "
                "buka kembali BatikCraft Studio. Generator dibatalkan agar aplikasi tidak "
                "crash karena SDXL jatuh ke CPU."
            )

        if not cuda_available:
            # Jalankan sebelum from_pretrained(), bukan sesudah model memenuhi RAM.
            from batikcraft_studio.ai.memory_guard import guard_cpu_generation

            try:
                guard_cpu_generation(int(getattr(settings, "resolution", 512)))
            except MemoryError as exc:
                raise BatificationError(str(exc)) from exc

        return original_factory(settings)

    batikbrew_generation._default_sdxl_pipeline_factory = guarded_factory
    _PATCHED = True


__all__ = ["install_cuda_runtime_guard_v042"]
