"""Testes de newsicad/commands/utility_commands.py: AREA (AA), ID, DDEDIT
(ED) e PURGE (PU) — os "ganhos rápidos" incorporados do guia oficial de
atalhos do AutoCAD."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Circle, LWPolyline, Point, Text
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


def test_p_alias_resolves_to_pan():
    interp, _doc = make_interpreter()
    assert interp.resolve_command("P") == "PAN"


def test_id_command_reports_point_info():
    interp, _doc = make_interpreter()
    interp.start("ID")
    interp.submit_point(Point(12.5, -3.25))
    assert not interp.active
    assert "12.5000" in interp.log[-1]
    assert "-3.2500" in interp.log[-1]


def test_area_command_computes_closed_polyline_area_and_perimeter():
    interp, doc = make_interpreter()
    square = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    )
    interp.start("AA")
    interp.context.selection.add(square.id)
    interp.submit_text("")
    assert not interp.active
    assert "100.0000" in interp.log[-1]  # área do quadrado 10x10
    assert "40.0000" in interp.log[-1]  # perímetro


def test_area_command_computes_circle_area():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=5))
    interp.start("AA")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    assert not interp.active
    assert f"{math.pi * 25:.4f}" in interp.log[-1]


def test_area_command_ignores_unsupported_entities_and_reports_nothing_selected():
    from newsicad.core.entities import Line

    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("AA")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    assert not interp.active
    assert "AREA" in interp.log[-1]


def test_ed_command_edits_text_content():
    interp, doc = make_interpreter()
    text = doc.add_entity(Text(insertion_point=Point(0, 0), content="antes"))
    interp.start("ED")
    interp.context.selection.add(text.id)
    interp.submit_text("")
    interp.submit_text("depois")
    assert not interp.active
    assert text.content == "depois"


def test_ed_command_reports_when_no_text_selected():
    from newsicad.core.entities import Line

    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("ED")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    assert not interp.active
    assert "ED" in interp.log[-1]


def test_purge_command_removes_unused_layer_and_reports_it():
    interp, doc = make_interpreter()
    doc.add_layer("SEM_USO")
    interp.start("PU")
    assert not interp.active
    assert "SEM_USO" not in doc.layers
    assert "SEM_USO" in interp.log[-1]


def test_purge_command_reports_nothing_to_remove():
    interp, doc = make_interpreter()
    interp.start("PU")
    assert not interp.active
    assert "nada" in interp.log[-1].lower()
