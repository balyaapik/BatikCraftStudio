"""Undo/redo hemat memori untuk kanvas raster."""

from __future__ import annotations

from PIL import Image

from batikcraft_studio.imaging.raster_document import RasterDocument
from batikcraft_studio.imaging.undo_history import UndoStack


def _solid(size, color):
    return Image.new("RGBA", size, color)


def test_undo_membatalkan_goresan_terakhir():
    doc = RasterDocument(width=200, height=200)
    layer = doc.active_layer
    stack = UndoStack()

    before = layer.image.copy()
    layer.composite(_solid((30, 30), (255, 0, 0, 255)), (10, 10))
    stack.record_layer_change(layer.layer_id, before, layer.image)

    before2 = layer.image.copy()
    layer.composite(_solid((30, 30), (0, 0, 255, 255)), (100, 100))
    stack.record_layer_change(layer.layer_id, before2, layer.image)

    stack.undo(doc)

    assert layer.image.getpixel((110, 110)) == (0, 0, 0, 0)   # goresan 2 hilang
    assert layer.image.getpixel((15, 15)) == (255, 0, 0, 255)  # goresan 1 tetap


def test_redo_mengembalikan():
    doc = RasterDocument(width=100, height=100)
    layer = doc.active_layer
    stack = UndoStack()

    before = layer.image.copy()
    layer.composite(_solid((20, 20), (0, 200, 0, 255)), (5, 5))
    stack.record_layer_change(layer.layer_id, before, layer.image)

    stack.undo(doc)
    assert layer.image.getpixel((10, 10)) == (0, 0, 0, 0)
    stack.redo(doc)
    assert layer.image.getpixel((10, 10)) == (0, 200, 0, 255)


def test_hanya_wilayah_berubah_disimpan():
    doc = RasterDocument(width=1000, height=1000)
    layer = doc.active_layer
    stack = UndoStack()

    before = layer.image.copy()
    layer.composite(_solid((20, 20), (0, 0, 0, 255)), (5, 5))
    stack.record_layer_change(layer.layer_id, before, layer.image)

    edit = stack._undo[-1]
    assert edit.before.width <= 30 and edit.before.height <= 30


def test_tanpa_perubahan_tidak_dicatat():
    doc = RasterDocument(width=64, height=64)
    layer = doc.active_layer
    stack = UndoStack()

    before = layer.image.copy()
    assert not stack.record_layer_change(layer.layer_id, before, layer.image.copy())
    assert not stack.can_undo


def test_percabangan_menghapus_redo():
    doc = RasterDocument(width=80, height=80)
    layer = doc.active_layer
    stack = UndoStack()

    b1 = layer.image.copy()
    layer.composite(_solid((10, 10), (1, 2, 3, 255)), (0, 0))
    stack.record_layer_change(layer.layer_id, b1, layer.image)
    stack.undo(doc)
    assert stack.can_redo

    b2 = layer.image.copy()
    layer.composite(_solid((10, 10), (9, 9, 9, 255)), (40, 40))
    stack.record_layer_change(layer.layer_id, b2, layer.image)

    assert not stack.can_redo


def test_batas_memori_mengusir_tertua():
    doc = RasterDocument(width=200, height=200)
    layer = doc.active_layer
    stack = UndoStack(max_bytes=5000)

    for i in range(40):
        before = layer.image.copy()
        layer.composite(_solid((40, 40), (i % 256, 0, 0, 255)), (i, i))
        stack.record_layer_change(layer.layer_id, before, layer.image)

    assert stack._used <= 5000 or len(stack._undo) == 1


def test_undo_kosong_aman():
    doc = RasterDocument(width=32, height=32)
    stack = UndoStack()

    assert stack.undo(doc) is None
    assert stack.redo(doc) is None
