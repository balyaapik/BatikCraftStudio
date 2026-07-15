"""Regression tests for the TkinterDnD application root bootstrap."""

from __future__ import annotations

from typing import Any

import tkinterdnd2

from batikcraft_studio import app as app_module
from batikcraft_studio import context_tool_app as context_module


class _FakeRoot:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


def test_dnd_root_is_created_before_temporary_tk_factory(monkeypatch: Any) -> None:
    """The DnD constructor must run while tkinter.Tk still points to the real class."""

    original_tk_factory = app_module.tk.Tk
    root = _FakeRoot()
    construction_factories: list[object] = []
    adopted_roots: list[object] = []

    def fake_dnd_root() -> _FakeRoot:
        construction_factories.append(app_module.tk.Tk)
        return root

    def fake_base_init(instance: Any) -> None:
        adopted = app_module.tk.Tk()
        adopted_roots.append(adopted)
        instance.root = adopted

    monkeypatch.setattr(tkinterdnd2.TkinterDnD, "Tk", fake_dnd_root)
    monkeypatch.setattr(context_module.DirectStyleApplication, "__init__", fake_base_init)

    instance = object.__new__(context_module.ContextToolApplication)
    context_module.ContextToolApplication.__init__(instance)

    assert construction_factories == [original_tk_factory]
    assert adopted_roots == [root]
    assert instance.root is root
    assert app_module.tk.Tk is original_tk_factory
    assert root.destroyed is False


def test_dnd_root_is_destroyed_when_application_initialization_fails(
    monkeypatch: Any,
) -> None:
    root = _FakeRoot()
    original_tk_factory = app_module.tk.Tk

    monkeypatch.setattr(tkinterdnd2.TkinterDnD, "Tk", lambda: root)

    def fail_initialization(_instance: object) -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(context_module.DirectStyleApplication, "__init__", fail_initialization)

    instance = object.__new__(context_module.ContextToolApplication)
    try:
        context_module.ContextToolApplication.__init__(instance)
    except RuntimeError as exc:
        assert str(exc) == "startup failed"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Initialization failure was not propagated.")

    assert root.destroyed is True
    assert app_module.tk.Tk is original_tk_factory
