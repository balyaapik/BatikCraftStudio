from __future__ import annotations

import json
from pathlib import Path

from batikcraft_studio.ai import AIBatikBackgroundOptions
from batikcraft_studio.ai.global_runtime import (
    apply_global_runtime_to_background_options,
    configure_pipeline_memory_features,
    pretrained_batification_options_from_global,
)
from batikcraft_studio.ai.runtime_settings import (
    AIRuntimeSettings,
    AIRuntimeSettingsStore,
    diagnose_ai_runtime,
)


class _FakeMPS:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available


class _FakeBackends:
    def __init__(self, mps_available: bool = False) -> None:
        self.mps = _FakeMPS(mps_available)


class _FakeProperties:
    total_memory = 8 * 1024**3


class _FakeCuda:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available

    def get_device_name(self, _index: int) -> str:
        return "Fake RTX"

    def get_device_properties(self, _index: int) -> _FakeProperties:
        return _FakeProperties()


class _FakeVersion:
    cuda = "12.4"


class _FakeTorch:
    __version__ = "2.6.0"
    version = _FakeVersion()
    float16 = "float16"
    float32 = "float32"
    bfloat16 = "bfloat16"

    def __init__(self, *, cuda: bool, mps: bool = False) -> None:
        self.cuda = _FakeCuda(cuda)
        self.backends = _FakeBackends(mps)


class _FakePipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enable_attention_slicing(self) -> None:
        self.calls.append("attention-on")

    def disable_attention_slicing(self) -> None:
        self.calls.append("attention-off")

    def enable_vae_slicing(self) -> None:
        self.calls.append("vae-slicing-on")

    def disable_vae_slicing(self) -> None:
        self.calls.append("vae-slicing-off")

    def enable_vae_tiling(self) -> None:
        self.calls.append("vae-tiling-on")

    def disable_vae_tiling(self) -> None:
        self.calls.append("vae-tiling-off")


def _settings(tmp_path: Path, **changes: object) -> AIRuntimeSettings:
    values: dict[str, object] = {
        "cache_dir": str(tmp_path / "cache"),
        "default_model": "local-or-hub/model",
    }
    values.update(changes)
    return AIRuntimeSettings(**values)


def test_settings_store_round_trip_and_corrupt_file_fallback(tmp_path: Path) -> None:
    store = AIRuntimeSettingsStore(tmp_path / "config" / "ai_runtime.json")
    saved = _settings(
        tmp_path,
        device="cuda",
        precision="float16",
        cpu_offload=False,
        vae_tiling=True,
    )

    destination = store.save(saved)

    assert destination.is_file()
    assert store.load() == saved
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["device"] == "cuda"
    assert Path(saved.cache_dir).is_dir()

    destination.write_text("{not valid json", encoding="utf-8")
    fallback = store.load()
    assert fallback.device == "auto"
    assert store.last_error is not None


def test_manual_cuda_falls_back_loudly_to_best_available_device(tmp_path: Path) -> None:
    """Kebijakan baru: pilihan GPU yang tidak tersedia tidak lagi menggagalkan
    generasi — jatuh ke perangkat terbaik yang ada DENGAN peringatan jelas
    (bukan diam-diam), sehingga semua tipe GPU/CPU tetap bisa dipakai."""

    report = diagnose_ai_runtime(
        _settings(tmp_path, device="cuda"),
        run_tensor_test=False,
        torch_module=_FakeTorch(cuda=False),
    )

    assert report.effective_device == "cpu"
    assert report.error is None
    assert any("CUDA" in warning and "tidak tersedia" in warning for warning in report.warnings)


def test_auto_runtime_detects_cuda_and_recommends_float16(tmp_path: Path) -> None:
    report = diagnose_ai_runtime(
        _settings(tmp_path, device="auto", precision="auto"),
        run_tensor_test=False,
        torch_module=_FakeTorch(cuda=True),
    )

    assert report.effective_device == "cuda"
    assert report.effective_precision == "float16"
    assert report.gpu_name == "Fake RTX"
    assert report.gpu_vram_gb == 8.0
    assert report.recommendation.cpu_offload is False


def test_cpu_float16_is_safely_promoted_to_float32(tmp_path: Path) -> None:
    report = diagnose_ai_runtime(
        _settings(tmp_path, device="cpu", precision="float16"),
        run_tensor_test=False,
        torch_module=_FakeTorch(cuda=False),
    )

    assert report.effective_device == "cpu"
    assert report.effective_precision == "float32"
    assert report.warnings


def test_global_settings_are_applied_to_background_and_object_batification(
    tmp_path: Path,
) -> None:
    runtime = _settings(
        tmp_path,
        device="cuda",
        precision="float16",
        cpu_offload=False,
        local_files_only=True,
    )
    creative = AIBatikBackgroundOptions(
        model_id_or_path="one-off/background-model",
        seed=77,
        resolution=512,
    )

    background = apply_global_runtime_to_background_options(creative, runtime)
    object_options = pretrained_batification_options_from_global(runtime)

    assert background.model_id_or_path == "one-off/background-model"
    assert background.device == "cuda"
    assert background.precision == "float16"
    assert background.local_files_only is True
    assert background.cache_dir == runtime.cache_dir
    assert object_options.model_id_or_path == runtime.default_model
    assert object_options.device == "cuda"
    assert object_options.cpu_offload is False


def test_low_vram_mode_forces_memory_saving_features(tmp_path: Path) -> None:
    runtime = _settings(
        tmp_path,
        cpu_offload=False,
        low_vram_mode=True,
        attention_slicing=False,
        vae_slicing=False,
        vae_tiling=False,
    )
    pipeline = _FakePipeline()

    configure_pipeline_memory_features(pipeline, runtime)

    assert runtime.effective_cpu_offload is True
    assert pipeline.calls == [
        "attention-on",
        "vae-slicing-on",
        "vae-tiling-on",
    ]


def test_memory_features_can_be_explicitly_disabled(tmp_path: Path) -> None:
    runtime = _settings(
        tmp_path,
        low_vram_mode=False,
        attention_slicing=False,
        vae_slicing=False,
        vae_tiling=False,
    )
    pipeline = _FakePipeline()

    configure_pipeline_memory_features(pipeline, runtime)

    assert pipeline.calls == [
        "attention-off",
        "vae-slicing-off",
        "vae-tiling-off",
    ]
