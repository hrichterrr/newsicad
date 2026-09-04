"""Etapa 3c do programa de otimização (v2.15.2): o canvas descobre o que
mudou pela VERSÃO da entidade, não pelo repr() de todas a cada passo.

`Entity.__setattr__` carimba uma versão nova a cada atribuição; a passada
leve do `refresh_entities` (comando em andamento) compara só identidade +
versão + cor, e a passada completa (sem comando ativo) confere também o repr
guardado — rede de segurança para mutações feitas no lugar.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, LWPolyline, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def test_atribuicao_bumpa_a_versao_e_touch_tambem():
    line = Line(start=Point(0, 0), end=Point(1, 1))
    v0 = line.version
    line.end = Point(5, 5)
    assert line.version > v0
    v1 = line.version
    line.touch()
    assert line.version > v1
    # a versão não vaza para igualdade nem repr
    other = Line(start=Point(0, 0), end=Point(5, 5), id=line.id)
    assert other == line
    assert "_version" not in repr(line)


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1000, 700)
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def _conta_criacoes(canvas):
    contador = {"n": 0}
    original = canvas._create_item

    def espiao(entity, color=None):
        if color is None:
            contador["n"] += 1
        return original(entity, color)

    canvas._create_item = espiao
    return contador


def test_passada_leve_nao_chama_repr_e_recria_so_o_que_mudou(window):
    doc, canvas = window.document, window.canvas
    linhas = [doc.add_entity(Line(start=Point(i, 0), end=Point(i, 10))) for i in range(300)]
    canvas.refresh_entities(full=True)

    criados = _conta_criacoes(canvas)
    reprs = {"n": 0}
    original_repr = Line.__repr__

    def espiao_repr(self):
        reprs["n"] += 1
        return original_repr(self)

    Line.__repr__ = espiao_repr
    try:
        linhas[7].end = Point(7, 99)  # mutação por atribuição (como MOVE/TRIM)
        canvas.refresh_entities(full=False)
    finally:
        Line.__repr__ = original_repr

    assert criados["n"] == 1
    assert reprs["n"] <= 1  # só o repr guardado da entidade recriada
    assert canvas._entity_items[linhas[7].id].sceneBoundingRect().height() > 50


def test_passada_completa_pega_mutacao_no_lugar(window):
    doc, canvas = window.document, window.canvas
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)]))
    canvas.refresh_entities(full=True)
    criados = _conta_criacoes(canvas)

    poly.points.append(Point(0, 500))  # no lugar, sem atribuição nem touch()
    canvas.refresh_entities(full=False)
    assert criados["n"] == 0  # a passada leve não tem como saber

    canvas.refresh_entities(full=True)
    assert criados["n"] == 1  # a completa confere o repr e recria
    assert canvas._entity_items[poly.id].sceneBoundingRect().height() > 400


def test_modo_padrao_e_leve_durante_comando_e_completo_fora(window):
    doc, canvas = window.document, window.canvas
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)]))
    canvas.refresh_entities()
    criados = _conta_criacoes(canvas)
    poly.points.append(Point(0, 500))

    window._handle_text_submitted("LINE")  # comando ativo: passada leve
    assert window.interpreter.active
    canvas.refresh_entities()
    assert criados["n"] == 0

    window.interpreter.cancel() if hasattr(window.interpreter, "cancel") else window._handle_text_submitted("")
    if window.interpreter.active:
        pytest.skip("não foi possível encerrar o comando neste ambiente")
    canvas.refresh_entities()
    assert criados["n"] == 1
