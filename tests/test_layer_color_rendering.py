"""Testes da renderização por cor de camada/entidade (CanvasView._effective_color):
até este marco, o canvas sempre desenhava tudo na mesma cor fixa (ENTITY_COLOR),
mesmo com `Layer.color` e `Entity.color` já existindo no modelo — o painel de
camadas dizia isso explicitamente como limitação documentada. Agora a cor da
camada (ou da entidade, se não for ByLayer) afeta o desenho de verdade."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.ui.canvas import ENTITY_COLOR  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_entity_on_bylayer_uses_layer_color():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES", color="#ff0000")
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0), layer="PAREDES"))
    window.canvas.refresh_entities()

    assert window.canvas._effective_color(line) == "#ff0000"
    item = window.canvas._entity_items[line.id]
    assert item.pen().color().name() == "#ff0000"


def test_entity_with_explicit_color_overrides_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES", color="#ff0000")
    circle = window.document.add_entity(
        Circle(center=Point(0, 0), radius=5, layer="PAREDES", color="#00ff00")
    )
    window.canvas.refresh_entities()

    assert window.canvas._effective_color(circle) == "#00ff00"
    item = window.canvas._entity_items[circle.id]
    assert item.pen().color().name() == "#00ff00"


def test_missing_layer_falls_back_to_entity_color_default():
    _app()
    window = MainWindow()
    line = Line(start=Point(0, 0), end=Point(5, 5), layer="INEXISTENTE")
    assert window.canvas._effective_color(line) == ENTITY_COLOR


def test_deselecting_restores_each_entity_own_color():
    _app()
    window = MainWindow()
    window.document.add_layer("A", color="#ff0000")
    window.document.add_layer("B", color="#0000ff")
    line_a = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 1), layer="A"))
    line_b = window.document.add_entity(Line(start=Point(2, 2), end=Point(3, 3), layer="B"))
    window.canvas.refresh_entities()

    window.selection.set({line_a.id, line_b.id})
    window.canvas.refresh_selection_highlight()
    # ambas ficam com a cor de seleção (uniforme) enquanto selecionadas
    assert window.canvas._entity_items[line_a.id].pen().color().name() != "#ff0000"

    window.selection.clear()
    window.canvas.refresh_selection_highlight()
    assert window.canvas._entity_items[line_a.id].pen().color().name() == "#ff0000"
    assert window.canvas._entity_items[line_b.id].pen().color().name() == "#0000ff"


def test_changing_layer_color_and_refreshing_updates_canvas():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES", color="#ff0000")
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0), layer="PAREDES"))
    window.canvas.refresh_entities()
    assert window.canvas._entity_items[line.id].pen().color().name() == "#ff0000"

    window.document.layers["PAREDES"].color = "#00ff00"
    window.canvas.refresh_entities()
    assert window.canvas._entity_items[line.id].pen().color().name() == "#00ff00"
