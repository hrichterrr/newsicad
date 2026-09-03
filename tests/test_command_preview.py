"""Testes do preview ao vivo desenhado em CanvasView._update_preview
(newsicad/ui/canvas.py). Cobre o bug real reportado: RECTANG mostrava uma
linha reta até o cursor durante o arrasto (igual LINE), não um contorno de
retângulo — mesmo a entidade final sendo uma LWPolyline fechada correta."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Point  # noqa: E402
from newsicad.ui.canvas import cad_to_scene  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_rectang_preview_shows_rectangle_outline_not_a_line():
    _app()
    window = MainWindow()
    window._handle_text_submitted("REC")
    window._handle_canvas_point(Point(0, 0))

    window.canvas._update_preview(Point(10, 5))
    path = window.canvas._preview_path

    assert path is not None
    assert not path.isEmpty()
    # uma linha reta (moveTo + lineTo) tem 2 elementos; um retângulo fechado
    # (addRect) tem mais que isso.
    assert path.elementCount() > 2

    expected = QRectF(cad_to_scene(Point(0, 0)), cad_to_scene(Point(10, 5))).normalized()
    bounds = path.boundingRect()
    assert bounds.width() == pytest.approx(expected.width(), abs=0.5)
    assert bounds.height() == pytest.approx(expected.height(), abs=0.5)


def test_line_preview_still_a_straight_line():
    """Confirma que o fix do RECTANG não bagunçou o preview genérico usado
    por LINE/PLINE/POLYGON/etc (moveTo + lineTo até o cursor)."""
    _app()
    window = MainWindow()
    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))

    window.canvas._update_preview(Point(10, 5))
    path = window.canvas._preview_path

    assert path is not None
    assert path.elementCount() == 2
