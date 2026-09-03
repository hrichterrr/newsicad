"""Testes da segunda leva de pedidos do grupo de testers (WhatsApp
"NewSicad"): SPLINE, BOUNDARY, PEDIT e HATCHEDIT."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Circle, Hatch, Line, LWPolyline, Point, Spline
from newsicad.core.geometry_ops import (
    catmull_rom_bezier,
    point_in_polygon,
    trace_simple_line_loop,
)
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# geometria pura: catmull_rom_bezier / point_in_polygon / trace_simple_line_loop
# ---------------------------------------------------------------------- #
def test_catmull_rom_bezier_two_points_is_straight_segment():
    segments = catmull_rom_bezier([Point(0, 0), Point(10, 0)], closed=False)
    assert len(segments) == 1
    p0, ctrl1, ctrl2, p3 = segments[0]
    assert p0.as_tuple() == (0, 0)
    assert p3.as_tuple() == (10, 0)


def test_catmull_rom_bezier_open_curve_passes_through_fit_points():
    points = [Point(0, 0), Point(5, 5), Point(10, 0), Point(15, 5)]
    segments = catmull_rom_bezier(points, closed=False)
    assert len(segments) == 3
    anchors = [segments[0][0]] + [seg[3] for seg in segments]
    assert [p.as_tuple() for p in anchors] == [p.as_tuple() for p in points]


def test_catmull_rom_bezier_closed_curve_has_one_segment_per_point():
    points = [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]
    segments = catmull_rom_bezier(points, closed=True)
    assert len(segments) == len(points)


def test_point_in_polygon_basic_square():
    square = [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]
    assert point_in_polygon(Point(5, 5), square)
    assert not point_in_polygon(Point(50, 50), square)


def test_trace_simple_line_loop_finds_rectangle():
    lines = [
        Line(start=Point(0, 0), end=Point(10, 0)),
        Line(start=Point(10, 0), end=Point(10, 10)),
        Line(start=Point(10, 10), end=Point(0, 10)),
        Line(start=Point(0, 10), end=Point(0, 0)),
    ]
    loop = trace_simple_line_loop(lines, Point(5, 5))
    assert loop is not None
    assert len(loop) == 4
    assert {p.as_tuple() for p in loop} == {(0, 0), (10, 0), (10, 10), (0, 10)}


def test_trace_simple_line_loop_returns_none_outside_any_loop():
    lines = [
        Line(start=Point(0, 0), end=Point(10, 0)),
        Line(start=Point(10, 0), end=Point(10, 10)),
        Line(start=Point(10, 10), end=Point(0, 10)),
        Line(start=Point(0, 10), end=Point(0, 0)),
    ]
    assert trace_simple_line_loop(lines, Point(50, 50)) is None


def test_trace_simple_line_loop_bails_out_on_t_junction():
    # retângulo + uma linha extra saindo do meio de uma aresta (nó de grau 3)
    lines = [
        Line(start=Point(0, 0), end=Point(10, 0)),
        Line(start=Point(10, 0), end=Point(10, 10)),
        Line(start=Point(10, 10), end=Point(0, 10)),
        Line(start=Point(0, 10), end=Point(0, 0)),
        Line(start=Point(0, 0), end=Point(5, 5)),  # parede interna encostando num canto
    ]
    assert trace_simple_line_loop(lines, Point(1, 1)) is None


def test_trace_simple_line_loop_picks_smallest_enclosing_loop():
    outer = [
        Line(start=Point(0, 0), end=Point(20, 0)),
        Line(start=Point(20, 0), end=Point(20, 20)),
        Line(start=Point(20, 20), end=Point(0, 20)),
        Line(start=Point(0, 20), end=Point(0, 0)),
    ]
    # segundo laço, desconectado, menor e também contendo o ponto de teste
    inner = [
        Line(start=Point(5, 5), end=Point(8, 5)),
        Line(start=Point(8, 5), end=Point(8, 8)),
        Line(start=Point(8, 8), end=Point(5, 8)),
        Line(start=Point(5, 8), end=Point(5, 5)),
    ]
    loop = trace_simple_line_loop(outer + inner, Point(6, 6))
    assert loop is not None
    assert {p.as_tuple() for p in loop} == {(5, 5), (8, 5), (8, 8), (5, 8)}


# ---------------------------------------------------------------------- #
# SPLINE
# ---------------------------------------------------------------------- #
def test_spline_command_creates_open_spline():
    interp, doc = make_interpreter()
    interp.start("SP")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_point(Point(10, 0))
    interp.submit_text("")  # Enter termina
    assert not interp.active

    splines = [e for e in doc.all_entities() if isinstance(e, Spline)]
    assert len(splines) == 1
    assert not splines[0].closed
    assert [p.as_tuple() for p in splines[0].points] == [(0, 0), (5, 5), (10, 0)]


def test_spline_command_close_option():
    interp, doc = make_interpreter()
    interp.start("SPLINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_text("Close")
    assert not interp.active
    spline = next(e for e in doc.all_entities() if isinstance(e, Spline))
    assert spline.closed


def test_spline_undo_removes_last_point():
    interp, doc = make_interpreter()
    interp.start("SP")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_text("Undo")
    interp.submit_point(Point(9, 9))
    interp.submit_text("")
    assert not interp.active
    spline = next(e for e in doc.all_entities() if isinstance(e, Spline))
    assert [p.as_tuple() for p in spline.points] == [(0, 0), (9, 9)]


def test_spline_moves_via_move_command():
    interp, doc = make_interpreter()
    spline = doc.add_entity(Spline(points=[Point(0, 0), Point(1, 1)]))
    interp.start("M")
    interp.context.selection.add(spline.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    assert not interp.active
    assert spline.points[0].as_tuple() == (5, 5)
    assert spline.points[1].as_tuple() == (6, 6)


def test_spline_dxf_round_trip(tmp_path):
    from newsicad.io.dxf_io import load_dxf, save_dxf

    doc = Document()
    doc.add_entity(Spline(points=[Point(0, 0), Point(5, 5), Point(10, 0)], closed=False))
    doc.add_entity(Spline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True))

    path = tmp_path / "splines.dxf"
    save_dxf(doc, path)
    loaded, skipped = load_dxf(path)

    assert skipped == 0
    splines = [e for e in loaded.all_entities() if isinstance(e, Spline)]
    assert len(splines) == 2
    assert any(s.closed for s in splines)
    assert any(not s.closed for s in splines)
    open_spline = next(s for s in splines if not s.closed)
    assert [p.as_tuple() for p in open_spline.points] == [(0, 0), (5, 5), (10, 0)]


# ---------------------------------------------------------------------- #
# BOUNDARY
# ---------------------------------------------------------------------- #
def test_boundary_from_closed_polyline_makes_independent_copy():
    interp, doc = make_interpreter()
    original = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    )
    interp.start("BO")
    interp.submit_point(Point(5, 5))
    assert not interp.active

    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert len(polys) == 2
    new_poly = next(p for p in polys if p.id != original.id)
    assert new_poly.closed
    assert [p.as_tuple() for p in new_poly.points] == [p.as_tuple() for p in original.points]


def test_boundary_from_circle_creates_polygon_approximation():
    interp, doc = make_interpreter()
    doc.add_entity(Circle(center=Point(0, 0), radius=5))
    interp.start("BOUNDARY")
    interp.submit_point(Point(0, 0))
    assert not interp.active

    poly = next(e for e in doc.all_entities() if isinstance(e, LWPolyline))
    assert poly.closed
    assert len(poly.points) == 64
    for p in poly.points:
        assert math.hypot(p.x, p.y) == pytest.approx(5)


def test_boundary_from_loose_lines_forming_rectangle():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    doc.add_entity(Line(start=Point(10, 0), end=Point(10, 10)))
    doc.add_entity(Line(start=Point(10, 10), end=Point(0, 10)))
    doc.add_entity(Line(start=Point(0, 10), end=Point(0, 0)))

    interp.start("BO")
    interp.submit_point(Point(5, 5))
    assert not interp.active

    poly = next(e for e in doc.all_entities() if isinstance(e, LWPolyline))
    assert poly.closed
    assert {p.as_tuple() for p in poly.points} == {(0, 0), (10, 0), (10, 10), (0, 10)}


def test_boundary_no_enclosing_shape_gives_info_message():
    interp, doc = make_interpreter()
    interp.start("BO")
    interp.submit_point(Point(5, 5))
    assert not interp.active
    assert any("nenhum contorno fechado" in line.lower() for line in interp.log)
    assert len(doc.all_entities()) == 0


# ---------------------------------------------------------------------- #
# PEDIT
# ---------------------------------------------------------------------- #
def test_pedit_close_sets_closed_true():
    interp, doc = make_interpreter()
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(1, 0), Point(1, 1)], closed=False))
    interp.start("PE")
    interp.context.selection.add(poly.id)
    interp.submit_text("")
    interp.submit_text("Close")
    interp.submit_text("eXit")
    assert not interp.active
    assert poly.closed


def test_pedit_add_vertex_appends_point():
    interp, doc = make_interpreter()
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(1, 0)], closed=False))
    interp.start("PEDIT")
    interp.context.selection.add(poly.id)
    interp.submit_text("")
    interp.submit_text("Add vertex")
    interp.submit_point(Point(2, 2))
    interp.submit_text("")  # Enter = eXit
    assert not interp.active
    assert [p.as_tuple() for p in poly.points] == [(0, 0), (1, 0), (2, 2)]


def test_pedit_remove_vertex_removes_nearest():
    interp, doc = make_interpreter()
    poly = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(1, 0), Point(2, 0)], closed=False)
    )
    interp.start("PE")
    interp.context.selection.add(poly.id)
    interp.submit_text("")
    interp.submit_text("Remove vertex")
    interp.submit_point(Point(0.9, 0.1))  # perto de (1, 0)
    interp.submit_text("")
    assert not interp.active
    assert [p.as_tuple() for p in poly.points] == [(0, 0), (2, 0)]


def test_pedit_no_polyline_selected_gives_info():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=1))
    interp.start("PE")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    assert not interp.active
    assert any("nenhuma polilinha selecionada" in line.lower() for line in interp.log)


# ---------------------------------------------------------------------- #
# HATCHEDIT
# ---------------------------------------------------------------------- #
def test_hatchedit_updates_angle_and_spacing():
    interp, doc = make_interpreter()
    hatch = doc.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])
    )
    interp.start("HE")
    interp.context.selection.add(hatch.id)
    interp.submit_text("")
    interp.submit_text("30")
    interp.submit_text("2.5")
    assert not interp.active
    assert hatch.angle == pytest.approx(math.radians(30))
    assert hatch.spacing == pytest.approx(2.5)


def test_hatchedit_enter_keeps_current_values():
    interp, doc = make_interpreter()
    hatch = doc.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])
    )
    original_angle, original_spacing = hatch.angle, hatch.spacing
    interp.start("HATCHEDIT")
    interp.context.selection.add(hatch.id)
    interp.submit_text("")
    interp.submit_text("")
    interp.submit_text("")
    assert not interp.active
    assert hatch.angle == original_angle
    assert hatch.spacing == original_spacing


def test_hatchedit_no_hatch_selected_gives_info():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    interp.start("HE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    assert not interp.active
    assert any("nenhuma hachura selecionada" in line_.lower() for line_ in interp.log)
