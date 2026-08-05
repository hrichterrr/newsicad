import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Ellipse, Line, LWPolyline, Point
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


def test_line_command_two_segments_then_enter():
    interp, doc = make_interpreter()
    interp.start("LINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_text("")  # Enter termina o comando
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    assert lines[0].start.as_tuple() == (0, 0)
    assert lines[0].end.as_tuple() == (10, 0)
    assert lines[1].end.as_tuple() == (10, 10)


def test_line_command_via_command_line_coords():
    interp, doc = make_interpreter()
    interp.start("L")  # alias
    interp.submit_text("0,0")
    interp.submit_text("@10,0")
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert lines[0].end.as_tuple() == (10, 0)


def test_circle_command():
    interp, doc = make_interpreter()
    interp.start("C")
    interp.submit_point(Point(5, 5))
    interp.submit_text("10")
    assert not interp.active
    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 1
    assert circles[0].center.as_tuple() == (5, 5)
    assert circles[0].radius == 10


def test_rectangle_command_creates_closed_polyline():
    interp, doc = make_interpreter()
    interp.start("REC")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 5))
    assert not interp.active
    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert len(polys) == 1
    assert polys[0].closed
    assert len(polys[0].points) == 4


def test_arc_command_through_3_points():
    interp, doc = make_interpreter()
    interp.start("A")
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(0, 10))
    interp.submit_point(Point(-10, 0))
    assert not interp.active
    arcs = [e for e in doc.all_entities() if isinstance(e, Arc)]
    assert len(arcs) == 1
    arc = arcs[0]
    assert arc.center.as_tuple() == (0, 0) or (
        abs(arc.center.x) < 1e-6 and abs(arc.center.y) < 1e-6
    )
    assert arc.radius == 10


def test_circle_radius_via_canvas_click_computes_distance():
    """Clique no canvas durante 'Specify radius' deve virar distância, não um Point bruto."""
    interp, doc = make_interpreter()
    interp.start("C")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(3, 4))  # clique a 5 unidades do centro
    assert not interp.active
    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 1
    assert isinstance(circles[0].radius, float)
    assert circles[0].radius == 5.0


def test_unknown_command_logs_error():
    interp, doc = make_interpreter()
    result = interp.start("BOGUS")
    assert result is None
    assert not interp.active
    assert any("desconhecido" in line for line in interp.log)


def test_pline_undo_removes_last_point():
    interp, doc = make_interpreter()
    interp.start("PL")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_text("undo")
    interp.submit_point(Point(0, 10))
    interp.submit_text("")
    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert len(polys) == 1
    assert [p.as_tuple() for p in polys[0].points] == [(0, 0), (0, 10)]


def test_ellipse_command():
    interp, doc = make_interpreter()
    interp.start("EL")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_text("5")
    assert not interp.active
    ellipses = [e for e in doc.all_entities() if isinstance(e, Ellipse)]
    assert len(ellipses) == 1
    assert ellipses[0].radius_major == pytest.approx(10)
    assert ellipses[0].radius_minor == pytest.approx(5)


def test_dist_command_logs_result_and_ends_without_waiting():
    interp, doc = make_interpreter()
    interp.start("DI")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(3, 4))
    assert not interp.active
    assert any("Distância = 5.0000" in line for line in interp.log)


def test_planned_command_gives_friendly_message():
    interp, doc = make_interpreter()
    result = interp.start("TR")  # TRIM: reconhecido, ainda não implementado
    assert result is None
    assert not interp.active
    assert any("reconhecido" in line and "TRIM" in line for line in interp.log)


def test_erase_command_removes_selected_entities():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    interp.start("E")
    interp.context.selection.add(line.id)
    interp.submit_text("")  # confirma seleção
    assert not interp.active
    assert doc.get_entity(line.id) is None


def test_erase_with_no_selection_does_nothing():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    interp.start("E")
    interp.submit_text("")  # Enter sem selecionar nada
    assert not interp.active
    assert doc.get_entity(line.id) is not None


def test_move_command_translates_selected_entity():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    interp.start("M")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    assert not interp.active
    assert line.start.as_tuple() == (5, 5)
    assert line.end.as_tuple() == (6, 6)


def test_copy_command_leaves_original_and_adds_clone():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    interp.start("CO")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 0))
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    assert line.start.as_tuple() == (0, 0)  # original intacto
    clone = next(e for e in lines if e.id != line.id)
    assert clone.start.as_tuple() == (5, 0)


def test_rotate_command_rotates_selected_entity():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(1, 0), radius=1))
    interp.start("RO")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_text("90")
    assert not interp.active
    assert circle.center.x == pytest.approx(0, abs=1e-9)
    assert circle.center.y == pytest.approx(1)


def test_scale_command_scales_selected_entity():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=2))
    interp.start("SC")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_text("3")
    assert not interp.active
    assert circle.radius == pytest.approx(6)


def test_mirror_command_default_keeps_source():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(1, 0), end=Point(2, 0)))
    interp.start("MI")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 1))
    interp.submit_text("")  # Enter = default No (mantém original)
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2  # original + espelhada
    assert doc.get_entity(line.id) is not None


def test_mirror_command_yes_deletes_source():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(1, 0), end=Point(2, 0)))
    interp.start("MI")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 1))
    interp.submit_text("yes")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert doc.get_entity(line.id) is None
