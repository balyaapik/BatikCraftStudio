"""Studio Batifikasi BatikBrew — jendela mandiri untuk mengubah gambar via SDXL.

Alur lama mengharuskan objek dipilih di kanvas lebih dulu, sehingga batifikasi
terikat pada isi dokumen. Jendela ini melepas keterikatan itu: gambar
di-drag-and-drop langsung ke sini, dibatifikasi, lalu hasilnya disimpan atau
dimasukkan ke kanvas — kanvas tidak perlu disentuh sama sekali.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

logger = logging.getLogger(__name__)

_SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
_THUMBNAIL = (128, 128)
_MAX_SOURCES = 24


@dataclass
class SourceImage:
    """Satu gambar sumber yang menunggu dibatifikasi."""

    path: Path | None
    content: bytes
    label: str
    thumbnail: Image.Image | None = None


@dataclass
class BatificationResult:
    """Satu hasil batifikasi."""

    content: bytes
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    thumbnail: Image.Image | None = None


def parse_dropped_paths(payload: str) -> list[Path]:
    """Uraikan daftar berkas dari tkdnd menjadi Path.

    tkdnd membungkus lintasan yang mengandung spasi dengan kurung kurawal,
    misalnya ``{C:/ada spasi/a.png} C:/b.png``. Menguraikannya dengan ``split()``
    biasa akan memecah lintasan tersebut jadi potongan yang tidak sahih.
    """

    paths: list[Path] = []
    buffer: list[str] = []
    in_braces = False
    for token in str(payload).split():
        if not in_braces and token.startswith("{"):
            in_braces = True
            buffer = [token[1:]]
            if token.endswith("}") and len(token) > 1:
                in_braces = False
                paths.append(Path(" ".join(buffer)[:-1] if token != "{}" else ""))
                buffer = []
            continue
        if in_braces:
            if token.endswith("}"):
                buffer.append(token[:-1])
                in_braces = False
                paths.append(Path(" ".join(buffer)))
                buffer = []
            else:
                buffer.append(token)
            continue
        paths.append(Path(token))
    if buffer:
        paths.append(Path(" ".join(buffer)))
    return [item for item in paths if str(item).strip()]


def is_supported_image(path: Path) -> bool:
    return path.suffix.casefold() in _SUPPORTED_SUFFIXES


def load_source_image(path: Path) -> SourceImage:
    """Baca berkas gambar menjadi ``SourceImage`` lengkap dengan thumbnail."""

    content = Path(path).read_bytes()
    thumbnail = build_thumbnail(content)
    return SourceImage(path=Path(path), content=content, label=Path(path).name, thumbnail=thumbnail)


def build_thumbnail(content: bytes, size: tuple[int, int] = _THUMBNAIL) -> Image.Image | None:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            preview = image.convert("RGBA")
    except (OSError, ValueError):
        logger.debug("Gambar tidak dapat dibaca untuk thumbnail.", exc_info=True)
        return None
    preview.thumbnail(size, Image.Resampling.LANCZOS)
    return preview


def build_generation_options(
    settings: Any,
    *,
    prompt: str,
    negative_prompt: str,
    variation_count: int,
    tileable: bool,
    inspiration_name: str,
) -> Any:
    """Susun opsi SDXL dari pengaturan model BatikBrew yang tersimpan."""

    from batikcraft_studio.ai.batikbrew_generation import BatikBrewGenerationOptions

    return BatikBrewGenerationOptions(
        model_id_or_path=settings.base_model_path or settings.model_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        inference_steps=settings.inference_steps,
        guidance_scale=settings.guidance_scale,
        resolution=settings.resolution,
        lora_path=settings.lora_path,
        lora_weight=settings.lora_weight,
        lora_trigger_words=tuple(settings.trigger_words),
        variation_count=max(1, int(variation_count)),
        tileable=bool(tileable),
        inspiration_name=inspiration_name,
        use_secondary_reference=False,
    )


class BatikBrewStudioWindow(tk.Toplevel):
    """Jendela mandiri: seret gambar ke sini, batifikasi, ambil hasilnya."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_insert: Callable[[Sequence[BatificationResult]], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Studio Batifikasi BatikBrew")
        self.geometry("1080x760")
        self.minsize(920, 640)
        self._on_insert = on_insert
        self._sources: list[SourceImage] = []
        self._results: list[BatificationResult] = []
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._busy = False
        self._worker: threading.Thread | None = None

        self._build_layout()
        self._register_drop_target()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Tata letak
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        self._drop_zone = tk.Label(
            left,
            text=(
                "Seret & lepaskan gambar ke sini\n"
                "(PNG, JPG, WEBP, BMP, TIFF)\n\n"
                "atau klik untuk memilih berkas"
            ),
            relief="ridge",
            borderwidth=2,
            padx=16,
            pady=24,
            justify="center",
            cursor="hand2",
        )
        self._drop_zone.grid(row=0, column=0, sticky="ew")
        self._drop_zone.bind("<Button-1>", lambda _e: self.choose_files())

        ttk.Label(left, text="Gambar sumber").grid(row=2, column=0, sticky="w", pady=(12, 4))
        self._source_strip = ttk.Frame(left)
        self._source_strip.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        ttk.Label(left, text="Hasil batifikasi").grid(row=4, column=0, sticky="w", pady=(12, 4))
        self._result_strip = ttk.Frame(left)
        self._result_strip.grid(row=3, column=0, sticky="nsew")

        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(6, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Arahan gaya").grid(row=0, column=0, sticky="w")
        self.prompt_value = tk.StringVar(
            value="ornamen batik Indonesia, garis luwes, motif organik"
        )
        ttk.Entry(right, textvariable=self.prompt_value).grid(row=1, column=0, sticky="ew")

        ttk.Label(right, text="Hindari").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.negative_value = tk.StringVar(
            value="blurry, low quality, watermark, text, photograph, 3d render"
        )
        ttk.Entry(right, textvariable=self.negative_value).grid(row=3, column=0, sticky="ew")

        controls = ttk.Frame(right)
        controls.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(controls, text="Variasi").pack(side="left")
        self.variation_value = tk.IntVar(value=4)
        ttk.Spinbox(
            controls, from_=1, to=8, width=4, textvariable=self.variation_value
        ).pack(side="left", padx=(6, 16))
        self.tileable_value = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Bisa diulang (tileable)", variable=self.tileable_value).pack(
            side="left"
        )

        actions = ttk.Frame(right)
        actions.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self._run_button = ttk.Button(actions, text="Batifikasi", command=self.start_batification)
        self._run_button.pack(side="left")
        ttk.Button(actions, text="Tambah gambar...", command=self.choose_files).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Kosongkan", command=self.clear_sources).pack(side="left")

        ttk.Label(right, text="Log proses").grid(row=7, column=0, sticky="w", pady=(12, 4))
        self._log = tk.Text(right, height=14, wrap="word", state="disabled")
        self._log.grid(row=6, column=0, sticky="nsew", pady=(12, 0))

        self._progress = ttk.Progressbar(right, mode="determinate")
        self._progress.grid(row=8, column=0, sticky="ew", pady=(8, 0))

        self._status = ttk.Label(right, text="Siap. Seret gambar untuk mulai.")
        self._status.grid(row=9, column=0, sticky="w", pady=(6, 0))

        save_row = ttk.Frame(right)
        save_row.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        self._save_button = ttk.Button(
            save_row, text="Simpan hasil...", command=self.save_results, state="disabled"
        )
        self._save_button.pack(side="left")
        self._insert_button = ttk.Button(
            save_row, text="Masukkan ke canvas", command=self.insert_results, state="disabled"
        )
        self._insert_button.pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def _register_drop_target(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            self._append_log(
                "Drag & drop tidak tersedia (tkinterdnd2 belum terpasang). "
                "Gunakan tombol 'Tambah gambar...'."
            )
            return False
        register = getattr(self._drop_zone, "drop_target_register", None)
        bind = getattr(self._drop_zone, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            return False
        try:
            register(DND_FILES)
            bind("<<DropEnter>>", self._on_drop_enter)
            bind("<<DropLeave>>", self._on_drop_leave)
            bind("<<Drop>>", self._on_drop)
        except tk.TclError:
            logger.debug("Registrasi drop target gagal.", exc_info=True)
            return False
        return True

    def _on_drop_enter(self, _event: Any) -> str:
        self._drop_zone.configure(relief="solid")
        return "copy"

    def _on_drop_leave(self, _event: Any) -> str:
        self._drop_zone.configure(relief="ridge")
        return "copy"

    def _on_drop(self, event: Any) -> str:
        self._drop_zone.configure(relief="ridge")
        self.add_paths(parse_dropped_paths(getattr(event, "data", "")))
        return "copy"

    # ------------------------------------------------------------------
    # Sumber
    # ------------------------------------------------------------------

    def choose_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Pilih gambar untuk dibatifikasi",
            filetypes=[
                ("Gambar", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("Semua berkas", "*.*"),
            ],
        )
        self.add_paths([Path(item) for item in paths])

    def add_paths(self, paths: Sequence[Path]) -> None:
        ditolak: list[str] = []
        for path in paths:
            if len(self._sources) >= _MAX_SOURCES:
                ditolak.append(f"{path.name} (batas {_MAX_SOURCES} gambar)")
                continue
            if not is_supported_image(path):
                ditolak.append(f"{path.name} (format tidak didukung)")
                continue
            try:
                self._sources.append(load_source_image(path))
            except OSError as exc:
                ditolak.append(f"{path.name} ({exc})")
        self._refresh_sources()
        if ditolak:
            self._append_log("Dilewati: " + "; ".join(ditolak))
        self._status.configure(text=f"{len(self._sources)} gambar siap dibatifikasi.")

    def clear_sources(self) -> None:
        self._sources.clear()
        self._results.clear()
        self._refresh_sources()
        self._refresh_results()
        self._status.configure(text="Daftar dikosongkan.")

    def _refresh_sources(self) -> None:
        self._render_strip(self._source_strip, [(s.thumbnail, s.label) for s in self._sources])

    def _refresh_results(self) -> None:
        self._render_strip(self._result_strip, [(r.thumbnail, r.label) for r in self._results])
        state = "normal" if self._results else "disabled"
        self._save_button.configure(state=state)
        self._insert_button.configure(state=state if self._on_insert else "disabled")

    def _render_strip(
        self, parent: ttk.Frame, entries: Sequence[tuple[Image.Image | None, str]]
    ) -> None:
        for child in parent.winfo_children():
            child.destroy()
        for column, (thumbnail, label) in enumerate(entries):
            cell = ttk.Frame(parent)
            cell.grid(row=column // 5, column=column % 5, padx=4, pady=4)
            if thumbnail is not None:
                photo = ImageTk.PhotoImage(thumbnail)
                # Referensi wajib dipegang; kalau tidak gambarnya hilang.
                self._photo_refs.append(photo)
                tk.Label(cell, image=photo, borderwidth=1, relief="solid").pack()
            ttk.Label(cell, text=label[:18], width=18, anchor="center").pack()

    # ------------------------------------------------------------------
    # Batifikasi
    # ------------------------------------------------------------------

    def start_batification(self) -> None:
        if self._busy:
            return
        if not self._sources:
            messagebox.showinfo(
                "Belum ada gambar",
                "Seret gambar ke jendela ini atau pakai tombol 'Tambah gambar...'.",
                parent=self,
            )
            return
        try:
            from batikcraft_studio.ai.batikbrew_model_settings import (
                get_batikbrew_model_settings_store,
            )

            settings = get_batikbrew_model_settings_store().load()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Pengaturan model", str(exc), parent=self)
            return
        if not settings.configured:
            messagebox.showwarning(
                "Model belum dipilih",
                "Pilih model SDXL dan LoRA BatikBrew lebih dulu di pengaturan AI lokal.",
                parent=self,
            )
            return

        try:
            options = build_generation_options(
                settings,
                prompt=self.prompt_value.get(),
                negative_prompt=self.negative_value.get(),
                variation_count=self.variation_value.get(),
                tileable=self.tileable_value.get(),
                inspiration_name=self._sources[0].label,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Pengaturan tidak valid", str(exc), parent=self)
            return

        self._set_busy(True)
        self._results.clear()
        self._refresh_results()
        total = len(self._sources) * max(1, int(self.variation_value.get()))
        self._progress.configure(maximum=total, value=0)
        self._append_log(f"Mulai: {len(self._sources)} gambar, target {total} hasil.")
        sources = list(self._sources)
        self._worker = threading.Thread(
            target=self._run_batification, args=(sources, options), daemon=True
        )
        self._worker.start()

    def _run_batification(self, sources: list[SourceImage], options: Any) -> None:
        from batikcraft_studio.ai.batikbrew_generation import (
            BatikBrewSDXLGenerationProvider,
        )
        from batikcraft_studio.ai.generation_trace import set_trace_sink

        set_trace_sink(lambda line: self.after(0, self._append_log, line))
        provider = BatikBrewSDXLGenerationProvider()
        try:
            for source in sources:
                content = self._without_background(source.content)
                try:
                    outputs = provider.render_variations(content, content, options)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Batifikasi gagal untuk %s", source.label)
                    self.after(0, self._append_log, f"GAGAL {source.label}: {exc}")
                    continue
                for index, output in enumerate(outputs, start=1):
                    result = BatificationResult(
                        content=output.content,
                        label=f"{Path(source.label).stem}-batik-{index}.png",
                        metadata=dict(getattr(output, "metadata", {}) or {}),
                        thumbnail=build_thumbnail(output.content),
                    )
                    self.after(0, self._add_result, result)
        finally:
            set_trace_sink(None)
            try:
                provider.unload()
            except Exception:  # noqa: BLE001
                logger.debug("Pelepasan pipeline gagal.", exc_info=True)
            self.after(0, self._finish_batification)

    @staticmethod
    def _without_background(content: bytes) -> bytes:
        """Hapus latar sebelum konversi, seperti alur batifikasi sebelumnya."""

        try:
            from batikcraft_studio.imaging.background_removal import remove_background

            cleaned, _changed = remove_background(content)
            return cleaned
        except Exception:  # noqa: BLE001
            logger.debug("Penghapusan latar dilewati.", exc_info=True)
            return content

    def _add_result(self, result: BatificationResult) -> None:
        self._results.append(result)
        self._progress.configure(value=len(self._results))
        self._refresh_results()
        self._status.configure(text=f"{len(self._results)} hasil selesai.")

    def _finish_batification(self) -> None:
        self._set_busy(False)
        if self._results:
            self._append_log(f"Selesai: {len(self._results)} hasil.")
            self._status.configure(text=f"Selesai — {len(self._results)} hasil siap disimpan.")
        else:
            self._status.configure(text="Tidak ada hasil. Periksa log proses.")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._run_button.configure(state="disabled" if busy else "normal")

    # ------------------------------------------------------------------
    # Keluaran
    # ------------------------------------------------------------------

    def save_results(self) -> None:
        if not self._results:
            return
        folder = filedialog.askdirectory(parent=self, title="Simpan hasil batifikasi ke folder")
        if not folder:
            return
        target = Path(folder)
        saved = 0
        for result in self._results:
            try:
                (target / result.label).write_bytes(result.content)
                saved += 1
            except OSError as exc:
                self._append_log(f"Gagal menyimpan {result.label}: {exc}")
        self._status.configure(text=f"{saved} berkas disimpan ke {target}.")
        self._append_log(f"{saved} berkas disimpan ke {target}.")

    def insert_results(self) -> None:
        if not self._results or self._on_insert is None:
            return
        try:
            self._on_insert(tuple(self._results))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Penyisipan hasil ke canvas gagal.")
            messagebox.showerror("Gagal memasukkan", str(exc), parent=self)
            return
        self._status.configure(text=f"{len(self._results)} hasil dimasukkan ke canvas.")

    # ------------------------------------------------------------------
    # Lain-lain
    # ------------------------------------------------------------------

    def _append_log(self, message: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", f"{message}\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(
                "Masih memproses",
                "Batifikasi masih berjalan. Tutup jendela ini?",
                parent=self,
            ):
                return
        try:
            from batikcraft_studio.ai.generation_trace import set_trace_sink

            set_trace_sink(None)
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


__all__ = [
    "BatificationResult",
    "BatikBrewStudioWindow",
    "SourceImage",
    "build_generation_options",
    "build_thumbnail",
    "is_supported_image",
    "load_source_image",
    "parse_dropped_paths",
]
