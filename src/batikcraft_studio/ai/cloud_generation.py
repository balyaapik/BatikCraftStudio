"""Cloud image-generation adapters for BatikBrew ornament and pattern workflows."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Mapping

from PIL import Image

from batikcraft_studio.ai.batikbrew_generation import (
    BatikBrewGenerationOptions,
    analyse_inspiration,
    make_tileable,
)
from batikcraft_studio.ai.generation_providers import (
    APISecretStore,
    CloudGenerationSettings,
    CloudGenerationSettingsStore,
    PROVIDER_GEMINI,
    PROVIDER_LOCAL,
    PROVIDER_OPENAI,
    PROVIDER_WATSONX,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_label,
)
from batikcraft_studio.ai.pretrained_batification import (
    PretrainedAIBatificationOptions,
    PretrainedAIBatificationResult,
)
from batikcraft_studio.imaging.structured_batification import BatificationError

GeneratorAdapter = Callable[[CloudGenerationSettings, str, str, str, str], bytes]


@dataclass(slots=True)
class _WatsonxToken:
    value: str
    expires_at: float
    api_key_hash: str


class CloudBatikGenerationProvider:
    """Generate Batik images using OpenAI, Gemini, or IBM watsonx.ai APIs."""

    def __init__(
        self,
        *,
        settings_store: CloudGenerationSettingsStore | None = None,
        secret_store: APISecretStore | None = None,
        generators: Mapping[str, GeneratorAdapter] | None = None,
    ) -> None:
        self.settings_store = settings_store or get_cloud_generation_settings_store()
        self.secret_store = secret_store or get_api_secret_store()
        self._watsonx_token: _WatsonxToken | None = None
        self._generators: dict[str, GeneratorAdapter] = {
            PROVIDER_OPENAI: self._generate_openai,
            PROVIDER_GEMINI: self._generate_gemini,
            PROVIDER_WATSONX: self._generate_watsonx,
        }
        if generators:
            self._generators.update(generators)

    @property
    def is_loaded(self) -> bool:
        return False

    def unload(self) -> None:
        self._watsonx_token = None

    def render(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> PretrainedAIBatificationResult:
        return self.render_variations(source_content, motif_content, options)[0]

    def render_variations(
        self,
        source_content: bytes,
        motif_content: bytes,
        options: PretrainedAIBatificationOptions | None = None,
    ) -> tuple[PretrainedAIBatificationResult, ...]:
        if not isinstance(options, BatikBrewGenerationOptions):
            raise BatificationError("Generasi cloud BatikBrew memerlukan pengaturan BatikBrew.")

        provider = str(getattr(options, "generation_provider", PROVIDER_LOCAL)).strip().casefold()
        if provider == PROVIDER_LOCAL or provider not in self._generators:
            raise BatificationError(f"Provider cloud tidak didukung: {provider}")

        settings = self.settings_store.load()
        api_key = self.secret_store.get(provider)
        if not api_key:
            raise BatificationError(
                f"API key {provider_label(provider)} belum diisi. Buka Pengaturan API pada dialog generasi."
            )
        model = str(getattr(options, "provider_model", "")).strip() or settings.model_for(provider)
        if not model:
            raise BatificationError(f"Model untuk {provider_label(provider)} belum diatur.")

        references = [_open_reference(source_content, "objek inspirasi")]
        if options.use_secondary_reference:
            references.append(_open_reference(motif_content, "referensi inspirasi kedua"))
        analysis = analyse_inspiration(
            references,
            inspiration_name=options.inspiration_name,
            custom_direction=options.prompt,
            negative_prompt=options.negative_prompt,
            trigger_words=options.lora_trigger_words,
        )

        output_mode = str(getattr(options, "output_mode", "pattern"))
        prompt_hash = int.from_bytes(
            hashlib.sha256(analysis.positive_prompt.encode("utf-8")).digest()[:4],
            "big",
        )
        base_seed = (int(options.seed) ^ prompt_hash) & 0x7FFFFFFF
        generator = self._generators[provider]
        results: list[PretrainedAIBatificationResult] = []

        for index in range(options.variation_count):
            seed_hint = (base_seed + index) & 0x7FFFFFFF
            variation_prompt = _variation_prompt(
                analysis.positive_prompt,
                analysis.negative_prompt,
                output_mode=output_mode,
                variation_index=index,
                variation_count=options.variation_count,
                seed_hint=seed_hint,
            )
            try:
                content = generator(settings, api_key, model, variation_prompt, output_mode)
            except BatificationError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider SDK errors vary by version
                raise BatificationError(
                    f"Generasi {provider_label(provider)} gagal: {exc}"
                ) from exc

            image = _decode_generated_image(content, provider_label(provider))
            if options.tileable and output_mode == "pattern":
                image = make_tileable(image.convert("RGB"))
            encoded = BytesIO()
            image.save(encoded, format="PNG", optimize=True)
            metadata = {
                "generation_mode": "batikbrew_cloud_text_to_image",
                "generation_engine": f"batikbrew-cloud-{provider}",
                "generation_provider": provider,
                "generation_provider_label": provider_label(provider),
                "provider_model": model,
                "source_used_as_inspiration": True,
                "source_used_as_img2img": False,
                "motif_fill_only": False,
                "variation_index": index,
                "variation_count": options.variation_count,
                "seed_hint": seed_hint,
                "base_seed_hint": base_seed,
                "provider_seed_guaranteed": False,
                "tileable": bool(options.tileable and output_mode == "pattern"),
                "palette_names": list(analysis.palette_names),
                "palette_hex": list(analysis.palette_hex),
                "edge_density": analysis.edge_density,
                "theme_keywords": list(analysis.theme_keywords),
                "style_hints": list(analysis.style_hints),
                "composition_hint": analysis.composition_hint,
                "prompt": variation_prompt,
                "negative_prompt": analysis.negative_prompt,
                "api_key_stored_in_project": False,
            }
            results.append(
                PretrainedAIBatificationResult(
                    content=encoded.getvalue(),
                    width=image.width,
                    height=image.height,
                    provider_id=f"batikbrew-cloud:{provider}:{model}",
                    metadata=metadata,
                )
            )
        return tuple(results)

    def _generate_openai(
        self,
        settings: CloudGenerationSettings,
        api_key: str,
        model: str,
        prompt: str,
        output_mode: str,
    ) -> bytes:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise BatificationError(
                'OpenAI API memerlukan paket openai. Instal aplikasi dengan extra "[ai]".'
            ) from exc

        client = OpenAI(
            api_key=api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_seconds,
        )
        parameters: dict[str, object] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "quality": "high",
            "output_format": "png",
            "background": "transparent" if output_mode == "ornament" else "opaque",
        }
        try:
            response = client.images.generate(**parameters)
        except TypeError:
            # Older compatible SDKs may not expose background/output_format yet.
            parameters.pop("background", None)
            parameters.pop("output_format", None)
            response = client.images.generate(**parameters)
        data = getattr(response, "data", None)
        if not data:
            raise BatificationError("OpenAI tidak mengembalikan gambar.")
        item = data[0]
        encoded = getattr(item, "b64_json", None)
        if encoded:
            return _decode_base64(encoded, "OpenAI")
        url = getattr(item, "url", None)
        if url:
            return _download_binary(str(url), settings.request_timeout_seconds)
        raise BatificationError("Respons OpenAI tidak berisi b64_json atau URL gambar.")

    def _generate_gemini(
        self,
        settings: CloudGenerationSettings,
        api_key: str,
        model: str,
        prompt: str,
        output_mode: str,
    ) -> bytes:
        del output_mode
        try:
            from google import genai
        except ImportError as exc:
            raise BatificationError(
                'Gemini API memerlukan paket google-genai. Instal aplikasi dengan extra "[ai]".'
            ) from exc

        client = genai.Client(api_key=api_key)
        interactions = getattr(client, "interactions", None)
        if interactions is not None and callable(getattr(interactions, "create", None)):
            response = interactions.create(
                model=model,
                input=prompt,
                response_format={
                    "type": "image",
                    "mime_type": "image/png",
                    "aspect_ratio": "1:1",
                    "image_size": "1K",
                },
            )
            output_image = getattr(response, "output_image", None)
            data = getattr(output_image, "data", None)
            if data:
                return _decode_maybe_base64(data, "Gemini")
            extracted = _extract_gemini_image(response)
            if extracted is not None:
                return extracted

        # Compatibility fallback for google-genai versions using generate_content.
        models = getattr(client, "models", None)
        generate = getattr(models, "generate_content", None)
        if not callable(generate):
            raise BatificationError("Versi google-genai tidak mendukung image generation.")
        try:
            from google.genai import types

            config = types.GenerateContentConfig(response_modalities=["IMAGE"])
        except (ImportError, AttributeError, TypeError):
            config = {"response_modalities": ["IMAGE"]}
        response = generate(model=model, contents=[prompt], config=config)
        extracted = _extract_gemini_image(response)
        if extracted is None:
            raise BatificationError("Gemini tidak mengembalikan gambar.")
        return extracted

    def _generate_watsonx(
        self,
        settings: CloudGenerationSettings,
        api_key: str,
        model: str,
        prompt: str,
        output_mode: str,
    ) -> bytes:
        del output_mode
        if not settings.watsonx_project_id:
            raise BatificationError("Project ID watsonx.ai belum diisi.")
        token = self._watsonx_access_token(settings, api_key)
        endpoint = (
            f"{settings.watsonx_url}/ml/v1/text/image?"
            f"version={urllib.parse.quote(settings.watsonx_api_version)}"
        )
        body = {
            "model_id": model,
            "project_id": settings.watsonx_project_id,
            "input": prompt,
            "parameters": {"height": 1024, "width": 1024},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "image/png",
                "Content-Type": "application/json",
            },
        )
        return _open_request(request, settings.request_timeout_seconds, "watsonx.ai")

    def _watsonx_access_token(
        self,
        settings: CloudGenerationSettings,
        api_key: str,
    ) -> str:
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        cached = self._watsonx_token
        if cached is not None and cached.api_key_hash == key_hash and cached.expires_at > time.time():
            return cached.value

        payload = urllib.parse.urlencode(
            {
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": api_key,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://iam.cloud.ibm.com/identity/token",
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        content = _open_request(request, settings.request_timeout_seconds, "IBM Cloud IAM")
        try:
            response = json.loads(content.decode("utf-8"))
            token = str(response["access_token"])
            expires_in = int(response.get("expires_in", 3600))
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BatificationError("Respons token IBM Cloud tidak valid.") from exc
        self._watsonx_token = _WatsonxToken(
            value=token,
            expires_at=time.time() + max(60, expires_in - 120),
            api_key_hash=key_hash,
        )
        return token


def _variation_prompt(
    positive_prompt: str,
    negative_prompt: str,
    *,
    output_mode: str,
    variation_index: int,
    variation_count: int,
    seed_hint: int,
) -> str:
    mode_instruction = (
        "Return exactly one isolated ornament centered on a clean background."
        if output_mode == "ornament"
        else "Return a complete square all-over Batik pattern suitable for seamless repetition."
    )
    return (
        f"{positive_prompt}. {mode_instruction} "
        f"Create visual variation {variation_index + 1} of {variation_count}; "
        f"composition seed hint {seed_hint}. Avoid: {negative_prompt}."
    )


def _open_reference(content: bytes, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            return image.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BatificationError(f"{label.capitalize()} tidak dapat dibaca.") from exc


def _decode_generated_image(content: bytes, provider_name: str) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            return image.convert("RGBA") if image.mode == "RGBA" else image.convert("RGB")
    except (OSError, ValueError) as exc:
        raise BatificationError(f"{provider_name} mengembalikan data gambar yang tidak valid.") from exc


def _decode_base64(value: object, provider_name: str) -> bytes:
    try:
        return base64.b64decode(str(value), validate=False)
    except (ValueError, TypeError) as exc:
        raise BatificationError(f"Data base64 {provider_name} tidak valid.") from exc


def _decode_maybe_base64(value: object, provider_name: str) -> bytes:
    if isinstance(value, bytes):
        return value
    return _decode_base64(value, provider_name)


def _extract_gemini_image(response: object) -> bytes | None:
    direct_parts = getattr(response, "parts", None)
    if direct_parts:
        for part in direct_parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return _decode_maybe_base64(data, "Gemini")
            as_image = getattr(part, "as_image", None)
            if callable(as_image):
                image = as_image()
                encoded = BytesIO()
                image.save(encoded, format="PNG")
                return encoded.getvalue()

    candidates = getattr(response, "candidates", None) or ()
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or ():
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return _decode_maybe_base64(data, "Gemini")

    for step in getattr(response, "steps", None) or ():
        for block in getattr(step, "content", None) or ():
            if getattr(block, "type", None) == "image" and getattr(block, "data", None):
                return _decode_maybe_base64(block.data, "Gemini")
    return None


def _download_binary(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "BatikCraftStudio/0.1"})
    return _open_request(request, timeout, "image download")


def _open_request(request: urllib.request.Request, timeout: int, label: str) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except OSError:
            detail = ""
        suffix = f" Detail: {detail}" if detail else ""
        raise BatificationError(f"{label} HTTP {exc.code}.{suffix}") from exc
    except urllib.error.URLError as exc:
        raise BatificationError(f"Koneksi ke {label} gagal: {exc.reason}") from exc


__all__ = ["CloudBatikGenerationProvider", "GeneratorAdapter"]
