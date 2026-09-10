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

    # outra versao do app NAO invalida (cada release esfriava o cache: 90 s de
    # parser por planta grande); mudanca de esquema (CACHE_VERSION) ou do
    # arquivo, sim
    assert open_cache.load_cached(drawing, "9.9.9") is not None
    monkeypatch.setattr(open_cache, "CACHE_VERSION", "esquema-novo")
    assert open_cache.load_cached(drawing, "2.14.0") is None
    monkeypatch.undo()
    monkeypatch.setenv("NEWSICAD_CACHE_DIR", str(tmp_path / "cache"))
    drawing.write_text("xy")
    assert open_cache.load_cached(drawing, "2.14.0") is None


def test_skipped_count_pickle_keeps_attributes():
    s = pickle.loads(pickle.dumps(SkippedCount(3, {"SOLID": 3}, ["n1"])))
    assert int(s) == 3 and s.by_type == {"SOLID": 3} and s.notes == ["n1"]


def test_load_dxf_notes_xrefs_and_loads_layout_without_viewport(tmp_path):
    """09/09/2026: pranchas (paper space) passaram a ser CARREGADAS em
    `document.layouts`, não só avisadas — uma prancha sem VIEWPORT (como
    esta) não gera nota nenhuma, só o conteúdo dela em `doc.layouts`. O
    aviso de XREF continua igual (isso sim não é carregado)."""
    dxf = ezdxf.new("R2000")
    dxf.modelspace().add_line((0, 0), (1, 0))
    layout = dxf.layouts.new("PRANCHA 01")
    layout.add_line((0, 0), (5, 0))
    layout.add_text("selo")
    dxf.blocks.new("BASE_ARQ", dxfattribs={"flags": 4 | 32, "xref_path": "C:/x/BASE_ARQ.dwg"})
    path = tmp_path / "n.dxf"
    dxf.saveas(path)

    doc, skipped = load_dxf(path)
    notes = " ".join(skipped.notes)
    assert "BASE_ARQ" in notes and "XREF" in notes
    assert "PRANCHA 01" in doc.layouts
    assert len(doc.layouts["PRANCHA 01"]) == 2


def test_load_dxf_notes_layout_with_viewport_not_drawn(tmp_path):
    """Uma prancha COM viewport (o caso comum de verdade — recorte/escala
    do Model space) ainda gera o aviso: o VIEWPORT em si não é desenhado,
    só o resto do conteúdo da prancha (que continua sendo carregado)."""
    dxf = ezdxf.new("R2000")
    dxf.modelspace().add_line((0, 0), (1, 0))
    layout = dxf.layouts.new("PRANCHA 01")
    layout.add_text("selo")
    layout.add_viewport(center=(0, 0), size=(10, 10), view_center_point=(0, 0), view_height=10)
    path = tmp_path / "n.dxf"
    dxf.saveas(path)

    doc, skipped = load_dxf(path)
    notes = " ".join(skipped.notes)
    assert "PRANCHA 01" in notes and "viewport" in notes.lower()
    assert "PRANCHA 01" in doc.layouts
    assert len(doc.layouts["PRANCHA 01"]) == 1


def test_load_dxf_without_layout_content_has_no_notes(tmp_path):
    dxf = ezdxf.new("R2000")
    dxf.modelspace().add_line((0, 0), (1, 0))
    path = tmp_path / "plain.dxf"
    dxf.saveas(path)
    _doc, skipped = load_dxf(path)
    assert skipped.notes == []


def test_altura_padrao_de_texto_vem_do_desenho_aberto(tmp_path):
    """Achado do teste de duas abas (2026-09-06): numa planta em metros os
    textos medem centésimos de unidade, e o MTEXT usava 2,5 fixo. Ao abrir,
    a altura mais comum do arquivo vira o padrão (Document.text_height)."""
    from newsicad.io.dxf_io import load_dxf as _load

    dxf = ezdxf.new("R2000")
    msp = dxf.modelspace()
    for _ in range(3):
        msp.add_text("A", dxfattribs={"height": 0.05}).set_placement((0, 0))
    msp.add_text("B", dxfattribs={"height": 1.5}).set_placement((1, 1))
    path = tmp_path / "alturas.dxf"
    dxf.saveas(path)

    doc, _ = _load(path)
    assert doc.text_height == 0.05
