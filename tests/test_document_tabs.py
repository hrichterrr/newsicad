"""Testes das abas de documento (vários desenhos abertos ao mesmo tempo na
mesma janela — ver newsicad/ui/document_session.py): cada aba tem seu
próprio documento/seleção/interpretador/undo, sem vazar estado entre abas."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.io.dxf_io import save_dxf  # noqa: E402
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


def test_fresh_window_starts_with_one_tab():
    _app()
    window = MainWindow()
    assert len(window.sessions) == 1
    assert window.doc_tabs.count() == 1
    assert window.sessions[0].untitled_label == "Drawing1"


def test_new_document_creates_second_independent_tab():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    window._new_document()

    assert len(window.sessions) == 2
    assert window.doc_tabs.currentIndex() == 1
    assert window.sessions[1].untitled_label == "Drawing2"
    # a aba nova está ativa e vazia...
    assert len(window.document.entities) == 0
    # ...a original tem a linha e não foi tocada.
    assert len(window.sessions[0].document.entities) == 1


def test_switching_tabs_swaps_active_document_and_canvas():
    _app()
    window = MainWindow()
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(5, 5)))
    window._new_document()
    assert line.id not in window.document.entities

    window.doc_tabs.setCurrentIndex(0)
    assert line.id in window.document.entities
    assert window.canvas is window.sessions[0].canvas


def test_undo_stack_is_independent_per_tab():
    _app()
    window = MainWindow()
    _draw_a_line(window)
    assert len(window.document.entities) == 1

    window._new_document()
    _draw_a_line(window)
    _draw_a_line(window)
    assert len(window.document.entities) == 2

    window._do_undo()
    assert len(window.document.entities) == 1

    window.doc_tabs.setCurrentIndex(0)
    assert len(window.document.entities) == 1  # aba 1 nunca teve nada desfeito


def test_open_file_creates_new_tab_leaving_current_tab_untouched(tmp_path):
    _app()
    window = MainWindow()
    _draw_a_line(window)

    dxf_path = tmp_path / "outro.dxf"
    save_dxf(window.document, dxf_path)

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(dxf_path), "DXF (*.dxf)"),
    ):
        window._open_file()

    assert len(window.sessions) == 2
    assert window.current_path == dxf_path
    assert len(window.document.entities) == 1
    assert window.sessions[0].current_path is None
    assert len(window.sessions[0].document.entities) == 1


def test_closing_clean_tab_does_not_prompt():
    _app()
    window = MainWindow()
    window._new_document()
    assert len(window.sessions) == 2

    with patch("newsicad.ui.main_window.QMessageBox.exec") as mock_exec:
        window._close_tab(1)
        mock_exec.assert_not_called()
    assert len(window.sessions) == 1


def test_closing_last_tab_always_leaves_one_blank_tab_open():
    _app()
    window = MainWindow()
    window._close_tab(0)
    assert len(window.sessions) == 1
    assert len(window.document.entities) == 0


def test_tab_label_shows_dirty_marker():
    _app()
    window = MainWindow()
    assert window.doc_tabs.tabText(0) == "Drawing1"
    _draw_a_line(window)
    assert window.doc_tabs.tabText(0) == "Drawing1 *"


def test_tab_label_shows_filename_after_save(tmp_path):
    _app()
    window = MainWindow()
    _draw_a_line(window)
    target = tmp_path / "meu_desenho.dxf"
    with patch(
        "newsicad.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "DXF (*.dxf)"),
    ):
        window._save_file_as()
    assert window.doc_tabs.tabText(0) == "meu_desenho.dxf"


def test_switching_tabs_syncs_status_bar_toggles():
    _app()
    window = MainWindow()
    window.grid_button.toggle()  # desliga GRID na aba 1
    assert not window.canvas.grid_visible

    window._new_document()
    assert window.canvas.grid_visible  # aba 2 nasce com o padrão (GRID ligado)
    assert window.grid_button.isChecked()

    window.doc_tabs.setCurrentIndex(0)
    assert not window.grid_button.isChecked()
    assert not window.canvas.grid_visible


def test_close_current_tab_helper():
    _app()
    window = MainWindow()
    window._new_document()
    assert len(window.sessions) == 2
    window._close_current_tab()
    assert len(window.sessions) == 1


def test_new_tab_corner_button_opens_a_new_tab():
    # "+" na barra de abas (setCornerWidget) — a forma óbvia de abrir uma
    # aba nova olhando só pra barra de abas, sem precisar saber do Ctrl+N ou
    # ir procurar no menu/ribbon (ver newsicad/ui/main_window.py, corrigido
    # depois de o Hamilton reportar "não dá pra abrir uma aba nova").
    _app()
    window = MainWindow()
    button = window.doc_tabs.cornerWidget()
    assert button is not None
    assert button.text() == "+"
    button.click()
    assert len(window.sessions) == 2
