"""Stable Google Gemini image generation for BatikBrew cloud workflows."""

from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from batikcraft_studio.ai.generation_providers import CloudGenerationSettings
from batikcraft_studio.imaging.structured_batification import BatificationError


def generate_gemini_image(
    settings: CloudGenerationSettings,
    api_key: str,
    model: str,
    prompt: str,
    output_mode: str,
) -> bytes:
    """Generate one image through the stable ``models.generate_content`` API.

    ``client.interactions`` is intentionally not used. The Interactions API is a
    preview surface whose request schema may change independently of Gemini image
    generation. Google documents ``models.generate_content`` as the supported
    image-generation path for the ``*-image`` models.
    """

    del output_mode
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise BatificationError(
            'Gemini API memerlukan paket google-genai. Instal aplikasi dengan extra "[ai]".'
        ) from exc

    try:
        http_options = types.HttpOptions(
            timeout=max(1, int(settings.request_timeout_seconds)) * 1000
        )
    except (AttributeError, TypeError, ValueError):
        http_options = {"timeout": max(1, int(settings.request_timeout_seconds)) * 1000}

    client = genai.Client(api_key=api_key, http_options=http_options)
    try:
        models = getattr(client, "models", None)
        generate = getattr(models, "generate_content", None)
        if not callable(generate):
            raise BatificationError("Versi google-genai tidak mendukung image generation.")

        try:
            config = types.GenerateContentConfig(response_modalities=["IMAGE"])
        except (AttributeError, TypeError, ValueError):
            config = {"response_modalities": ["IMAGE"]}

        response = generate(model=model, contents=prompt, config=config)
        content = _extract_gemini_image(response)
        if content is None:
            raise BatificationError(
                "Gemini tidak mengembalikan gambar. Pastikan model yang dipilih adalah "
                "model image generation, misalnya gemini-3.1-flash-image."
            )
        return content
    except BatificationError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK error classes vary by version
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        if code is not None:
            raise BatificationError(f"Gemini API HTTP {code}: {message}") from exc
        raise BatificationError(f"Generasi Gemini gagal: {message}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _extract_gemini_image(response: object) -> bytes | None:
    for part in _response_parts(response):
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None)
        if data:
            return _decode_image_data(data)

        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            try:
                image = as_image()
            except (AttributeError, TypeError, ValueError):
                image = None
            if isinstance(image, Image.Image):
                encoded = BytesIO()
                image.save(encoded, format="PNG")
                return encoded.getvalue()
    return None


def _response_parts(response: object) -> tuple[object, ...]:
    direct = getattr(response, "parts", None)
    if direct:
        return tuple(direct)

    collected: list[object] = []
    for candidate in getattr(response, "candidates", None) or ():
        content = getattr(candidate, "content", None)
        collected.extend(getattr(content, "parts", None) or ())
    return tuple(collected)


def _decode_image_data(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    try:
        return base64.b64decode(str(value), validate=False)
    except (TypeError, ValueError) as exc:
        raise BatificationError("Data gambar Gemini tidak valid.") from exc


__all__ = ["generate_gemini_image"]
