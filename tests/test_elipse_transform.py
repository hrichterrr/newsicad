"""Elipse participa das transformações, e a seleção é tudo ou nada.

Auditoria de 2026-09-07: `translate/rotate/scale/mirror_entity` não tinham
ramo para `Ellipse` e caíam no `raise TypeError` final. Como MOVE/COPY/ROTATE/
SCALE/MIRROR percorrem a seleção num laço, a exceção interrompia no meio —
parte dos objetos já tinha se movido, o resto ficava para trás, e a divisão
mudava a cada execução (a ordem vem de um `set`). As plantas reais têm de 85 a
327 elipses cada.
"""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Ellipse, Line, Point
from newsicad.core.geometry_ops import (
    mirror_entity,
    rotate_entity,
    scale_entity,
    translate_entity,
)
from newsicad.core.selection import Selection


def _interp():
    doc = Document()
    return CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES), doc


def _elipse():
    return Ellipse(center=Point(10, 5), radius_major=4, radius_minor=2, rotation=0.0)


def test_translate_move_o_centro():
    e = _elipse()
    translate_entity(e, 3, -2)
    assert (e.center.x, e.center.y) == (13, 3)
    assert (e.radius_major, e.radius_minor) == (4, 2)


def test_rotate_gira_centro_e_inclinacao():
    e = _elipse()
    rotate_entity(e, Point(0, 0), math.pi / 2)
    assert e.center.x == pytest.approx(-5) and e.center.y == pytest.approx(10)
    assert e.rotation == pytest.approx(math.pi / 2)


def test_scale_escala_centro_e_os_dois_raios():
    e = _elipse()
    scale_entity(e, Point(0, 0), 2.0)
    assert (e.center.x, e.center.y) == (20, 10)
    assert (e.radius_major, e.radius_minor) == (8, 4)


def test_mirror_reflete_centro_e_inclinacao():
    e = Ellipse(center=Point(4, 3), radius_major=4, radius_minor=2, rotation=math.radians(30))
    m = mirror_entity(e, Point(0, 0), Point(1, 0))  # espelho no eixo X
    assert m.center.x == pytest.approx(4) and m.center.y == pytest.approx(-3)
    assert m.rotation == pytest.approx(math.radians(330))
    assert e.center.y == 3  # o original não muda


def test_move_com_elipse_na_selecao_move_a_selecao_INTEIRA():
    interp, doc = _interp()
    elipse = doc.add_entity(_elipse())
    linhas = [doc.add_entity(Line(start=Point(i, 0), end=Point(i, 1))) for i in range(8)]

    interp.start("MOVE")
    for e in [elipse, *linhas]:
        interp.context.selection.add(e.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(100, 100))

    assert not interp.active
    assert elipse.center.x == pytest.approx(110) and elipse.center.y == pytest.approx(105)
    assert all(l.start.x >= 100 for l in linhas), "seleção foi movida pela metade"
    assert not any("erro inesperado" in linha for linha in interp.log), interp.log


def test_selecao_com_tipo_nao_transformavel_nao_move_nada():
    """Rede de segurança: se um tipo novo não tiver ramo, o comando recusa
    ANTES de mexer, em vez de aplicar pela metade."""
    from newsicad.core.entities import Entity

    class TipoNovo(Entity):
        pass

    interp, doc = _interp()
    linhas = [doc.add_entity(Line(start=Point(i, 0), end=Point(i, 1))) for i in range(5)]
    exotico = doc.add_entity(TipoNovo())

    interp.start("MOVE")
    for e in [exotico, *linhas]:
        interp.context.selection.add(e.id)
    interp.submit_text("")
    assert not interp.active
    assert all(l.start.x == i for i, l in enumerate(linhas)), "moveu apesar do tipo não suportado"
    assert any("não transforma" in linha for linha in interp.log), interp.log
