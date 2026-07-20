# BatikCraft Studio 0.4.3

## Fixed

- Fixed the Windows frozen dependency worker using the legacy parser before the release 0.4.2 bootstrap patch was installed.
- Fixed **PyTorch GPU (CUDA)** installation failing with `unrecognized arguments: --torch-variant` and exit code `2`.
- Ensured the private installer accepts and forwards the explicit `cpu` or `cuda` Torch variant before downloading wheels.

## Validation

- Added a regression test that verifies the frozen desktop entry point installs the corrected dependency bootstrap before importing the installer function.
- Desktop CI builds the Windows installer and runs the bundled dependency-installer smoke test.
