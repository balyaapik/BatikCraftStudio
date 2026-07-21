"""Regresi crash driver CUDA (0xC0000409 di nvcuda64.dll, laporan v0.5.7)."""

from __future__ import annotations

import pytest

from batikcraft_studio.ai import cuda_stability

_ORIGINAL_STATE_DIR = cuda_stability._state_dir


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(cuda_stability, "_state_dir", lambda: tmp_path)
    return tmp_path


def test_sentinel_hanya_ditulis_untuk_cuda():
    cuda_stability.begin_gpu_attempt("cpu", "model")
    assert not cuda_stability.sentinel_path().exists()

    cuda_stability.begin_gpu_attempt("cuda", "model")
    assert cuda_stability.sentinel_path().exists()


def test_generasi_sukses_membersihkan_sentinel_dan_riwayat():
    cuda_stability.begin_gpu_attempt("cuda", "model")
    cuda_stability.end_gpu_attempt("cuda", succeeded=True)

    assert not cuda_stability.sentinel_path().exists()
    assert not cuda_stability.crash_record_path().exists()
    assert cuda_stability.detect_previous_gpu_crash() is None


def test_sentinel_tertinggal_dihitung_sebagai_crash():
    cuda_stability.begin_gpu_attempt("cuda", "model-a")
    # Proses "mati" tanpa sempat memanggil end_gpu_attempt.

    record = cuda_stability.detect_previous_gpu_crash()
    assert record is not None
    assert record.count == 1
    assert record.device == "cuda"
    assert record.model == "model-a"
    assert not record.should_force_cpu
    assert not cuda_stability.sentinel_path().exists()


def test_crash_berulang_menurunkan_perangkat_ke_cpu():
    for _ in range(cuda_stability.MAX_GPU_CRASHES):
        cuda_stability.begin_gpu_attempt("cuda", "model-a")
        cuda_stability.detect_previous_gpu_crash()

    device, warning = cuda_stability.guard_device("cuda")
    assert device == "cpu"
    assert warning and "driver NVIDIA" in warning


def test_crash_tunggal_masih_mengizinkan_gpu():
    cuda_stability.begin_gpu_attempt("cuda", "model-a")

    device, warning = cuda_stability.guard_device("cuda")
    assert device == "cuda"
    assert warning is None


def test_guard_device_tidak_menyentuh_cpu():
    assert cuda_stability.guard_device("cpu") == ("cpu", None)


def test_riwayat_direset_setelah_generasi_gpu_berhasil():
    cuda_stability.begin_gpu_attempt("cuda", "model-a")
    cuda_stability.detect_previous_gpu_crash()
    assert cuda_stability.crash_record_path().exists()

    cuda_stability.begin_gpu_attempt("cuda", "model-a")
    cuda_stability.end_gpu_attempt("cuda", succeeded=True)

    assert cuda_stability.guard_device("cuda") == ("cuda", None)


def test_apply_cuda_safety_mematikan_autotune():
    class _Cudnn:
        benchmark = True
        allow_tf32 = True

    class _Matmul:
        allow_tf32 = True

    cudnn = _Cudnn()
    matmul = _Matmul()

    class _Backends:
        pass

    backends = _Backends()
    backends.cudnn = cudnn
    backends.cuda = type("C", (), {})()
    backends.cuda.matmul = matmul
    torch = type("T", (), {})()
    torch.backends = backends

    applied = cuda_stability.apply_cuda_safety(torch)

    assert cudnn.benchmark is False
    assert cudnn.allow_tf32 is False
    assert matmul.allow_tf32 is False
    assert any("cudnn.benchmark" in item for item in applied)


def test_apply_cuda_safety_aman_untuk_torch_tanpa_backends():
    assert cuda_stability.apply_cuda_safety(object())


def test_folder_status_tidak_bisa_ditulis_tidak_menggagalkan_generasi(monkeypatch):
    """Regresi 0.5.8: WinError 5 pada C:\\Program Files\\BatikCraft Studio\\log.

    Pengaman crash GPU tidak boleh pernah menggagalkan generasi; kalau folder
    statusnya tidak bisa ditulis, fitur menonaktifkan diri diam-diam.
    """

    monkeypatch.setattr(cuda_stability, "_state_dir", lambda: None)

    cuda_stability.begin_gpu_attempt("cuda", "model")
    cuda_stability.end_gpu_attempt("cuda", succeeded=True)
    cuda_stability.clear_gpu_crash_history()

    assert cuda_stability.sentinel_path() is None
    assert cuda_stability.crash_record_path() is None
    assert cuda_stability.detect_previous_gpu_crash() is None
    assert cuda_stability.guard_device("cuda") == ("cuda", None)


def test_state_dir_menelan_permission_error(monkeypatch):
    from batikcraft_studio import logging_setup

    def _denied() -> object:
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(logging_setup, "default_log_dir", _denied)

    assert _ORIGINAL_STATE_DIR() is None


def test_default_log_dir_jatuh_ke_folder_per_user(monkeypatch, tmp_path):
    """Folder di samping exe yang tidak bisa ditulis harus dilewati."""

    from batikcraft_studio import dependency_bootstrap, logging_setup

    program_files = tmp_path / "Program Files" / "BatikCraft Studio"
    per_user = tmp_path / "LocalAppData" / "BatikCraftStudio"

    monkeypatch.setattr(
        dependency_bootstrap,
        "default_managed_dependency_root",
        lambda: program_files / "dependencies",
    )
    monkeypatch.setattr(
        dependency_bootstrap,
        "_per_user_application_data_root",
        lambda: per_user,
    )
    monkeypatch.setattr(
        dependency_bootstrap,
        "_directory_is_writable",
        lambda directory: per_user in directory.parents or directory == per_user,
    )

    assert logging_setup.default_log_dir() == per_user / "log"
