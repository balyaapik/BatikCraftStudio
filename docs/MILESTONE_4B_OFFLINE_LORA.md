# Milestone 4B — Offline LoRA Dataset and Model Pipeline

Milestone 4B replaces the planned internet provider with a local-only model workflow.

## Guarantees

- BatikCraft does not upload the canvas, prompt, dataset, or model.
- Base model, ControlNet, and LoRA paths must exist on the user's computer.
- Hugging Face offline variables are enabled.
- Diffusers loaders use `local_files_only=True`.
- A failed model load or inference does not mutate the project.
- Source, Batik render, and isen/detail remain separate objects.

The repository does not contain multi-gigabyte model weights. Distribution builds can bundle
`.batikmodel` files and local Diffusers model folders beside the installer.

## Dataset Studio

Open:

```text
AI Batik → Dataset Studio…
```

Each sample supports:

- required Batik target;
- optional source or sketch;
- optional line-art conditioning image;
- optional mask;
- caption/prompt;
- category and style;
- target roles.

The output is:

```text
*.batikdataset
```

A dataset archive contains canonical PNG files, metadata, captions, and SHA-256 checksums.

Style-only LoRA data needs a target and caption. Paired transformation data such as
`human sketch → wayang Batik` should also include source, conditioning, and mask.

## Training notebook

Use:

```text
notebooks/kaggle_train_batikcraft_lora.ipynb
```

The notebook is standalone and does not clone BatikCraftStudio. It embeds
`offline_lora_training_pipeline.py`, accepts one `.batikdataset`, trains an SD 1.5 UNet LoRA,
generates validation previews, and exports:

```text
*.batikmodel
```

The notebook supports a local Diffusers base-model folder under `/kaggle/input`. A model ID may
also be used during training when Kaggle internet is enabled, but the resulting desktop runtime
still requires local model folders.

## Model pack

A `.batikmodel` contains:

```text
manifest.json
lora/pytorch_lora_weights.safetensors
previews/
training-report.json
```

Its manifest records:

- model ID and version;
- base-model family;
- trigger words;
- recommended LoRA weight;
- resolution;
- capabilities;
- ControlNet family;
- license and author;
- checksums and byte sizes.

## Offline Model Manager

Open:

```text
AI Batik → Kelola Model Offline…
```

Workflow:

1. Install a `.batikmodel`.
2. Select the installed LoRA.
3. Choose a local Diffusers base-model directory.
4. Choose a local ControlNet directory.
5. Configure device, precision, steps, and adapter strengths.
6. Activate the model.

Installed models are stored in:

```text
Windows:
%LOCALAPPDATA%\BatikCraftStudio\models

Linux:
$XDG_DATA_HOME/BatikCraftStudio/models
```

Set `BATIKCRAFT_MODEL_LIBRARY` to override the directory.

## Selection-to-Batik

Use:

```text
AI Batik → Batifikasi Seleksi Area…
Ctrl+Alt+S
```

Drag a rectangle around lines, strokes, or visible objects. BatikCraft:

1. snapshots the selected area;
2. removes pixels matching the canvas background;
3. preserves the snapshot as an editable source object;
4. opens the prompt dialog;
5. runs the active local provider;
6. creates a separate render object;
7. creates a separate isen/detail object when enabled.

The complete operation is one Undo transaction.

Example prompt:

```text
jadikan tokoh ini wayang kulit perempuan dengan ornamen batik klasik Jawa
```

## Local runtime

The optional application extra is:

```powershell
python -m pip install -e ".[ai]"
```

The provider lazily imports Torch and Diffusers. The editor remains usable without these packages,
using the deterministic Milestone 4A foundation renderer.

The first local provider uses:

```text
local base model
+ local ControlNet line-art
+ installed LoRA
+ selected canvas snapshot
+ prompt
```

The generated image retains the source alpha. High-frequency details are extracted into a
separate transparent isen/detail component. Future model packs can replace this heuristic with a
multi-pass component model while keeping the project format unchanged.

## Suggested first model

```text
Base family: SD 1.5
Resolution: 512
LoRA rank: 16
Trigger: bcr_wayang
Training steps: 1,200 initial experiment
ControlNet: local line-art compatible with the same base family
```

Training quality depends on dataset rights, captions, consistency, and sample diversity. Dataset
Studio stores author and license metadata so model packs can retain provenance.
