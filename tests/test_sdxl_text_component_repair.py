from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from batikcraft_studio import __main__
from batikcraft_studio.ai.sdxl_text_component_repair import (
    _complete_sdxl_pipeline_factory,
    _repair_sdxl_prompt_components,
)
from batikcraft_studio.imaging.structured_batification import BatificationError


class _Tokenizer:
    model_max_length = 77

    def __init__(self, size: int = 100) -> None:
        self.size = size

    def __len__(self) -> int:
        return self.size

    def tokenize(self, text: str) -> list[str]:
        return text.split()


class _Embeddings:
    def __init__(self, size: int) -> None:
        self.num_embeddings = size


class _Encoder:
    def __init__(self, size: int = 100) -> None:
        self.size = size

    def get_input_embeddings(self) -> _Embeddings:
        return _Embeddings(self.size)


class _Pipeline:
    def __init__(
        self,
        *,
        tokenizer: Any = None,
        text_encoder: Any = None,
        tokenizer_2: Any = None,
        text_encoder_2: Any = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.text_encoder = text_encoder
        self.tokenizer_2 = tokenizer_2
        self.text_encoder_2 = text_encoder_2
        self.registered: list[str] = []

    def register_modules(self, **components: Any) -> None:
        for name, component in components.items():
            setattr(self, name, component)
            self.registered.append(name)


def _settings(*, local_files_only: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        model_id_or_path="local-sdxl",
        local_files_only=local_files_only,
        cache_dir=None,
    )


def test_missing_secondary_sdxl_pair_is_restored_before_encode_prompt() -> None:
    primary_tokenizer = _Tokenizer()
    pipeline = _Pipeline(
        tokenizer=primary_tokenizer,
        text_encoder=_Encoder(),
    )
    loaded: list[tuple[str, str]] = []

    def loader(
        name: str,
        source: str,
        subfolder: str,
        _settings_value: Any,
        _dtype: Any,
    ) -> Any:
        loaded.append((name, source))
        assert subfolder == name
        if name == "tokenizer_2":
            return _Tokenizer()
        if name == "text_encoder_2":
            return _Encoder()
        raise FileNotFoundError(name)

    repaired = _repair_sdxl_prompt_components(
        pipeline,
        _settings(),
        component_loader=loader,
    )

    assert pipeline.tokenizer is primary_tokenizer
    assert pipeline.tokenizer_2 is not None
    assert pipeline.text_encoder_2 is not None
    assert repaired == ("text_encoder_2", "tokenizer_2")
    assert {name for name, _source in loaded} == {"tokenizer_2", "text_encoder_2"}


def test_secondary_tokenizer_can_reuse_matching_primary_vocabulary() -> None:
    primary_tokenizer = _Tokenizer(size=321)
    pipeline = _Pipeline(
        tokenizer=primary_tokenizer,
        text_encoder=_Encoder(size=321),
    )

    def loader(
        name: str,
        _source: str,
        _subfolder: str,
        _settings_value: Any,
        _dtype: Any,
    ) -> Any:
        if name == "text_encoder_2":
            return _Encoder(size=321)
        raise FileNotFoundError(name)

    repaired = _repair_sdxl_prompt_components(
        pipeline,
        _settings(),
        component_loader=loader,
    )

    assert pipeline.tokenizer_2 is primary_tokenizer
    assert "tokenizer_2" in repaired
    assert pipeline.text_encoder_2 is not None


def test_incomplete_sdxl_reports_actionable_error_instead_of_none_tokenize() -> None:
    pipeline = _Pipeline(
        tokenizer=_Tokenizer(size=100),
        text_encoder=_Encoder(size=100),
    )

    def missing_loader(
        _name: str,
        _source: str,
        _subfolder: str,
        _settings_value: Any,
        _dtype: Any,
    ) -> Any:
        raise FileNotFoundError("not cached")

    with pytest.raises(BatificationError, match="tokenizer_2") as captured:
        _repair_sdxl_prompt_components(
            pipeline,
            _settings(local_files_only=True),
            component_loader=missing_loader,
        )

    assert "local-files-only" in str(captured.value)
    assert "NoneType" not in str(captured.value)


def test_factory_repairs_components_before_device_or_cpu_offload() -> None:
    source = inspect.getsource(_complete_sdxl_pipeline_factory)
    repair_index = source.index("_repair_sdxl_prompt_components(")

    assert repair_index < source.index("pipeline.enable_model_cpu_offload()")
    assert repair_index < source.index("pipeline.to(device)")


def test_startup_installs_text_repair_before_lora_restore() -> None:
    source = inspect.getsource(__main__.main)

    assert "install_sdxl_text_component_repair" in source
    assert source.index("install_sdxl_text_component_repair()") < source.index(
        "install_lora_activation_persistence()"
    )
