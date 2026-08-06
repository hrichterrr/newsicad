"""Testes dos comandos BLOCK/INSERT (newsicad/commands/block_commands.py):
criação de definição com coordenadas relativas ao ponto base, consumo das
entidades originais, e criação de BlockReference via INSERT (com validação
do nome do bloco e defaults de escala/rotação)."""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Circle, Line, Point
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


def test_block_command_creates_definition_and_consumes_selection():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))

    interp.start("B")
    interp.submit_text("MYBLOCK")
    interp.submit_point(Point(0, 0))
    interp.context.selection.add(line.id)
    interp.submit_text("")  # confirma seleção

    assert not interp.active
    assert "MYBLOCK" in doc.block_definitions
    assert doc.get_entity(line.id) is None  # BLOCK "consome" o original

    refs = [e for e in doc.all_entities() if isinstance(e, BlockReference)]
    assert len(refs) == 1
    assert refs[0].block_name == "MYBLOCK"
    assert refs[0].insertion_point.as_tuple() == (0, 0)


def test_block_command_definition_coords_relative_to_base_point():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(10, 10), end=Point(15, 10)))

    interp.start("BLOCK")
    interp.submit_text("OFFSETBLOCK")
    interp.submit_point(Point(10, 10))
    interp.context.selection.add(line.id)
    interp.submit_text("")

    assert not interp.active
    def_line = doc.block_definitions["OFFSETBLOCK"][0]
    assert def_line.start.as_tuple() == (0, 0)
    assert def_line.end.as_tuple() == (5, 0)


def test_block_command_no_selection_cancels_without_consuming_entities():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))

    interp.start("B")
    interp.submit_text("EMPTYBLOCK")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Enter sem selecionar nada

    assert not interp.active
    assert "EMPTYBLOCK" not in doc.block_definitions
    assert doc.get_entity(line.id) is not None


def test_block_command_empty_name_cancels():
    interp, doc = make_interpreter()
    interp.start("B")
    interp.submit_text("")  # Enter em branco no nome
    assert not interp.active
    assert doc.block_definitions == {}


def test_insert_command_creates_reference_with_defaults():
    interp, doc = make_interpreter()
    doc.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 1))])

    interp.start("I")
    interp.submit_text("CHAIR")
    interp.submit_point(Point(5, 5))
    interp.submit_text("")  # scale default <1>
    interp.submit_text("")  # rotation default <0>

    assert not interp.active
    refs = [e for e in doc.all_entities() if isinstance(e, BlockReference)]
    assert len(refs) == 1
    assert refs[0].block_name == "CHAIR"
    assert refs[0].insertion_point.as_tuple() == (5, 5)
    assert refs[0].scale == 1.0
    assert refs[0].rotation == 0.0


def test_insert_command_reprompts_on_unknown_block_name():
    interp, doc = make_interpreter()
    doc.define_block("CHAIR", [Circle(center=Point(0, 0), radius=1)])

    interp.start("INSERT")
    interp.submit_text("NOPE")  # nome inexistente
    assert interp.active  # continua pedindo um nome válido, não cancela

    interp.submit_text("CHAIR")
    interp.submit_point(Point(0, 0))
    interp.submit_text("2")
    interp.submit_text("90")

    assert not interp.active
    refs = [e for e in doc.all_entities() if isinstance(e, BlockReference)]
    assert len(refs) == 1
    assert refs[0].scale == 2.0
    assert refs[0].rotation == pytest.approx(math.radians(90))


def test_insert_command_empty_name_cancels():
    interp, doc = make_interpreter()
    interp.start("I")
    interp.submit_text("")
    assert not interp.active
    assert doc.all_entities() == []
