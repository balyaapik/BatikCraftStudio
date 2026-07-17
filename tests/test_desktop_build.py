from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_build_uses_native_onedir_packages() -> None:
    source = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")

    assert '"--onedir"' in source
    assert '"--windowed"' in source
    assert '"--icon"' in source
    assert '"--osx-bundle-identifier"' in source
    assert "BatikCraftStudio.exe" in source
    assert "BatikCraftStudio.app" in source


def test_portable_build_excludes_large_local_ai_frameworks() -> None:
    source = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")

    for module in ("torch", "diffusers", "transformers", "accelerate", "peft"):
        assert f'"{module}"' in source


def test_workflow_builds_all_supported_desktop_targets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "windows-2022" in workflow
    assert "ubuntu-22.04" in workflow
    assert "macos-15-intel" in workflow
    assert "macos-15" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "workflow_dispatch:" in workflow


def test_linux_package_registers_a_desktop_icon() -> None:
    source = (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8")

    assert "batikcraft-studio.desktop.in" in source
    assert "StartupWMClass=BatikCraftStudio" in source
    assert "gtk-update-icon-cache" in source


def test_desktop_build_profile_contains_pyinstaller_and_cloud_clients() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "desktop-build = [" in pyproject
    assert '"pyinstaller>=6.21,<7"' in pyproject
    assert '"openai>=1.0,<3"' in pyproject
    assert '"google-genai>=1.0,<2"' in pyproject
