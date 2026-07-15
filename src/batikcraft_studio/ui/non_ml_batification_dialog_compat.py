"""Python 3.13 compatible wrapper for the non-ML Batification dialog."""

from __future__ import annotations

import tkinter as tk

from batikcraft_studio.imaging.non_ml_batification import (
    NonMLBatificationMode,
    NonMLBatificationOptions,
)

from .non_ml_batification_dialog import (
    NonMLBatificationDialog as _LegacyNonMLBatificationDialog,
    PreviewRenderer,
)

_MODE_BY_LABEL = {
    "Isi + Garis": NonMLBatificationMode.FILL_OUTLINE,
    "Isi Motif": NonMLBatificationMode.FILL,
    "Garis Motif": NonMLBatificationMode.OUTLINE,
}


class NonMLBatificationDialog(_LegacyNonMLBatificationDialog):
    """Dispatch Tkinter widget options and Batification settings safely.

    The original dialog used ``_options()`` for Batification settings. Tkinter
    itself calls ``self._options(cnf)`` while constructing every widget, which
    causes a signature collision on Python 3.13. This wrapper preserves the
    existing workflow while routing Tkinter calls to ``tk.Misc._options``.
    """

    def _options(
        self,
        cnf: object | None = None,
        kw: object | None = None,
    ) -> object:
        if cnf is not None or kw is not None:
            return tk.Misc._options(self, cnf, kw)  # type: ignore[arg-type]
        return self._batification_options()

    def _batification_options(self) -> NonMLBatificationOptions:
        return NonMLBatificationOptions(
            mode=_MODE_BY_LABEL[self.mode_value.get()],
            pattern_scale=float(self.pattern_scale_value.get()),
            pattern_rotation=float(self.rotation_value.get()),
            pattern_opacity=float(self.opacity_value.get()),
            outline_strength=float(self.outline_strength_value.get()),
            outline_width=int(self.outline_width_value.get()),
            preserve_shading=float(self.shading_value.get()),
            background_tolerance=int(self.tolerance_value.get()),
        )


__all__ = ["NonMLBatificationDialog", "PreviewRenderer"]
