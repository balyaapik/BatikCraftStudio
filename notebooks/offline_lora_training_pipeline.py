"""Standalone BatikCraft LoRA training pipeline for Kaggle or a local GPU.

This file deliberately has no imports from `batikcraft_studio`. A notebook can embed it and train
from one `.batikdataset`, then export one installable `.batikmodel`.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BATIK_DATASET_FORMAT = "batikcraft-training-dataset"
BATIK_MODEL_FORMAT = "batikcraft-model-pack"


@dataclass(slots=True)
class TrainingConfig:
    dataset_path: str
    base_model: str
    output_dir: str = "/kaggle/working/batikcraft-lora-output"
    model_id: str = "batikcraft-custom-v1"
    model_name: str = "BatikCraft Custom LoRA"
    trigger_word: str = "bcr_batik"
    base_model_family: str = "sd15"
    resolution: int = 512
    train_batch_size: int = 1
    gradient_accumulation_steps: int = 4
    max_train_steps: int = 1200
    learning_rate: float = 1e-4
    rank: int = 16
    seed: int = 2026
    mixed_precision: str = "fp16"
    checkpointing_steps: int = 250
    validation_prompt: str = "bcr_batik, ornamental Indonesian batik motif"
    validation_images: int = 4
    recommended_weight: float = 0.85
    author: str = ""
    description: str = ""
    license_name: str = ""


def extract_batikdataset(
    archive_path: str | Path,
    output_dir: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate checksums and convert targets/captions to ImageFolder metadata."""

    source = Path(archive_path)
    destination = Path(output_dir)
    if destination.exists():
        shutil.rmtree(destination)
    images_dir = destination / "train"
    images_dir.mkdir(parents=True)
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != BATIK_DATASET_FORMAT:
            raise RuntimeError("File bukan BatikCraft training dataset.")
        samples = manifest.get("samples")
        if not isinstance(samples, list) or not samples:
            raise RuntimeError("Dataset tidak memiliki sample.")
        metadata_rows: list[dict[str, str]] = []
        normalized: list[dict[str, Any]] = []
        for index, sample in enumerate(samples):
            files = sample.get("files", {})
            checksums = sample.get("sha256", {})
            target_name = files.get("target")
            if not isinstance(target_name, str):
                raise RuntimeError(f"Sample {index + 1} tidak memiliki target.")
            content = archive.read(target_name)
            if hashlib.sha256(content).hexdigest() != checksums.get("target"):
                raise RuntimeError(f"Checksum target sample {index + 1} tidak cocok.")
            filename = f"{index:06d}.png"
            (images_dir / filename).write_bytes(content)
            caption = str(sample.get("caption", "")).strip()
            if not caption:
                raise RuntimeError(f"Caption sample {index + 1} kosong.")
            metadata_rows.append({"file_name": filename, "text": caption})
            normalized.append(
                {
                    "file_name": filename,
                    "caption": caption,
                    "category": sample.get("category", ""),
                    "style": sample.get("style", ""),
                    "source_available": "source" in files,
                    "conditioning_available": "conditioning" in files,
                    "mask_available": "mask" in files,
                }
            )
    with (images_dir / "metadata.jsonl").open("w", encoding="utf-8") as handle:
        for row in metadata_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {
        "dataset": manifest["dataset"],
        "sample_count": len(normalized),
        "samples": normalized,
    }
    (destination / "dataset-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest["dataset"], normalized


def train_lora(config: TrainingConfig) -> Path:
    """Train UNet LoRA weights with Diffusers, PEFT, and Accelerate."""

    _seed_everything(config.seed)
    output_dir = Path(config.output_dir)
    prepared_dir = output_dir / "prepared-dataset"
    dataset_metadata, samples = extract_batikdataset(
        config.dataset_path,
        prepared_dir,
    )
    trigger_word = config.trigger_word or dataset_metadata.get("trigger_word", "bcr_batik")
    output_dir.mkdir(parents=True, exist_ok=True)

    import torch
    import torch.nn.functional as functional
    from accelerate import Accelerator
    from datasets import load_dataset
    from diffusers import AutoencoderKL, DDPMScheduler, StableDiffusionPipeline, UNet2DConditionModel
    from diffusers.optimization import get_scheduler
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict
    from torch.utils.data import DataLoader
    from torchvision import transforms
    from transformers import CLIPTextModel, CLIPTokenizer

    accelerator = Accelerator(
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        mixed_precision=config.mixed_precision,
    )
    tokenizer = CLIPTokenizer.from_pretrained(
        config.base_model,
        subfolder="tokenizer",
    )
    text_encoder = CLIPTextModel.from_pretrained(
        config.base_model,
        subfolder="text_encoder",
    )
    vae = AutoencoderKL.from_pretrained(config.base_model, subfolder="vae")
    unet = UNet2DConditionModel.from_pretrained(config.base_model, subfolder="unet")
    noise_scheduler = DDPMScheduler.from_pretrained(
        config.base_model,
        subfolder="scheduler",
    )

    vae.requires_grad_(False)
    text_encoder.requires_grad_(False)
    unet.requires_grad_(False)
    unet.add_adapter(
        LoraConfig(
            r=config.rank,
            lora_alpha=config.rank,
            init_lora_weights="gaussian",
            target_modules=["to_k", "to_q", "to_v", "to_out.0"],
        )
    )

    dataset = load_dataset(
        "imagefolder",
        data_dir=str(prepared_dir / "train"),
        split="train",
    )
    image_transform = transforms.Compose(
        [
            transforms.Resize(
                config.resolution,
                interpolation=transforms.InterpolationMode.BILINEAR,
            ),
            transforms.CenterCrop(config.resolution),
            transforms.RandomHorizontalFlip(p=0.15),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ]
    )

    def preprocess(examples: dict[str, list[Any]]) -> dict[str, Any]:
        images = [image.convert("RGB") for image in examples["image"]]
        captions = [
            _ensure_trigger(str(text), trigger_word)
            for text in examples["text"]
        ]
        examples["pixel_values"] = [image_transform(image) for image in images]
        examples["input_ids"] = tokenizer(
            captions,
            max_length=tokenizer.model_max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        ).input_ids
        return examples

    dataset = dataset.with_transform(preprocess)

    def collate(examples: list[dict[str, Any]]) -> dict[str, Any]:
        pixel_values = torch.stack([example["pixel_values"] for example in examples])
        input_ids = torch.stack([example["input_ids"] for example in examples])
        return {
            "pixel_values": pixel_values.to(memory_format=torch.contiguous_format).float(),
            "input_ids": input_ids,
        }

    loader = DataLoader(
        dataset,
        shuffle=True,
        collate_fn=collate,
        batch_size=config.train_batch_size,
        num_workers=2,
    )
    trainable = [parameter for parameter in unet.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=config.learning_rate,
        betas=(0.9, 0.999),
        weight_decay=1e-2,
        eps=1e-8,
    )
    updates_per_epoch = math.ceil(
        len(loader) / config.gradient_accumulation_steps
    )
    epochs = math.ceil(config.max_train_steps / max(updates_per_epoch, 1))
    scheduler = get_scheduler(
        "constant_with_warmup",
        optimizer=optimizer,
        num_warmup_steps=min(100, config.max_train_steps // 10),
        num_training_steps=config.max_train_steps,
    )
    unet, optimizer, loader, scheduler = accelerator.prepare(
        unet,
        optimizer,
        loader,
        scheduler,
    )
    weight_dtype = (
        torch.float16
        if accelerator.mixed_precision == "fp16"
        else torch.bfloat16
        if accelerator.mixed_precision == "bf16"
        else torch.float32
    )
    vae.to(accelerator.device, dtype=weight_dtype)
    text_encoder.to(accelerator.device, dtype=weight_dtype)
    global_step = 0
    losses: list[float] = []

    for _epoch in range(epochs):
        unet.train()
        for batch in loader:
            with accelerator.accumulate(unet):
                latents = vae.encode(
                    batch["pixel_values"].to(
                        accelerator.device,
                        dtype=weight_dtype,
                    )
                ).latent_dist.sample()
                latents = latents * vae.config.scaling_factor
                noise = torch.randn_like(latents)
                batch_size = latents.shape[0]
                timesteps = torch.randint(
                    0,
                    noise_scheduler.config.num_train_timesteps,
                    (batch_size,),
                    device=latents.device,
                ).long()
                noisy_latents = noise_scheduler.add_noise(
                    latents,
                    noise,
                    timesteps,
                )
                encoder_hidden_states = text_encoder(
                    batch["input_ids"].to(accelerator.device)
                )[0]
                prediction = unet(
                    noisy_latents,
                    timesteps,
                    encoder_hidden_states,
                ).sample
                target = (
                    noise_scheduler.get_velocity(latents, noise, timesteps)
                    if noise_scheduler.config.prediction_type == "v_prediction"
                    else noise
                )
                loss = functional.mse_loss(
                    prediction.float(),
                    target.float(),
                    reduction="mean",
                )
                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(trainable, 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if accelerator.sync_gradients:
                global_step += 1
                losses.append(float(loss.detach().item()))
                if (
                    config.checkpointing_steps > 0
                    and global_step % config.checkpointing_steps == 0
                ):
                    accelerator.save_state(
                        str(output_dir / f"checkpoint-{global_step}")
                    )
            if global_step >= config.max_train_steps:
                break
        if global_step >= config.max_train_steps:
            break

    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        unwrapped = accelerator.unwrap_model(unet)
        lora_state = convert_state_dict_to_diffusers(
            get_peft_model_state_dict(unwrapped)
        )
        StableDiffusionPipeline.save_lora_weights(
            save_directory=str(output_dir / "lora"),
            unet_lora_layers=lora_state,
            safe_serialization=True,
        )
        report = {
            "config": asdict(config),
            "dataset_sample_count": len(samples),
            "global_step": global_step,
            "mean_loss_last_100": (
                sum(losses[-100:]) / len(losses[-100:]) if losses else None
            ),
            "trigger_word": trigger_word,
        }
        (output_dir / "training-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    accelerator.wait_for_everyone()
    return output_dir / "lora" / "pytorch_lora_weights.safetensors"


def generate_validation_previews(
    config: TrainingConfig,
    lora_path: str | Path,
) -> tuple[Path, ...]:
    """Generate deterministic validation previews after training."""

    import torch
    from diffusers import AutoPipelineForText2Image

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    pipeline = AutoPipelineForText2Image.from_pretrained(
        config.base_model,
        torch_dtype=dtype,
    ).to(device)
    weights = Path(lora_path)
    pipeline.load_lora_weights(
        str(weights.parent),
        weight_name=weights.name,
        adapter_name="batikcraft_training",
    )
    pipeline.set_adapters(
        ["batikcraft_training"],
        adapter_weights=[config.recommended_weight],
    )
    previews_dir = Path(config.output_dir) / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    prompt = _ensure_trigger(config.validation_prompt, config.trigger_word)
    for index in range(config.validation_images):
        generator = torch.Generator(device=device).manual_seed(config.seed + index)
        image = pipeline(
            prompt,
            num_inference_steps=30,
            guidance_scale=7.0,
            generator=generator,
        ).images[0]
        path = previews_dir / f"preview-{index + 1:02d}.png"
        image.save(path)
        outputs.append(path)
    return tuple(outputs)


def build_batikmodel(
    config: TrainingConfig,
    lora_path: str | Path,
    previews: tuple[Path, ...] = (),
) -> Path:
    """Package trained weights, previews, and report as one `.batikmodel`."""

    output_dir = Path(config.output_dir)
    weights_path = Path(lora_path)
    report_path = output_dir / "training-report.json"
    files: list[tuple[str, str, bytes]] = [
        ("lora/pytorch_lora_weights.safetensors", "lora", weights_path.read_bytes())
    ]
    for index, preview in enumerate(previews, start=1):
        files.append((f"previews/preview-{index:02d}.png", "preview", preview.read_bytes()))
    if report_path.is_file():
        files.append(("training-report.json", "training-report", report_path.read_bytes()))
    file_manifest = [
        {
            "path": path,
            "role": role,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        for path, role, content in files
    ]
    manifest = {
        "format": BATIK_MODEL_FORMAT,
        "schema_version": "1.0",
        "model": {
            "id": config.model_id,
            "name": config.model_name,
            "version": "1.0.0",
            "type": "lora",
            "base_model_family": config.base_model_family,
            "trigger_words": [config.trigger_word],
            "recommended_weight": config.recommended_weight,
            "resolution": config.resolution,
            "capabilities": [
                "object",
                "selection",
                "inpainting",
                "structured-output",
            ],
            "lora_file": "lora/pytorch_lora_weights.safetensors",
            "author": config.author,
            "description": config.description,
            "license": config.license_name,
            "controlnet_family": "lineart",
            "negative_prompt": (
                "photorealistic, watermark, text, blurry, merged objects, solid background"
            ),
            "metadata": {
                "trainer": "batikcraft-standalone-lora-v1",
                "seed": config.seed,
                "steps": config.max_train_steps,
                "rank": config.rank,
            },
        },
        "files": file_manifest,
    }
    destination = output_dir / f"{config.model_id}.batikmodel"
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        for path, _role, content in files:
            archive.writestr(path, content)
    return destination


def _ensure_trigger(caption: str, trigger_word: str) -> str:
    text = caption.strip()
    return text if trigger_word in text.split() else f"{trigger_word}, {text}"


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass


__all__ = [
    "TrainingConfig",
    "build_batikmodel",
    "extract_batikdataset",
    "generate_validation_previews",
    "train_lora",
]
