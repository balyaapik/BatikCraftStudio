# Training an SDXL Batik Style LoRA for BatikBrew

Notebook: `notebooks/kaggle_train_batikbrew_sdxl_style_lora.ipynb`

## Purpose

Turn a photo of **any object** — a bottle, a flower, a wayang figure, a vehicle — into a
batik ornament through **BatikBrew**. The LoRA learns *style* only. Object shape is
supplied at inference time, so the target object **does not need to be in the dataset**.

## Why a Separate Notebook

| | `kaggle_train_batik_style_any_object.ipynb` | This notebook |
| --- | --- | --- |
| Base model | Stable Diffusion 1.5 | **Stable Diffusion XL** |
| Resolution | 512 px | 1024 px |
| Used by | Object Batikfication | **BatikBrew** |
| `base_model_family` | `sd15` | `sdxl` |

BatikBrew loads an SDXL pipeline. An `sd15` LoRA cannot be used there, and vice versa.
Since 0.5.3 the application detects the mismatch and runs an SD 1.5 LoRA on an SD 1.5
pipeline instead of failing.

## Where Are the "Bottle → Batik Bottle" Pairs?

There are none, and none are needed. This is *style transfer*, not *paired translation*:

| Stage | Source of **shape** | Source of **style** |
| --- | --- | --- |
| Training | no objects at all | batik images plus a trigger word |
| Inference | your object photo (img2img + ControlNet Canny) | the trained LoRA |

A bottle stays bottle-shaped for two reasons: a low img2img `strength` (0.40–0.55), and
**ControlNet Canny** locking the silhouette to the source image's edges. Because shape is
never learned, one LoRA works for any object — including objects that never appeared in
the dataset.

Paired training — hundreds of original photos alongside batik versions — only makes sense
if you want one very specific, uniform transformation. It is expensive and produces a less
general result. Cell 5c in the notebook already generates original↔batik pairs if you need
them for curation, marketplace examples, or later refinement.

## Kaggle Requirements

- Accelerator: **GPU T4 ×2** or **P100** (roughly 15 GB VRAM).
- **Internet: On** — the SDXL 1.0 base is downloaded.
- Dataset: a folder of **batik images only**. Twenty is the minimum; 200–500 gives a far
  more consistent style.

## Steps

1. Upload your batik images as a Kaggle Dataset.
2. Open the notebook and point `CFG.dataset_root` at that dataset.
3. Optionally adjust `trigger_word`, `max_steps` (1200 ≈ 1.5–2 hours on a T4), and
   `resolution` (drop to 768 if you run out of VRAM).
4. **Run All.** Cell 5 shows an object → batik preview.
5. Download the `*.batikmodel` file from the Output panel.

## Downloading the Result

In the **Output** panel, click the `*.batikmodel` file and use that file's own download
button. **Avoid "Download All"** — Kaggle wraps every output in a single `.zip`, so you
get an archive containing the package rather than the package itself. If you already did,
extract the `.zip` and take the `.batikmodel` from inside it.

## Repairing an Old Package Without Retraining

If you already have training output — a `.zip`, a `.safetensors`, or a `.batikmodel` that
was rejected — this repository includes a small tool that reuses the weights instead of
retraining:

```bash
python scripts/repair_batikmodel.py output.zip
python scripts/repair_batikmodel.py pytorch_lora_weights.safetensors --family sdxl
python scripts/repair_batikmodel.py old-package.batikmodel -o repaired.batikmodel
```

It accepts all three input shapes, including Kaggle's "Download All" `.zip`, infers the
model family from the weights, builds a complete manifest, and validates it before
writing. Use `--family`, `--resolution`, `--id`, `--name`, `--trigger`, or `--author` to
override any inferred value. It needs only Python 3.11+ and no extra libraries.

## Installing in the Application

**Dependency Center → Offline AI Models & LoRA tab → Install .batikmodel…**, then select
the model and press **Activate Model**. Make sure the active base model is
**BatikBrew SDXL (base model)**.

## Using It

Right-click an object or image on the canvas → **Generate BatikBrew Motif/Pattern**. When
the pairing is correct, the log panel shows `Base model family: Stable Diffusion XL` and
`LoRA family: Stable Diffusion XL`.

## Tuning the Result

| Symptom | Adjustment |
| --- | --- |
| Object shape drifts too far | Lower `strength` (0.40–0.50) |
| Batik style too weak | Raise `strength` (0.65–0.75) or the LoRA weight |
| Motif too busy | Reduce `max_steps`, or enrich the dataset captions |
| Silhouette not preserved | Raise `controlnet_conditioning_scale` (0.8–1.0) |
| Colours drift from the batik palette | Add soga and indigo toned images to the dataset |

## If You See "Invalid model manifest"

The application validates the manifest strictly: root keys must be exactly `format`,
`schema_version`, `model`, and `files`; the `model` block must carry all 16 fields
(including `license` and `controlnet_family`); and every `files` entry needs `path`,
`role`, `sha256`, and `size`.

The notebook's packaging cell checks all of this before writing the file, so make sure you
are running the latest version of the notebook.
