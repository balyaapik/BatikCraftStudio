"""Scoped optional dependency profiles for BatikCraft Studio AI features.

The desktop executable can already contain lightweight cloud SDKs and the model
bootstrap.  Heavy local inference packages are installed into the managed dependency
folder only when the user selects the local AI profile.  Keeping profiles explicit
prevents the old one-click action from reinstalling every cloud and local package at
once.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from importlib import metadata
from typing import Final

from packaging.requirements import Requirement

PROFILE_LOCAL = "local"
PROFILE_OPENAI = "openai"
PROFILE_GEMINI = "gemini"
PROFILE_ALL = "all"


@dataclass(frozen=True, slots=True)
class DependencySpec:
    """One importable optional dependency and its supported version range."""

    module: str
    requirement: str
    distribution: str
    label: str
    groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Dependency state without importing heavyweight packages."""

    available: bool
    compatible: bool
    version: str | None
    detail: str


DEPENDENCIES: Final[tuple[DependencySpec, ...]] = (
    DependencySpec("torch", "torch>=2.4", "torch", "PyTorch", (PROFILE_LOCAL,)),
    DependencySpec(
        "diffusers",
        "diffusers>=0.39,<0.40",
        "diffusers",
        "Diffusers",
        (PROFILE_LOCAL,),
    ),
    DependencySpec(
        "transformers",
        "transformers>=4.48,<5",
        "transformers",
        "Transformers",
        (PROFILE_LOCAL,),
    ),
    DependencySpec(
        "accelerate",
        "accelerate>=1.2",
        "accelerate",
        "Accelerate",
        (PROFILE_LOCAL,),
    ),
    DependencySpec(
        "huggingface_hub",
        "huggingface-hub>=0.34,<1",
        "huggingface-hub",
        "Hugging Face Hub",
        (PROFILE_LOCAL,),
    ),
    DependencySpec("peft", "peft>=0.17", "peft", "PEFT / LoRA", (PROFILE_LOCAL,)),
    DependencySpec(
        "safetensors",
        "safetensors>=0.8",
        "safetensors",
        "Safetensors",
        (PROFILE_LOCAL,),
    ),
    DependencySpec("numpy", "numpy>=1.26,<3", "numpy", "NumPy", (PROFILE_LOCAL,)),
    DependencySpec("openai", "openai>=1.0,<3", "openai", "OpenAI", (PROFILE_OPENAI,)),
    DependencySpec(
        "google.genai",
        "google-genai>=1.0,<2",
        "google-genai",
        "Google GenAI",
        (PROFILE_GEMINI,),
    ),
    DependencySpec(
        "keyring",
        "keyring>=25,<27",
        "keyring",
        "Credential Vault",
        (PROFILE_OPENAI, PROFILE_GEMINI),
    ),
)

PROFILE_LABELS: Final[dict[str, str]] = {
    PROFILE_LOCAL: "AI Lokal SDXL + Training LoRA",
    PROFILE_OPENAI: "Provider OpenAI",
    PROFILE_GEMINI: "Provider Gemini",
    PROFILE_ALL: "Semua profil AI",
}


def dependencies_for_profile(profile_id: str) -> tuple[DependencySpec, ...]:
    """Return a stable, de-duplicated list for one install profile."""

    profile = str(profile_id).strip().casefold()
    if profile == PROFILE_ALL:
        return DEPENDENCIES
    if profile not in PROFILE_LABELS:
        raise ValueError(f"Profil dependency AI tidak dikenal: {profile_id}")
    return tuple(item for item in DEPENDENCIES if profile in item.groups)


def dependency_status(spec: DependencySpec) -> DependencyStatus:
    """Check import availability and distribution version without importing the module."""

    try:
        available = importlib.util.find_spec(spec.module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        available = False
    if not available:
        return DependencyStatus(False, False, None, "Belum terpasang")

    try:
        installed_version = metadata.version(spec.distribution)
    except metadata.PackageNotFoundError:
        # PyInstaller can expose an importable bundled package without conventional
        # dist-info metadata. Treat that copy as ready so the managed installer does
        # not download a duplicate into dependencies/python/site-packages.
        return DependencyStatus(True, True, None, "Terpasang di aplikasi")

    requirement = Requirement(spec.requirement)
    compatible = installed_version in requirement.specifier
    detail = (
        f"Siap · {installed_version}"
        if compatible
        else f"Versi tidak cocok · {installed_version} · perlu {requirement.specifier}"
    )
    return DependencyStatus(True, compatible, installed_version, detail)


def missing_requirements(profile_id: str) -> tuple[str, ...]:
    """Return only absent or incompatible requirements for one profile."""

    return tuple(
        spec.requirement
        for spec in dependencies_for_profile(profile_id)
        if not dependency_status(spec).compatible
    )


def profile_ready(profile_id: str) -> bool:
    return not missing_requirements(profile_id)


def profile_progress(profile_id: str) -> tuple[int, int]:
    dependencies = dependencies_for_profile(profile_id)
    ready = sum(1 for item in dependencies if dependency_status(item).compatible)
    return ready, len(dependencies)


def profile_tags(spec: DependencySpec) -> str:
    labels: list[str] = []
    if PROFILE_LOCAL in spec.groups:
        labels.append("Lokal")
    if PROFILE_OPENAI in spec.groups:
        labels.append("OpenAI")
    if PROFILE_GEMINI in spec.groups:
        labels.append("Gemini")
    return "/".join(labels)


__all__ = [
    "DEPENDENCIES",
    "PROFILE_ALL",
    "PROFILE_GEMINI",
    "PROFILE_LABELS",
    "PROFILE_LOCAL",
    "PROFILE_OPENAI",
    "DependencySpec",
    "DependencyStatus",
    "dependencies_for_profile",
    "dependency_status",
    "missing_requirements",
    "profile_progress",
    "profile_ready",
    "profile_tags",
]
