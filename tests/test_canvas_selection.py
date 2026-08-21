"""Testes de integração da UI: seleção por clique/janela no canvas real
(via QTest, simulando eventos de mouse de verdade), não só a lógica pura.

Existem para pegar bugs que só aparecem na integração Qt (ex.: um item
gráfico que não é atualizado depois que a entidade é movida em memória) —
esse tipo de bug não é visível testando só commands/core isoladamente.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Point  # noqa: E402
from newsicad.ui.canvas import cad_to_scene  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _viewport_pos(window: MainWindow, cad_point: Point) -> QPoint:
    return window.canvas.mapFromScene(cad_to_scene(cad_point))


def test_click_selects_entity_under_cursor():
    app = _app()
    window = MainWindow()
    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")  # termina LINE
    app.processEvents()

    window._handle_text_submitted("ERASE")
    pos = _viewport_pos(window, Point(5, 0))
    QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    app.processEvents()

    assert len(window.selection.ids) == 1


def test_window_drag_selects_fully_enclosed_entities():
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 20))
    window._handle_canvas_point(Point(10, 20))
    window._handle_text_submitted("")
    app.processEvents()

    assert len(window.document.entities) == 2

    window._handle_text_submitted("ERASE")
    start = _viewport_pos(window, Point(-5, -5))
    end = _viewport_pos(window, Point(15, 25))

    viewport = window.canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, pos=QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2))
    QTest.mouseMove(viewport, pos=end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()

    assert len(window.selection.ids) == 2

    window._handle_text_submitted("")  # confirma seleção -> apaga
    app.processEvents()
    assert len(window.document.entities) == 0


def test_crossing_drag_selects_partially_touched_entities():
    """Arrasto da direita pra esquerda = crossing: seleciona qualquer coisa
    que a janela toque, mesmo sem estar totalmente dentro."""
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(20, 0))  # linha horizontal longa
    window._handle_text_submitted("")
    app.processEvents()

    window._handle_text_submitted("ERASE")
    # janela cobre só a metade esquerda da linha (0..20), de x=-5 a x=10,
    # arrastada da DIREITA pra ESQUERDA (start.x > end.x) -> modo crossing
    start = _viewport_pos(window, Point(10, -5))
    end = _viewport_pos(window, Point(-5, 5))

    viewport = window.canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, pos=QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2))
    QTest.mouseMove(viewport, pos=end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()

    assert len(window.selection.ids) == 1


def test_move_via_real_mouse_events_updates_rendered_geometry():
    """Regressão: MOVE precisa atualizar o item gráfico de uma entidade
    mutada em memória, não só o Document."""
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")
    app.processEvents()

    line = next(iter(window.document.entities.values()))
    line_id = line.id

    window._handle_text_submitted("MOVE")
    pos = _viewport_pos(window, Point(5, 0))
    QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    app.processEvents()
    assert line_id in window.selection.ids

    window._handle_text_submitted("")  # confirma seleção
    window._handle_canvas_point(Point(0, 0))  # base point
    window._handle_canvas_point(Point(0, 50))  # second point
    app.processEvents()

    moved = window.document.get_entity(line_id)
    assert moved.start.as_tuple() == (0, 50)
    assert moved.end.as_tuple() == (10, 50)

    # o item gráfico renderizado precisa refletir a nova posição
    item = window.canvas._entity_items[line_id]
    rendered_line = item.line()
    expected_start = cad_to_scene(moved.start)
    assert abs(rendered_line.x1() - expected_start.x()) < 1e-6
    assert abs(rendered_line.y1() - expected_start.y()) < 1e-6


def test_delete_key_erases_selected_entities():
    """Regressão: selecionar clicando direto no canvas (sem comando ativo)
    e apertar Delete precisa apagar a seleção, igual ao ERASE."""
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")
    app.processEvents()
    assert len(window.document.entities) == 1

    pos = _viewport_pos(window, Point(5, 0))
    QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    app.processEvents()
    assert len(window.selection.ids) == 1

    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Delete)
    app.processEvents()

    assert len(window.document.entities) == 0
    assert len(window.selection.ids) == 0


def test_delete_key_without_selection_does_nothing():
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")
    app.processEvents()
    assert len(window.document.entities) == 1

    QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Delete)
    app.processEvents()

    assert len(window.document.entities) == 1
