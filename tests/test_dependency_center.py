"""Pusat Dependensi: katalog, kelayakan, dan tabel bercentang."""

from __future__ import annotations

from batikcraft_studio.ui import dependency_catalog as catalog
from batikcraft_studio.ui.dependency_center import _progress_bar


def test_catalog_covers_packages_and_models() -> None:
    keys = {item.key for item in catalog.CATALOG}
    assert {"torch", "diffusers", "sdxl", "sd15"} <= keys
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
