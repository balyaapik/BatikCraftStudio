# BatikCraft Studio 0.4.4

## Fixed

- Fixed `PermissionError: [WinError 5]` on `torch\lib\asmjit.dll` when installing Accelerate + PEFT after PyTorch CUDA.
- Companion dependency installs no longer use the destructive `pip --target --upgrade` policy against an active managed Torch runtime.
- Pip dependency resolution is constrained to the exact installed Torch version and matching official CPU/CUDA wheel index.
- Stale `torch-*.dist-info` metadata left by a failed CPU-wheel replacement is removed without touching loaded Torch DLLs.
- Accelerate/PEFT installation now requires the user to install either PyTorch CUDA or PyTorch CPU first.
- The installer verifies that the Torch variant remains unchanged after companion packages finish installing.

## Validation

- Added regression tests for locked CUDA DLL preservation, exact Torch constraints, matching CUDA index selection, and safe stale-metadata cleanup.
- Existing direct PyTorch installation behavior remains unchanged: old Torch is purged in the isolated worker, the selected official index is exclusive, and the installed variant is verified.
