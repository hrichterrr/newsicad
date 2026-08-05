"""Undo/Redo (Ctrl+Z/Ctrl+Y) de ponta a ponta: atalho de teclado -> UndoStack
-> Document -> canvas. Complementa test_undo.py (que só testa UndoStack
isolado) verificando a fiação real na MainWindow."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ctrl_z_undoes_last_command():
    app = _app()
    window = MainWindow()
    window.show()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")
    app.processEvents()
    assert len(window.document.entities) == 1

    QTest.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert len(window.document.entities) == 0


def test_ctrl_y_redoes_after_ctrl_z():
    app = _app()
    window = MainWindow()
    window.show()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(10, 0))
    window._handle_text_submitted("")
    app.processEvents()

    QTest.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert len(window.document.entities) == 0

    QTest.keyClick(window, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert len(window.document.entities) == 1


def test_typed_undo_command_also_works():
    app = _app()
    window = MainWindow()

    window._handle_text_submitted("CIRCLE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_text_submitted("5")
    app.processEvents()
    assert len(window.document.entities) == 1

    window._handle_text_submitted("U")  # alias de UNDO
    app.processEvents()
    assert len(window.document.entities) == 0
