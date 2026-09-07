"""Enter num prompt que EXIGE um valor encerra o comando, em vez de virar
valor de campo.

Auditoria de 2026-09-07: o sentinela `ENTER` chegava ao gerador e era gravado
direto na entidade — CIRCLE guardava um `object()` no raio, a entidade entrava
no desenho e a partir dali repintar, desfazer e SALVAR estouravam, sem o
usuário conseguir nem apagar o objeto ruim. Outros 13 comandos devolviam um
erro interno de Python na linha de comando.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Point
from newsicad.core.selection import Selection
from newsicad.io.dxf_io import save_dxf


def _interp():
    doc = Document()
    return CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES), doc


# (comando, respostas antes do Enter que quebrava)
CASOS_QUE_ENVENENAVAM = [
    ("CIRCLE", [Point(0, 0)]),
    ("POINT", []),
    ("DIMLINEAR", [Point(0, 0), Point(10, 0)]),
    ("DIMALIGNED", [Point(0, 0), Point(10, 0)]),
    ("DIMANGULAR", [Point(0, 0), Point(10, 0), Point(0, 10)]),
]


@pytest.mark.parametrize("comando,pontos", CASOS_QUE_ENVENENAVAM)
def test_enter_encerra_sem_criar_entidade(comando, pontos):
    interp, doc = _interp()
    interp.start(comando)
    for p in pontos:
        interp.submit_point(p)
    interp.submit_text("")  # Enter no prompt que exige valor

    assert not interp.active
    assert not doc.all_entities(), f"{comando} criou entidade com o sentinela ENTER"
    # e o desenho continua gravável
    save_dxf(doc, pathlib.Path(tempfile.mkdtemp()) / "ok.dxf")


# (comando, respostas antes do Enter que precisa cancelar). POLYGON começa com
# um prompt que TEM padrão ("Enter number of sides <4>"), então o Enter que
# cancela é o do prompt seguinte.
CASOS_ERRO_INTERNO = [
    ("ARC", []),
    ("RECTANG", []),
    ("POLYGON", [""]),
    ("ELLIPSE", []),
    ("OFFSET", []),
    ("MLINE", []),
    ("BREAK", []),
    ("DIST", []),
    ("ID", []),
]


@pytest.mark.parametrize("comando,antes", CASOS_ERRO_INTERNO)
def test_enter_no_primeiro_ponto_cancela_limpo(comando, antes):
    """Sem erro interno de Python na linha de comando."""
    interp, doc = _interp()
    interp.start(comando)
    for resposta in antes:
        interp.submit_text(resposta)
    interp.submit_text("")
    assert not interp.active
    assert not doc.all_entities()
    assert not any("erro inesperado" in linha for linha in interp.log), interp.log


def test_prompt_com_valor_padrao_continua_aceitando_enter():
    """A convenção do `<padrão>` no texto do prompt continua valendo."""
    interp, doc = _interp()
    doc.define_block("B", [])
    interp.start("INSERT")
    interp.submit_text("B")
    interp.submit_point(Point(1, 2))
    interp.submit_text("")  # escala padrão <1>
    interp.submit_text("")  # rotação padrão <0>
    assert not interp.active
    refs = doc.all_entities()
    assert len(refs) == 1 and refs[0].scale == 1.0


def test_sequencia_de_pontos_ainda_termina_com_enter():
    """LINE/PLINE/SPLINE e afins usam Enter para encerrar a sequência."""
    interp, doc = _interp()
    interp.start("LINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_text("")  # Enter encerra a sequência, mantendo o desenhado
    assert not interp.active
    assert len(doc.all_entities()) == 2
