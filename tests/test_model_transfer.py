from __future__ import annotations

import threading
from pathlib import Path

import pytest

from batikcraft_studio import dependency_bootstrap
from batikcraft_studio.model_transfer import (
    ModelTransferCancelled,
    copy_model_pack_with_progress,
    download_marketplace_model,
)


class _FakeClient:
    token = "test-token"
    timeout = 10
    base_url = "https://example.test"

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path}"


class _FakeResponse:
    def __init__(self, payload: bytes, *, status: int = 200, headers: dict[str, str] | None = None):
        self.payload = payload
        self.offset = 0
        self.status = status
        self.headers = headers or {"Content-Length": str(len(payload))}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, size: int) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_local_lora_copy_reports_real_bytes(tmp_path: Path) -> None:
    source = tmp_path / "model.batikmodel"
    source.write_bytes(b"batik" * 1000)
    events: list[tuple[int, int, str]] = []

    output = copy_model_pack_with_progress(
        source,
        tmp_path / "cache" / source.name,
        progress=lambda completed, total, name: events.append((completed, total, name)),
    )

    assert output.read_bytes() == source.read_bytes()
    assert events[0][0] == 0
    assert events[-1][:2] == (source.stat().st_size, source.stat().st_size)
    assert events[-1][2] == source.name


def test_local_lora_copy_stops_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "model.batikmodel"
    source.write_bytes(b"x" * 700_000)
    cancel_event = threading.Event()

    def cancel_after_first_chunk(completed: int, _total: int, _name: str) -> None:
        if completed > 0:
            cancel_event.set()

    target = tmp_path / "cache" / source.name
    with pytest.raises(ModelTransferCancelled):
        copy_model_pack_with_progress(
            source,
            target,
            progress=cancel_after_first_chunk,
            cancel_event=cancel_event,
        )

    assert not target.exists()
    assert not target.with_name(f".{target.name}.part").exists()


def test_marketplace_lora_download_reports_content_length(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(dependency_bootstrap.DEPENDENCIES_DIR_ENV, str(tmp_path))
    payload = b"model-data" * 1000
    monkeypatch.setattr(
        "batikcraft_studio.model_transfer.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )
    events: list[tuple[int, int, str]] = []

    output = download_marketplace_model(
        _FakeClient(),
        42,
        progress=lambda completed, total, name: events.append((completed, total, name)),
    )

    assert output == tmp_path / "cache" / "model-downloads" / "model-42.batikmodel"
    assert output.read_bytes() == payload
    assert events[-1][:2] == (len(payload), len(payload))


def test_marketplace_cancel_preserves_partial_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(dependency_bootstrap.DEPENDENCIES_DIR_ENV, str(tmp_path))
    payload = b"partial-model" * 1000
    monkeypatch.setattr(
        "batikcraft_studio.model_transfer.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )
    cancel_event = threading.Event()

    def cancel_after_data(completed: int, _total: int, _name: str) -> None:
        if completed > 0:
            cancel_event.set()

    with pytest.raises(ModelTransferCancelled):
        download_marketplace_model(
            _FakeClient(),
            9,
            progress=cancel_after_data,
            cancel_event=cancel_event,
        )

    partial = tmp_path / "cache" / "model-downloads" / "model-9.batikmodel.part"
    assert partial.is_file()
    assert partial.read_bytes() == payload
