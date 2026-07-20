# BatikCraft Studio 0.4.2

## CUDA installer and runtime reliability

- PyTorch CPU and PyTorch CUDA are now mutually exclusive in the Dependency Center.
- **Pilih Semua** chooses CUDA on supported NVIDIA systems and CPU elsewhere.
- Frozen Windows builds preserve the selected Torch variant in the private installer process.
- Torch wheels use the selected official PyTorch index with `--index-url`, preventing a newer CPU wheel from PyPI from replacing CUDA.
- The previous managed Torch package, metadata, and companion directories are removed before changing variants.
- Every explicit Torch installation is verified after pip finishes; a mismatched CPU/CUDA wheel is reported as an installation failure.
- Managed `site-packages` is exposed to later pip processes so Diffusers, Transformers, Accelerate, and PEFT can reuse the installed Torch runtime instead of resolving another wheel.
- On NVIDIA systems, BatikBrew SDXL refuses to fall back to CPU when Torch CUDA is unavailable and shows a repair instruction instead.
- CPU memory preflight now runs before the SDXL pipeline is loaded, reducing hard process termination from RAM exhaustion.

## Upgrade note

After installing **PyTorch GPU (CUDA)**, close and reopen BatikCraft Studio before running Generator Pola or Generator Motif. This ensures the process no longer holds the previous Torch DLLs in memory.
