"""Testes dos comandos escolhidos pelo Hamilton pra sair de "fora de escopo"
no artifact de referência do AutoCAD: FIELD, CLIP/CLIPOFF (recorte de
bloco/xref/imagem) e COPYCLIP/CUTCLIP/PASTECLIP (clipboard do Windows)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Circle, ImageReference, Line, LWPolyline, Point, Text
from newsicad.core.fields import compute_field_value, resolve_field_text
from newsicad.core.selection import Selection


def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


class _FakeView:
    """`nearest_entity` (fallback puro usado quando `ctx.view` é None) não
    sabe medir distância até BlockReference/ImageReference (só linhas/arcos/
    polylines — ver `point_entity_distance` em core/geometry_ops.py), então
    os testes de CLIP precisam de um `ctx.view._hit_test` de mentira, igual
    ao CanvasView de verdade forneceria a partir de qualquer clique."""

    def __init__(self, entity_id: str) -> None:
        self._entity_id = entity_id

    def _hit_test(self, _point: Point) -> str:
        return self._entity_id


# ---------------------------------------------------------------------- #
# FIELD
# ---------------------------------------------------------------------- #
def test_field_area_links_to_closed_polyline_and_stays_live():
    interp, doc = make_interpreter()
    square = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    )
    interp.start("FIELD")
    interp.submit_text("Area")
    interp.submit_point(Point(5, 0))  # clique em cima da borda de baixo do quadrado
    interp.submit_point(Point(20, 20))  # ponto de inserção do texto
    interp.submit_text("")  # altura padrão
    assert not interp.active

    texts = [e for e in doc.all_entities() if isinstance(e, Text)]
    assert len(texts) == 1
    field = texts[0]
    assert field.field_type == "AREA"
    assert field.field_ref == square.id
    assert field.content == "100.00 m²"

    # move um vértice: a área muda, e resolve_field_text acompanha sem
    # precisar recriar o Text (mesma mecânica que CanvasView.refresh_entities
    # usa a cada redesenho).
    square.points[2] = Point(20, 10)
    assert resolve_field_text(field, doc) == "150.00 m²"


def test_field_length_links_to_line():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(3, 4)))
    interp.start("FIELD")
    interp.submit_text("Length")
    interp.submit_point(Point(1.5, 2))
    interp.submit_point(Point(0, 0))
    interp.submit_text("")
    assert not interp.active

    field = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert field.field_ref == line.id
    assert field.content == "5.00 m"


def test_field_date_needs_no_reference():
    interp, doc = make_interpreter()
    interp.start("FIELD")
    interp.submit_text("Date")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")
    assert not interp.active

    field = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert field.field_ref is None
    assert field.content == date.today().strftime("%d/%m/%Y")


def test_field_area_shows_placeholder_when_reference_deleted():
    doc = Document()
    square = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)], closed=True)
    )
    text = Text(insertion_point=Point(0, 0), field_type="AREA", field_ref=square.id)
    doc.remove_entity(square.id)
    assert resolve_field_text(text, doc) == "#REF!"


def test_compute_field_value_area_on_circle():
    doc = Document()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=2))
    value = compute_field_value("AREA", doc, circle.id)
    assert value.endswith("m²")


# ---------------------------------------------------------------------- #
# CLIP / CLIPOFF
# ---------------------------------------------------------------------- #
def test_clip_sets_rectangular_boundary_on_block_reference():
    interp, doc = make_interpreter()
    doc.block_definitions["DOOR"] = [Line(start=Point(0, 0), end=Point(1, 0))]
    block = doc.add_entity(
        BlockReference(block_name="DOOR", insertion_point=Point(10, 10), scale=2.0, rotation=0.0)
    )
    interp.context.view = _FakeView(block.id)
    interp.start("CLIP")
    interp.submit_point(Point(10, 10))  # seleciona o bloco (hit-test por proximidade)
    interp.submit_point(Point(10, 10))  # primeiro canto -> local (0, 0)
    interp.submit_point(Point(14, 12))  # canto oposto -> local (2, 1), já descontando scale=2
    assert not interp.active

    assert block.clip_boundary is not None
    xs = sorted({round(p.x, 6) for p in block.clip_boundary})
    ys = sorted({round(p.y, 6) for p in block.clip_boundary})
    assert xs == [0.0, 2.0]
    assert ys == [0.0, 1.0]


def test_clip_sets_boundary_on_image_reference_relative_to_insertion_point():
    interp, doc = make_interpreter()
    image = doc.add_entity(
        ImageReference(path=Path("x.png"), insertion_point=Point(0, 0), width=100, height=50)
    )
    interp.context.view = _FakeView(image.id)
    interp.start("CLIP")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_point(Point(40, 30))
    assert not interp.active

    xs = sorted({round(p.x, 6) for p in image.clip_boundary})
    ys = sorted({round(p.y, 6) for p in image.clip_boundary})
    assert xs == [10.0, 40.0]
    assert ys == [10.0, 30.0]


def test_clip_rejects_non_clippable_entity():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("CLIP")
    interp.submit_point(Point(0.5, 0))
    assert not interp.active


def test_clipoff_removes_boundary():
    interp, doc = make_interpreter()
    doc.block_definitions["DOOR"] = [Line(start=Point(0, 0), end=Point(1, 0))]
    block = doc.add_entity(BlockReference(block_name="DOOR", insertion_point=Point(0, 0)))
    block.clip_boundary = [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)]

    interp.context.view = _FakeView(block.id)
    interp.start("CLIPOFF")
    interp.submit_point(Point(0, 0))
    assert not interp.active
    assert block.clip_boundary is None


# ---------------------------------------------------------------------- #
# COPYCLIP / CUTCLIP / PASTECLIP
# ---------------------------------------------------------------------- #
def test_copyclip_then_pasteclip_creates_translated_copy_with_new_id():
    qapp()
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(2, 0)))

    interp.start("COPYCLIP")
    interp.context.selection.add(line.id)
    interp.submit_text("")  # confirma seleção
    interp.submit_point(Point(0, 0))  # ponto base
    assert not interp.active

    interp.start("PASTECLIP")
    interp.submit_point(Point(10, 5))  # ponto de inserção
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    pasted = next(l for l in lines if l.id != line.id)
    assert pasted.start.as_tuple() == (10.0, 5.0)
    assert pasted.end.as_tuple() == (12.0, 5.0)
    # original intacto — COPYCLIP não apaga
    assert line.start.as_tuple() == (0.0, 0.0)


def test_cutclip_removes_original_then_pasteclip_restores_it():
    qapp()
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(2, 0)))

    interp.start("CUTCLIP")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    assert not interp.active
    assert doc.get_entity(line.id) is None
    assert not doc.all_entities()

    interp.start("PASTECLIP")
    interp.submit_point(Point(0, 0))
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert lines[0].id != line.id  # id regenerado, não colide com o original apagado


def test_pasteclip_with_empty_clipboard_does_nothing():
    qapp()
    QApplication.clipboard().clear()
    interp, doc = make_interpreter()
    interp.start("PASTECLIP")
    assert not interp.active
    assert not doc.all_entities()


def test_copyclip_with_no_selection_does_not_touch_clipboard():
    qapp()
    QApplication.clipboard().clear()
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("COPYCLIP")
    interp.submit_text("")  # Enter sem selecionar nada
    assert not interp.active

    interp.start("PASTECLIP")  # clipboard vazio: comando termina sozinho no start()
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, Line)]) == 1
