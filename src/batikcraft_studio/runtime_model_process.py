"""Cancellable child-process entry point for managed runtime model downloads."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

RUNTIME_INSTALL_FLAG = "--batikcraft-install-runtime-model"


def runtime_model_install_command(
    family: str,
    *,
    root: str | Path,
    event_file: str | Path,
    executable: str | Path | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """Build the command used by the GUI to isolate a model transfer."""

    normalized = str(family).strip().casefold()
    if normalized not in {"sd15", "sdxl"}:
        raise ValueError("family harus sd15 atau sdxl")
    launcher = str(executable or sys.executable)
    install_root = str(Path(root).expanduser().resolve())
    progress_path = str(Path(event_file).expanduser().resolve())
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    arguments = [
        RUNTIME_INSTALL_FLAG,
        "--family",
        normalized,
        "--root",
        install_root,
        "--event-file",
        progress_path,
    ]
    if is_frozen:
        return [launcher, *arguments]
    return [launcher, "-m", "batikcraft_studio.runtime_model_process", *arguments]


def _write_event(stream: TextIO, kind: str, **payload: object) -> None:
    stream.write(json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "\n")
    stream.flush()


def run_runtime_model_installer(
    family: str,
    *,
    root: str | Path,
    event_file: str | Path,
    installer_override: Callable[..., object] | None = None,
) -> int:
    """Run one managed model installer and serialize progress as JSON lines.

    The downloader runs in a child process, so every compatibility and integrity
    policy required by the desktop process must be installed again here.  Without
    that, an interrupted SDXL folder could pass the legacy folder-only check and
    emit a false ``complete`` event immediately.
    """

    from batikcraft_studio.ai.model_connectivity import apply_saved_model_connectivity
    from batikcraft_studio.ai.sdxl_runtime_integrity import (
        install_sdxl_runtime_integrity,
        validate_batikbrew_runtime_strict,
    )
    from batikcraft_studio.dependency_bootstrap import activate_managed_ai_packages
    from batikcraft_studio.runtime_compatibility import install_runtime_compatibility

    activate_managed_ai_packages()
    install_runtime_compatibility()
    apply_saved_model_connectivity()
    install_sdxl_runtime_integrity()

    from batikcraft_studio.ai.runtime_model_installer import (
        RuntimeModelInstallCancelled,
        RuntimeModelInstallError,
        RuntimeModelInstallProgress,
        install_batikbrew_runtime,
        install_default_runtime_models,
    )

    normalized = str(family).strip().casefold()
    if normalized not in {"sd15", "sdxl"}:
        raise ValueError("family harus sd15 atau sdxl")
    installer = installer_override or (
        install_batikbrew_runtime if normalized == "sdxl" else install_default_runtime_models
    )
    progress_path = Path(event_file).expanduser().resolve()
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    with progress_path.open("w", encoding="utf-8", errors="replace", buffering=1) as stream:
        def report(event: RuntimeModelInstallProgress) -> None:
            _write_event(stream, "progress", **asdict(event))

        try:
            installed = installer(Path(root).expanduser().resolve(), progress=report)
            if normalized == "sdxl":
                # Never trust a return code alone. Validate the exact folder that the
                # worker is about to report as complete.
                validate_batikbrew_runtime_strict(installed)
        except RuntimeModelInstallCancelled as exc:
            _write_event(stream, "cancelled", message=str(exc))
            return 2
        except RuntimeModelInstallError as exc:
            _write_event(stream, "error", message=str(exc))
            return 1
        except Exception as exc:  # noqa: BLE001 - preserve worker failure details
            _write_event(stream, "error", message=f"Instalasi gagal: {exc}")
            return 1

        _write_event(stream, "complete", family=normalized)
        return 0


def maybe_run_runtime_model_installer(argv: Sequence[str] | None = None) -> int | None:
    """Run the private model-worker entry point when its flag is present."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != RUNTIME_INSTALL_FLAG:
        return None
    parser = argparse.ArgumentParser(prog="BatikCraftStudio runtime model installer")
    parser.add_argument(RUNTIME_INSTALL_FLAG, action="store_true")
    parser.add_argument("--family", required=True, choices=("sd15", "sdxl"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--event-file", required=True)
    namespace = parser.parse_args(arguments)
    return run_runtime_model_installer(
        namespace.family,
        root=namespace.root,
        event_file=namespace.event_file,
    )


def main() -> int:
    result = maybe_run_runtime_model_installer()
    if result is None:
        raise SystemExit(f"{RUNTIME_INSTALL_FLAG} diperlukan")
    return result


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RUNTIME_INSTALL_FLAG",
    "maybe_run_runtime_model_installer",
    "run_runtime_model_installer",
    "runtime_model_install_command",
]
