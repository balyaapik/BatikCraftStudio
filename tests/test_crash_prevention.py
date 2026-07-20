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
    assert source.count("*_torch_index_arguments(),") == 2


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
