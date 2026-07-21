# BatikCraft Studio 0.4.6

## Fixed

- Fixed PyTorch GPU/CPU rows being reported as **Installed** when the managed wheel was incomplete or mixed and failed with `cannot import name 'amp' from partially initialized module 'torch'`.
- PyTorch readiness now validates critical package files, `torch.amp`, `torch.cuda`, the native `torch._C` extension, Windows DLL inventory, wheel metadata, and critical entries from `RECORD`.
- Corrupt PyTorch installations are shown as **NEEDS REPAIR** and never receive 100% progress until validation succeeds.
- Failed partial `torch` imports are cleared safely before a repaired runtime is retried.
- SDXL and SD 1.5 + ControlNet are now resolved independently across the writable managed root and the legacy beside-executable root.
- The Dependency Center and the Offline AI & LoRA model tab now use the same validated model locations.

## Recovery

- Users affected by a mixed PyTorch installation should select the correct PyTorch CUDA or CPU row and run the repair install again, then restart BatikCraft Studio.
- Valid SDXL or SD 1.5/ControlNet model folders are reused even when the two model families are stored in different supported roots.

## Validation

- Added regression coverage for missing `torch/amp`, complete Torch wheel inventory, cleanup of partial imports, and split model-family roots.
- Lint, unit tests, and desktop installer builds passed before release preparation.
