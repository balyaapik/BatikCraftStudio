"""Local SDXL LoRA training worker for BatikCraft `.batikdataset` archives."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image

from batikcraft_studio.ai.dataset_pack import load_batik_dataset, safe_identifier
from batikcraft_studio.ai.model_pack import (
    BatikModelManifest,
    build_batik_model_pack,
)


ProgressCallback = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class LocalLoraTrainingConfig:
    dataset_path: str
    base_model: str
    output_dir: str
    model_name: str
    model_id: str
    version: str = "1.0.0"
    resolution: int = 1024
    max_steps: int = 500
    learning_rate: float = 1e-4
    rank: int = 16
    alpha: int = 16
    batch_size: int = 1
    gradient_accumulation: int = 4
    seed: int = 2026

    def validate(self) -> "LocalLoraTrainingConfig":
        dataset = Path(self.dataset_path).expanduser()
        if not dataset.is_file():
            raise ValueError(f"Dataset tidak ditemukan: {dataset}")
        if not self.base_model.strip():
            raise ValueError("Base model SDXL wajib diisi.")
        if not self.model_name.strip():
            raise ValueError("Nama model wajib diisi.")
        safe_identifier(self.model_id)
        if self.resolution not in {512, 640, 768, 896, 1024}:
            raise ValueError("Resolution harus 512, 640, 768, 896, atau 1024.")
        if not 10 <= self.max_steps <= 100_000:
            raise ValueError("Max steps harus berada antara 10 dan 100000.")
        if not math.isfinite(self.learning_rate) or not 1e-7 <= self.learning_rate <= 1e-2:
            raise ValueError("Learning rate harus berada antara 1e-7 dan 1e-2.")
        if self.rank not in {4, 8, 16, 32, 64, 128}:
            raise ValueError("LoRA rank harus 4, 8, 16, 32, 64, atau 128.")
        if not 1 <= self.alpha <= 256:
            raise ValueError("LoRA alpha harus berada antara 1 dan 256.")
        if not 1 <= self.batch_size <= 8:
            raise ValueError("Batch size harus berada antara 1 dan 8.")
        if not 1 <= self.gradient_accumulation <= 64:
            raise ValueError("Gradient accumulation harus berada antara 1 dan 64.")
        return self


def default_training_root() -> Path:
    """Return the per-user training output folder."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BatikCraftStudio" / "training"


def run_local_lora_training(
    config: LocalLoraTrainingConfig,
    *,
    progress: ProgressCallback = print,
) -> Path:
    """Train one UNet LoRA and package it as an installable `.batikmodel`."""

    config.validate()
    bundle = load_batik_dataset(config.dataset_path)
    if "sdxl" not in bundle.metadata.base_model_family.casefold():
        raise ValueError(
            "Dataset bukan SDXL. Ubah Base Model Family menjadi 'sdxl' dari Dataset Studio."
        )

    progress(f"Dataset: {bundle.metadata.name} · {len(bundle.samples)} sample")
    progress("Memeriksa runtime PyTorch, Diffusers, Transformers, dan PEFT…")

    try:
        import numpy as np
        import torch
        import torch.nn.functional as functional
        from diffusers import DDPMScheduler, StableDiffusionXLPipeline
        from diffusers.utils import convert_state_dict_to_diffusers
        from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
    except ImportError as exc:
        raise RuntimeError(
            "Dependency training belum lengkap. Buka menu Dependencies lalu instal paket AI."
        ) from exc

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Training LoRA lokal memerlukan GPU CUDA. CPU sengaja tidak digunakan karena "
            "waktu training dapat sangat lama."
        )

    output_dir = Path(config.output_dir).expanduser()
    run_dir = output_dir / safe_identifier(config.model_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)

    dtype = torch.float16
    device = torch.device("cuda")
    progress(f"Memuat SDXL: {config.base_model}")
    pipeline = StableDiffusionXLPipeline.from_pretrained(
        config.base_model,
        torch_dtype=dtype,
        use_safetensors=True,
    )
    pipeline.set_progress_bar_config(disable=True)
    pipeline.vae.requires_grad_(False)
    pipeline.text_encoder.requires_grad_(False)
    pipeline.text_encoder_2.requires_grad_(False)
    pipeline.unet.requires_grad_(False)

    lora_config = LoraConfig(
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=("to_q", "to_k", "to_v", "to_out.0"),
        lora_dropout=0.05,
        bias="none",
    )
    pipeline.unet = get_peft_model(pipeline.unet, lora_config)
    pipeline.unet.enable_gradient_checkpointing()
    pipeline.to(device)

    trainable = [parameter for parameter in pipeline.unet.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=config.learning_rate,
        betas=(0.9, 0.999),
        weight_decay=1e-2,
        eps=1e-8,
    )
    scheduler = DDPMScheduler.from_config(pipeline.scheduler.config)

    samples = list(bundle.samples)
    if not samples:
        raise RuntimeError("Dataset tidak memiliki sample training.")

    optimizer.zero_grad(set_to_none=True)
    effective_batch = config.batch_size * config.gradient_accumulation
    progress(
        "Training dimulai: "
        f"{config.max_steps} steps · batch efektif {effective_batch} · rank {config.rank}"
    )

    global_step = 0
    micro_step = 0
    while global_step < config.max_steps:
        batch_samples = [
            samples[(micro_step * config.batch_size + index) % len(samples)]
            for index in range(config.batch_size)
        ]
        images = torch.stack(
            [
                _image_tensor(sample.target_content, config.resolution, np, torch)
                for sample in batch_samples
            ]
        ).to(device=device, dtype=dtype)
        prompts = [
            _training_caption(
                sample.caption,
                trigger_word=bundle.metadata.trigger_word,
                category=sample.category,
                style=sample.style,
            )
            for sample in batch_samples
        ]

        with torch.no_grad():
            latents = pipeline.vae.encode(images).latent_dist.sample()
            latents = latents * pipeline.vae.config.scaling_factor
            encoded = pipeline.encode_prompt(
                prompt=prompts,
                device=device,
                num_images_per_prompt=1,
                do_classifier_free_guidance=False,
            )
            prompt_embeds = encoded[0]
            pooled_prompt_embeds = encoded[2]

        noise = torch.randn_like(latents)
        timesteps = torch.randint(
            0,
            scheduler.config.num_train_timesteps,
            (latents.shape[0],),
            device=device,
            dtype=torch.long,
        )
        noisy_latents = scheduler.add_noise(latents, noise, timesteps)
        time_ids = torch.tensor(
            [
                config.resolution,
                config.resolution,
                0,
                0,
                config.resolution,
                config.resolution,
            ],
            device=device,
            dtype=pooled_prompt_embeds.dtype,
        ).repeat(latents.shape[0], 1)
        prediction = pipeline.unet(
            noisy_latents,
            timesteps,
            encoder_hidden_states=prompt_embeds,
            added_cond_kwargs={
                "text_embeds": pooled_prompt_embeds,
                "time_ids": time_ids,
            },
        ).sample
        if scheduler.config.prediction_type == "v_prediction":
            target = scheduler.get_velocity(latents, noise, timesteps)
        else:
            target = noise
        loss = functional.mse_loss(prediction.float(), target.float(), reduction="mean")
        (loss / config.gradient_accumulation).backward()
        micro_step += 1

        if micro_step % config.gradient_accumulation != 0:
            continue
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        global_step += 1
        if global_step == 1 or global_step % 10 == 0 or global_step == config.max_steps:
            progress(
                f"STEP {global_step}/{config.max_steps} · loss={loss.item():.6f}"
            )

    progress("Menyimpan bobot LoRA…")
    state = get_peft_model_state_dict(pipeline.unet)
    diffusers_state = convert_state_dict_to_diffusers(state)
    StableDiffusionXLPipeline.save_lora_weights(
        str(weights_dir),
        unet_lora_layers=diffusers_state,
        safe_serialization=True,
    )
    weights = weights_dir / "pytorch_lora_weights.safetensors"
    if not weights.is_file():
        candidates = tuple(weights_dir.glob("*.safetensors"))
        if not candidates:
            raise RuntimeError("Diffusers tidak menghasilkan file LoRA safetensors.")
        weights = candidates[0]

    report_path = run_dir / "training-report.json"
    report = {
        "format": "batikcraft-local-lora-training-report",
        "schema_version": "1.0",
        "dataset": {
            "id": bundle.metadata.dataset_id,
            "name": bundle.metadata.name,
            "samples": len(bundle.samples),
            "trigger_word": bundle.metadata.trigger_word,
        },
        "config": asdict(config),
        "result": {
            "weights": str(weights),
            "steps": config.max_steps,
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = BatikModelManifest(
        model_id=config.model_id,
        name=config.model_name,
        version=config.version,
        model_type="lora",
        base_model_family="sdxl",
        trigger_words=(bundle.metadata.trigger_word,),
        recommended_weight=0.85,
        resolution=config.resolution,
        capabilities=("ornament", "pattern"),
        lora_file=weights.name,
        author=bundle.metadata.author,
        description=bundle.metadata.description
        or f"LoRA lokal dari dataset {bundle.metadata.name}.",
        license_name="Creator-defined",
        metadata={
            "training_backend": "BatikCraftStudio local SDXL LoRA",
            "dataset_id": bundle.metadata.dataset_id,
        },
    )
    package_path = build_batik_model_pack(
        manifest,
        weights,
        run_dir / f"{safe_identifier(config.model_id)}.batikmodel",
        training_report=report_path,
    )
    progress(f"RESULT:{package_path}")

    del pipeline
    torch.cuda.empty_cache()
    return package_path


def _image_tensor(content: bytes, resolution: int, np: object, torch: object):
    with Image.open(BytesIO(content)) as source:
        image = source.convert("RGB")
        width, height = image.size
        scale = resolution / min(width, height)
        resized = image.resize(
            (max(resolution, round(width * scale)), max(resolution, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
        left = max(0, (resized.width - resolution) // 2)
        top = max(0, (resized.height - resolution) // 2)
        cropped = resized.crop((left, top, left + resolution, top + resolution))
        array = np.asarray(cropped).astype("float32") / 127.5 - 1.0
    return torch.from_numpy(array).permute(2, 0, 1)


def _training_caption(
    caption: str,
    *,
    trigger_word: str,
    category: str,
    style: str,
) -> str:
    values = [trigger_word, caption.strip(), category.strip(), style.strip()]
    unique = tuple(dict.fromkeys(value for value in values if value))
    return ", ".join(unique)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train BatikCraft SDXL LoRA locally")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = LocalLoraTrainingConfig(
        dataset_path=args.dataset,
        base_model=args.base_model,
        output_dir=args.output_dir,
        model_name=args.model_name,
        model_id=args.model_id,
        version=args.version,
        resolution=args.resolution,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        rank=args.rank,
        alpha=args.alpha,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
        seed=args.seed,
    )
    run_local_lora_training(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LocalLoraTrainingConfig",
    "default_training_root",
    "run_local_lora_training",
]
