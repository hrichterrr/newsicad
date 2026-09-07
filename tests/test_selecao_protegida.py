"""Camada travada e camada desligada não entram em seleção.

Auditoria de 2026-09-07: o clique no canvas já respeitava as duas, mas os
comandos que varrem o desenho inteiro (QSELECT, SELECTSIMILAR, STRETCH) e o
Ctrl+A pegavam tudo — e o Del seguinte apagava o que o usuário tinha
protegido ou o que nem estava na tela.
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
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _tres_linhas(doc: Document):
    """Uma em camada travada, uma em camada desligada, uma normal."""
    doc.add_layer("TRAVADA")
    doc.layers["TRAVADA"].locked = True
    doc.add_layer("OCULTA")
    doc.layers["OCULTA"].visible = False
    return (
        doc.add_entity(Line(layer="TRAVADA", start=Point(0, 0), end=Point(10, 0))),
        doc.add_entity(Line(layer="OCULTA", start=Point(0, 1), end=Point(10, 1))),
        doc.add_entity(Line(start=Point(0, 2), end=Point(10, 2))),
    )


def _interp(doc):
    return CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES)


def test_qselect_ignora_camada_travada_e_oculta():
    doc = Document()
    travada, oculta, livre = _tres_linhas(doc)
    interp = _interp(doc)
    interp.start("QSELECT")
    interp.submit_text("Line")
    assert interp.context.selection.ids == {livre.id}


def test_selectsimilar_ignora_camada_travada_e_oculta():
    doc = Document()
    travada, oculta, livre = _tres_linhas(doc)
    interp = _interp(doc)
    interp.start("SELECTSIMILAR")
    interp.context.selection.add(livre.id)
    interp.submit_text("")
    assert interp.context.selection.ids == {livre.id}


def test_stretch_nao_move_o_que_esta_protegido():
    doc = Document()
    travada, oculta, livre = _tres_linhas(doc)
    interp = _interp(doc)
    interp.start("STRETCH")
    interp.submit_point(Point(-1, -1))   # janela cobrindo as três
    interp.submit_point(Point(11, 3))
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(50, 0))

    assert livre.start.x == pytest.approx(50)
    assert travada.start.x == pytest.approx(0), "moveu objeto em camada travada"
    assert oculta.start.x == pytest.approx(0), "moveu objeto em camada desligada"


def test_ctrl_a_e_del_nao_pegam_o_que_esta_protegido():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    try:
        travada, oculta, livre = _tres_linhas(win.document)
        win.canvas.refresh_entities()
        win._select_all()
        assert win.selection.ids == {livre.id}

        win._delete_selected()
        assert travada.id in win.document.entities
        assert oculta.id in win.document.entities
        assert livre.id not in win.document.entities
    finally:
        win.hide()
        win.deleteLater()
        app.processEvents()


def test_destravar_e_religar_devolve_a_selecao():
    doc = Document()
    travada, oculta, livre = _tres_linhas(doc)
    doc.layers["TRAVADA"].locked = False
    doc.layers["OCULTA"].visible = True
    interp = _interp(doc)
    interp.start("QSELECT")
    interp.submit_text("Line")
    assert interp.context.selection.ids == {travada.id, oculta.id, livre.id}
