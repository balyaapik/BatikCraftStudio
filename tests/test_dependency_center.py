"""Pusat Dependensi: katalog, kelayakan, dan tabel bercentang."""

from __future__ import annotations

from batikcraft_studio.ui import dependency_catalog as catalog
from batikcraft_studio.ui.dependency_center import _progress_bar


def test_catalog_covers_packages_and_models() -> None:
    keys = {item.key for item in catalog.CATALOG}
    assert {"torch_cpu", "torch_cuda", "diffusers", "sdxl", "sd15"} <= keys
    sdxl = next(item for item in catalog.CATALOG if item.key == "sdxl")
    assert sdxl.kind == catalog.KIND_MODEL
    assert sdxl.size_text.endswith("GB")


def test_eligibility_fails_when_disk_is_too_small(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "free_disk_bytes", lambda: 1 * 1024**3)
    sdxl = next(item for item in catalog.CATALOG if item.key == "sdxl")
    eligible, reason = catalog.eligibility(sdxl)
    assert eligible is False
    assert "Ruang disk" in reason


def test_eligibility_passes_with_ample_disk(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "free_disk_bytes", lambda: 200 * 1024**3)
    from batikcraft_studio.ai import torch_wheel_index

    monkeypatch.setattr(torch_wheel_index, "nvidia_gpu_present", lambda: True)
    for item in catalog.CATALOG:
        assert catalog.eligibility(item)[0] is True


def test_requirements_include_companion_packages() -> None:
    diffusers = next(item for item in catalog.CATALOG if item.key == "diffusers")
    requirements = catalog.requirements_for(diffusers)
    assert any("diffusers" in value for value in requirements)
    assert any("transformers" in value for value in requirements)


def test_progress_bar_renders_proportionally() -> None:
    assert _progress_bar(0.0).count("█") == 0
    assert _progress_bar(1.0).count("░") == 0
    half = _progress_bar(0.5)
    assert half.count("█") == 6 and half.count("░") == 6


def test_pytorch_is_offered_as_separate_cpu_and_cuda_rows() -> None:
    keys = {item.key for item in catalog.CATALOG}
    assert {"torch_cpu", "torch_cuda"} <= keys

    cuda = next(item for item in catalog.CATALOG if item.key == "torch_cuda")
    cpu = next(item for item in catalog.CATALOG if item.key == "torch_cpu")
    assert cuda.requires_nvidia is True and cuda.variant == "cuda"
    assert cpu.requires_nvidia is False and cpu.variant == "cpu"
    # Build GPU jauh lebih besar daripada build CPU.
    assert cuda.size_bytes > cpu.size_bytes * 4


def test_cuda_row_is_ineligible_without_nvidia_gpu(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "free_disk_bytes", lambda: 200 * 1024**3)
    from batikcraft_studio.ai import torch_wheel_index

    monkeypatch.setattr(torch_wheel_index, "nvidia_gpu_present", lambda: False)
    cuda = next(item for item in catalog.CATALOG if item.key == "torch_cuda")
    eligible, reason = catalog.eligibility(cuda)
    assert eligible is False and "NVIDIA" in reason


def test_install_command_honours_requested_torch_variant() -> None:
    from batikcraft_studio.dependency_bootstrap import managed_ai_install_command
    from batikcraft_studio.ai.torch_wheel_index import CPU_WHEEL_INDEX, CUDA_WHEEL_INDEX

    cuda_command = managed_ai_install_command(
        ["torch>=2.4"], frozen=False, torch_variant="cuda"
    )
    cpu_command = managed_ai_install_command(
        ["torch>=2.4"], frozen=False, torch_variant="cpu"
    )
    assert CUDA_WHEEL_INDEX in cuda_command
    assert CPU_WHEEL_INDEX in cpu_command


def test_progress_indicators_animate() -> None:
    from batikcraft_studio.ui.dependency_center import _pulse_bar

    # Fase tanpa angka: indikator berpindah posisi setiap tick.
    assert _pulse_bar(0) != _pulse_bar(1) != _pulse_bar(2)
    # Fase berangka: ujung bar berdenyut agar tidak tampak diam.
    assert _progress_bar(0.5, pulse=0) != _progress_bar(0.5, pulse=1)


def test_model_tab_has_no_dependency_install_buttons() -> None:
    import inspect

    from batikcraft_studio.ui import dependency_center

    source = inspect.getsource(dependency_center.DependencyCenterWindow._build_model_tab)
    assert "Instal Runtime SD1.5" not in source
    assert "Instal BatikBrew SDXL" not in source
    # Panel model fokus pada LoRA + runtime aktif.
    assert "LoRA Terpasang" in source
    assert "Aktifkan Model" in source
    assert "Pakai Renderer Fondasi" in source


def test_model_progress_callback_matches_installer_signature() -> None:
    """Regresi: installer memanggil callback dengan SATU objek progres.
    Versi lama memakai empat argumen sehingga unduhan model selalu gagal
    dengan 'missing 3 required positional arguments'."""

    import inspect

    from batikcraft_studio.ai.runtime_model_installer import RuntimeModelInstallProgress
    from batikcraft_studio.ui.dependency_center import DependencyCenterWindow

    source = inspect.getsource(DependencyCenterWindow._install_model)
    assert "def progress(update: object) -> None:" in source
    assert "download_percent" in source

    # Objek progres nyata memberi persentase byte yang benar.
    update = RuntimeModelInstallProgress(
        stage="sdxl",
        message="Mengunduh unet",
        completed=1,
        total=4,
        downloaded_bytes=3_000_000,
        total_bytes=12_000_000,
    )
    assert update.download_percent == 25.0


def test_gpu_detection_avoids_launching_nvidia_smi_first() -> None:
    """nvidia-smi.exe sempat gagal start (0xc0000142) di aplikasi beku dan
    memunculkan dialog Windows. Deteksi utama kini lewat pustaka driver."""

    import inspect

    from batikcraft_studio.ai import torch_wheel_index

    source = inspect.getsource(torch_wheel_index.nvidia_gpu_present)
    assert "nvcuda.dll" in source
    assert "cuInit" in source
    fallback = inspect.getsource(torch_wheel_index._nvidia_smi_reports_gpu)
    assert "CREATE_NO_WINDOW" in fallback


def test_installation_log_captures_everything_the_terminal_shows() -> None:
    """Pada build beku, pip menulis SELURUH keluarannya ke file log anak dan
    pipa stdout hanya menerima sedikit — jendela harus ikut membaca file itu."""

    import inspect

    from batikcraft_studio.ui.dependency_center import DependencyCenterWindow

    packages = inspect.getsource(DependencyCenterWindow._install_packages)
    # Semua baris stdout dicatat, termasuk baris progres.
    assert 'self._messages.put(("log", stripped))' in packages
    assert "_tail_log_file" in packages
    assert "[exit code]" in packages

    header = inspect.getsource(DependencyCenterWindow._log_header)
    for field in ("Paket", "Varian torch", "Target", "Cache pip", "Python", "Mode"):
        assert field in header

    model = inspect.getsource(DependencyCenterWindow._install_model)
    assert "current_file" in model and "MB" in model


def test_log_tail_reads_incremental_lines(tmp_path) -> None:
    """Pembacaan bertahap tidak mengulang baris lama dan menahan baris
    yang belum lengkap sampai newline tiba."""

    import queue

    from batikcraft_studio.ui.dependency_center import DependencyCenterWindow

    window = DependencyCenterWindow.__new__(DependencyCenterWindow)
    window._messages = queue.Queue()

    path = tmp_path / "dependency-install.log"
    path.write_text("Collecting torch\nDownloading torch.whl\n", encoding="utf-8")
    offset, pending = window._read_log_chunk(path, 0, "")
    lines = [payload for kind, payload in list(window._messages.queue) if kind == "log"]
    assert lines == ["Collecting torch", "Downloading torch.whl"]

    with path.open("a", encoding="utf-8") as handle:
        handle.write("Successfully installed torch\n")
    window._messages = queue.Queue()
    offset, pending = window._read_log_chunk(path, offset, pending)
    lines = [payload for kind, payload in list(window._messages.queue) if kind == "log"]
    assert lines == ["Successfully installed torch"]


def test_log_tab_offers_save_and_clear() -> None:
    import inspect

    from batikcraft_studio.ui import dependency_center

    source = inspect.getsource(dependency_center.DependencyCenterWindow._build_log_tab)
    assert "Simpan Log…" in source
    assert "Bersihkan" in source
    assert "Buka Folder Log" in source
