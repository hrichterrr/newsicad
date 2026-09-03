"""Testes do suporte a blocos dinâmicos importados de .dwg/.dxf reais
(auditoria 2026-08-28 — o bug da "planta explodida" do arquivo Joe Lee):

1. Definições de bloco ANÔNIMAS "*U..." (onde o AutoCAD materializa a
   representação de cada bloco dinâmico) agora são carregadas — antes, 2/3
   a 3/4 dos símbolos de um .dwg real renderizavam como grupos vazios.
   "*Model_Space"/"*Paper_Space"/"*D..."/"*X..." continuam fora.
2. Escala POR EIXO em BlockReference (`scale_y`): INSERTs com xscale ≠
   yscale (esticados) e/ou escala negativa (espelhados) não são mais
   colapsados num único float uniforme. Round-trip completo no .dxf.
3. ATTRIBs (etiquetas/valores preenchidos dos blocos) viram entidades Text
   independentes na leitura; ATTDEF (o molde) deixa de contar como
   "entidade não suportada".
4. MIRROR de BlockReference agora é um espelhamento exato (inverte
   scale_y), não mais a simplificação que só movia o ponto de inserção.
5. refresh_entities incremental por "impressão digital" (a correção de
   lentidão que acompanha o item 1 — carregar os *U adiciona milhares de
   itens, reconstruir tudo a cada passo era 6-8s num arquivo real).
"""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import BlockReference, Line, Point, Text  # noqa: E402
from newsicad.core.geometry_ops import mirror_entity, scale_entity  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------- #
# leitura: blocos anônimos *U + escala por eixo + ATTRIB
# ---------------------------------------------------------------------- #
def _make_dynamic_block_dxf(path) -> None:
    """Monta com ezdxf puro um .dxf com a mesma estrutura que um .dwg com
    blocos dinâmicos produz depois de convertido: INSERT do modelspace
    apontando pra um bloco anônimo *U, com escala não-uniforme/negativa."""
    doc = ezdxf.new("R2000")
    blk = doc.blocks.new(name="*U42")
    blk.add_line((0, 0), (10, 0))
    blk.add_line((0, 0), (0, 4))
    named = doc.blocks.new(name="Tomada")
    named.add_circle((0, 0), 1.5)
    msp = doc.modelspace()
    msp.add_blockref("*U42", (5, 5), dxfattribs={"xscale": -2.0, "yscale": 2.0})
    msp.add_blockref("Tomada", (20, 20), dxfattribs={"xscale": 0.05, "yscale": 0.05})
    doc.saveas(path)


def test_load_dxf_keeps_anonymous_u_blocks(tmp_path):
    path = tmp_path / "dynamic.dxf"
    _make_dynamic_block_dxf(path)
    document, skipped = load_dxf(path)

    assert "*U42" in document.block_definitions
    assert len(document.block_definitions["*U42"]) == 2
    refs = [e for e in document.all_entities() if isinstance(e, BlockReference)]
    assert {r.block_name for r in refs} == {"*U42", "Tomada"}
    # nenhuma instância órfã (o sintoma antigo: grupo vazio no canvas)
    assert all(r.block_name in document.block_definitions for r in refs)


def test_load_dxf_still_skips_internal_anonymous_blocks(tmp_path):
    path = tmp_path / "internos.dxf"
    doc = ezdxf.new("R2000")
    for name in ("*D99", "*X7"):
        blk = doc.blocks.new(name=name)
        blk.add_line((0, 0), (1, 1))
    doc.modelspace().add_line((0, 0), (5, 5))
    doc.saveas(path)

    document, _ = load_dxf(path)
    assert "*D99" not in document.block_definitions
    assert "*X7" not in document.block_definitions
    assert "*Model_Space" not in document.block_definitions


def test_load_dxf_reads_per_axis_scale_including_negative(tmp_path):
    path = tmp_path / "dynamic.dxf"
    _make_dynamic_block_dxf(path)
    document, _ = load_dxf(path)

    flipped = next(
        e for e in document.all_entities()
        if isinstance(e, BlockReference) and e.block_name == "*U42"
    )
    assert flipped.scale == pytest.approx(-2.0)
    assert flipped.scale_y == pytest.approx(2.0)
    assert flipped.scale_xy() == (pytest.approx(-2.0), pytest.approx(2.0))

    uniform = next(
        e for e in document.all_entities()
        if isinstance(e, BlockReference) and e.block_name == "Tomada"
    )
    assert uniform.scale == pytest.approx(0.05)
    assert uniform.scale_y is None  # uniforme continua compacto como antes
    assert uniform.scale_xy() == (pytest.approx(0.05), pytest.approx(0.05))


def test_per_axis_scale_round_trips_through_save(tmp_path):
    path = tmp_path / "dynamic.dxf"
    _make_dynamic_block_dxf(path)
    document, _ = load_dxf(path)

    out = tmp_path / "resaved.dxf"
    save_dxf(document, out)
    reloaded, skipped = load_dxf(out)

    assert skipped == 0
    assert "*U42" in reloaded.block_definitions  # a definição anônima sobreviveu
    flipped = next(
        e for e in reloaded.all_entities()
        if isinstance(e, BlockReference) and e.block_name == "*U42"
    )
    assert flipped.scale == pytest.approx(-2.0)
    assert flipped.scale_y == pytest.approx(2.0)


def test_attribs_become_text_and_attdef_is_not_counted(tmp_path):
    path = tmp_path / "attribs.dxf"
    doc = ezdxf.new("R2000")
    blk = doc.blocks.new(name="Etiquetado")
    blk.add_line((0, 0), (2, 0))
    blk.add_attdef("TAG", (0, 1), dxfattribs={"height": 1.0})
    msp = doc.modelspace()
    ref = msp.add_blockref("Etiquetado", (10, 10))
    ref.add_attrib("TAG", "TOMADA-07", (10, 11), dxfattribs={"height": 1.0})
    doc.saveas(path)

    document, skipped = load_dxf(path)
    assert skipped == 0  # ATTDEF não conta mais como "não suportada"
    texts = [e for e in document.all_entities() if isinstance(e, Text)]
    assert any(t.content == "TOMADA-07" for t in texts)
    tag = next(t for t in texts if t.content == "TOMADA-07")
    assert tag.insertion_point.as_tuple() == (10, 11)


# ---------------------------------------------------------------------- #
# geometria: SCALE e MIRROR com escala por eixo
# ---------------------------------------------------------------------- #
def test_uniform_scale_preserves_non_uniform_proportion():
    ref = BlockReference(block_name="B", insertion_point=Point(2, 2), scale=-2.0, scale_y=2.0)
    scale_entity(ref, Point(0, 0), 3.0)
    assert ref.scale == pytest.approx(-6.0)
    assert ref.scale_y == pytest.approx(6.0)
    assert ref.insertion_point.as_tuple() == (6, 6)


def test_mirror_flips_scale_y_and_reflects_rotation():
    ref = BlockReference(
        block_name="B", insertion_point=Point(3, 1), scale=1.0, rotation=math.radians(30)
    )
    mirrored = mirror_entity(ref, Point(0, 0), Point(10, 0))  # espelho no eixo X
    assert isinstance(mirrored, BlockReference)
    assert mirrored.insertion_point.x == pytest.approx(3)
    assert mirrored.insertion_point.y == pytest.approx(-1)
    # refl(0°)·rot(30°) = rot(-30°)·scale(1,-1)
    assert mirrored.rotation == pytest.approx(math.radians(-30) % (2 * math.pi))
    sx, sy = mirrored.scale_xy()
    assert sx == pytest.approx(1.0)
    assert sy == pytest.approx(-1.0)


def test_double_mirror_returns_to_uniform_orientation():
    ref = BlockReference(block_name="B", insertion_point=Point(3, 1), scale=2.0)
    once = mirror_entity(ref, Point(0, 0), Point(10, 0))
    twice = mirror_entity(once, Point(0, 0), Point(10, 0))
    assert isinstance(twice, BlockReference)
    sx, sy = twice.scale_xy()
    assert sx == pytest.approx(2.0)
    assert sy == pytest.approx(2.0)
    assert twice.insertion_point.y == pytest.approx(1)


# ---------------------------------------------------------------------- #
# canvas: render/bbox com escala por eixo + refresh incremental
# ---------------------------------------------------------------------- #
def test_canvas_renders_non_uniform_block_with_correct_bbox():
    _app()
    from newsicad.ui.main_window import MainWindow

    window = MainWindow()
    doc = window.document
    doc.define_block("*U42", [Line(start=Point(0, 0), end=Point(10, 0))])
    ref = doc.add_entity(
        BlockReference(block_name="*U42", insertion_point=Point(0, 0), scale=-2.0, scale_y=3.0)
    )
    window.canvas.refresh_entities()

    item = window.canvas._entity_items[ref.id]
    rect = item.sceneBoundingRect()
    # linha local de (0,0)-(10,0) com sx=-2 → vai de x=0 até x=-20
    assert rect.left() == pytest.approx(-20, abs=0.5)
    assert rect.right() == pytest.approx(0, abs=0.5)

    bbox = window.canvas._entity_bbox_scene(ref)
    assert bbox.left() == pytest.approx(-20, abs=0.5)

    # hit-test: um ponto sobre a linha transformada (x=-10, y=0) acha o bloco
    assert window.canvas._hit_test(Point(-10, 0)) == ref.id


def test_refresh_entities_reuses_items_when_nothing_changed():
    _app()
    from newsicad.ui.main_window import MainWindow

    window = MainWindow()
    doc = window.document
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.refresh_entities()
    item_before = window.canvas._entity_items[line.id]

    window.canvas.refresh_entities()  # nada mudou
    assert window.canvas._entity_items[line.id] is item_before  # item REUSADO

    line.end = Point(20, 20)  # mutação in-place (o caso MOVE)
    window.canvas.refresh_entities()
    assert window.canvas._entity_items[line.id] is not item_before  # recriado


def test_refresh_entities_rebuilds_instances_after_block_redefinition():
    _app()
    from newsicad.ui.main_window import MainWindow

    window = MainWindow()
    doc = window.document
    doc.define_block("CAM", [Line(start=Point(0, 0), end=Point(1, 0))])
    ref = doc.add_entity(BlockReference(block_name="CAM", insertion_point=Point(0, 0)))
    window.canvas.refresh_entities()
    item_before = window.canvas._entity_items[ref.id]

    # BEDIT "Save": redefine o conteúdo — a instância precisa re-renderizar
    doc.define_block("CAM", [Line(start=Point(0, 0), end=Point(5, 5))])
    window.canvas.refresh_entities()
    item_after = window.canvas._entity_items[ref.id]
    assert item_after is not item_before
    assert item_after.sceneBoundingRect().width() == pytest.approx(5, abs=0.5)


def test_refresh_entities_removes_item_when_layer_hidden():
    _app()
    from newsicad.ui.main_window import MainWindow

    window = MainWindow()
    doc = window.document
    doc.add_layer("CFTV")
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0), layer="CFTV"))
    window.canvas.refresh_entities()
    assert line.id in window.canvas._entity_items

    doc.layers["CFTV"].visible = False
    window.canvas.refresh_entities()
    assert line.id not in window.canvas._entity_items

    doc.layers["CFTV"].visible = True
    window.canvas.refresh_entities()
    assert line.id in window.canvas._entity_items


def test_properties_panel_shows_split_scale_for_non_uniform():
    from newsicad.ui.properties_panel import _geometry_fields

    uniform = BlockReference(block_name="B", scale=0.05)
    rows = dict(_geometry_fields(uniform))
    assert "Escala" in rows and "Escala X" not in rows

    stretched = BlockReference(block_name="B", scale=-2.0, scale_y=2.0)
    rows = dict(_geometry_fields(stretched))
    assert "Escala X" in rows and "Escala Y" in rows and "Escala" not in rows
