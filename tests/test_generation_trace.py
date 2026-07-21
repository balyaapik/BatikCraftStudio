"""Panel log generasi + kejelasan perangkat komputasi."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from batikcraft_studio.ai import generation_trace


def _cpu_torch() -> SimpleNamespace:
    return SimpleNamespace(
        __version__="2.13.0+cpu",
        version=SimpleNamespace(cuda=None),
        cuda=SimpleNamespace(is_available=lambda: False),
    )


def _cuda_torch() -> SimpleNamespace:
    return SimpleNamespace(
        __version__="2.5.1+cu121",
        version=SimpleNamespace(cuda="12.1"),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_name=lambda index: "NVIDIA GeForce RTX 4050 Laptop GPU",
            get_device_properties=lambda index: SimpleNamespace(
                total_memory=6 * 1024**3
            ),
        ),
    )


def test_trace_reaches_the_ui_sink() -> None:
    captured: list[str] = []
    generation_trace.set_trace_sink(captured.append)
    try:
        generation_trace.trace("Variasi 1/4 dimulai")
        generation_trace.trace("  langkah 5/28")
    finally:
        generation_trace.set_trace_sink(None)
    assert captured == ["Variasi 1/4 dimulai", "  langkah 5/28"]

    # Setelah sink dilepas, trace tetap aman (hanya ke log aplikasi).
    generation_trace.trace("tanpa sink")


def test_environment_summary_reports_gpu_details() -> None:
    lines = generation_trace.describe_compute_environment(_cuda_torch())
    joined = "\n".join(lines)
    assert "2.5.1+cu121" in joined
    assert "CUDA tersedia: ya" in joined
    assert "RTX 4050" in joined and "6.0 GB VRAM" in joined


def test_cpu_build_with_nvidia_gpu_warns_the_user(monkeypatch) -> None:
    """Penyebab paling sering GPU menganggur: torch build CPU terpasang
    padahal ada GPU NVIDIA."""

    from batikcraft_studio.ai import torch_wheel_index

    monkeypatch.setattr(torch_wheel_index, "nvidia_gpu_present", lambda: True)
    lines = generation_trace.describe_compute_environment(_cpu_torch())
    joined = "\n".join(lines)
    assert "build CPU" in joined
    assert "PERINGATAN" in joined
    assert "PyTorch GPU (CUDA)" in joined


def test_dialog_exposes_terminal_style_log_panel() -> None:
    from batikcraft_studio.ui import progress_dialog

    source = inspect.getsource(progress_dialog)
    assert "Log proses" in source
    assert "def log_line" in source
    assert "def _append_log" in source


def test_batikbrew_worker_streams_steps_into_the_dialog() -> None:
    from batikcraft_studio.ai import batikbrew_generation
    from batikcraft_studio.ui import context_tool_editor_hotfixes

    engine = inspect.getsource(batikbrew_generation)
    assert "describe_compute_environment" in engine
    assert "_step_callback" in engine
    assert "callback_on_step_end" in engine

    ui = inspect.getsource(context_tool_editor_hotfixes)
    assert "set_trace_sink(sink)" in ui
    assert "set_trace_sink(None)" in ui


def test_incomplete_unet_config_no_longer_breaks_generation() -> None:
    """Regresi: folder SDXL dengan unet/config.json 'sample_size': null
    membuat diffusers menghitung `height or default_sample_size * vae_scale_factor`
    sehingga muncul "unsupported operand type(s) for *: 'NoneType' and 'int'"."""

    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    # Nilai baku SDXL dipulihkan sebelum pipeline dipanggil.
    assert "pipeline.default_sample_size = 128" in source
    assert "pipeline.vae_scale_factor = 8" in source
    # Semua angka dinormalkan; tidak ada None yang lolos ke pipeline.
    assert "render_resolution = int(render_resolution or 1024)" in source
    assert "steps = max(1, int(options.inference_steps or 30))" in source
    assert "num_inference_steps=steps," in source
    assert "guidance_scale=guidance," in source


def test_generation_failures_report_full_traceback() -> None:
    """Pesan singkat menyembunyikan penyebab; traceback harus masuk log."""

    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    assert "traceback.format_exc()" in source
    assert "type(exc).__name__" in source
