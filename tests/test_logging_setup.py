"""Fitur log file: folder log/, rotasi, penangkap crash & exception."""

from __future__ import annotations

import logging

from batikcraft_studio import logging_setup


def test_file_logging_writes_to_log_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        logging_setup, "default_log_dir", lambda: tmp_path / "log"
    )
    monkeypatch.setattr(logging_setup, "_INSTALLED", False)

    log_dir = logging_setup.install_file_logging()

    assert log_dir == tmp_path / "log"
    assert log_dir.is_dir()
    logging.getLogger("batikcraft_studio.uji").info("baris uji log")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = (log_dir / "batikcraft.log").read_text(encoding="utf-8")
    assert "baris uji log" in content
    # crash native tercatat lewat faulthandler ke file terpisah
    assert (log_dir / "crash-native.log").exists()

    # idempoten: pemasangan kedua tidak menggandakan handler
    before = len(logging.getLogger().handlers)
    logging_setup.install_file_logging()
    assert len(logging.getLogger().handlers) == before


def test_uncaught_thread_exception_is_logged(tmp_path, monkeypatch) -> None:
    import threading
    import time

    monkeypatch.setattr(
        logging_setup, "default_log_dir", lambda: tmp_path / "log"
    )
    monkeypatch.setattr(logging_setup, "_INSTALLED", False)
    log_dir = logging_setup.install_file_logging()

    def boom() -> None:
        raise RuntimeError("ledakan-thread-uji")

    thread = threading.Thread(target=boom, name="uji-crash")
    thread.start()
    thread.join()
    time.sleep(0.05)
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = (log_dir / "batikcraft.log").read_text(encoding="utf-8")
    assert "ledakan-thread-uji" in content
    assert "uji-crash" in content


def test_menu_and_startup_are_wired() -> None:
    import inspect

    from batikcraft_studio import __main__ as entry
    from batikcraft_studio import batikbrew_context_tool_app as app

    assert "install_file_logging" in inspect.getsource(entry)
    assert "Buka Folder Log Aplikasi" in inspect.getsource(app)


def test_cpu_generation_enables_memory_savers() -> None:
    import inspect

    from batikcraft_studio.ai import batikbrew_generation

    source = inspect.getsource(batikbrew_generation)
    assert 'if device == "cpu":' in source
    assert "enable_attention_slicing" in source
    assert "enable_vae_tiling" in source
