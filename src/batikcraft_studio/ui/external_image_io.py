"""Platform-tolerant helpers for external image files and system clipboard data."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image

from batikcraft_studio.assets import SUPPORTED_IMAGE_EXTENSIONS

_IMAGE_SUFFIXES = frozenset(SUPPORTED_IMAGE_EXTENSIONS)


def is_supported_image_path(path: Path | str) -> bool:
    """Return whether a path uses one of the supported raster image suffixes."""

    return Path(path).suffix.casefold() in _IMAGE_SUFFIXES


def image_dialog_filetypes() -> tuple[tuple[str, str], ...]:
    """Return Tk file-dialog filters for every supported external image type."""

    patterns = " ".join(f"*{suffix}" for suffix in SUPPORTED_IMAGE_EXTENSIONS)
    return (
        ("Supported images", patterns),
        ("PNG images", "*.png"),
        ("JPEG images", "*.jpg *.jpeg *.jfif"),
        ("TIFF images", "*.tif *.tiff"),
        ("WebP images", "*.webp"),
        ("Bitmap/GIF/ICO", "*.bmp *.gif *.ico"),
        ("All files", "*.*"),
    )


def paths_from_drop_data(
    splitlist: Callable[[str], tuple[str, ...]],
    data: str,
) -> tuple[Path, ...]:
    """Parse TkDND's brace-aware file list and retain supported existing files."""

    try:
        raw_values = splitlist(str(data))
    except Exception:  # noqa: BLE001 - Tcl parser differences are platform-specific
        raw_values = tuple(str(data).splitlines())
    return _deduplicated_supported_paths(raw_values)


def paths_from_clipboard_text(text: str) -> tuple[Path, ...]:
    """Parse newline, URI-list, or one-path clipboard text."""

    values: list[str] = []
    for line in str(text).replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            values.append(stripped)
    return _deduplicated_supported_paths(values)


def clipboard_payloads() -> tuple[tuple[str, bytes], ...]:
    """Read image bytes or copied image files from the operating-system clipboard."""

    try:
        from PIL import ImageGrab

        result = ImageGrab.grabclipboard()
    except (ImportError, NotImplementedError, OSError, RuntimeError):
        result = None

    if isinstance(result, Image.Image):
        output = BytesIO()
        result.convert("RGBA").save(output, format="PNG", optimize=True)
        return (("clipboard-image.png", output.getvalue()),)
    if isinstance(result, (list, tuple)):
        return payloads_from_paths(_deduplicated_supported_paths(result))
    return ()


def payloads_from_paths(paths: Iterable[Path | str]) -> tuple[tuple[str, bytes], ...]:
    """Read supported files, skipping paths that disappear or cannot be read."""

    payloads: list[tuple[str, bytes]] = []
    for value in paths:
        path = Path(value)
        if not is_supported_image_path(path) or not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if content:
            payloads.append((path.name, content))
    return tuple(payloads)


def _deduplicated_supported_paths(values: Iterable[object]) -> tuple[Path, ...]:
    paths: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = _path_from_external_value(str(value))
        if path is None or not is_supported_image_path(path) or not path.is_file():
            continue
        key = str(path.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return tuple(paths)


def _path_from_external_value(value: str) -> Path | None:
    text = value.strip().strip("{}")
    if not text:
        return None
    if text.casefold().startswith("file://"):
        parsed = urlparse(text)
        decoded = unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            decoded = f"//{parsed.netloc}{decoded}"
        if len(decoded) >= 3 and decoded[0] == "/" and decoded[2] == ":":
            decoded = decoded[1:]
        text = decoded
    return Path(text).expanduser()


__all__ = [
    "clipboard_payloads",
    "image_dialog_filetypes",
    "is_supported_image_path",
    "paths_from_clipboard_text",
    "paths_from_drop_data",
    "payloads_from_paths",
]
