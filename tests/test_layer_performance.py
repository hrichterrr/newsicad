"""Etapa 2 do programa de otimização (v2.15.1): mexer em camadas não pode
reconstruir a cena.

Relato de 2026-09-03 na planta NEWSI-CASA PAU BRASIL-R01 (43 mil entidades):
um clique na lâmpada do painel de camadas congelou o programa — 178 s medidos
— porque a impressão digital de todo item carregava o estado de TODAS as
camadas e a visibilidade era feita destruindo/recriando itens. Aqui os
testes são de COMPORTAMENTO (quantos itens são criados, o que fica visível),
com volume suficiente para pegar regressão sem depender de cronômetro.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import BlockReference, Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402

N_POR_CAMADA = 400
CAMADAS = ("A-WALL", "A-DOOR", "E-POWER")


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1200, 800)
    doc = win.document
    for layer in CAMADAS:
        doc.add_layer(layer, "#00FF00")
        for i in range(N_POR_CAMADA):
            doc.add_entity(Line(layer=layer, start=Point(i, 0), end=Point(i, 10)))
    # um bloco cujos filhos estão numa camada específica: a cor DELA muda o
    # desenho do bloco, a das outras não
    doc.define_block("BLK", [Line(layer="A-DOOR", start=Point(0, 0), end=Point(1, 1))])
    doc.add_entity(BlockReference(layer="0", block_name="BLK", insertion_point=Point(0, 0)))
    win.canvas.refresh_entities()
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def _conta_criacoes(canvas):
    """Conta itens de PRIMEIRO nível criados (chamadas sem cor explícita —
    os filhos de bloco passam pelo mesmo `_create_item`, mas com a cor já
    resolvida pelo pai)."""
    contador = {"n": 0}
    original = canvas._create_item

    def espiao(entity, color=None):
        if color is None:
            contador["n"] += 1
        return original(entity, color)

    canvas._create_item = espiao
    return contador


def _itens_da_camada(win, layer):
    doc, canvas = win.document, win.canvas
    return [canvas._entity_items[e.id] for e in doc.entities.values() if e.layer == layer]


def test_lampada_nao_recria_item_algum(window):
    canvas, panel = window.canvas, window.layer_dock
    antes = len(canvas._scene.items())
    criados = _conta_criacoes(canvas)

    panel._set_visible("A-WALL", False)
    assert criados["n"] == 0
    assert len(canvas._scene.items()) == antes  # nada destruído
    assert all(not item.isVisible() for item in _itens_da_camada(window, "A-WALL"))
    assert all(item.isVisible() for item in _itens_da_camada(window, "A-DOOR"))

    panel._set_visible("A-WALL", True)
    assert criados["n"] == 0
    assert all(item.isVisible() for item in _itens_da_camada(window, "A-WALL"))


def test_refresh_entities_respeita_camada_desligada_sem_recriar(window):
    """O caminho normal de comando (refresh_entities) também não pode voltar
    a recriar tudo por causa de uma camada desligada."""
    canvas = window.canvas
    window.document.layers["A-WALL"].visible = False
    criados = _conta_criacoes(canvas)
    canvas.refresh_entities()
    assert criados["n"] == 0
    assert all(not item.isVisible() for item in _itens_da_camada(window, "A-WALL"))


def test_cadeado_nao_recria_item_algum(window):
    canvas, panel = window.canvas, window.layer_dock
    criados = _conta_criacoes(canvas)
    panel._set_locked("A-WALL", True)
    canvas.refresh_entities()  # o que o próximo passo de comando faria
    assert criados["n"] == 0


def test_cor_da_camada_recria_so_quem_usa_a_camada(window):
    canvas, panel = window.canvas, window.layer_dock
    criados = _conta_criacoes(canvas)
    panel._set_color_with_hex("A-DOOR", "#FF0000")
    # as 400 linhas da camada + o bloco cuja definição usa a camada
    assert criados["n"] == N_POR_CAMADA + 1
    assert all(item.pen().color().name().upper() == "#FF0000" for item in _itens_da_camada(window, "A-DOOR"))

    criados["n"] = 0
    panel._set_color_with_hex("E-POWER", "#0000FF")
    assert criados["n"] == N_POR_CAMADA  # o bloco não usa E-POWER


def test_hit_test_continua_com_pre_filtro_com_camada_desligada(window):
    """Antes, esconder uma camada tirava itens da cena e o pré-filtro
    espacial do clique se desligava para sempre (hit-test exato em todas
    as entidades a cada clique)."""
    canvas, panel = window.canvas, window.layer_dock
    panel._set_visible("A-WALL", False)
    tolerance = canvas._hit_tolerance_world()
    longe = list(canvas._hit_candidates(Point(1e6, 1e6), tolerance))
    assert longe == []  # pré-filtro ativo: nada perto, nada testado

    # e a entidade escondida não é selecionável
    assert canvas._hit_test(Point(5, 5)) is None or window.document.entities[canvas._hit_test(Point(5, 5))].layer != "A-WALL"


def test_zoom_extents_ignora_camada_desligada(window):
    canvas, panel = window.canvas, window.layer_dock
    doc = window.document
    doc.add_entity(Line(layer="A-WALL", start=Point(0, 0), end=Point(5000, 5000)))
    canvas.refresh_entities()
    com = canvas.compute_extents_rect()
    panel._set_visible("A-WALL", False)
    sem = canvas.compute_extents_rect()
    assert sem.width() < com.width()
