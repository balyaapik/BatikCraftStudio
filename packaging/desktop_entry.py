"""Frozen desktop entry point for BatikCraft Studio."""

from __future__ import annotations

import sys

from batikcraft_studio.dependency_bootstrap import maybe_run_dependency_installer
from batikcraft_studio.runtime_model_process import maybe_run_runtime_model_installer

runtime_exit_code = maybe_run_runtime_model_installer(sys.argv[1:])
if runtime_exit_code is not None:
    raise SystemExit(runtime_exit_code)

installer_exit_code = maybe_run_dependency_installer(sys.argv[1:])
if installer_exit_code is not None:
    raise SystemExit(installer_exit_code)

from batikcraft_studio.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
