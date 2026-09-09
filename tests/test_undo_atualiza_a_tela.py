"""Desfazer um MOVE devolvia a entidade ao lugar certo no DOCUMENTO e deixava
o DESENHO na posição errada.

`pickle.loads` monta o objeto restaurado direto no `__dict__`, sem passar pelo
`Entity.__setattr__`, então ele não entrava no registro de alterados
(`entities.drain_dirty()`); e como o id dele já tinha item na cena, também não
contava como "novo". A passada incremental do canvas não via nada para fazer.

Na tela parecia que o Ctrl+Z não tinha feito nada, e o objeto ficava
impossível de selecionar: o clique procura onde o documento diz que ele está,
e ali não havia item nenhum. Relatado pelo Hamilton em 09/09/2026, movendo uma
caixa de som para fora da planta. Vale para todo undo/redo de alteração NO
LUGAR — MOVE, ROTATE, SCALE, STRETCH, mudança de propriedade; desfazer um
apagar ou um criar sempre funcionou, porque ali os ids somem ou aparecem.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.core.undo import UndoStack  # noqa: E402
from newsicad.ui.canvas import CanvasView  # noqa: E402


@pytest.fixture
def cena():
    QApplication.instance() or QApplication([])
    doc = Document()
    interp = CommandInterpreter(
        CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES
    )
    canvas = CanvasView(doc, interp)
    canvas.resize(800, 600)
    return doc, canvas, UndoStack(doc)


def _bbox(canvas, entity_id):
    return canvas._entity_items[entity_id].sceneBoundingRect()


def test_desfazer_um_move_devolve_o_desenho_junto(cena):
    doc, canvas, undo = cena
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    canvas.refresh_entities()
    origem = _bbox(canvas, linha.id)

    undo.push()
    linha.start = Point(900, 700)
    linha.end = Point(910, 700)
    canvas.refresh_entities()
    assert _bbox(canvas, linha.id) != origem, "o move nem chegou a aparecer"

    undo.undo()
    canvas.refresh_entities()
    assert _bbox(canvas, linha.id) == origem, "o desenho ficou na posição de antes do undo"


def test_o_objeto_desfeito_volta_a_ser_selecionavel(cena):
    doc, canvas, undo = cena
    linha = doc.add_entity(Line(start=Point(0, 5), end=Point(10, 5)))
    canvas.refresh_entities()
    canvas.zoom_extents()
    meio = Point(5, 5)
    assert canvas._hit_test(meio) == linha.id

    undo.push()
    linha.start = Point(900, 700)
    linha.end = Point(910, 700)
    canvas.refresh_entities()

    undo.undo()
    canvas.refresh_entities()
    assert canvas._hit_test(meio) == linha.id, (
        "o clique não acha o objeto onde o documento diz que ele está"
    )


def test_refazer_tambem_leva_o_desenho(cena):
    doc, canvas, undo = cena
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    canvas.refresh_entities()

    undo.push()
    linha.start = Point(900, 700)
    linha.end = Point(910, 700)
    canvas.refresh_entities()
    movido = _bbox(canvas, linha.id)

    undo.undo()
    canvas.refresh_entities()
    undo.redo()
    canvas.refresh_entities()
    assert _bbox(canvas, linha.id) == movido


def test_o_que_nao_mudou_nao_e_recriado(cena):
    """O barato do undo incremental é justamente não recriar a cena toda —
    quem não mudou tem de continuar sendo o MESMO item gráfico."""
    doc, canvas, undo = cena
    parada = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    movida = doc.add_entity(Line(start=Point(0, 5), end=Point(1, 5)))
    canvas.refresh_entities()
    item_da_parada = canvas._entity_items[parada.id]

    undo.push()
    movida.start = Point(900, 700)
    canvas.refresh_entities()
    undo.undo()
    canvas.refresh_entities()

    assert canvas._entity_items[parada.id] is item_da_parada
