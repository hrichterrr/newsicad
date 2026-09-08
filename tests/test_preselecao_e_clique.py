"""Dois atritos que a auditoria de 07/09/2026 com as amostras oficiais da
Autodesk expôs:

- treze comandos jogavam fora a seleção que o usuário tinha acabado de fazer
  e voltavam a pedir "Select objects" — inclusive quando chamados pelo menu
  de contexto, que só abre COM objetos selecionados;
- clicar no canvas durante um prompt que pede PALAVRA mandava o objeto Point
  para dentro do comando: o FIELD morria com erro de Python na tela e o MTEXT
  escrevia "Point(x=105, y=105)" na prancha.
"""

from __future__ import annotations

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Dimension, Line, Point, Text
from newsicad.core.selection import Selection


def _cena():
    doc = Document()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    b = doc.add_entity(Line(start=Point(0, 5), end=Point(10, 5)))
    interp = CommandInterpreter(
        CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES
    )
    return interp, doc, a, b


@pytest.mark.parametrize(
    "comando",
    ["ERASE", "COPYCLIP", "CUTCLIP", "JOIN", "EXPLODE", "DIVIDE", "MEASURE",
     "PEDIT", "LAYISO", "LAYMCH", "MATCHPROP", "HATCHEDIT", "MOVE", "COPY",
     "ROTATE", "SCALE", "MIRROR"],
)
def test_comando_usa_a_selecao_que_ja_existe(comando):
    interp, doc, a, b = _cena()
    interp.context.selection.set({a.id, b.id})
    interp.start(comando)
    prompt = interp.current_prompt
    mensagem = "" if prompt is None else prompt.message
    assert "Select objects" not in mensagem, f"{comando} pediu seleção de novo"
    assert interp.context.preselection_available is False, "a pré-seleção não foi usada"
    # MATCHPROP e LAYMCH pedem uma SEGUNDA seleção (o destino) — isso é o
    # fluxo do AutoCAD, não o defeito.
    if interp.active and interp.current_prompt.kind == "selection":
        assert "destination" in mensagem or "to change" in mensagem, mensagem


def test_sem_preselecao_o_comando_pergunta_normalmente():
    interp, doc, a, b = _cena()
    interp.start("ERASE")
    assert interp.current_prompt.kind == "selection"
    assert "Select objects" in interp.current_prompt.message


def test_a_preselecao_vale_uma_vez_so_por_comando():
    """DIMBREAK pede a cota e DEPOIS o que a cruza — a segunda etapa tem de
    voltar a perguntar, senão usaria a mesma seleção duas vezes."""
    interp, doc, a, b = _cena()
    cota = doc.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 3))
    )
    interp.context.selection.set({cota.id})
    interp.start("DIMBREAK")
    assert interp.current_prompt is not None
    assert interp.current_prompt.kind == "selection"
    assert "cross" in interp.current_prompt.message


@pytest.mark.parametrize("comando", ["FIELD", "MTEXT", "INSERT", "TABLE"])
def test_clique_em_prompt_de_palavra_e_ignorado(comando):
    interp, doc, a, b = _cena()
    interp.start(comando)
    for _ in range(6):
        prompt = interp.current_prompt
        if prompt is None:
            break
        if prompt.kind in ("text", "keyword"):
            antes = prompt.message
            depois = interp.submit_point(Point(105, 105))
            assert depois is not None, f"{comando}: o clique derrubou o comando"
            assert depois.message == antes, f"{comando}: o clique andou com o prompt"
            assert interp.active, f"{comando}: o comando morreu com o clique"
            break
        if prompt.kind == "point":
            interp.submit_point(Point(1, 1))
        elif prompt.kind == "distance":
            interp.submit_text("1")
        else:
            interp.submit_text("")
    assert not any(
        isinstance(e, Text) and "Point(" in e.content for e in doc.all_entities()
    ), "um Point virou texto na prancha"
    assert not any("erro inesperado" in linha for linha in interp.log), interp.log
