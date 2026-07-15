"""Responsive preview dialog for Stable Diffusion Batik canvas backgrounds."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from batikcraft_studio.ai.pretrained_background import AIBatikBackgroundOptions
from batikcraft_studio.application.background_ai_session import AIBatikBackgroundPreview
from batikcraft_studio.imaging.raster import RasterImageError, normalize_raster_image

PreviewRenderer = Callable[
    [AIBatikBackgroundOptions, bytes | None, str | None],
    AIBatikBackgroundPreview,
]


class AIBatikBackgroundDialog(tk.Toplevel):
    """Generate a background in memory and apply it only after explicit approval."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        render_preview: PreviewRenderer,
        reference_content: bytes | None = None,
        reference_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        defaults = AIBatikBackgroundOptions()
        self.result: AIBatikBackgroundPreview | None = None
        self._render_preview = render_preview
        self._reference_content = reference_content
        self._reference_name = reference_name
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._reference_photo: ImageTk.PhotoImage | None = None
        self._queue: Queue[tuple[str, object]] = Queue()
        self._working = False
        self._destroyed = False
        self._poll_after_id: str | None = None

        self.title("AI Batik Background")
        self.geometry("1080x760")
        self.minsize(940, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.model_value = tk.StringVar(master=self, value=defaults.model_id_or_path)
        self.steps_value = tk.IntVar(master=self, value=defaults.inference_steps)
        self.guidance_value = tk.DoubleVar(master=self, value=defaults.guidance_scale)
        self.seed_value = tk.IntVar(master=self, value=defaults.seed)
        self.resolution_value = tk.IntVar(master=self, value=defaults.resolution)
        self.seamless_value = tk.BooleanVar(master=self, value=defaults.seamless)
        self.use_reference_value = tk.BooleanVar(
            master=self,
            value=reference_content is not None,
        )
        self.reference_strength_value = tk.DoubleVar(
            master=self,
            value=defaults.reference_strength,
        )
        self.reference_scale_value = tk.DoubleVar(master=self, value=defaults.reference_scale)
        self.status_value = tk.StringVar(
            master=self,
            value="Atur prompt lalu klik Generate Preview.",
        )
        self.reference_value = tk.StringVar(
            master=self,
            value=reference_name or "Tidak ada motif referensi",
        )

        self._build(defaults)
        self._show_reference()
        self.grab_set()

    def _build(self, defaults: AIBatikBackgroundOptions) -> None:
        shell = ttk.Frame(self, padding=14)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=2)
        shell.columnconfigure(1, weight=3)
        shell.rowconfigure(1, weight=1)

        ttk.Label(
            shell,
            text="Generate AI Batik Background",
            font=("TkDefaultFont", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controls = ttk.LabelFrame(shell, text="Pengaturan Stable Diffusion", padding=10)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        controls.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(controls, text="Model").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(controls, textvariable=self.model_value).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=2,
        )
        row += 1

        ttk.Label(controls, text="Prompt").grid(row=row, column=0, sticky="nw", pady=2)
        self.prompt_text = tk.Text(controls, height=6, wrap="word")
        self.prompt_text.grid(row=row, column=1, sticky="ew", pady=2)
        self.prompt_text.insert("1.0", defaults.prompt)
        row += 1

        ttk.Label(controls, text="Negative prompt").grid(
            row=row,
            column=0,
            sticky="nw",
            pady=2,
        )
        self.negative_text = tk.Text(controls, height=5, wrap="word")
        self.negative_text.grid(row=row, column=1, sticky="ew", pady=2)
        self.negative_text.insert("1.0", defaults.negative_prompt)
        row += 1

        row = self._spin_control(
            controls,
            row,
            "Inference steps",
            self.steps_value,
            1,
            100,
            1,
        )
        row = self._spin_control(
            controls,
            row,
            "Guidance scale",
            self.guidance_value,
            0.0,
            30.0,
            0.1,
        )
        row = self._spin_control(
            controls,
            row,
            "Seed",
            self.seed_value,
            -2_147_483_648,
            2_147_483_647,
            1,
        )

        ttk.Label(controls, text="Resolusi proses").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(
            controls,
            textvariable=self.resolution_value,
            values=(512, 640, 768, 896, 1024),
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Checkbutton(
            controls,
            text="Haluskan sisi agar lebih cocok sebagai pola berulang/seamless",
            variable=self.seamless_value,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 2))
        row += 1

        reference = ttk.LabelFrame(controls, text="Motif Referensi (Opsional)", padding=8)
        reference.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        reference.columnconfigure(1, weight=1)
        self.reference_preview = ttk.Label(reference, text="Tanpa referensi", anchor="center")
        self.reference_preview.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 8))
        ttk.Label(reference, textvariable=self.reference_value, wraplength=230).grid(
            row=0,
            column=1,
            sticky="w",
        )
        ttk.Checkbutton(
            reference,
            text="Gunakan motif ini sebagai panduan img2img",
            variable=self.use_reference_value,
        ).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Button(reference, text="Pilih File Motif…", command=self._choose_reference).grid(
            row=2,
            column=1,
            sticky="w",
            pady=2,
        )
        row += 1

        row = self._spin_control(
            controls,
            row,
            "Kekuatan referensi",
            self.reference_strength_value,
            0.0,
            1.0,
            0.01,
        )
        row = self._spin_control(
            controls,
            row,
            "Skala motif referensi",
            self.reference_scale_value,
            0.08,
            4.0,
            0.01,
        )
        controls.rowconfigure(row, weight=1)

        preview_frame = ttk.LabelFrame(shell, text="Preview Background", padding=10)
        preview_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.preview_label = ttk.Label(
            preview_frame,
            text="Preview belum dibuat",
            anchor="center",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            preview_frame,
            text=(
                "Hasil akan ditempatkan pada layer paling bawah dan menutup seluruh canvas. "
                "Model diunduh otomatis pada penggunaan pertama."
            ),
            foreground="#6D655D",
            wraplength=520,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        footer = ttk.Frame(shell)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_value, wraplength=620).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=150)
        self.progress.grid(row=0, column=1, padx=6)
        self.generate_button = ttk.Button(
            footer,
            text="Generate Preview",
            command=self.generate_preview,
        )
        self.generate_button.grid(row=0, column=2, padx=4)
        self.apply_button = ttk.Button(
            footer,
            text="Terapkan Background",
            command=self.apply,
            state="disabled",
        )
        self.apply_button.grid(row=0, column=3, padx=4)
        self.cancel_button = ttk.Button(footer, text="Batal", command=self.cancel)
        self.cancel_button.grid(row=0, column=4, padx=(4, 0))

    def _spin_control(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        from_value: float,
        to_value: float,
        increment: float,
    ) -> int:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=from_value,
            to=to_value,
            increment=increment,
        ).grid(row=row, column=1, sticky="ew", pady=2)
        return row + 1

    def collect_options(self) -> AIBatikBackgroundOptions:
        return AIBatikBackgroundOptions(
            model_id_or_path=self.model_value.get(),
            prompt=self.prompt_text.get("1.0", "end-1c"),
            negative_prompt=self.negative_text.get("1.0", "end-1c"),
            inference_steps=int(self.steps_value.get()),
            guidance_scale=float(self.guidance_value.get()),
            seed=int(self.seed_value.get()),
            resolution=int(self.resolution_value.get()),
            seamless=bool(self.seamless_value.get()),
            reference_strength=float(self.reference_strength_value.get()),
            reference_scale=float(self.reference_scale_value.get()),
        )

    def _choose_reference(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Pilih Motif Referensi",
            filetypes=(
                ("Image", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            raster = normalize_raster_image(path.read_bytes())
        except (OSError, RasterImageError) as exc:
            messagebox.showerror("Motif tidak dapat dibaca", str(exc), parent=self)
            return
        self._reference_content = raster.content
        self._reference_name = path.stem
        self.reference_value.set(path.name)
        self.use_reference_value.set(True)
        self._show_reference()
        self.result = None
        self.apply_button.configure(state="disabled")

    def _show_reference(self) -> None:
        if self._reference_content is None:
            self._reference_photo = None
            self.reference_preview.configure(image="", text="Tanpa referensi")
            return
        try:
            with Image.open(BytesIO(self._reference_content)) as source:
                source.load()
                image = source.convert("RGBA")
            image.thumbnail((116, 116), Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            self._reference_photo = None
            self.reference_preview.configure(image="", text="Preview gagal")
            return
        self._reference_photo = ImageTk.PhotoImage(image)
        self.reference_preview.configure(image=self._reference_photo, text="")

    def generate_preview(self) -> None:
        if self._working:
            return
        try:
            options = self.collect_options()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan tidak valid", str(exc), parent=self)
            return
        reference = self._reference_content if self.use_reference_value.get() else None
        reference_name = self._reference_name if reference is not None else None
        self._working = True
        self.result = None
        self.generate_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.progress.start(12)
        self.status_value.set(
            "Memuat model dan menghasilkan pola di latar belakang. Penggunaan pertama dapat lebih lama…"
        )

        def worker() -> None:
            try:
                preview = self._render_preview(options, reference, reference_name)
            except Exception as exc:  # noqa: BLE001 - worker errors must return to Tk
                self._queue.put(("error", str(exc)))
            else:
                self._queue.put(("success", preview))

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-ai-background",
        ).start()
        if self._poll_after_id is None:
            self._poll_after_id = self.after(80, self._poll_worker)

    def _poll_worker(self) -> None:
        self._poll_after_id = None
        if self._destroyed:
            return
        try:
            kind, payload = self._queue.get_nowait()
        except Empty:
            self._poll_after_id = self.after(80, self._poll_worker)
            return
        self._working = False
        self.progress.stop()
        self.generate_button.configure(state="normal")
        if kind == "error":
            self.status_value.set(str(payload))
            messagebox.showerror("Generasi background gagal", str(payload), parent=self)
            return
        if not isinstance(payload, AIBatikBackgroundPreview):
            self.status_value.set("Hasil background AI tidak dikenali.")
            return
        self.result = payload
        self._show_result(payload)
        self.apply_button.configure(state="normal")
        mode = payload.result.metadata.get("mode", "text2img")
        self.status_value.set(
            f"Preview selesai ({mode}, seed {payload.options.seed}). "
            "Klik Terapkan Background bila hasil sudah sesuai."
        )

    def _show_result(self, preview: AIBatikBackgroundPreview) -> None:
        try:
            with Image.open(BytesIO(preview.result.content)) as source:
                source.load()
                image = source.convert("RGBA")
            image.thumbnail((590, 590), Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            self._preview_photo = None
            self.preview_label.configure(image="", text="Preview tidak dapat ditampilkan")
            return
        self._preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self._preview_photo, text="")

    def apply(self) -> None:
        if self.result is None or self._working:
            return
        self._close()

    def cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        self._destroyed = True
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        self.progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


__all__ = ["AIBatikBackgroundDialog"]
