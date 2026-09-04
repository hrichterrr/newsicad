"""Testes de integração canvas + camadas: desligar a visibilidade de uma
camada tira a entidade do canvas de verdade (não só "esconde visualmente") —
some da cena, do hit-test, da seleção por janela, do zoom extents e do
OSNAP. Trancar a camada mantém a entidade visível mas bloqueia seleção."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window_with_line_on_layer(layer: str = "PAREDES") -> tuple[MainWindow, Line]:
    _app()
    window = MainWindow()
    window.document.add_layer(layer)
    line = window.document.add_entity(Line(layer=layer, start=Point(0, 0), end=Point(10, 0)))
    window.canvas.refresh_entities()
    return window, line


def test_hiding_layer_hides_entity_item_without_destroying_it():
    """Camada desligada: o item fica na cena, só invisível (v2.15.1 — antes
    era destruído e recriado ao religar, o que custava uma reconstrução
    total da cena em planta grande; ver tests/test_layer_performance.py)."""
    window, line = _window_with_line_on_layer()
    assert line.id in window.canvas._entity_items
    assert window.canvas._entity_items[line.id].isVisible()

    window.document.layers["PAREDES"].visible = False
    window.canvas.refresh_entities()
    assert line.id in window.canvas._entity_items
    assert not window.canvas._entity_items[line.id].isVisible()

    window.document.layers["PAREDES"].visible = True
    window.canvas.refresh_entities()
    assert window.canvas._entity_items[line.id].isVisible()


def test_hiding_layer_excludes_entity_from_hit_test():
    window, line = _window_with_line_on_layer()
    assert window.canvas._hit_test(Point(5, 0)) == line.id

    window.document.layers["PAREDES"].visible = False
    assert window.canvas._hit_test(Point(5, 0)) is None


def test_locking_layer_excludes_entity_from_hit_test_but_keeps_it_visible():
    window, line = _window_with_line_on_layer()

    window.document.layers["PAREDES"].locked = True
    assert window.canvas._hit_test(Point(5, 0)) is None
    # ainda desenhada, só não selecionável
    assert line.id in window.canvas._entity_items


def test_hiding_layer_excludes_entity_from_zoom_extents():
    window, line = _window_with_line_on_layer()
    window.document.add_entity(Line(layer="0", start=Point(100, 100), end=Point(101, 101)))
    window.canvas.refresh_entities()

    window.document.layers["PAREDES"].visible = False
    rect = window.canvas.compute_extents_rect()
    assert rect is not None
    # se a linha escondida (perto da origem) ainda contasse, o rect
    # incluiria x=0; como não deveria, o retângulo fica só perto de (100,100)
    assert rect.left() > 50


def test_locking_layer_via_panel_clears_selection_of_that_layer():
    window, line = _window_with_line_on_layer()
    window.selection.add(line.id)
    assert line.id in window.selection.ids

    window.layer_dock._set_locked("PAREDES", True)
    assert line.id not in window.selection.ids
