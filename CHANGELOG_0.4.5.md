# BatikCraft Studio 0.4.5

## Fixed

- Partial SDXL/base-model folders left after an out-of-disk-space failure are no longer reported as installed.
- Model installation status now depends on complete runtime validation instead of merely checking whether the destination folder contains files.
- Partially downloaded models are shown as `PERLU REPARASI` and their progress remains below 100% until validation succeeds.
- Disk eligibility and pre-download checks now use the remaining required model size, allowing safe resume after storage is freed.
- Batch installation results now preserve failure counts and no longer display a generic success message or force overall progress to 100% when any component fails.
- Resumable partial files are retained so users can continue the download without starting over.

## Validation

- Added regression tests for partial SDXL detection, validated installation state, insufficient-disk preflight failure, resumable progress, and failed-batch status handling.
- CI, Windows installer build, and the bundled dependency installer smoke test must pass before publication.
