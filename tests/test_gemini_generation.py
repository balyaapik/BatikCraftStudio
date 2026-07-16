from __future__ import annotations

import sys
from io import BytesIO
from types import ModuleType, SimpleNamespace

from PIL import Image

from batikcraft_studio.ai.gemini_generation import (
    _gemini_error_message,
    generate_gemini_image,
)
from batikcraft_studio.ai.generation_providers import CloudGenerationSettings


def _png_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), (91, 43, 31))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_gemini_uses_models_generate_content_instead_of_interactions(monkeypatch) -> None:
    calls: dict[str, object] = {}
    expected = _png_bytes()

    class FakeHttpOptions:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

    class FakeGenerateContentConfig:
        def __init__(self, *, response_modalities: list[str]) -> None:
            self.response_modalities = response_modalities

    class FakeInteractions:
        def create(self, **_kwargs: object) -> object:
            raise AssertionError("experimental interactions API must not be called")

    class FakeModels:
        def generate_content(self, **kwargs: object) -> object:
            calls["generate_content"] = kwargs
            return SimpleNamespace(
                parts=[SimpleNamespace(inline_data=SimpleNamespace(data=expected))]
            )

    class FakeClient:
        def __init__(self, *, api_key: str, http_options: object) -> None:
            calls["api_key"] = api_key
            calls["timeout"] = getattr(http_options, "timeout", None)
            self.interactions = FakeInteractions()
            self.models = FakeModels()

        def close(self) -> None:
            calls["closed"] = True

    google_module = ModuleType("google")
    genai_module = ModuleType("google.genai")
    types_module = ModuleType("google.genai.types")
    genai_module.Client = FakeClient  # type: ignore[attr-defined]
    genai_module.types = types_module  # type: ignore[attr-defined]
    types_module.HttpOptions = FakeHttpOptions  # type: ignore[attr-defined]
    types_module.GenerateContentConfig = FakeGenerateContentConfig  # type: ignore[attr-defined]
    google_module.genai = genai_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_module)

    result = generate_gemini_image(
        CloudGenerationSettings(request_timeout_seconds=60),
        "gemini-test-key",
        "gemini-3.1-flash-image",
        "Create one Batik ornament",
        "ornament",
    )

    request = calls["generate_content"]
    assert isinstance(request, dict)
    assert request["model"] == "gemini-3.1-flash-image"
    assert request["contents"] == "Create one Batik ornament"
    assert request["config"].response_modalities == ["IMAGE"]
    assert calls["timeout"] == 60_000
    assert calls["closed"] is True
    assert result == expected


def test_gemini_quota_error_is_short_and_actionable() -> None:
    error = SimpleNamespace(
        code=429,
        message="RESOURCE_EXHAUSTED: You exceeded your current quota.",
    )

    message = _gemini_error_message(error)  # type: ignore[arg-type]

    assert "Kuota Gemini habis" in message
    assert "Tutup dialog ini" in message
    assert "provider lain" in message
