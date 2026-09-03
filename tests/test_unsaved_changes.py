"""Testes da proteção contra perda de trabalho não salvo: detecção de
"documento sujo" (_is_dirty) e o diálogo Save/Discard/Cancel disparado por
fechar a janela, File > New e File > Open (bug real reportado por Hamilton —
antes disso, essas três ações descartavam o desenho em silêncio)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from newsicad.core.entities import Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _draw_a_line(window: MainWindow) -> None:
    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(1, 1))
    window._handle_text_submitted("")


def test_fresh_document_is_not_dirty():
    _app()
    window = MainWindow()
    assert not window._is_dirty()


def test_drawing_marks_document_dirty():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    assert window._is_dirty()


def test_confirm_discard_returns_true_without_prompt_when_clean():
    _app()
    window = MainWindow()
    with patch("newsicad.ui.main_window.QMessageBox.exec") as mock_exec:
        assert window._confirm_discard_changes() is True
        mock_exec.assert_not_called()


def test_confirm_discard_cancel_keeps_dirty_and_returns_false():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        assert window._confirm_discard_changes() is False
    assert window._is_dirty()


def test_confirm_discard_discard_returns_true():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Discard,
    ):
        assert window._confirm_discard_changes() is True


def test_confirm_discard_save_writes_file_and_clears_dirty(tmp_path):
    _app()
    window = MainWindow()
    _draw_a_line(window)
    target = tmp_path / "work.dxf"
    window.current_path = target
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Save,
    ):
        assert window._confirm_discard_changes() is True
    assert target.exists()
    assert not window._is_dirty()


def test_new_document_opens_extra_tab_without_prompting():
    # Desde as abas de documento existirem (várias sessões independentes na
    # mesma janela — ver newsicad/ui/document_session.py), File > New nunca
    # mais descarta nada: ele abre uma aba nova em branco e deixa a aba atual
    # (com o trabalho não salvo) intocada, então não há mais diálogo de
    # confirmação nesse fluxo.
    _app()
    window = MainWindow()
    _draw_a_line(window)
    with patch("newsicad.ui.main_window.QMessageBox.exec") as mock_exec:
        window._new_document()
        mock_exec.assert_not_called()

    assert len(window.sessions) == 2
    # a aba nova (agora ativa) está vazia...
    assert len(window.document.entities) == 0
    assert not window._is_dirty()
    # ...e a aba original, com a linha desenhada, continua intocada.
    assert len(window.sessions[0].document.entities) == 1


def test_closing_dirty_tab_blocked_by_cancel_keeps_it_open():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        window._close_tab(0)
    assert len(window.sessions) == 1
    assert len(window.document.entities) == 1


def test_closing_dirty_tab_discard_removes_it_and_opens_blank_replacement():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    window.current_path = Path("old.dxf")
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Discard,
    ):
        window._close_tab(0)
    # fechar a última aba sempre deixa uma aba em branco no lugar (nunca
    # fica com zero abas abertas).
    assert len(window.sessions) == 1
    assert len(window.document.entities) == 0
    assert window.current_path is None
    assert not window._is_dirty()


def test_close_event_ignored_on_cancel():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    event = QCloseEvent()
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        window.closeEvent(event)
    assert not event.isAccepted()


def test_close_event_accepted_on_discard():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    event = QCloseEvent()
    with patch(
        "newsicad.ui.main_window.QMessageBox.exec",
        return_value=QMessageBox.StandardButton.Discard,
    ):
        window.closeEvent(event)
    assert event.isAccepted()


def test_close_event_accepted_without_prompt_when_clean():
    _app()
    window = MainWindow()
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
