"""Persistent active local model profile for BatikBrew generation."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_SCHEMA_VERSION = 1


def default_batikbrew_model_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path(
        os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    return root / "BatikCraftStudio" / "batikbrew_model.json"


@dataclass(frozen=True, slots=True)
class BatikBrewLocalModelSettings:
    """One centrally selected SDXL runtime and LoRA profile."""

    schema_version: int = _SCHEMA_VERSION
    model_id: str = ""
    base_model_path: str = ""
    lora_path: str = ""
    lora_weight: float = 1.0
    trigger_words: tuple[str, ...] = ("batikbrew",)
    inference_steps: int = 30
    guidance_scale: float = 7.5
    resolution: int = 1024

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("Versi pengaturan model BatikBrew tidak didukung.")
        model_id = str(self.model_id).strip()
        base_model = str(self.base_model_path).strip()
        lora_path = str(self.lora_path).strip()
        weight = float(self.lora_weight)
        steps = int(self.inference_steps)
        guidance = float(self.guidance_scale)
        resolution = int(self.resolution)
        triggers = tuple(
            dict.fromkeys(str(value).strip() for value in self.trigger_words if str(value).strip())
        )
        if not 0.0 <= weight <= 2.0:
            raise ValueError("Bobot LoRA harus berada antara 0 dan 2.")
        if not 10 <= steps <= 150:
            raise ValueError("Inference steps harus berada antara 10 dan 150.")
        if not 1.0 <= guidance <= 30.0:
            raise ValueError("Guidance scale harus berada antara 1 dan 30.")
        if resolution not in {512, 640, 768, 896, 1024}:
            raise ValueError("Resolusi BatikBrew tidak didukung.")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "base_model_path", base_model)
        object.__setattr__(self, "lora_path", lora_path)
        object.__setattr__(self, "lora_weight", weight)
        object.__setattr__(self, "trigger_words", triggers or ("batikbrew",))
        object.__setattr__(self, "inference_steps", steps)
        object.__setattr__(self, "guidance_scale", guidance)
        object.__setattr__(self, "resolution", resolution)

    @property
    def configured(self) -> bool:
        return bool(self.model_id and self.base_model_path and self.lora_path)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["trigger_words"] = list(self.trigger_words)
        return payload


class BatikBrewLocalModelSettingsStore:
    """Atomically persist the local model selected in Settings."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_batikbrew_model_settings_path()
        self.last_error: str | None = None

    def load(self) -> BatikBrewLocalModelSettings:
        self.last_error = None
        if not self.path.is_file():
            return BatikBrewLocalModelSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Akar konfigurasi harus berupa object JSON.")
            allowed = set(BatikBrewLocalModelSettings.__dataclass_fields__)
            values = {key: value for key, value in payload.items() if key in allowed}
            values.setdefault("schema_version", _SCHEMA_VERSION)
            if "trigger_words" in values:
                values["trigger_words"] = tuple(values["trigger_words"])
            return BatikBrewLocalModelSettings(**values)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self.last_error = f"Pengaturan model BatikBrew rusak: {exc}"
            return BatikBrewLocalModelSettings()

    def save(self, settings: BatikBrewLocalModelSettings) -> Path:
        if not isinstance(settings, BatikBrewLocalModelSettings):
            raise TypeError("settings harus berupa BatikBrewLocalModelSettings.")
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

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.last_error = None


_DEFAULT_STORE: BatikBrewLocalModelSettingsStore | None = None


def get_batikbrew_model_settings_store() -> BatikBrewLocalModelSettingsStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = BatikBrewLocalModelSettingsStore()
    return _DEFAULT_STORE


__all__ = [
    "BatikBrewLocalModelSettings",
    "BatikBrewLocalModelSettingsStore",
    "default_batikbrew_model_settings_path",
    "get_batikbrew_model_settings_store",
]
