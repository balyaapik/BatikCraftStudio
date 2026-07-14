"""Indonesian/English labels for the offline LoRA milestone."""

from __future__ import annotations

from batikcraft_studio import i18n as _i18n

_TRANSLATIONS = {
    "id": {
        "ai.dialog.selection_title": "Batifikasi Seleksi Area",
        "offline.dialog.provider_model": "Model LoRA lokal (offline)",
        "offline.dialog.model_note": (
            "Model, base model, dan ControlNet dibaca dari penyimpanan lokal. Source, render, "
            "dan isen tetap disimpan sebagai objek terpisah."
        ),
        "offline.selection.menu": "Batifikasi Seleksi Area…",
        "offline.selection.instructions": (
            "Tarik kotak pada canvas untuk memilih garis/objek yang akan dibatifikasi."
        ),
        "offline.selection.cancelled": "Seleksi AI dibatalkan.",
        "offline.selection.source_name": "Seleksi AI",
        "offline.selection.rendered": (
            "Seleksi selesai dibatifikasi sebagai versi {version} melalui {provider}."
        ),
        "offline.dataset.menu": "Dataset Studio…",
        "offline.dataset.title": "Dataset Studio — Training LoRA",
        "offline.dataset.metadata": "Metadata Dataset",
        "offline.dataset.id": "ID",
        "offline.dataset.name": "Nama",
        "offline.dataset.author": "Author",
        "offline.dataset.trigger": "Trigger word",
        "offline.dataset.base_family": "Keluarga base model",
        "offline.dataset.sample": "Tambah Sample",
        "offline.dataset.target": "Target batik",
        "offline.dataset.source": "Sumber/sketsa",
        "offline.dataset.conditioning": "Conditioning/line art",
        "offline.dataset.mask": "Mask",
        "offline.dataset.category": "Kategori",
        "offline.dataset.style": "Gaya",
        "offline.dataset.caption": "Caption/prompt",
        "offline.dataset.add_sample": "Tambahkan Sample",
        "offline.dataset.remove_sample": "Hapus Sample",
        "offline.dataset.export": "Ekspor .batikdataset",
        "offline.dataset.note": (
            "Target wajib. Source, conditioning, dan mask boleh dikosongkan untuk LoRA gaya."
        ),
        "offline.dataset.choose_image": "Pilih image dataset",
        "offline.dataset.target_required": "Pilih target batik terlebih dahulu.",
        "offline.dataset.empty": "Dataset belum memiliki sample.",
        "offline.dataset.exported": "Dataset berhasil dibuat:\n{path}",
        "offline.models.menu": "Kelola Model Offline…",
        "offline.models.title": "Model AI Offline",
        "offline.models.installed": "LoRA Terpasang",
        "offline.models.version": "Versi",
        "offline.models.base_family": "Base",
        "offline.models.weight": "Bobot",
        "offline.models.install": "Pasang .batikmodel…",
        "offline.models.uninstall": "Hapus",
        "offline.models.runtime": "Runtime Lokal",
        "offline.models.base_path": "Folder base model",
        "offline.models.controlnet_path": "Folder ControlNet",
        "offline.models.device": "Perangkat",
        "offline.models.precision": "Presisi",
        "offline.models.steps": "Inference steps",
        "offline.models.guidance": "Guidance scale",
        "offline.models.control_scale": "Kekuatan ControlNet",
        "offline.models.lora_scale": "Kekuatan LoRA",
        "offline.models.cpu_offload": "CPU offload untuk menghemat VRAM",
        "offline.models.offline_note": (
            "Semua folder harus sudah tersedia di komputer. Runtime memakai mode offline "
            "dan tidak mengunduh model dari internet."
        ),
        "offline.models.foundation": "Pakai Renderer Fondasi",
        "offline.models.activate": "Aktifkan Model",
        "offline.models.foundation_active": "Provider aktif: renderer fondasi lokal.",
        "offline.models.active": "Model offline aktif: {model}",
        "offline.models.uninstall_confirm": "Hapus model offline {model}?",
        "offline.models.select_required": "Pilih model LoRA yang akan diaktifkan.",
        "offline.models.provider_status": "Provider Batification aktif: {provider}",
    },
    "en": {
        "ai.dialog.selection_title": "Batify Area Selection",
        "offline.dialog.provider_model": "Local LoRA model (offline)",
        "offline.dialog.model_note": (
            "The model, base model, and ControlNet are read from local storage. Source, render, "
            "and isen remain separate objects."
        ),
        "offline.selection.menu": "Batify Area Selection…",
        "offline.selection.instructions": (
            "Drag a rectangle on the canvas around the lines or objects to Batify."
        ),
        "offline.selection.cancelled": "AI selection cancelled.",
        "offline.selection.source_name": "AI Selection",
        "offline.selection.rendered": (
            "Selection Batified as version {version} with {provider}."
        ),
        "offline.dataset.menu": "Dataset Studio…",
        "offline.dataset.title": "Dataset Studio — LoRA Training",
        "offline.dataset.metadata": "Dataset Metadata",
        "offline.dataset.id": "ID",
        "offline.dataset.name": "Name",
        "offline.dataset.author": "Author",
        "offline.dataset.trigger": "Trigger word",
        "offline.dataset.base_family": "Base model family",
        "offline.dataset.sample": "Add Sample",
        "offline.dataset.target": "Batik target",
        "offline.dataset.source": "Source/sketch",
        "offline.dataset.conditioning": "Conditioning/line art",
        "offline.dataset.mask": "Mask",
        "offline.dataset.category": "Category",
        "offline.dataset.style": "Style",
        "offline.dataset.caption": "Caption/prompt",
        "offline.dataset.add_sample": "Add Sample",
        "offline.dataset.remove_sample": "Remove Sample",
        "offline.dataset.export": "Export .batikdataset",
        "offline.dataset.note": (
            "Target is required. Source, conditioning, and mask are optional for style LoRA."
        ),
        "offline.dataset.choose_image": "Choose dataset image",
        "offline.dataset.target_required": "Choose a Batik target image first.",
        "offline.dataset.empty": "The dataset has no samples.",
        "offline.dataset.exported": "Dataset created:\n{path}",
        "offline.models.menu": "Manage Offline Models…",
        "offline.models.title": "Offline AI Models",
        "offline.models.installed": "Installed LoRAs",
        "offline.models.version": "Version",
        "offline.models.base_family": "Base",
        "offline.models.weight": "Weight",
        "offline.models.install": "Install .batikmodel…",
        "offline.models.uninstall": "Remove",
        "offline.models.runtime": "Local Runtime",
        "offline.models.base_path": "Base model folder",
        "offline.models.controlnet_path": "ControlNet folder",
        "offline.models.device": "Device",
        "offline.models.precision": "Precision",
        "offline.models.steps": "Inference steps",
        "offline.models.guidance": "Guidance scale",
        "offline.models.control_scale": "ControlNet strength",
        "offline.models.lora_scale": "LoRA strength",
        "offline.models.cpu_offload": "CPU offload to reduce VRAM use",
        "offline.models.offline_note": (
            "All folders must already exist on this computer. The runtime uses offline mode "
            "and never downloads model files."
        ),
        "offline.models.foundation": "Use Foundation Renderer",
        "offline.models.activate": "Activate Model",
        "offline.models.foundation_active": "Active provider: local foundation renderer.",
        "offline.models.active": "Active offline model: {model}",
        "offline.models.uninstall_confirm": "Remove offline model {model}?",
        "offline.models.select_required": "Select the LoRA model to activate.",
        "offline.models.provider_status": "Active Batification provider: {provider}",
    },
}


def install_offline_ai_translations() -> None:
    """Install Milestone 4B labels into the shared catalog."""

    for language, catalog in _TRANSLATIONS.items():
        _i18n._TRANSLATIONS[language].update(catalog)  # type: ignore[attr-defined]


__all__ = ["install_offline_ai_translations"]
