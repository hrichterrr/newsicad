"""Testes dos comandos de anotação: MTEXT, DIMLINEAR, DIMALIGNED, DIMANGULAR,
DIMRADIUS, DIMDIAMETER, DIMSTYLE e HATCH — mesmo padrão de
tests/test_interpreter.py (aciona o CommandInterpreter de verdade em vez de
chamar a função geradora diretamente)."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Circle, Dimension, Hatch, LWPolyline, Point, Text
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ------------------------------------------------------------------ #
# MTEXT
# ------------------------------------------------------------------ #
def test_mtext_command_creates_text_entity():
    interp, doc = make_interpreter()
    interp.start("MTEXT")
    interp.submit_point(Point(1, 2))
    interp.submit_text("Hello NewSIcad")
    assert not interp.active
    texts = [e for e in doc.all_entities() if isinstance(e, Text)]
    assert len(texts) == 1
    assert texts[0].insertion_point.as_tuple() == (1, 2)
    assert texts[0].content == "Hello NewSIcad"
    assert texts[0].height > 0


def test_mtext_alias_t_works():
    interp, doc = make_interpreter()
    interp.start("T")
    interp.submit_point(Point(0, 0))
    interp.submit_text("linha1\nlinha2")
    texts = [e for e in doc.all_entities() if isinstance(e, Text)]
    assert len(texts) == 1
    assert "\n" in texts[0].content


def test_mtext_empty_content_creates_nothing():
    interp, doc = make_interpreter()
    interp.start("MT")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Enter sem digitar nada
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, Text)]


# ------------------------------------------------------------------ #
# DIMLINEAR / DIMALIGNED / DIMANGULAR
# ------------------------------------------------------------------ #
def test_dimlinear_command_creates_linear_dimension():
    interp, doc = make_interpreter()
    interp.start("DLI")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    interp.submit_point(Point(0, 5))
    assert not interp.active
    dims = [e for e in doc.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1
    assert dims[0].kind == "linear"
    assert dims[0].measurement() == pytest.approx(10.0)
    assert any("Dimension text" in line for line in interp.log)


def test_dimlinear_vertical_measures_dy():
    interp, doc = make_interpreter()
    interp.start("DLI")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(1, 10))  # dy(10) > dx(1) -> mede vertical
    interp.submit_point(Point(5, 0))
    dim = doc.all_entities()[0]
    assert dim.measurement() == pytest.approx(10.0)


def test_dimaligned_command_measures_full_distance():
    interp, doc = make_interpreter()
    interp.start("DAL")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(3, 4))
    interp.submit_point(Point(1, 1))
    dims = [e for e in doc.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1
    assert dims[0].kind == "aligned"
    assert dims[0].measurement() == pytest.approx(5.0)


def test_dimangular_command_measures_angle_between_rays():
    interp, doc = make_interpreter()
    interp.start("DAN")
    interp.submit_point(Point(0, 0))  # vértice
    interp.submit_point(Point(10, 0))  # primeiro raio
    interp.submit_point(Point(0, 10))  # segundo raio
    interp.submit_point(Point(5, 5))  # posição do arco
    dims = [e for e in doc.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1
    assert dims[0].kind == "angular"
    assert dims[0].measurement() == pytest.approx(90.0)


# ------------------------------------------------------------------ #
# DIMRADIUS / DIMDIAMETER
# ------------------------------------------------------------------ #
def test_dimradius_command_uses_selected_circle():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=5.0))
    interp.start("DRA")
    interp.context.selection.add(circle.id)
    interp.submit_text("")  # confirma seleção
    interp.submit_point(Point(4, 4))
    assert not interp.active
    dims = [e for e in doc.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1
    assert dims[0].kind == "radius"
    assert dims[0].center.as_tuple() == (0, 0)
    assert dims[0].radius == 5.0
    assert dims[0].measurement_text() == "R5.00"


def test_dimdiameter_command_uses_selected_circle():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(1, 1), radius=3.0))
    interp.start("DDI")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    interp.submit_point(Point(4, 4))
    dims = [e for e in doc.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1
    assert dims[0].kind == "diameter"
    assert dims[0].measurement() == pytest.approx(6.0)


def test_dimradius_no_circle_selected_creates_nothing():
    interp, doc = make_interpreter()
    interp.start("DRA")
    interp.submit_text("")  # Enter sem selecionar nada
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, Dimension)]


# ------------------------------------------------------------------ #
# DIMSTYLE
# ------------------------------------------------------------------ #
def test_dimstyle_command_is_informational_only():
    interp, doc = make_interpreter()
    interp.start("D")
    assert not interp.active
    assert not doc.all_entities()
    assert any("estilo" in line.lower() for line in interp.log)


# ------------------------------------------------------------------ #
# HATCH
# ------------------------------------------------------------------ #
def test_hatch_command_with_closed_polyline_boundary():
    interp, doc = make_interpreter()
    boundary = doc.add_entity(
        LWPolyline(
            points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
            closed=True,
        )
    )
    interp.start("H")
    interp.context.selection.add(boundary.id)
    interp.submit_text("")
    assert not interp.active
    hatches = [e for e in doc.all_entities() if isinstance(e, Hatch)]
    assert len(hatches) == 1
    assert len(hatches[0].boundary_points) == 4


def test_hatch_command_open_polyline_is_rejected():
    interp, doc = make_interpreter()
    boundary = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)], closed=False)
    )
    interp.start("HATCH")
    interp.context.selection.add(boundary.id)
    interp.submit_text("")
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, Hatch)]
    assert any("LWPolyline fechada" in line for line in interp.log)


# ------------------------------------------------------------------ #
# LEADER (prioridade 4 — reusa LWPolyline + Text)
# ------------------------------------------------------------------ #
def test_leader_command_creates_polyline_and_text():
    interp, doc = make_interpreter()
    interp.start("LEADER")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_text("")  # termina a linha do leader
    interp.submit_text("Nota importante")
    assert not interp.active
    polys = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    texts = [e for e in doc.all_entities() if isinstance(e, Text)]
    assert len(polys) == 1
    assert [p.as_tuple() for p in polys[0].points] == [(0, 0), (5, 5)]
    assert len(texts) == 1
    assert texts[0].content == "Nota importante"
    assert texts[0].insertion_point.as_tuple() == (5, 5)


def test_leader_alias_le_works_and_empty_text_still_keeps_line():
    interp, doc = make_interpreter()
    interp.start("LE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(1, 1))
    interp.submit_text("")
    interp.submit_text("")  # sem anotação
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, LWPolyline)]) == 1
    assert not [e for e in doc.all_entities() if isinstance(e, Text)]


def test_leader_single_point_creates_nothing():
    interp, doc = make_interpreter()
    interp.start("LEADER")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Enter direto: só 1 ponto, não é um leader válido
    assert not interp.active
    assert not doc.all_entities()
