"""Resolusi perangkat universal: semua tipe GPU terdeteksi, tanpa error keras."""

from __future__ import annotations

from types import SimpleNamespace

from batikcraft_studio.ai.device_resolution import (
    available_torch_devices,
    describe_device_fallback,
    resolve_torch_device,
)


def _fake_torch(*, cuda: bool = False, xpu: bool | None = None, mps: bool | None = None):
    namespace = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(),
    )
    if xpu is not None:
        namespace.xpu = SimpleNamespace(is_available=lambda: xpu)
    if mps is not None:
        namespace.backends.mps = SimpleNamespace(is_available=lambda: mps)
    return namespace


def test_cuda_request_falls_back_to_cpu_instead_of_failing() -> None:
    torch = _fake_torch(cuda=False)
    assert resolve_torch_device(torch, "cuda") == "cpu"
    note = describe_device_fallback("cuda", "cpu")
    assert note is not None and "CUDA" in note and "CPU" in note


def test_intel_xpu_and_apple_mps_are_detected() -> None:
    assert resolve_torch_device(_fake_torch(xpu=True), "auto") == "xpu"
    assert resolve_torch_device(_fake_torch(mps=True), "auto") == "mps"
    assert available_torch_devices(_fake_torch(cuda=True, xpu=True, mps=True)) == (
        "cuda",
        "xpu",
        "mps",
        "cpu",
    )


def test_explicit_available_device_is_honoured() -> None:
    assert resolve_torch_device(_fake_torch(cuda=True), "cuda") == "cuda"
    assert resolve_torch_device(_fake_torch(cuda=True), "cpu") == "cpu"
    assert describe_device_fallback("auto", "cpu") is None


def test_diagnosis_reports_fallback_as_warning_not_error() -> None:
    from batikcraft_studio.ai.runtime_settings import _effective_device

    assert _effective_device("cuda", False, False) == "cpu"
    assert _effective_device("mps", False, False) == "cpu"
    assert _effective_device("cuda", True, False) == "cuda"
