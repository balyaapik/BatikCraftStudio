# Cloud API Providers for BatikCraftStudio

BatikCraftStudio supports four generation engines from the object context menu:

1. **SDXL + LoRA Lokal**
2. **IBM watsonx.ai API**
3. **Google Gemini Image API**
4. **OpenAI / ChatGPT Image API**

The provider is selected after choosing **Ornamen Tunggal** or **Pola**. The default provider is stored separately for each output mode, so a user can—for example—use OpenAI for isolated ornaments and watsonx.ai for full patterns.

## Configuration

Open:

```text
Right-click selected object
→ Generate Motif BatikBrew — Lokal / API…
→ choose Ornamen Tunggal or Pola
→ Pengaturan API…
```

Non-secret settings are stored in:

```text
%APPDATA%\BatikCraftStudio\cloud_generation.json
```

API keys are stored in the operating-system credential vault through `keyring`. They are never written into:

- `.batikcraft` project files;
- generated object metadata;
- clipboard payloads;
- `.batikcraftnft` packages;
- recent-project metadata.

Environment variables can be used instead and take priority:

```text
OPENAI_API_KEY
GEMINI_API_KEY or GOOGLE_API_KEY
WATSONX_APIKEY or IBM_CLOUD_API_KEY
```

## OpenAI

Default model:

```text
gpt-image-1
```

The integration uses the OpenAI Images API and requests PNG output. Ornamen Tunggal requests a transparent background when supported by the selected model. The normal BatikCraftStudio ornament segmentation still runs afterward to remove any residual background.

## Google Gemini

Default model:

```text
gemini-3.1-flash-image
```

The integration uses the documented `client.models.generate_content` image-generation workflow from `google-genai`, with `response_modalities=["IMAGE"]`. It intentionally does not call the preview `client.interactions` API. Gemini output is normalized to PNG before being committed to the project.

## IBM watsonx.ai

Default endpoint:

```text
https://us-south.ml.cloud.ibm.com
```

Default model:

```text
stable-diffusion-xl-1024-v1-0
```

A watsonx.ai **Project ID** is required. The integration exchanges the IBM Cloud API key for an IAM bearer token, then calls:

```text
POST /ml/v1/text/image?version=2023-07-07
```

with `Accept: image/png`.

## Output behavior

### Ornamen Tunggal

- one isolated Batik ornament;
- no repeat grid;
- background removed;
- cropped PNG with transparent margin;
- copy/paste compatible.

### Pola

- one complete square all-over pattern;
- optional opposite-edge blending for seamless tiling;
- copy/paste compatible;
- tile preview remains available in the variation chooser.

## Reproducibility

Local SDXL uses a deterministic seed. Cloud image APIs do not necessarily guarantee deterministic seed support. BatikCraftStudio therefore sends the seed as a **composition seed hint** and records it in metadata, but `provider_seed_guaranteed` is `false` for cloud results.

## Installation

Cloud provider SDKs are included in the AI extra:

```powershell
python -m pip install -e ".[dev,ai]"
```

This installs `openai`, `google-genai`, and `keyring` alongside the existing local Stable Diffusion dependencies.
