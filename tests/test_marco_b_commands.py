"""Testes do Marco B do plano de melhorias (2026-08-22): MLINE, XLINE/RAY,
BREAK/BREAK AT POINT, LENGTHEN, DONUT, POINT real (substituindo o marcador
Circle de DIVIDE/MEASURE) e justificação de MTEXT."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point, PointEntity, Ray, Text, XLine
from newsicad.core.geometry_ops import (
    mirror_entity,
    rotate_entity,
    scale_entity,
    translate_entity,
)
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# POINT
# ---------------------------------------------------------------------- #
def test_point_command_creates_point_entity():
    interp, doc = make_interpreter()
    interp.start("PO")
    interp.submit_point(Point(3, 4))
    assert not interp.active

    points = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(points) == 1
    assert points[0].location == Point(3, 4)


# ---------------------------------------------------------------------- #
# XLINE / RAY
# ---------------------------------------------------------------------- #
def test_xline_command_creates_infinite_line_through_two_points():
    interp, doc = make_interpreter()
    interp.start("XL")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_text("")  # Enter termina
    assert not interp.active

    xlines = [e for e in doc.all_entities() if isinstance(e, XLine)]
    assert len(xlines) == 1
    assert xlines[0].point == Point(0, 0)
    assert xlines[0].angle == pytest.approx(math.pi / 4)


def test_xline_command_supports_multiple_through_points_from_same_base():
    interp, doc = make_interpreter()
    interp.start("XLINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(0, 10))
    interp.submit_text("")
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, XLine)]) == 2


def test_ray_command_creates_ray_with_correct_angle():
    interp, doc = make_interpreter()
    interp.start("RAY")
    interp.submit_point(Point(1, 1))
    interp.submit_point(Point(1, 5))
    interp.submit_text("")
    assert not interp.active

    rays = [e for e in doc.all_entities() if isinstance(e, Ray)]
    assert len(rays) == 1
    assert rays[0].point == Point(1, 1)
    assert rays[0].angle == pytest.approx(math.pi / 2)


# ---------------------------------------------------------------------- #
# DONUT
# ---------------------------------------------------------------------- #
def test_donut_command_creates_circle_with_inner_radius():
    interp, doc = make_interpreter()
    interp.start("DO")
    interp.submit_text("1.0")
    interp.submit_text("2.0")
    interp.submit_point(Point(5, 5))
    interp.submit_text("")  # Enter termina
    assert not interp.active

    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 1
    assert circles[0].center == Point(5, 5)
    assert circles[0].radius == pytest.approx(1.0)
    assert circles[0].inner_radius == pytest.approx(0.5)


def test_donut_command_rejects_inside_diameter_not_smaller_than_outside():
    interp, doc = make_interpreter()
    interp.start("DONUT")
    interp.submit_text("2.0")
    interp.submit_text("1.0")
    assert not interp.active
    assert not doc.all_entities()


def test_donut_command_default_diameters_on_enter():
    interp, doc = make_interpreter()
    interp.start("DONUT")
    interp.submit_text("")
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")
    circle = next(e for e in doc.all_entities() if isinstance(e, Circle))
    assert circle.radius == pytest.approx(0.5)
    assert circle.inner_radius == pytest.approx(0.25)


# ---------------------------------------------------------------------- #
# MLINE
# ---------------------------------------------------------------------- #
def test_mline_command_creates_two_parallel_polylines():
    interp, doc = make_interpreter()
    interp.start("ML")
    interp.submit_text("2.0")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_text("")
    assert not interp.active

    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert len(polys) == 2
    ys = sorted(p.points[0].y for p in polys)
    assert ys == pytest.approx([-1.0, 1.0])


def test_mline_command_rejects_non_positive_width():
    interp, doc = make_interpreter()
    interp.start("MLINE")
    interp.submit_text("0")
    assert not interp.active
    assert not doc.all_entities()


# ---------------------------------------------------------------------- #
# BREAK
# ---------------------------------------------------------------------- #
def test_break_removes_segment_between_two_points_on_line():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("BR")
    interp.submit_point(Point(3, 0))
    interp.submit_point(Point(7, 0))
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    segments = sorted((round(l.start.x, 6), round(l.end.x, 6)) for l in lines)
    assert segments == [(0.0, 3.0), (7.0, 10.0)]


def test_break_at_one_end_only_shortens_line():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("BREAK")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(4, 0))
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert (lines[0].start.x, lines[0].end.x) == (4.0, 10.0)


def test_break_on_circle_converts_to_arc():
    interp, doc = make_interpreter()
    doc.add_entity(Circle(center=Point(0, 0), radius=5))
    interp.start("BREAK")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(0, 5))
    assert not interp.active

    assert not [e for e in doc.all_entities() if isinstance(e, Circle)]
    arcs = [e for e in doc.all_entities() if isinstance(e, Arc)]
    assert len(arcs) == 1
    assert arcs[0].start_angle == pytest.approx(math.pi / 2)
    assert arcs[0].end_angle == pytest.approx(0.0)


def test_break_first_point_suboption_overrides_click_point():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("BREAK")
    interp.submit_point(Point(3, 0))  # ponto de seleção do objeto (será substituído)
    interp.submit_text("First point")
    interp.submit_point(Point(2, 0))
    interp.submit_point(Point(8, 0))
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    segments = sorted((round(l.start.x, 6), round(l.end.x, 6)) for l in lines)
    assert segments == [(0.0, 2.0), (8.0, 10.0)]


def test_breakatpoint_splits_line_without_removing_material():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("BREAKATPOINT")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(5, 0))
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    segments = sorted((round(l.start.x, 6), round(l.end.x, 6)) for l in lines)
    assert segments == [(0.0, 5.0), (5.0, 10.0)]


def test_breakatpoint_rejects_circle():
    interp, doc = make_interpreter()
    doc.add_entity(Circle(center=Point(0, 0), radius=5))
    interp.start("BREAKATPOINT")
    interp.submit_point(Point(5, 0))
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, Circle)]) == 1


# ---------------------------------------------------------------------- #
# LENGTHEN
# ---------------------------------------------------------------------- #
def test_lengthen_delta_extends_from_nearest_end():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("LEN")
    interp.submit_text("DElta")
    interp.submit_text("5")
    interp.submit_point(Point(9, 0))  # mais perto do end
    interp.submit_text("")  # Enter termina
    assert not interp.active
    assert line.start == Point(0, 0)
    assert line.end.x == pytest.approx(15.0)


def test_lengthen_total_sets_absolute_length():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("LENGTHEN")
    interp.submit_text("Total")
    interp.submit_text("20")
    interp.submit_point(Point(9, 0))
    interp.submit_text("")
    assert not interp.active
    assert line.end.x == pytest.approx(20.0)


def test_lengthen_percent_scales_length():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("LENGTHEN")
    interp.submit_text("Percent")
    interp.submit_text("150")
    interp.submit_point(Point(9, 0))
    interp.submit_text("")
    assert not interp.active
    assert line.end.x == pytest.approx(15.0)


def test_lengthen_arc_extends_sweep_from_nearest_end():
    interp, doc = make_interpreter()
    arc = doc.add_entity(Arc(center=Point(0, 0), radius=10, start_angle=0.0, end_angle=math.pi / 2))
    interp.start("LENGTHEN")
    interp.submit_text("DElta")
    interp.submit_text(str(10 * math.pi / 2))  # dobra o comprimento do arco
    pick = arc.end_point()
    interp.submit_point(pick)
    interp.submit_text("")
    assert not interp.active
    assert arc.start_angle == pytest.approx(0.0)
    assert arc.end_angle == pytest.approx(math.pi)


# ---------------------------------------------------------------------- #
# DIVIDE / MEASURE agora usam PointEntity real
# ---------------------------------------------------------------------- #
def test_divide_creates_point_entities_not_circles():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("DIVIDE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("4")
    assert not interp.active

    markers = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(markers) == 3
    assert not [e for e in doc.all_entities() if isinstance(e, Circle)]


def test_measure_creates_point_entities_not_circles():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("MEASURE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("3")
    assert not interp.active

    markers = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(markers) == 3


# ---------------------------------------------------------------------- #
# MTEXT com justificação
# ---------------------------------------------------------------------- #
def test_mtext_default_justify_is_top_left():
    interp, doc = make_interpreter()
    interp.start("MTEXT")
    interp.submit_point(Point(0, 0))
    interp.submit_text("Hello")
    assert not interp.active
    text = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert text.justify == "TL"


def test_mtext_justify_suboption_sets_justify_field():
    interp, doc = make_interpreter()
    interp.start("MTEXT")
    interp.submit_text("Justify")
    interp.submit_text("MC")
    interp.submit_point(Point(0, 0))
    interp.submit_text("Hello")
    assert not interp.active
    text = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert text.justify == "MC"
    assert text.insertion_point == Point(0, 0)


# ---------------------------------------------------------------------- #
# geometry_ops: dispatch para os novos tipos
# ---------------------------------------------------------------------- #
def test_translate_point_entity():
    p = PointEntity(location=Point(1, 1))
    translate_entity(p, 2, 3)
    assert p.location == Point(3, 4)


def test_translate_xline():
    x = XLine(point=Point(0, 0), angle=0.5)
    translate_entity(x, 1, 1)
    assert x.point == Point(1, 1)
    assert x.angle == pytest.approx(0.5)


def test_rotate_xline_changes_angle_and_point():
    x = XLine(point=Point(1, 0), angle=0.0)
    rotate_entity(x, Point(0, 0), math.pi / 2)
    assert x.point.x == pytest.approx(0.0)
    assert x.point.y == pytest.approx(1.0)
    assert x.angle == pytest.approx(math.pi / 2)


def test_scale_ray_moves_point_only():
    r = Ray(point=Point(2, 0), angle=0.3)
    scale_entity(r, Point(0, 0), 3.0)
    assert r.point == Point(6, 0)
    assert r.angle == pytest.approx(0.3)


def test_mirror_point_entity():
    p = PointEntity(location=Point(2, 3))
    mirrored = mirror_entity(p, Point(0, 0), Point(0, 1))
    assert mirrored.location.x == pytest.approx(-2)
    assert mirrored.location.y == pytest.approx(3)


def test_scale_circle_scales_inner_radius_too():
    c = Circle(center=Point(0, 0), radius=2.0, inner_radius=1.0)
    scale_entity(c, Point(0, 0), 2.0)
    assert c.radius == pytest.approx(4.0)
    assert c.inner_radius == pytest.approx(2.0)


# ---------------------------------------------------------------------- #
# DXF round-trip
# ---------------------------------------------------------------------- #
def test_dxf_roundtrip_point_xline_ray_donut_and_text_justify(tmp_path):
    from newsicad.io.dxf_io import load_dxf, save_dxf

    doc = Document()
    doc.add_entity(PointEntity(location=Point(1, 2)))
    doc.add_entity(XLine(point=Point(0, 0), angle=math.pi / 4))
    doc.add_entity(Ray(point=Point(1, 1), angle=math.pi / 3))
    doc.add_entity(Circle(center=Point(5, 5), radius=2.0, inner_radius=1.0))
    doc.add_entity(Text(insertion_point=Point(3, 3), content="oi", justify="MC"))

    path = tmp_path / "marco_b.dxf"
    save_dxf(doc, path)
    reloaded, skipped = load_dxf(path)

    assert skipped == 0
    points = [e for e in reloaded.all_entities() if isinstance(e, PointEntity)]
    assert len(points) == 1
    assert points[0].location.x == pytest.approx(1)
    assert points[0].location.y == pytest.approx(2)

    xlines = [e for e in reloaded.all_entities() if isinstance(e, XLine)]
    assert len(xlines) == 1
    assert xlines[0].angle == pytest.approx(math.pi / 4)

    rays = [e for e in reloaded.all_entities() if isinstance(e, Ray)]
    assert len(rays) == 1
    assert rays[0].angle == pytest.approx(math.pi / 3)

    circles = [e for e in reloaded.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 2  # outer + inner, sem preenchimento (ver dxf_io.py)
    radii = sorted(c.radius for c in circles)
    assert radii == pytest.approx([1.0, 2.0])

    text = next(e for e in reloaded.all_entities() if isinstance(e, Text))
    assert text.justify == "MC"
