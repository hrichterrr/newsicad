import math

from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    interp = CommandInterpreter(doc, COMMAND_REGISTRY, ALIASES)
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
