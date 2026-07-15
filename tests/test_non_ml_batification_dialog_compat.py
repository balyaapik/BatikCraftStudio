"""Regression tests for the Python 3.13 Batification dialog bootstrap."""

from __future__ import annotations

from inspect import signature

from batikcraft_studio.ui.non_ml_batification_dialog_compat import (
    NonMLBatificationDialog,
)


class _Value:
    def __init__(self, value: object) -> None:
        self._value = value

    def get(self) -> object:
        return self._value


def test_dialog_options_signature_accepts_tkinter_configuration() -> None:
    """Tkinter constructs Toplevel widgets through ``self._options(cnf)``."""

    parameters = signature(NonMLBatificationDialog._options).parameters

    assert "cnf" in parameters
    assert "kw" in parameters


def test_no_argument_options_call_builds_batification_settings() -> None:
    dialog = object.__new__(NonMLBatificationDialog)
    dialog.mode_value = _Value("Isi + Garis")
    dialog.pattern_scale_value = _Value(0.75)
    dialog.rotation_value = _Value(15.0)
    dialog.opacity_value = _Value(0.8)
    dialog.outline_strength_value = _Value(0.9)
    dialog.outline_width_value = _Value(3)
    dialog.shading_value = _Value(0.5)
    dialog.tolerance_value = _Value(30)

    options = dialog._options()

    assert options.pattern_scale == 0.75
    assert options.pattern_rotation == 15.0
    assert options.pattern_opacity == 0.8
    assert options.outline_strength == 0.9
    assert options.outline_width == 3
    assert options.preserve_shading == 0.5
    assert options.background_tolerance == 30
