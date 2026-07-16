# BatikBrew SDXL Generation in BatikCraft Studio

BatikCraft Studio now ports the generation architecture from the BatikCraft notebooks instead of treating an object as an img2img texture-fill target.

## Source notebooks

- `BatikCraft/notebooks/BatikBrew_AI_Training_Kaggle_FIXED_v1_2.ipynb`
- `BatikCraft/notebooks/BatikBrew_AI_Model_Testing_Colab.ipynb`

The training notebook teaches a LoRA on top of Stable Diffusion XL. The testing notebook treats uploaded photos as inspiration: it analyses colours, edge density, filename/theme hints, and composition, then builds a Batik prompt for SDXL text-to-image generation.

## Studio workflow

1. Select one object on the canvas as the primary inspiration.
2. Optionally Shift-select a second object to combine two sources.
3. Choose **Generate Motif BatikBrew — SDXL LoRA…**.
4. Studio extracts a dominant Batik palette, edge density, theme keywords, and a composition hint.
5. The Batik grammar prompt is built from the notebook rules.
6. SDXL + the BatikBrew LoRA generates one to four independent seed variations.
7. Opposite edges are blended when tileable output is enabled.
8. The user selects one variation before it is added to the project.

The source image is not passed to SDXL as an img2img input. It is not filled with a repeating texture, masked, or traced. It is used only to produce the creative prompt context.

## Required model family

The BatikBrew notebook LoRA is trained for:

```text
stabilityai/stable-diffusion-xl-base-1.0
```

An SD 1.5 LoRA cannot be loaded into the SDXL pipeline. Model packs intended for this workflow should declare:

```json
{
  "base_model_family": "sdxl",
  "capabilities": [
    "batikbrew-generation",
    "text-to-image",
    "multi-variation",
    "tileable-output"
  ],
  "metadata": {
    "generation_engine": "batikbrew-sdxl-notebook",
    "base_model_id": "stabilityai/stable-diffusion-xl-base-1.0"
  }
}
```

A raw `batikbrew_lora.safetensors` file can also be selected directly in the generation dialog.

## Managed runtime

Use either of these locations in the application:

```text
AI Batik → Kelola Model LoRA → Instal BatikBrew SDXL…
```

or:

```text
Generate Motif BatikBrew → Unduh SDXL…
```

The model is downloaded once to the persistent per-user runtime folder. The download is resumable and shows progress.

## Metadata saved with the generated object

Each selected result stores:

- generation engine and mode;
- base model and LoRA path;
- prompt and negative prompt;
- extracted palette and theme keywords;
- edge density and composition hint;
- seed and variation index;
- guidance, steps, and resolution;
- whether tileable processing was applied.

This allows project exports and future marketplace uploads to identify how a motif was generated.
