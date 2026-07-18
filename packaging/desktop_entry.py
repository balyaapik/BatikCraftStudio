"""Frozen desktop entry point for BatikCraft Studio."""

from __future__ import annotations

import sys

from batikcraft_studio.dependency_bootstrap import maybe_run_dependency_installer

installer_exit_code = maybe_run_dependency_installer(sys.argv[1:])
if installer_exit_code is not None:
    raise SystemExit(installer_exit_code)

from batikcraft_studio.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
