# AI, Training, NFT, and Marketplace Audit (July 2026)

## Two Families of AI

**Local models** — available and working: Stable Diffusion 1.5 with ControlNet for
object batikfication, and SDXL with LoRA for BatikBrew. Both load from the local model
library (`runtime_model_installer`, `batikbrew_generation`).

**Cloud models** — available: OpenAI (Image API), Google Gemini (Image API), and IBM
watsonx.ai (`generation_providers.PROVIDER_WATSONX`). The provider is chosen in the
"Select AI Generation Model" dialog; API keys are stored in the system keyring.

**Claude (Anthropic)** — *cannot be used for batikfication*. Anthropic does not offer an
image generation API, and batikfication requires an image-to-image model. The realistic
option, if Claude integration is still wanted, is to use it to compose and enrich prompts
that an image provider (OpenAI, Gemini, watsonx, or SDXL) then executes. Not implemented;
this needs a product decision.

## Stable Diffusion Download Efficiency (Fixed)

Downloads were enormous and slow because the `unet/*`, `vae/*`, and `text_encoder/*`
patterns pulled **every** duplicate of each weight — `.bin` *and* `.safetensors`, fp32
*and* `.fp16` *and* `non_ema` — while the pipeline loads only one set.

The installer now deduplicates per weight (`_dedupe_weight_files`): `.safetensors` takes
priority, and duplicate `.fp16` / `non_ema` variants are skipped.

| Model | Before | After |
| --- | --- | --- |
| SD 1.5 | ~15 GB | ~5.2 GB |
| SDXL | ~19 GB | ~13 GB |
| ControlNet | 2.9 GB | 1.45 GB |

Per-file resume and safe cancellation already existed and still work; the progress bar
reports real byte counts.

## Batikfication Now Always Uses a Model (Fixed)

"Non-AI batikfication" was removed from the context menu, the `Ctrl+Shift+B` shortcut,
and its dialog. All batikfication now goes through a model — local SD, LoRA, or cloud.
The internal deterministic renderer remains because the model pipeline uses it as a
pre-processing stage.

## AI Dependencies and Progress Reporting

The Dependency Manager installs AI packages into a managed per-profile directory,
streams the log, and can be cancelled. Model download progress reports real byte
percentages per stage.

Suggested follow-up, not yet done and requiring hands-on GUI testing: one uniform
progress window for **all** downloads — dependencies, models, and asset packs — with a
queue, time estimates, and history.

## User Model Training — Matches the Intended Flow

1. **Train.** AI menu → Dataset Studio to prepare a dataset → local LoRA training
   (`LocalLoraTrainingWindow`) with progress, logging, and cancellation.
2. **Save to the library.** Training output is stored in the local model library and can
   be activated for generation; LoRA activation persists across sessions.
3. **Sell via BatikCraftWeb.** `publish_model_pack` from the Marketplace menu, with a
   price. Buyers purchase (`purchase_model`), then download and install
   (`download_model` plus the "My Model Library" tab).

## Motif NFTs — Present, Including Minting

A project or motif is packaged as `.batiknft` (see `BATIKCRAFT_NFT_FORMAT`). The
"Mint and Publish Active Project as NFT…" menu uploads it through `publish_nft_package`
with a starting auction price. The marketplace lists NFTs, auction status, and bids
(`place_bid`).

## Selling Model Libraries — Working

The "Model Marketplace" tab (buying) and "My Model Library" tab (installing) work
through `list_models`, `purchase_model`, `model_library`, and `download_model`.

## NFT Economics View (New)

Marketplace menu → **"NFT Economics Analysis…"** opens a line chart of price movement per
NFT, built from bid history (`GET nfts/{id}/bids/`). The summary shows starting and
current price, low and high, bid count, trend percentage, and auction status.

Note: if the BatikCraftWeb backend does not yet expose a bid history endpoint, the window
shows a fallback message. The server side needs to expose the bid list; the POST route
already exists.
