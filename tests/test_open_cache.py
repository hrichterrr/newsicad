"""Cache de abertura (newsicad/io/open_cache.py) e avisos de layouts/xrefs
(SkippedCount.notes) — v2.14.0."""

from __future__ import annotations

import pickle

import ezdxf

from newsicad.core.document import Document
from newsicad.core.entities import Line, Point
from newsicad.io import open_cache
from newsicad.io.dxf_io import SkippedCount, load_dxf


def test_store_and_load_roundtrip_and_invalidation(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSICAD_CACHE_DIR", str(tmp_path / "cache"))
    drawing = tmp_path / "a.dxf"
    drawing.write_text("x")
    doc = Document()
    doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    skipped = SkippedCount(2, {"REGION": 2}, ["nota"])

    assert open_cache.load_cached(drawing, "2.14.0") is None
    assert open_cache.store_cached(drawing, "2.14.0", (doc, skipped))
    loaded_doc, loaded_skipped = open_cache.load_cached(drawing, "2.14.0")
    assert len(loaded_doc.entities) == 1
    assert int(loaded_skipped) == 2 and loaded_skipped.by_type == {"REGION": 2}
    assert loaded_skipped.notes == ["nota"]

    # outra versão do app ou arquivo alterado -> entrada inválida
    assert open_cache.load_cached(drawing, "9.9.9") is None
    drawing.write_text("xy")
    assert open_cache.load_cached(drawing, "2.14.0") is None


def test_skipped_count_pickle_keeps_attributes():
    s = pickle.loads(pickle.dumps(SkippedCount(3, {"SOLID": 3}, ["n1"])))
    assert int(s) == 3 and s.by_type == {"SOLID": 3} and s.notes == ["n1"]


def test_load_dxf_notes_layouts_and_xrefs(tmp_path):
    dxf = ezdxf.new("R2000")
    dxf.modelspace().add_line((0, 0), (1, 0))
    layout = dxf.layouts.new("PRANCHA 01")
    layout.add_line((0, 0), (5, 0))
    layout.add_text("selo")
    dxf.blocks.new("BASE_ARQ", dxfattribs={"flags": 4 | 32, "xref_path": "C:/x/BASE_ARQ.dwg"})
    path = tmp_path / "n.dxf"
    dxf.saveas(path)

    _doc, skipped = load_dxf(path)
    notes = " ".join(skipped.notes)
    assert "PRANCHA 01 (2)" in notes
    assert "BASE_ARQ" in notes and "XREF" in notes


def test_load_dxf_without_layout_content_has_no_notes(tmp_path):
    dxf = ezdxf.new("R2000")
    dxf.modelspace().add_line((0, 0), (1, 0))
    path = tmp_path / "plain.dxf"
    dxf.saveas(path)
    _doc, skipped = load_dxf(path)
    assert skipped.notes == []
