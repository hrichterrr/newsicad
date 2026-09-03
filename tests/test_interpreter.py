import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Ellipse, Line, LWPolyline, Point, PointEntity
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
    # REGION continua reconhecido-mas-não-implementado nesta versão (ver
    # newsicad/commands/registry.py PLANNED_COMMANDS) — TRIM, ALIGN,
    # BOUNDARY e (mais recentemente) TABLE foram implementados, ver
    # test_trim_* abaixo, tests/test_new_commands.py e
    # tests/test_marco_c_commands.py.
    interp, doc = make_interpreter()
    result = interp.start("REGION")  # REGION: reconhecido, ainda não implementado
    assert result is None
    assert not interp.active
    assert any("reconhecido" in line and "REGION" in line for line in interp.log)


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
    # a cópia espelhada precisa de um id próprio: se herdasse o id do
    # original (bug de clone_entity via deepcopy preservando o id), o
    # add_entity subsequente sobrescreveria o original no dict por id.
    mirrored = next(e for e in lines if e.id != line.id)
    assert mirrored.id != line.id
    assert doc.get_entity(mirrored.id) is mirrored


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


# ---------------------------------------------------------------------- #
# TRIM
# ---------------------------------------------------------------------- #
def test_trim_line_against_cutting_edge_shortens_it():
    interp, doc = make_interpreter()
    target = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    cutter = doc.add_entity(Line(start=Point(5, -5), end=Point(5, 5)))
    interp.start("TR")
    interp.context.selection.add(cutter.id)
    interp.submit_text("")  # confirma seleção das cutting edges
    interp.submit_point(Point(8, 0))  # clica no lado direito do alvo
    interp.submit_text("")  # Enter termina o TRIM
    assert not interp.active
    assert target.start.as_tuple() == (0, 0)
    assert target.end.as_tuple() == pytest.approx((5, 0))


def test_trim_line_between_two_cutters_splits_into_two():
    interp, doc = make_interpreter()
    target = doc.add_entity(Line(start=Point(0, 0), end=Point(20, 0)))
    left_cutter = doc.add_entity(Line(start=Point(5, -5), end=Point(5, 5)))
    right_cutter = doc.add_entity(Line(start=Point(15, -5), end=Point(15, 5)))
    interp.start("TR")
    interp.context.selection.set({left_cutter.id, right_cutter.id})
    interp.submit_text("")
    interp.submit_point(Point(10, 0))  # clica entre os dois cutters
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line) and e.id not in (left_cutter.id, right_cutter.id)]
    assert len(lines) == 2
    ends = sorted(l.end.x if l.start.x < l.end.x else l.start.x for l in lines)
    assert ends == [pytest.approx(5), pytest.approx(20)]


def test_trim_no_intersection_logs_message_without_crashing():
    interp, doc = make_interpreter()
    target = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    cutter = doc.add_entity(Line(start=Point(50, -5), end=Point(50, 5)))
    interp.start("TR")
    interp.context.selection.add(cutter.id)
    interp.submit_text("")
    interp.submit_point(Point(5, 0))
    assert interp.active  # continua esperando outro clique, não crasha
    assert any("Nenhuma interseção" in line for line in interp.log)
    interp.submit_text("")


# ---------------------------------------------------------------------- #
# EXTEND
# ---------------------------------------------------------------------- #
def test_extend_line_to_boundary():
    interp, doc = make_interpreter()
    target = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))
    boundary = doc.add_entity(Line(start=Point(10, -5), end=Point(10, 5)))
    interp.start("EX")
    interp.context.selection.add(boundary.id)
    interp.submit_text("")
    interp.submit_point(Point(4, 0))  # clica perto da ponta que deve se mover
    interp.submit_text("")
    assert not interp.active
    assert target.end.as_tuple() == pytest.approx((10, 0))
    assert target.start.as_tuple() == (0, 0)


# ---------------------------------------------------------------------- #
# OFFSET
# ---------------------------------------------------------------------- #
def test_offset_line_creates_parallel_copy():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("O")
    interp.submit_text("2")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    new_line = next(l for l in lines if l.id != line.id)
    assert new_line.start.y == pytest.approx(2)


def test_offset_circle_creates_larger_circle():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=5))
    interp.start("O")
    interp.submit_text("2")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(20, 0))
    interp.submit_text("")
    assert not interp.active
    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 2
    new_circle = next(c for c in circles if c.id != circle.id)
    assert new_circle.radius == pytest.approx(7)


# ---------------------------------------------------------------------- #
# FILLET / CHAMFER
# ---------------------------------------------------------------------- #
def test_fillet_command_requires_radius_before_selecting():
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    line2 = doc.add_entity(Line(start=Point(10, 0), end=Point(10, 10)))
    interp.start("F")
    interp.submit_point(Point(5, 0))  # sem ter setado raio ainda
    assert not interp.active
    assert any("raio" in line.lower() for line in interp.log)
    arcs = [e for e in doc.all_entities() if isinstance(e, Arc)]
    assert len(arcs) == 0


def test_fillet_command_full_flow_with_radius_option():
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    line2 = doc.add_entity(Line(start=Point(10, 0), end=Point(10, 10)))
    interp.start("F")
    interp.submit_text("radius")
    interp.submit_text("2")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(10, 5))
    assert not interp.active
    arcs = [e for e in doc.all_entities() if isinstance(e, Arc)]
    assert len(arcs) == 1
    assert arcs[0].radius == pytest.approx(2)
    assert line1.end.x == pytest.approx(8)


def test_chamfer_command_full_flow_with_distance_option():
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    line2 = doc.add_entity(Line(start=Point(10, 0), end=Point(10, 10)))
    interp.start("CHA")
    interp.submit_text("distance")
    interp.submit_text("2")
    interp.submit_text("3")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(10, 5))
    assert not interp.active
    chamfer_lines_found = [e for e in doc.all_entities() if isinstance(e, Line) and e.id not in (line1.id, line2.id)]
    assert len(chamfer_lines_found) == 1
    assert line1.end.x == pytest.approx(8)
    assert line2.start.y == pytest.approx(3)


# ---------------------------------------------------------------------- #
# JOIN
# ---------------------------------------------------------------------- #
def test_join_collinear_connected_lines():
    interp, doc = make_interpreter()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))
    b = doc.add_entity(Line(start=Point(5, 0), end=Point(10, 0)))
    interp.start("J")
    interp.context.selection.set({a.id, b.id})
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    survivor = lines[0]
    ends = sorted([survivor.start.x, survivor.end.x])
    assert ends == [pytest.approx(0), pytest.approx(10)]


def test_join_non_collinear_lines_does_nothing():
    interp, doc = make_interpreter()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))
    b = doc.add_entity(Line(start=Point(0, 0), end=Point(0, 5)))
    interp.start("J")
    interp.context.selection.set({a.id, b.id})
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2


# ---------------------------------------------------------------------- #
# EXPLODE
# ---------------------------------------------------------------------- #
def test_explode_polyline_creates_individual_lines():
    interp, doc = make_interpreter()
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)]))
    interp.start("X")
    interp.context.selection.add(poly.id)
    interp.submit_text("")
    assert not interp.active
    assert doc.get_entity(poly.id) is None
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2


# ---------------------------------------------------------------------- #
# STRETCH
# ---------------------------------------------------------------------- #
def test_stretch_moves_only_vertex_inside_crossing_window():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("S")
    interp.submit_point(Point(-5, -5))  # primeiro canto da janela
    interp.submit_point(Point(5, 5))  # segundo canto (só pega o start, x=0)
    interp.submit_point(Point(0, 0))  # base point
    interp.submit_point(Point(0, 10))  # second point (dx=0, dy=10)
    assert not interp.active
    assert line.start.as_tuple() == (0, 10)
    assert line.end.as_tuple() == (10, 0)  # fora da janela, não se move


# ---------------------------------------------------------------------- #
# DIVIDE / MEASURE
# ---------------------------------------------------------------------- #
def test_divide_line_into_n_segments_creates_n_minus_1_markers():
    # Desde o comando POINT existir (marco B, 2026-08-22), DIVIDE cria
    # PointEntity de verdade em vez do Circle minúsculo usado antes — ver
    # tests/test_marco_b_commands.py para a cobertura completa desse marco.
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("DIV")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("4")
    assert not interp.active
    markers = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(markers) == 3
    xs = sorted(m.location.x for m in markers)
    assert xs == [pytest.approx(2.5), pytest.approx(5.0), pytest.approx(7.5)]


def test_measure_line_by_fixed_length():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("ME")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("3")
    assert not interp.active
    markers = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(markers) == 3  # em x=3,6,9 (10//3=3 marcadores)
    xs = sorted(m.location.x for m in markers)
    assert xs == [pytest.approx(3), pytest.approx(6), pytest.approx(9)]


# ---------------------------------------------------------------------- #
# comandos de desenho respeitam a camada atual (document.current_layer) —
# regressão: até pouco tempo atrás, LINE/CIRCLE/ARC/etc. sempre criavam a
# entidade sem passar `layer=`, e como o default do dataclass Entity.layer
# é "0" (não vazio), o fallback de Document.add_entity pro current_layer
# nunca disparava — toda entidade nova ia parar em "0" mesmo com uma outra
# camada selecionada como atual.
# ---------------------------------------------------------------------- #
def test_line_command_lands_on_current_layer():
    interp, doc = make_interpreter()
    doc.add_layer("ELETRICA")
    doc.set_current_layer("ELETRICA")

    interp.start("LINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_text("")

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert lines[0].layer == "ELETRICA"


def test_circle_command_lands_on_current_layer():
    interp, doc = make_interpreter()
    doc.add_layer("ELETRICA")
    doc.set_current_layer("ELETRICA")

    interp.start("CIRCLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("5")

    circles = [e for e in doc.all_entities() if isinstance(e, Circle)]
    assert len(circles) == 1
    assert circles[0].layer == "ELETRICA"
