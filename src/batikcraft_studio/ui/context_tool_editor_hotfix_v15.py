"""BatikBrew generation that consumes centrally managed AI settings."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import messagebox

from batikcraft_studio.ai.batikbrew_generation_modes import (
    OUTPUT_MODE_ORNAMENT,
    BatikBrewModeGenerationOptions,
)
from batikcraft_studio.ai.batikbrew_model_settings import (
    get_batikbrew_model_settings_store,
)
from batikcraft_studio.ai.generation_providers import (
    PROVIDER_LOCAL,
    get_api_secret_store,
    get_cloud_generation_settings_store,
    provider_label,
)
from batikcraft_studio.ai.global_runtime import pretrained_batification_options_from_global
from batikcraft_studio.ai.hybrid_batik_generation import CloudBatikBrewOptions
from batikcraft_studio.ai.pretrained_batification import PretrainedAIBatificationOptions
from batikcraft_studio.application import ProjectSessionError
from batikcraft_studio.imaging.structured_batification import BatificationError

from .batikbrew_output_mode_dialog import BatikBrewOutputModeDialog
from .batikbrew_request_dialog import BatikBrewRequest, BatikBrewRequestDialog
from .context_tool_editor_hotfix_v14 import ContextToolEditorWorkspaceView as _HotfixV14Editor
from .progress_dialog import ProgressDialog, ProgressUpdate


class ContextToolEditorWorkspaceView(_HotfixV14Editor):
    """Generate with the provider, API model, runtime, and LoRA saved in Settings."""

    def batify_selected_with_pretrained_ai(self) -> None:
        if self._pretrained_ai_running:
            self.set_status("Generasi BatikBrew masih berjalan. Tunggu proses sebelumnya selesai.")
            progress = self._object_ai_progress
            if progress is not None and progress.winfo_exists():
                progress.lift()
            return
        selected = self._pretrained_ai_session.selected_object_ids
        if len(selected) not in {1, 2}:
            self.set_status(
                "Pilih satu objek inspirasi. Shift-pilih objek kedua untuk menggabungkan "
                "dua sumber inspirasi."
            )
            return

        mode_dialog = BatikBrewOutputModeDialog(self)
        self.wait_window(mode_dialog)
        output_mode = mode_dialog.result
        if output_mode is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return

        cloud_settings = get_cloud_generation_settings_store().load()
        provider_id = cloud_settings.provider_for_mode(output_mode)
        defaults = pretrained_batification_options_from_global()
        options = self._collect_centralized_options(
            defaults=defaults,
            output_mode=output_mode,
            provider_id=provider_id,
        )
        if options is None:
            return

        progress = ProgressDialog(
            self,
            title=(
                "Generate Ornamen BatikBrew"
                if output_mode == OUTPUT_MODE_ORNAMENT
                else "Generate Pola BatikBrew"
            ),
            message="Menyiapkan objek inspirasi…",
            cancellable=False,
            auto_close_ms=None,
        )
        self._object_ai_progress = progress
        progress.post(
            ProgressUpdate(
                "Tahap 1/6 — Membaca objek inspirasi",
                1,
                6,
                detail=(
                    "Satu objek" if len(selected) == 1 else "Dua objek akan dianalisis bersama"
                ),
            )
        )
        try:
            plan = self._pretrained_ai_session.prepare_selected_pretrained_ai(options)
        except ProjectSessionError as exc:
            progress.fail(str(exc))
            self.set_status(str(exc))
            return

        self._pretrained_ai_running = True
        kind = "ornamen tunggal" if output_mode == OUTPUT_MODE_ORNAMENT else "pola penuh"
        provider_name = provider_label(provider_id)
        self.set_status(
            f"{provider_name} sedang membuat {options.variation_count} variasi {kind}."
        )

        def worker() -> None:
            reporter = progress.reporter
            try:
                reporter.update(
                    "Tahap 2/6 — Menganalisis warna, garis, tema, dan komposisi",
                    2,
                    6,
                    detail="Dominant palette, edge density, theme keywords, dan prompt Batik.",
                )
                if provider_id == PROVIDER_LOCAL:
                    stage = "Tahap 3/6 — Memuat model dan LoRA aktif dari Settings"
                    detail = (
                        f"Base model: {options.model_id_or_path}\n"
                        f"LoRA: {Path(options.lora_path).name}"
                    )
                else:
                    stage = f"Tahap 3/6 — Menghubungkan {provider_name}"
                    detail = f"Model API: {getattr(options, 'provider_model', '-')}"
                reporter.update(stage, 3, 6, detail=detail)
                reporter.update(
                    "Tahap 4/6 — Menghasilkan variasi gambar",
                    detail=(
                        f"{options.variation_count} variasi · provider {provider_name} · "
                        f"seed hint {options.seed}"
                    ),
                )
                results = self._pretrained_ai_session.render_pretrained_ai_variations(plan)
                reporter.update(
                    "Tahap 5/6 — Menyelesaikan transparansi atau tileable output",
                    5,
                    6,
                    detail=(
                        "Background dihapus untuk ornamen tunggal"
                        if output_mode == OUTPUT_MODE_ORNAMENT
                        else "Opposite-edge blending untuk pola seamless"
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - provider SDK errors vary
                message = str(exc)
                progress.fail(message)
                self._post_pretrained_ai_callback(
                    lambda: self._finish_batikbrew_error(message)
                )
                return
            self._post_pretrained_ai_callback(
                lambda: self._show_batikbrew_variations(plan, results)
            )

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"batikcraft-batikbrew-{provider_id}-generation",
        ).start()

    def _collect_centralized_options(
        self,
        *,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        provider_id: str,
    ) -> BatikBrewModeGenerationOptions | CloudBatikBrewOptions | None:
        provider_summary = self._provider_summary(provider_id)
        if provider_summary is None:
            return None
        cloud_request = provider_id != PROVIDER_LOCAL
        dialog = BatikBrewRequestDialog(
            self,
            output_mode=output_mode,
            provider_summary=provider_summary,
            prompt=defaults.prompt,
            negative_prompt=defaults.negative_prompt,
            seed=defaults.seed,
            default_variation_count=1 if cloud_request else 4,
            request_notice=(
                "Setiap variasi cloud mengirim satu request gambar terpisah. Default dibuat "
                "1 variasi untuk mengurangi biaya dan mencegah error 429 Too Many Requests."
                if cloud_request
                else "Generasi lokal tidak memakai kuota API; default tetap 4 variasi."
            ),
        )
        self.wait_window(dialog)
        request = dialog.result
        if request is None:
            self.set_status("Generasi BatikBrew dibatalkan.")
            return None
        try:
            if provider_id == PROVIDER_LOCAL:
                return self._local_options(defaults, output_mode, request)
            return self._cloud_options(defaults, output_mode, provider_id, request)
        except (BatificationError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan AI tidak valid", str(exc), parent=self)
            return None

    def _provider_summary(self, provider_id: str) -> str | None:
        if provider_id == PROVIDER_LOCAL:
            active = get_batikbrew_model_settings_store().load()
            if not active.configured:
                messagebox.showerror(
                    "Model lokal belum diatur",
                    "Belum ada model SDXL + LoRA aktif. Buka Settings → Pengaturan AI, "
                    "Model & LoRA → Model Lokal, Runtime & LoRA, lalu aktifkan satu model.",
                    parent=self,
                )
                return None
            return f"{provider_label(provider_id)} · {active.model_id}"

        cloud = get_cloud_generation_settings_store().load()
        model = cloud.model_for(provider_id)
        if not get_api_secret_store().has(provider_id):
            messagebox.showerror(
                "API key belum diatur",
                f"API key {provider_label(provider_id)} belum tersedia. Buka Settings → "
                "Pengaturan AI, Model & LoRA → Provider Cloud & Model API.",
                parent=self,
            )
            return None
        return f"{provider_label(provider_id)} · {model}"

    def _local_options(
        self,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        request: BatikBrewRequest,
    ) -> BatikBrewModeGenerationOptions:
        active = get_batikbrew_model_settings_store().load()
        if not active.configured:
            raise BatificationError("Model lokal BatikBrew belum dipilih dari Settings.")
        if not Path(active.lora_path).expanduser().is_file():
            raise BatificationError(
                "File LoRA aktif tidak ditemukan. Pilih ulang model dari Settings."
            )
        model_path = Path(active.base_model_path).expanduser()
        return BatikBrewModeGenerationOptions(
            model_id_or_path=active.base_model_path,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            inference_steps=active.inference_steps,
            guidance_scale=active.guidance_scale,
            seed=request.seed,
            device=defaults.device,
            precision=defaults.precision,
            local_files_only=model_path.exists(),
            cpu_offload=defaults.cpu_offload,
            cache_dir=defaults.cache_dir,
            resolution=active.resolution,
            lora_path=active.lora_path,
            lora_weight=active.lora_weight,
            lora_trigger_words=active.trigger_words,
            variation_count=request.variation_count,
            tileable=request.tileable,
            output_mode=output_mode,
        )

    def _cloud_options(
        self,
        defaults: PretrainedAIBatificationOptions,
        output_mode: str,
        provider_id: str,
        request: BatikBrewRequest,
    ) -> CloudBatikBrewOptions:
        settings = get_cloud_generation_settings_store().load()
        return CloudBatikBrewOptions(
            model_id_or_path=defaults.model_id_or_path,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            strength=defaults.strength,
            ai_blend=defaults.ai_blend,
            pattern_scale=defaults.pattern_scale,
            preserve_shading=defaults.preserve_shading,
            inference_steps=defaults.inference_steps,
            guidance_scale=defaults.guidance_scale,
            seed=request.seed,
            device=defaults.device,
            precision=defaults.precision,
            local_files_only=False,
            cpu_offload=False,
            cache_dir=defaults.cache_dir,
            resolution=defaults.resolution,
            lora_path="",
            lora_weight=0.0,
            lora_trigger_words=("traditional Indonesian batik",),
            variation_count=request.variation_count,
            tileable=request.tileable,
            generation_provider=provider_id,
            provider_model=settings.model_for(provider_id),
            output_mode=output_mode,
        )


__all__ = ["ContextToolEditorWorkspaceView"]