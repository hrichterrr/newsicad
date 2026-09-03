"""Testes dos comandos novos do marco de feedback do grupo de testers
(WhatsApp "NewSicad"): POLYGON, ALIGN, ARRAY (retangular/polar), MATCHPROP,
SELECTSIMILAR."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Circle, Line, LWPolyline, Point
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# POLYGON
# ---------------------------------------------------------------------- #
def test_polygon_inscribed_creates_closed_polyline_at_radius():
    interp, doc = make_interpreter()
    interp.start("POL")
    interp.submit_text("4")
    interp.submit_point(Point(0, 0))
    interp.submit_text("Inscribed")
    interp.submit_text("5")
    assert not interp.active

    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert len(polys) == 1
    poly = polys[0]
    assert poly.closed
    assert len(poly.points) == 4
    for point in poly.points:
        assert math.hypot(point.x, point.y) == pytest.approx(5)


def test_polygon_circumscribed_vertices_farther_than_radius():
    interp, doc = make_interpreter()
    interp.start("POL")
    interp.submit_text("4")
    interp.submit_point(Point(0, 0))
    interp.submit_text("Circumscribed")
    interp.submit_text("5")
    assert not interp.active

    poly = next(e for e in doc.all_entities() if isinstance(e, LWPolyline))
    vertex_radius = math.hypot(poly.points[0].x, poly.points[0].y)
    assert vertex_radius == pytest.approx(5 / math.cos(math.pi / 4))


def test_polygon_default_sides_is_four_on_enter():
    interp, doc = make_interpreter()
    interp.start("POL")
    interp.submit_text("")  # Enter -> default 4 lados
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Enter -> default Inscribed
    interp.submit_text("1")
    assert not interp.active
    poly = next(e for e in doc.all_entities() if isinstance(e, LWPolyline))
    assert len(poly.points) == 4


# ---------------------------------------------------------------------- #
# ALIGN
# ---------------------------------------------------------------------- #
def test_align_translate_only():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("AL")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))  # first source
    interp.submit_point(Point(10, 10))  # first destination
    interp.submit_point(Point(1, 0))  # second source
    interp.submit_point(Point(11, 10))  # second destination
    interp.submit_text("")  # scale? default No
    assert not interp.active
    assert line.start.as_tuple() == pytest.approx((10, 10))
    assert line.end.as_tuple() == pytest.approx((11, 10))


def test_align_translate_and_rotate_90_degrees():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("AL")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(1, 0))
    interp.submit_point(Point(0, 1))
    interp.submit_text("")
    assert not interp.active
    assert line.start.as_tuple() == pytest.approx((0, 0), abs=1e-9)
    assert line.end.x == pytest.approx(0, abs=1e-9)
    assert line.end.y == pytest.approx(1)


def test_align_with_scale_yes_resizes():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("AL")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(1, 0))
    interp.submit_point(Point(2, 0))  # destino 2x mais longe -> escala x2
    interp.submit_text("Yes")
    assert not interp.active
    assert line.end.as_tuple() == pytest.approx((2, 0))


# ---------------------------------------------------------------------- #
# ARRAY
# ---------------------------------------------------------------------- #
def test_array_rectangular_creates_grid():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("AR")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("Rectangular")
    interp.submit_text("2")  # rows
    interp.submit_text("2")  # cols
    interp.submit_text("10")  # row spacing
    interp.submit_text("5")  # col spacing
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 4
    starts = sorted(l.start.as_tuple() for l in lines)
    assert starts == sorted([(0.0, 0.0), (5.0, 0.0), (0.0, 10.0), (5.0, 10.0)])


def test_array_polar_full_circle():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(1, 0), radius=0.1))
    interp.start("AR")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    interp.submit_text("Polar")
    interp.submit_point(Point(0, 0))
    interp.submit_text("4")
    interp.submit_text("")  # Enter -> 360 (volta completa)
    assert not interp.active

    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 4
    expected = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    for ex, ey in expected:
        assert any(
            c.center.x == pytest.approx(ex, abs=1e-9) and c.center.y == pytest.approx(ey, abs=1e-9)
            for c in circles
        )


# ---------------------------------------------------------------------- #
# MATCHPROP
# ---------------------------------------------------------------------- #
def test_matchprop_copies_layer_and_color():
    interp, doc = make_interpreter()
    doc.add_layer("WALLS")
    source = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1), layer="WALLS", color="#FF0000"))
    target = doc.add_entity(Circle(center=Point(0, 0), radius=1))

    interp.start("MA")
    interp.context.selection.add(source.id)
    interp.submit_text("")
    interp.context.selection.add(target.id)
    interp.submit_text("")
    assert not interp.active
    assert target.layer == "WALLS"
    assert target.color == "#FF0000"


# ---------------------------------------------------------------------- #
# SELECTSIMILAR
# ---------------------------------------------------------------------- #
def test_select_similar_selects_only_same_type():
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    line2 = doc.add_entity(Line(start=Point(2, 2), end=Point(3, 3)))
    doc.add_entity(Circle(center=Point(0, 0), radius=1))

    interp.start("SIM")
    interp.context.selection.add(line1.id)
    interp.submit_text("")
    assert not interp.active
    assert interp.context.selection.ids == {line1.id, line2.id}


def test_select_similar_uses_existing_selection_as_seed_without_reprompting():
    """Bug real reportado: SIM sempre limpava a seleção atual e pedia pra
    selecionar de novo, quebrando o fluxo natural de "clico no objeto,
    depois digito SIM"."""
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    line2 = doc.add_entity(Line(start=Point(2, 2), end=Point(3, 3)))
    doc.add_entity(Circle(center=Point(0, 0), radius=1))

    interp.context.selection.add(line1.id)  # já selecionado ANTES do comando
    interp.start("SIM")
    assert not interp.active  # não deve ficar esperando uma seleção nova
    assert interp.context.selection.ids == {line1.id, line2.id}
