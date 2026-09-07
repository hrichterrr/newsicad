"""Os defeitos menores da auditoria de 2026-09-07: geometria degenerada
aceita em silêncio, comandos que colapsam o desenho, pré-seleção descartada,
undo fantasma e tipos esquecidos no STRETCH.
"""

from __future__ import annotations

import math

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY, READ_ONLY_COMMANDS
from newsicad.core.document import Document
from newsicad.core.entities import Circle, Dimension, Ellipse, Line, LWPolyline, Point
from newsicad.core.selection import Selection


def _interp():
    doc = Document()
    return CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES), doc


# ---------------------------------------------------------------- geometria
@pytest.mark.parametrize("raio", ["0", "-5"])
def test_circle_recusa_raio_nao_positivo(raio):
    interp, doc = _interp()
    interp.start("CIRCLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text(raio)
    assert not interp.active
    assert not doc.all_entities()


def test_rectang_recusa_cantos_coincidentes():
    interp, doc = _interp()
    interp.start("RECTANG")
    interp.submit_point(Point(5, 5))
    interp.submit_point(Point(5, 5))
    assert not interp.active
    assert not doc.all_entities()


@pytest.mark.parametrize("lados", ["0", "-4", "1000000"])
def test_polygon_recusa_numero_de_lados_absurdo(lados):
    interp, doc = _interp()
    interp.start("POLYGON")
    interp.submit_text(lados)
    assert not interp.active
    assert not doc.all_entities()


def test_polygon_recusa_raio_nao_positivo():
    interp, doc = _interp()
    interp.start("POLYGON")
    interp.submit_text("6")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Inscribed
    interp.submit_text("0")
    assert not interp.active
    assert not doc.all_entities()


# ------------------------------------------------------------------ colapso
def test_align_com_destinos_coincidentes_nao_colapsa():
    interp, doc = _interp()
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("ALIGN")
    interp.context.selection.add(linha.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))   # src1
    interp.submit_point(Point(0, 0))   # dst1
    interp.submit_point(Point(10, 0))  # src2
    interp.submit_point(Point(0, 0))   # dst2 == dst1
    interp.submit_text("Yes")
    comprimento = linha.start.distance_to(linha.end)
    assert comprimento > 1e-6, "a geometria colapsou num ponto"


def test_array_polar_com_angulo_zero_e_recusado():
    interp, doc = _interp()
    linha = doc.add_entity(Line(start=Point(1, 0), end=Point(2, 0)))
    interp.start("ARRAY")
    interp.context.selection.add(linha.id)
    interp.submit_text("")
    interp.submit_text("Polar")
    interp.submit_point(Point(0, 0))
    interp.submit_text("6")
    interp.submit_text("0")
    assert not interp.active
    assert len(doc.all_entities()) == 1, "criou cópias empilhadas no mesmo lugar"


# -------------------------------------------------------------- pré-seleção
def test_move_usa_a_selecao_que_ja_existe():
    """É o que o menu de contexto faz: abre COM objetos selecionados."""
    interp, doc = _interp()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    b = doc.add_entity(Line(start=Point(0, 1), end=Point(1, 1)))
    interp.context.selection.set({a.id, b.id})

    interp.start("MOVE")
    assert interp.current_prompt.message.startswith("Specify base point")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 10))
    assert a.start.x == pytest.approx(10) and b.start.x == pytest.approx(10)


# ------------------------------------------------------------ undo fantasma
def test_dimstyle_nao_empilha_passo_de_undo():
    assert "DIMSTYLE" in READ_ONLY_COMMANDS


# ---------------------------------------------------------------- stretch
def test_stretch_leva_elipse_e_hachura_junto():
    interp, doc = _interp()
    elipse = doc.add_entity(Ellipse(center=Point(5, 5), radius_major=2, radius_minor=1))
    poly = doc.add_entity(LWPolyline(points=[Point(4, 4), Point(6, 4), Point(6, 6)], closed=True))
    fora = doc.add_entity(Circle(center=Point(100, 100), radius=1))

    interp.start("STRETCH")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 10))
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(20, 0))

    assert elipse.center.x == pytest.approx(25), "elipse ficou para trás"
    assert poly.points[0].x == pytest.approx(24)
    assert fora.center.x == pytest.approx(100)


# ---------------------------------------------------------------- dimbreak
def test_dimbreak_repetido_nao_acumula_pontos_iguais():
    """Rodar DIMBREAK duas vezes sobre a mesma cota e o mesmo objeto que a
    cruza empilhava o mesmo ponto de novo — a lista crescia sem fim e cada
    ponto repetido abria mais uma folga no mesmo lugar."""
    interp, doc = _interp()
    cota = doc.add_entity(
        Dimension(
            kind="linear",
            point1=Point(0, 0),
            point2=Point(10, 0),
            dim_line_point=Point(0, 5),
        )
    )
    cruza = doc.add_entity(Line(start=Point(5, -5), end=Point(5, 10)))

    def roda():
        interp.start("DIMBREAK")
        interp.context.selection.set({cota.id})
        interp.submit_text("")
        interp.context.selection.set({cruza.id})
        interp.submit_text("")

    roda()
    depois_da_primeira = list(cota.break_points)
    assert depois_da_primeira, "a primeira passada devia achar a interseção"

    roda()
    assert len(cota.break_points) == len(depois_da_primeira)
