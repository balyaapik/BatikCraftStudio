"""Cegah 'aplikasi tiba-tiba tertutup' saat generasi AI.

Dua penyebab dari log lapangan:
1. torch wheel CPU-only terpasang walau ada GPU NVIDIA -> SDXL di CPU.
2. RAM tidak cukup untuk SDXL fp32 di CPU -> proses dibunuh OS tanpa dialog.
"""

from __future__ import annotations

import inspect

import pytest

from batikcraft_studio.ai import memory_guard, torch_wheel_index


def test_cuda_wheel_index_used_only_when_nvidia_gpu_present(monkeypatch) -> None:
    monkeypatch.setattr(torch_wheel_index, "nvidia_gpu_present", lambda: True)
    assert torch_wheel_index.torch_index_arguments() == [
        "--extra-index-url",
        torch_wheel_index.CUDA_WHEEL_INDEX,
    ]

    monkeypatch.setattr(torch_wheel_index, "nvidia_gpu_present", lambda: False)
    assert torch_wheel_index.torch_index_arguments() == []


def test_installer_commands_include_torch_index() -> None:
    from batikcraft_studio import dependency_bootstrap

    source = inspect.getsource(dependency_bootstrap)
    # Jalur frozen dan non-frozen sama-sama menyisipkan index wheel torch;
    # jalur non-frozen kini meneruskan varian pilihan pengguna (CPU/CUDA).
    assert "*_torch_index_arguments(torch_variant)," in source
    assert "*_torch_index_arguments()," in source


def test_low_memory_refuses_with_clear_message_instead_of_dying(monkeypatch) -> None:
    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 4.0)
    with pytest.raises(MemoryError, match="RAM bebas"):
        memory_guard.guard_cpu_generation(1024)


def test_tight_memory_lowers_resolution(monkeypatch) -> None:
    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 11.0)
    resolution, note = memory_guard.guard_cpu_generation(1024)
    assert resolution == 768
    assert note is not None and "diturunkan" in note


def test_ample_memory_keeps_requested_resolution(monkeypatch) -> None:
    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 32.0)
    assert memory_guard.guard_cpu_generation(1024) == (1024, None)


def test_generation_applies_guard_and_logs_device() -> None:
    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    assert "guard_cpu_generation" in source
    assert "width=render_resolution" in source
    assert "Pipeline SDXL siap" in source


def test_torch_variant_detection_reads_version_string(tmp_path, monkeypatch) -> None:
    """Regresi: build CPU sempat terbaca sebagai CUDA karena teks terpotong,
    sehingga tabel menandai 'PyTorch GPU Terpasang' padahal torch +cpu."""

    from batikcraft_studio.ui import dependency_catalog

    packages = tmp_path / "site-packages"
    (packages / "torch").mkdir(parents=True)
    monkeypatch.setattr(
        dependency_catalog, "default_managed_ai_package_dir", lambda: packages
    )

    (packages / "torch" / "version.py").write_text(
        "__version__ = '2.13.0+cpu'\ndebug = False\ncuda: Optional[str] = None\n",
        encoding="utf-8",
    )
    assert dependency_catalog.installed_torch_variant() == "cpu"

    (packages / "torch" / "version.py").write_text(
        "__version__ = '2.5.1+cu121'\ndebug = False\ncuda: Optional[str] = '12.1'\n",
        encoding="utf-8",
    )
    assert dependency_catalog.installed_torch_variant() == "cuda"


def test_explicit_variant_uses_index_url_not_extra_index() -> None:
    """--extra-index-url membuat pip memilih versi tertinggi lintas index,
    sehingga wheel CPU PyPI mengalahkan wheel CUDA. Varian eksplisit wajib
    memakai --index-url."""

    from batikcraft_studio.ai.torch_wheel_index import CPU_WHEEL_INDEX, CUDA_WHEEL_INDEX
    from batikcraft_studio.dependency_bootstrap import managed_ai_install_command

    cuda = managed_ai_install_command(["torch>=2.4"], frozen=False, torch_variant="cuda")
    assert "--index-url" in cuda and CUDA_WHEEL_INDEX in cuda
    assert "--extra-index-url" not in cuda

    cpu = managed_ai_install_command(["torch>=2.4"], frozen=False, torch_variant="cpu")
    assert "--index-url" in cpu and CPU_WHEEL_INDEX in cpu


def test_cpu_paths_halve_memory_and_guard_both_providers() -> None:
    import inspect

    from batikcraft_studio.ai import batikbrew_generation, pretrained_batification

    pattern_source = inspect.getsource(batikbrew_generation)
    canvas_source = inspect.getsource(pretrained_batification)
    for source in (pattern_source, canvas_source):
        assert "_cpu_friendly_dtype" in source
        assert "guard_cpu_generation" in source
    assert "enable_vae_tiling" in canvas_source


def test_model_load_is_guarded_before_weights_are_read(monkeypatch) -> None:
    """Kasus lapangan: RAM 13.6/15.7 GB terpakai (sisa ~2 GB) lalu aplikasi
    tertutup sendiri saat Generate BatikBrew. Pemuatan bobot adalah puncak
    pemakaian RAM dan harus diperiksa sebelum dimulai."""

    from batikcraft_studio.ai import memory_guard

    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 2.0)
    with pytest.raises(MemoryError, match="RAM bebas"):
        memory_guard.guard_model_load(device="cuda", dtype_name="torch.float16")

    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 24.0)
    memory_guard.guard_model_load(device="cuda", dtype_name="torch.float16")

    # float32 memerlukan dua kali lipat dibanding float16.
    monkeypatch.setattr(memory_guard, "available_memory_gb", lambda: 10.0)
    memory_guard.guard_model_load(device="cpu", dtype_name="torch.float16")
    with pytest.raises(MemoryError):
        memory_guard.guard_model_load(device="cpu", dtype_name="torch.float32")


def test_pipelines_stream_weights_and_offload_on_small_vram() -> None:
    import inspect

    from batikcraft_studio.ai import batikbrew_generation, pretrained_batification

    pattern = inspect.getsource(batikbrew_generation)
    canvas = inspect.getsource(pretrained_batification)
    # low_cpu_mem_usage memangkas puncak RAM saat memuat dari ~2x menjadi ~1x.
    assert "low_cpu_mem_usage=True" in pattern
    assert "low_cpu_mem_usage=True" in canvas
    assert "guard_model_load" in pattern and "guard_model_load" in canvas
    # GPU laptop 6 GB (mis. RTX 4050) wajib offload untuk SDXL fp16.
    assert "_vram_is_tight" in pattern
    assert "total_gb < 8.0" in pattern
