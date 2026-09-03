"""Testes dos comandos "planejados" do catálogo AutoCAD (artifact do redesign
de UI, 2026-08-22): REVCLOUD, WIPEOUT, LAYMCH, LAYISO/LAYUNISO, QSELECT,
CENTERMARK e DIMBREAK."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Dimension, Hatch, Line, Point
from newsicad.core.geometry_ops import dimension_line_segment, split_segment_with_gaps
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# REVCLOUD
# ---------------------------------------------------------------------- #
def test_revcloud_creates_one_arc_per_edge_closing_the_loop():
    interp, doc = make_interpreter()
    interp.start("REVCLOUD")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_text("")  # Enter fecha
    assert not interp.active

    arcs = [e for e in doc.all_entities() if isinstance(e, Arc)]
    assert len(arcs) == 3  # (0,0)-(10,0), (10,0)-(10,10), (10,10)-(0,0)


def test_revcloud_needs_at_least_two_points():
    interp, doc = make_interpreter()
    interp.start("REVCLOUD")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")
    assert not interp.active
    assert not doc.all_entities()


# ---------------------------------------------------------------------- #
# WIPEOUT
# ---------------------------------------------------------------------- #
def test_wipeout_creates_solid_fill_hatch():
    interp, doc = make_interpreter()
    interp.start("WIPEOUT")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_text("")
    assert not interp.active

    hatches = [e for e in doc.all_entities() if isinstance(e, Hatch)]
    assert len(hatches) == 1
    assert hatches[0].solid_fill is True
    assert len(hatches[0].boundary_points) == 3


def test_wipeout_needs_at_least_three_points():
    interp, doc = make_interpreter()
    interp.start("WIPEOUT")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_text("")
    assert not interp.active
    assert not doc.all_entities()


def test_wipeout_dxf_roundtrip_preserves_solid_fill(tmp_path):
    from newsicad.io.dxf_io import load_dxf, save_dxf

    doc = Document()
    doc.add_entity(Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10)], solid_fill=True))
    path = tmp_path / "wipeout.dxf"
    save_dxf(doc, path)
    reloaded, skipped = load_dxf(path)
    assert skipped == 0
    hatch = next(e for e in reloaded.all_entities() if isinstance(e, Hatch))
    assert hatch.solid_fill is True


# ---------------------------------------------------------------------- #
# LAYMCH
# ---------------------------------------------------------------------- #
def test_laymch_moves_targets_to_source_layer():
    interp, doc = make_interpreter()
    doc.add_layer("PAREDES")
    source = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1), layer="PAREDES"))
    target = doc.add_entity(Line(start=Point(5, 5), end=Point(6, 6), layer="0"))

    interp.start("LAYMCH")
    interp.context.selection.add(source.id)
    interp.submit_text("")
    interp.context.selection.set({target.id})
    interp.submit_text("")
    assert not interp.active
    assert target.layer == "PAREDES"


# ---------------------------------------------------------------------- #
# LAYISO / LAYUNISO
# ---------------------------------------------------------------------- #
def test_layiso_hides_other_layers_and_layuniso_restores():
    interp, doc = make_interpreter()
    doc.add_layer("PAREDES")
    doc.add_layer("COTAS")
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1), layer="PAREDES"))

    interp.start("LAYISO")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    assert not interp.active
    assert doc.layers["PAREDES"].visible is True
    assert doc.layers["COTAS"].visible is False
    assert doc.layers["0"].visible is False

    interp.start("LAYUNISO")
    assert not interp.active
    assert doc.layers["COTAS"].visible is True
    assert doc.layers["0"].visible is True


def test_layuniso_with_nothing_isolated_gives_info_message():
    interp, doc = make_interpreter()
    interp.start("LAYUNISO")
    assert not interp.active
    assert any("nenhum isolamento" in line.lower() for line in interp.log)


# ---------------------------------------------------------------------- #
# QSELECT
# ---------------------------------------------------------------------- #
def test_qselect_selects_all_of_given_type():
    interp, doc = make_interpreter()
    line1 = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    line2 = doc.add_entity(Line(start=Point(2, 2), end=Point(3, 3)))
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=5))

    interp.start("QSELECT")
    interp.submit_text("LINE")
    assert not interp.active
    assert interp.context.selection.ids == {line1.id, line2.id}
    assert circle.id not in interp.context.selection.ids


def test_qselect_unknown_type_gives_info_message():
    interp, doc = make_interpreter()
    interp.start("QSELECT")
    interp.submit_text("BANANA")
    assert not interp.active
    assert any("desconhecido" in line.lower() for line in interp.log)


# ---------------------------------------------------------------------- #
# CENTERMARK
# ---------------------------------------------------------------------- #
def test_centermark_adds_cross_lines_at_circle_center():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(10, 10), radius=5))

    interp.start("CENTERMARK")
    interp.submit_point(Point(15, 10))  # ponto na borda do círculo
    interp.submit_text("")
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2
    for line in lines:
        mid = Point((line.start.x + line.end.x) / 2, (line.start.y + line.end.y) / 2)
        assert mid.x == pytest.approx(10)
        assert mid.y == pytest.approx(10)


def test_centermark_rejects_non_circle_arc():
    interp, doc = make_interpreter()
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("CENTERMARK")
    interp.submit_point(Point(5, 0))
    interp.submit_text("")
    assert not interp.active
    assert len(doc.all_entities()) == 1  # só a Line original, nenhuma cruz adicionada


# ---------------------------------------------------------------------- #
# DIMBREAK
# ---------------------------------------------------------------------- #
def test_dimbreak_adds_break_points_from_crossing_object():
    interp, doc = make_interpreter()
    dim = doc.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 5))
    )
    crosser = doc.add_entity(Line(start=Point(5, -5), end=Point(5, 15)))

    interp.start("DIMBREAK")
    interp.context.selection.add(dim.id)
    interp.submit_text("")
    interp.context.selection.set({crosser.id})
    interp.submit_text("")
    assert not interp.active

    assert len(dim.break_points) == 1
    assert dim.break_points[0].x == pytest.approx(5)
    assert dim.break_points[0].y == pytest.approx(5)


def test_dimbreak_rejects_non_linear_aligned_dimension():
    interp, doc = make_interpreter()
    dim = doc.add_entity(Dimension(kind="radius", center=Point(0, 0), radius=5, leader_point=Point(5, 5)))
    interp.start("DIMBREAK")
    interp.context.selection.add(dim.id)
    interp.submit_text("")
    assert not interp.active
    assert any("linear/aligned" in line.lower() for line in interp.log)


def test_split_segment_with_gaps_creates_two_pieces_around_one_break():
    a, b = Point(0, 0), Point(10, 0)
    pieces = split_segment_with_gaps(a, b, [Point(5, 0)], gap=1.0)
    assert len(pieces) == 2
    assert pieces[0][1].x == pytest.approx(4.0)
    assert pieces[1][0].x == pytest.approx(6.0)


def test_split_segment_with_gaps_merges_overlapping_breaks():
    a, b = Point(0, 0), Point(10, 0)
    pieces = split_segment_with_gaps(a, b, [Point(4, 0), Point(5, 0)], gap=1.0)
    assert len(pieces) == 2
    assert pieces[0][1].x == pytest.approx(3.0)
    assert pieces[1][0].x == pytest.approx(6.0)


def test_dimension_line_segment_none_for_radius():
    dim = Dimension(kind="radius", center=Point(0, 0), radius=5, leader_point=Point(5, 5))
    assert dimension_line_segment(dim) is None
