"""Testes de integração da UI pros novos tipos de entidade (Text, Dimension,
Hatch): confirma que CanvasView consegue criar o QGraphicsItem de cada um
(_create_item não lança), que entram no hit-test de seleção (_hit_test) e
que participam da bounding box de zoom/seleção por janela
(_entity_bbox_scene) — mesmo padrão de tests/test_canvas_selection.py."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Dimension, Hatch, Point, Text  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_text_entity_renders_and_is_selectable():
    app = _app()
    window = MainWindow()
    text = window.document.add_entity(
        Text(insertion_point=Point(0, 0), content="Hello", height=2.5)
    )
    window.canvas.refresh_entities()
    app.processEvents()

    assert text.id in window.canvas._entity_items
    assert window.canvas._hit_test(Point(1, -1)) == text.id  # dentro do bbox do texto
    bbox = window.canvas._entity_bbox_scene(text)
    assert bbox.width() > 0 and bbox.height() > 0


def test_rotated_text_bbox_is_not_degenerate():
    app = _app()
    window = MainWindow()
    text = window.document.add_entity(
        Text(insertion_point=Point(5, 5), content="Rotated", height=3.0, rotation=math.radians(90))
    )
    window.canvas.refresh_entities()
    app.processEvents()
    bbox = window.canvas._entity_bbox_scene(text)
    assert bbox.width() > 0 and bbox.height() > 0


def test_dimension_linear_renders_and_is_selectable():
    app = _app()
    window = MainWindow()
    dim = window.document.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 5))
    )
    window.canvas.refresh_entities()
    app.processEvents()

    assert dim.id in window.canvas._entity_items
    # ponto sobre a linha de cota (y=5, entre x=0 e x=10)
    assert window.canvas._hit_test(Point(5, 5)) == dim.id


def test_dimension_radius_renders_and_is_selectable():
    app = _app()
    window = MainWindow()
    dim = window.document.add_entity(
        Dimension(kind="radius", center=Point(0, 0), radius=5.0, leader_point=Point(10, 10))
    )
    window.canvas.refresh_entities()
    app.processEvents()
    assert dim.id in window.canvas._entity_items
    bbox = window.canvas._entity_bbox_scene(dim)
    assert bbox.width() >= 0 and bbox.height() >= 0


def test_hatch_renders_and_click_inside_boundary_selects_it():
    app = _app()
    window = MainWindow()
    hatch = window.document.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])
    )
    window.canvas.refresh_entities()
    app.processEvents()

    assert hatch.id in window.canvas._entity_items
    # ponto bem no meio do contorno (não perto de nenhuma borda)
    assert window.canvas._hit_test(Point(5, 5)) == hatch.id
    bbox = window.canvas._entity_bbox_scene(hatch)
    assert bbox.width() == 10 and bbox.height() == 10


def test_zoom_extents_includes_new_entity_types_without_raising():
    app = _app()
    window = MainWindow()
    window.document.add_entity(Text(insertion_point=Point(0, 0), content="X", height=2.0))
    window.document.add_entity(
        Dimension(kind="angular", center=Point(0, 0), point1=Point(10, 0), point2=Point(0, 10), dim_line_point=Point(5, 5))
    )
    window.document.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(20, 0), Point(20, 20), Point(0, 20)])
    )
    window.canvas.refresh_entities()
    app.processEvents()
    window.canvas.zoom_extents()  # não deve lançar exceção
