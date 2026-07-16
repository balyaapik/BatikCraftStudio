"""Provider selection and credential storage for cloud Batik generation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

PROVIDER_LOCAL = "local_sdxl"
PROVIDER_WATSONX = "watsonx"
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"

PROVIDER_IDS = (
    PROVIDER_LOCAL,
    PROVIDER_WATSONX,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
)

PROVIDER_LABELS: dict[str, str] = {
    PROVIDER_LOCAL: "SDXL + LoRA Lokal",
    PROVIDER_WATSONX: "IBM watsonx.ai API",
    PROVIDER_GEMINI: "Google Gemini Image API",
    PROVIDER_OPENAI: "OpenAI / ChatGPT Image API",
}

DEFAULT_OPENAI_MODEL = "gpt-image-1"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-image"
DEFAULT_WATSONX_MODEL = "stable-diffusion-xl-1024-v1-0"
DEFAULT_WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
DEFAULT_WATSONX_VERSION = "2023-07-07"

_SETTINGS_SCHEMA_VERSION = 1
_SECRET_SERVICE = "BatikCraftStudio.CloudAI"
_SECRET_NAMES = {
    PROVIDER_OPENAI: "openai-api-key",
    PROVIDER_GEMINI: "gemini-api-key",
    PROVIDER_WATSONX: "watsonx-api-key",
}
_ENV_NAMES = {
    PROVIDER_OPENAI: ("OPENAI_API_KEY",),
    PROVIDER_GEMINI: ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    PROVIDER_WATSONX: ("WATSONX_APIKEY", "IBM_CLOUD_API_KEY"),
}


def default_cloud_generation_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    return root / "BatikCraftStudio" / "cloud_generation.json"


def provider_label(provider_id: str) -> str:
    return PROVIDER_LABELS.get(provider_id, provider_id)


def provider_id_from_label(label: str) -> str:
    for provider_id, provider_name in PROVIDER_LABELS.items():
        if provider_name == label:
            return provider_id
    normalized = str(label).strip().casefold()
    for provider_id in PROVIDER_IDS:
        if provider_id.casefold() == normalized:
            return provider_id
    return PROVIDER_LOCAL


@dataclass(frozen=True, slots=True)
class CloudGenerationSettings:
    """Non-secret provider configuration and per-output-mode defaults."""

    schema_version: int = _SETTINGS_SCHEMA_VERSION
    ornament_provider: str = PROVIDER_LOCAL
    pattern_provider: str = PROVIDER_LOCAL
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_model: str = DEFAULT_GEMINI_MODEL
    watsonx_model: str = DEFAULT_WATSONX_MODEL
    watsonx_url: str = DEFAULT_WATSONX_URL
    watsonx_project_id: str = ""
    watsonx_api_version: str = DEFAULT_WATSONX_VERSION
    request_timeout_seconds: int = 240

    def __post_init__(self) -> None:
        if self.schema_version != _SETTINGS_SCHEMA_VERSION:
            raise ValueError("Versi pengaturan cloud AI tidak didukung.")
        ornament = _validated_provider(self.ornament_provider)
        pattern = _validated_provider(self.pattern_provider)
        timeout = int(self.request_timeout_seconds)
        if not 30 <= timeout <= 900:
            raise ValueError("Timeout API harus berada antara 30 dan 900 detik.")
        openai_model = _required_text(self.openai_model, "Model OpenAI")
        gemini_model = _required_text(self.gemini_model, "Model Gemini")
        watsonx_model = _required_text(self.watsonx_model, "Model watsonx.ai")
        openai_base_url = _required_url(self.openai_base_url, "Base URL OpenAI")
        watsonx_url = _required_url(self.watsonx_url, "URL watsonx.ai")
        version = _required_text(self.watsonx_api_version, "Versi API watsonx.ai")
        project_id = str(self.watsonx_project_id).strip()
        if len(project_id) > 200:
            raise ValueError("Project ID watsonx.ai terlalu panjang.")

        object.__setattr__(self, "ornament_provider", ornament)
        object.__setattr__(self, "pattern_provider", pattern)
        object.__setattr__(self, "openai_model", openai_model)
        object.__setattr__(self, "openai_base_url", openai_base_url.rstrip("/"))
        object.__setattr__(self, "gemini_model", gemini_model)
        object.__setattr__(self, "watsonx_model", watsonx_model)
        object.__setattr__(self, "watsonx_url", watsonx_url.rstrip("/"))
        object.__setattr__(self, "watsonx_project_id", project_id)
        object.__setattr__(self, "watsonx_api_version", version)
        object.__setattr__(self, "request_timeout_seconds", timeout)

    def provider_for_mode(self, output_mode: str) -> str:
        return self.ornament_provider if output_mode == "ornament" else self.pattern_provider

    def with_provider_for_mode(self, output_mode: str, provider_id: str) -> CloudGenerationSettings:
        provider = _validated_provider(provider_id)
        if output_mode == "ornament":
            return replace(self, ornament_provider=provider)
        return replace(self, pattern_provider=provider)

    def model_for(self, provider_id: str) -> str:
        provider = _validated_provider(provider_id)
        if provider == PROVIDER_OPENAI:
            return self.openai_model
        if provider == PROVIDER_GEMINI:
            return self.gemini_model
        if provider == PROVIDER_WATSONX:
            return self.watsonx_model
        return ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> CloudGenerationSettings:
        allowed = set(cls.__dataclass_fields__)
        payload = {key: item for key, item in value.items() if key in allowed}
        payload.setdefault("schema_version", _SETTINGS_SCHEMA_VERSION)
        return cls(**payload)


class CloudGenerationSettingsStore:
    """Atomically persist non-secret cloud provider settings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_cloud_generation_settings_path()
        self.last_error: str | None = None

    def load(self) -> CloudGenerationSettings:
        self.last_error = None
        if not self.path.is_file():
            return CloudGenerationSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Akar konfigurasi harus berupa object JSON.")
            return CloudGenerationSettings.from_mapping(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.last_error = f"Pengaturan cloud AI rusak; default lokal digunakan. Detail: {exc}"
            return CloudGenerationSettings()

    def save(self, settings: CloudGenerationSettings) -> Path:
        if not isinstance(settings, CloudGenerationSettings):
            raise TypeError("settings harus berupa CloudGenerationSettings.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        encoded = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        try:
            temporary.write_text(encoded + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        self.last_error = None
        return self.path


class APISecretStore:
    """Store API keys in the OS credential vault through keyring.

    Environment variables always take priority and are never copied to disk:
    OPENAI_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY, and
    WATSONX_APIKEY/IBM_CLOUD_API_KEY.
    """

    def __init__(self, service_name: str = _SECRET_SERVICE) -> None:
        self.service_name = service_name

    def get(self, provider_id: str) -> str | None:
        provider = _validated_cloud_provider(provider_id)
        for variable in _ENV_NAMES[provider]:
            value = os.environ.get(variable, "").strip()
            if value:
                return value
        try:
            import keyring

            value = keyring.get_password(self.service_name, _SECRET_NAMES[provider])
        except Exception:  # noqa: BLE001 - keyring backend availability is platform-specific
            return None
        return None if value is None else str(value).strip() or None

    def set(self, provider_id: str, value: str) -> None:
        provider = _validated_cloud_provider(provider_id)
        secret = str(value).strip()
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError(
                'Penyimpanan API key memerlukan paket keyring. Instal aplikasi dengan extra "[ai]".'
            ) from exc
        try:
            if secret:
                keyring.set_password(self.service_name, _SECRET_NAMES[provider], secret)
            else:
                try:
                    keyring.delete_password(self.service_name, _SECRET_NAMES[provider])
                except Exception:  # noqa: BLE001 - absent secrets are already deleted
                    pass
        except Exception as exc:  # noqa: BLE001 - expose OS vault failures as UI errors
            raise RuntimeError(f"API key gagal disimpan ke credential vault: {exc}") from exc

    def has(self, provider_id: str) -> bool:
        return bool(self.get(provider_id))


_GLOBAL_SETTINGS_STORE = CloudGenerationSettingsStore()
_GLOBAL_SECRET_STORE = APISecretStore()


def get_cloud_generation_settings_store() -> CloudGenerationSettingsStore:
    return _GLOBAL_SETTINGS_STORE


def load_cloud_generation_settings() -> CloudGenerationSettings:
    return _GLOBAL_SETTINGS_STORE.load()


def save_cloud_generation_settings(settings: CloudGenerationSettings) -> Path:
    return _GLOBAL_SETTINGS_STORE.save(settings)


def get_api_secret_store() -> APISecretStore:
    return _GLOBAL_SECRET_STORE


def _validated_provider(value: object) -> str:
    provider = str(value).strip().casefold()
    if provider not in PROVIDER_IDS:
        raise ValueError(f"Provider AI tidak didukung: {value}")
    return provider


def _validated_cloud_provider(value: object) -> str:
    provider = _validated_provider(value)
    if provider == PROVIDER_LOCAL:
        raise ValueError("Provider lokal tidak menggunakan API key.")
    return provider


def _required_text(value: object, label: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 500:
        raise ValueError(f"{label} tidak valid.")
    return text


def _required_url(value: object, label: str) -> str:
    text = _required_text(value, label)
    if not text.startswith(("https://", "http://")):
        raise ValueError(f"{label} harus diawali http:// atau https://.")
    return text


__all__ = [
    "APISecretStore",
    "CloudGenerationSettings",
    "CloudGenerationSettingsStore",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_WATSONX_MODEL",
    "DEFAULT_WATSONX_URL",
    "DEFAULT_WATSONX_VERSION",
    "PROVIDER_GEMINI",
    "PROVIDER_IDS",
    "PROVIDER_LABELS",
    "PROVIDER_LOCAL",
    "PROVIDER_OPENAI",
    "PROVIDER_WATSONX",
    "default_cloud_generation_settings_path",
    "get_api_secret_store",
    "get_cloud_generation_settings_store",
    "load_cloud_generation_settings",
    "provider_id_from_label",
    "provider_label",
    "save_cloud_generation_settings",
]
