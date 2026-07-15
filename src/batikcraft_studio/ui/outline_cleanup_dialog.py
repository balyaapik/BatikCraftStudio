"""Responsive preview dialog for cleaning noisy raster outline objects."""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from io import BytesIO
from queue import Empty, Queue
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk

from batikcraft_studio.application.outline_cleanup_session import OutlineCleanupPreview
from batikcraft_studio.imaging.outline_cleanup import OutlineCleanupOptions

PreviewRenderer = Callable[[OutlineCleanupOptions], OutlineCleanupPreview]

_SOURCE_MODE_LABELS = {
    "Otomatis": "auto",
    "Piksel gelap": "dark",
    "Transparansi / alpha": "alpha",
}


class OutlineCleanupDialog(tk.Toplevel):
    """Preview cleanup settings without changing the active project until Apply."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        source_name: str,
        source_content: bytes,
        render_preview: PreviewRenderer,
    ) -> None:
        super().__init__(parent)
        self.result: OutlineCleanupPreview | None = None
        self._source_content = source_content
        self._render_preview = render_preview
        self._current_preview: OutlineCleanupPreview | None = None
        self._source_photo: ImageTk.PhotoImage | None = None
        self._result_photo: ImageTk.PhotoImage | None = None
        self._queue: Queue[tuple[int, str, object]] = Queue()
        self._generation = 0
        self._working = False
        self._destroyed = False
        self._poll_after_id: str | None = None

        self.title("Rapikan Outline")
        self.geometry("1040x720")
        self.minsize(920, 640)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.threshold_value = tk.IntVar(master=self, value=96)
        self.speckle_value = tk.IntVar(master=self, value=24)
        self.smooth_value = tk.DoubleVar(master=self, value=0.8)
        self.close_gap_value = tk.IntVar(master=self, value=1)
        self.thin_value = tk.IntVar(master=self, value=0)
        self.outline_only_value = tk.BooleanVar(master=self, value=False)
        self.invert_value = tk.BooleanVar(master=self, value=False)
        self.source_mode_value = tk.StringVar(master=self, value="Otomatis")
        self.line_color_value = tk.StringVar(master=self, value="#1C1714")
        self.status_value = tk.StringVar(master=self, value="Menyiapkan preview…")
        self.diagnostics_value = tk.StringVar(master=self, value="")

        self._build(source_name)
        self._show_source()
        for variable in (
            self.threshold_value,
            self.speckle_value,
            self.smooth_value,
            self.close_gap_value,
            self.thin_value,
            self.outline_only_value,
            self.invert_value,
            self.source_mode_value,
            self.line_color_value,
        ):
            variable.trace_add("write", self._mark_dirty)

        self.grab_set()
        self.after_idle(self.process_preview)

    def _build(self, source_name: str) -> None:
        shell = ttk.Frame(self, padding=14)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=3)
        shell.columnconfigure(1, weight=3)
        shell.columnconfigure(2, weight=2)
        shell.rowconfigure(1, weight=1)

        ttk.Label(
            shell,
            text=f"Rapikan Outline — {source_name}",
            font=("TkDefaultFont", 13, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        source_frame = ttk.LabelFrame(shell, text="Objek Asli", padding=8)
        source_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(0, weight=1)
        self.source_preview = ttk.Label(source_frame, anchor="center")
        self.source_preview.grid(row=0, column=0, sticky="nsew")

        result_frame = ttk.LabelFrame(shell, text="Preview Outline Bersih", padding=8)
        result_frame.grid(row=1, column=1, sticky="nsew", padx=7)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.result_preview = ttk.Label(
            result_frame,
            text="Preview belum diproses",
            anchor="center",
        )
        self.result_preview.grid(row=0, column=0, sticky="nsew")

        controls = ttk.LabelFrame(shell, text="Pengaturan", padding=10)
        controls.grid(row=1, column=2, sticky="nsew", padx=(7, 0))
        controls.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(controls, text="Interpretasi sumber").grid(row=row, column=0, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.source_mode_value,
            values=tuple(_SOURCE_MODE_LABELS),
            state="readonly",
            width=20,
        ).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        row = self._spin_control(
            controls,
            row,
            "Ambang garis",
            self.threshold_value,
            0,
            255,
            1,
        )
        row = self._spin_control(
            controls,
            row,
            "Hapus bercak ≤ px",
            self.speckle_value,
            0,
            20_000,
            1,
        )
        row = self._spin_control(
            controls,
            row,
            "Haluskan tepi",
            self.smooth_value,
            0.0,
            8.0,
            0.1,
        )
        row = self._spin_control(
            controls,
            row,
            "Tutup celah",
            self.close_gap_value,
            0,
            6,
            1,
        )
        row = self._spin_control(
            controls,
            row,
            "Tipiskan garis",
            self.thin_value,
            0,
            6,
            1,
        )

        ttk.Checkbutton(
            controls,
            text="Ubah bidang hitam menjadi kontur saja",
            variable=self.outline_only_value,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 2))
        row += 1
        ttk.Checkbutton(
            controls,
            text="Deteksi garis terang pada latar gelap",
            variable=self.invert_value,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1

        ttk.Label(controls, text="Warna garis").grid(row=row, column=0, sticky="w", pady=(5, 2))
        color_row = ttk.Frame(controls)
        color_row.grid(row=row, column=1, sticky="ew", pady=(5, 2))
        color_row.columnconfigure(0, weight=1)
        ttk.Entry(color_row, textvariable=self.line_color_value, width=10).grid(
            row=0,
            column=0,
            sticky="ew",
        )
        ttk.Button(color_row, text="Pilih…", command=self._choose_color).grid(
            row=0,
            column=1,
            padx=(4, 0),
        )
        row += 1

        ttk.Separator(controls).grid(row=row, column=0, columnspan=2, sticky="ew", pady=9)
        row += 1
        preset_row = ttk.Frame(controls)
        preset_row.grid(row=row, column=0, columnspan=2, sticky="ew")
        for column, (label, command) in enumerate(
            (
                ("Auto Bersih", self._preset_clean),
                ("Garis Tipis", self._preset_thin),
                ("Kontur Saja", self._preset_contour),
            )
        ):
            preset_row.columnconfigure(column, weight=1)
            ttk.Button(preset_row, text=label, command=command).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=2,
            )
        row += 1

        ttk.Label(
            controls,
            textvariable=self.diagnostics_value,
            wraplength=250,
            foreground="#6D655D",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
        controls.rowconfigure(row, weight=1)

        status = ttk.Frame(shell)
        status.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_value).grid(row=0, column=0, sticky="w")
        self.preview_button = ttk.Button(
            status,
            text="Proses Preview",
            command=self.process_preview,
        )
        self.preview_button.grid(row=0, column=1, padx=4)
        self.apply_button = ttk.Button(
            status,
            text="Terapkan",
            command=self.apply,
            state="disabled",
        )
        self.apply_button.grid(row=0, column=2, padx=4)
        ttk.Button(status, text="Batal", command=self.cancel).grid(row=0, column=3, padx=(4, 0))

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
            width=10,
        ).grid(row=row, column=1, sticky="ew", pady=2)
        return row + 1

    def _show_source(self) -> None:
        self._source_photo = self._photo_from_content(self._source_content)
        self.source_preview.configure(image=self._source_photo)

    def _photo_from_content(self, content: bytes) -> ImageTk.PhotoImage:
        with Image.open(BytesIO(content)) as opened:
            opened.load()
            image = opened.convert("RGBA")
        image.thumbnail((330, 500), Image.Resampling.LANCZOS)
        background = Image.new("RGBA", image.size, (250, 248, 244, 255))
        background.alpha_composite(image)
        return ImageTk.PhotoImage(background)

    def _cleanup_options(self) -> OutlineCleanupOptions:
        return OutlineCleanupOptions(
            threshold=int(self.threshold_value.get()),
            speckle_area=int(self.speckle_value.get()),
            smooth_radius=float(self.smooth_value.get()),
            close_gaps=int(self.close_gap_value.get()),
            thin_lines=int(self.thin_value.get()),
            outline_only=bool(self.outline_only_value.get()),
            source_mode=_SOURCE_MODE_LABELS[self.source_mode_value.get()],
            invert=bool(self.invert_value.get()),
            line_color=self.line_color_value.get().strip(),
        )

    def process_preview(self) -> None:
        if self._working:
            return
        try:
            options = self._cleanup_options()
        except (KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Pengaturan tidak valid", str(exc), parent=self)
            return

        self._generation += 1
        generation = self._generation
        self._working = True
        self._current_preview = None
        self.preview_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.status_value.set("Membersihkan bercak dan menghaluskan garis di latar belakang…")

        def worker() -> None:
            try:
                preview = self._render_preview(options)
            except Exception as exc:  # noqa: BLE001 - worker error must return to Tk
                self._queue.put((generation, "error", str(exc)))
            else:
                self._queue.put((generation, "success", preview))

        threading.Thread(
            target=worker,
            daemon=True,
            name="batikcraft-outline-cleanup-preview",
        ).start()
        if self._poll_after_id is None:
            self._poll_after_id = self.after(60, self._poll_worker)

    def _poll_worker(self) -> None:
        self._poll_after_id = None
        if self._destroyed:
            return
        terminal: tuple[int, str, object] | None = None
        while True:
            try:
                event = self._queue.get_nowait()
            except Empty:
                break
            if event[0] == self._generation:
                terminal = event
        if terminal is None:
            self._poll_after_id = self.after(60, self._poll_worker)
            return

        _generation, kind, payload = terminal
        self._working = False
        self.preview_button.configure(state="normal")
        if kind == "error":
            self.status_value.set(str(payload))
            messagebox.showerror("Preview outline gagal", str(payload), parent=self)
            return
        if not isinstance(payload, OutlineCleanupPreview):
            self.status_value.set("Hasil preview outline tidak dikenali.")
            return

        self._current_preview = payload
        self._result_photo = self._photo_from_content(payload.result.content)
        self.result_preview.configure(image=self._result_photo, text="")
        self.apply_button.configure(state="normal")
        result = payload.result
        self.diagnostics_value.set(
            f"Mode: {result.resolved_source_mode} · "
            f"{result.removed_components} bercak / {result.removed_pixels} piksel dihapus · "
            f"cakupan garis {result.output_coverage * 100:.1f}%"
        )
        self.status_value.set("Preview selesai. Terapkan bila garis sudah sesuai.")

    def _mark_dirty(self, *_args: object) -> None:
        if not hasattr(self, "apply_button"):
            return
        self._current_preview = None
        self.apply_button.configure(state="disabled")
        if not self._working:
            self.status_value.set("Pengaturan berubah. Klik Proses Preview untuk memperbarui hasil.")

    def _choose_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.line_color_value.get(),
            parent=self,
            title="Pilih Warna Outline",
        )
        if selected:
            self.line_color_value.set(selected.upper())

    def _preset_clean(self) -> None:
        self.threshold_value.set(96)
        self.speckle_value.set(24)
        self.smooth_value.set(0.8)
        self.close_gap_value.set(1)
        self.thin_value.set(0)
        self.outline_only_value.set(False)
        self.after_idle(self.process_preview)

    def _preset_thin(self) -> None:
        self.threshold_value.set(104)
        self.speckle_value.set(18)
        self.smooth_value.set(0.6)
        self.close_gap_value.set(1)
        self.thin_value.set(1)
        self.outline_only_value.set(False)
        self.after_idle(self.process_preview)

    def _preset_contour(self) -> None:
        self.threshold_value.set(96)
        self.speckle_value.set(32)
        self.smooth_value.set(0.8)
        self.close_gap_value.set(1)
        self.thin_value.set(0)
        self.outline_only_value.set(True)
        self.after_idle(self.process_preview)

    def apply(self) -> None:
        if self._current_preview is None:
            return
        self.result = self._current_preview
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
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


__all__ = ["OutlineCleanupDialog"]
