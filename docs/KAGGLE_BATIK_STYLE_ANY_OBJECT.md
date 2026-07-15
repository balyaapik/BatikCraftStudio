# Kaggle Batik Style LoRA for Any Object

Notebook: `notebooks/kaggle_train_batik_style_any_object.ipynb`

## Purpose

Train a Batik **style** LoRA from Batik-only imagery, then apply it to an object that may never have appeared in the training data. The object shape is supplied during inference, not learned from the Batik dataset.

Examples include wayang, plants, animals, vehicles, architecture, ornaments, or imported transparent assets.

## Pipeline

Training:

```text
Batik image folders
→ style-focused captions
→ SD 1.5 UNet LoRA training
→ pytorch_lora_weights.safetensors
→ installable .batikmodel
```

Inference:

```text
source object + original alpha/mask
+ optional motif reference
+ Batik LoRA
+ optional Canny ControlNet
→ low-strength img2img
→ restore original silhouette and outlines
→ transparent Batik object PNG
```

The object dataset is intentionally not required. Stable Diffusion supplies general object knowledge; the LoRA supplies Batik visual language.

## Kaggle setup

1. Open the notebook on Kaggle.
2. Enable a GPU accelerator. T4 16 GB is sufficient for the default SD 1.5 configuration.
3. Add a folder containing Batik images through **Add Input**.
4. Optionally add a test object, manual mask, and motif reference.
5. Edit the `CFG` cell.
6. Run the cells in order.

The notebook is standalone and does not clone or import the private repository.

## Dataset guidance

Prefer a diverse, licensed dataset with categories such as:

- parang;
- kawung;
- ceplok;
- mega mendung;
- lereng;
- sogan;
- floral and ornamental Batik;
- isen-isen and wax-resist line details.

The auto-captioner uses folder names only as Batik style tags. It avoids requiring object labels.

Recommended starting point:

```text
resolution: 512
batch size: 1
gradient accumulation: 4
steps: 1200–2000
LoRA rank: 16
learning rate: 1e-4
```

## Preserving an unseen object

A transparent PNG is best. For a flat background, the notebook estimates the foreground from corner colors. A manual mask can override it.

When identity drifts:

```text
strength: 0.25–0.34
ControlNet scale: 0.95–1.15
outline strength: increase gradually
```

When Batik is too weak:

```text
LoRA weight: 0.90–1.10
strength: increase gradually
motif reference: provide one
```

## Outputs

```text
/kaggle/working/batikcraft-any-object-lora/
├── lora/pytorch_lora_weights.safetensors
├── object-previews/
├── training-report.json
└── batikcraft-style-any-object-v1.batikmodel
```

Install the `.batikmodel` through BatikCraftStudio's Model Manager. The offline application runtime still needs a compatible local SD 1.5 base model and Canny ControlNet when ControlNet is enabled.

## Scope and limitations

- Exact silhouette is restored after diffusion, but internal semantic details can still change.
- A style LoRA cannot guarantee culturally correct symbolism without curated labels and expert review.
- The first Kaggle run may download the base and ControlNet models.
- CI validates notebook structure and Python syntax; full GPU training is not executed in GitHub Actions.
