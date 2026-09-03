"""Testes de integração do IMPORTPDF na MainWindow (newsicad/ui/main_window.py
_start_import_pdf) — mesmo padrão de mock de QFileDialog usado em
test_menu_file_actions.py. A extração em si já é coberta por
tests/test_pdf_import.py; aqui o foco é a fiação com Document/undo/seleção."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

import fitz  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Text  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_pdf(path, page_sizes=((200, 200),), with_content: bool = True) -> None:
    doc = fitz.open()
    for width, height in page_sizes:
        page = doc.new_page(width=width, height=height)
        if with_content:
            page.draw_line((10, 10), (100, 100))
            page.insert_text((10, 50), "Texto")
    doc.save(str(path))
    doc.close()


def test_import_pdf_adds_entities_and_selects_them(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "single.pdf"
    _make_pdf(path)

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ):
        window._start_import_pdf()

    entities = list(window.document.all_entities())
    assert any(isinstance(e, Line) for e in entities)
    assert any(isinstance(e, Text) for e in entities)
    assert window.selection.ids == {e.id for e in entities}


def test_import_pdf_undoable(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "single.pdf"
    _make_pdf(path)

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ):
        window._start_import_pdf()
    assert len(window.document.entities) > 0

    window._do_undo()
    assert len(window.document.entities) == 0


def test_import_pdf_cancelled_dialog_does_nothing():
    _app()
    window = MainWindow()

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        window._start_import_pdf()

    assert len(window.document.entities) == 0


def test_import_pdf_invalid_file_shows_error_and_adds_nothing(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "not_a_pdf.pdf"
    path.write_text("lixo, não é pdf")

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ), patch("newsicad.ui.main_window.QMessageBox.critical") as mock_critical:
        window._start_import_pdf()

    mock_critical.assert_called_once()
    assert len(window.document.entities) == 0


def test_import_pdf_empty_page_shows_info_and_adds_nothing(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "empty.pdf"
    _make_pdf(path, with_content=False)

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ), patch("newsicad.ui.main_window.QMessageBox.information") as mock_info:
        window._start_import_pdf()

    mock_info.assert_called_once()
    assert len(window.document.entities) == 0


def test_import_pdf_multi_page_prompts_and_uses_chosen_page(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "multi.pdf"
    # página 1 vazia, página 2 com conteúdo — só devia importar da 2 se
    # escolhermos a página 2
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    page2 = doc.new_page(width=200, height=200)
    page2.draw_line((10, 10), (100, 100))
    doc.save(str(path))
    doc.close()

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ), patch(
        "newsicad.ui.main_window.QInputDialog.getInt",
        return_value=(2, True),
    ):
        window._start_import_pdf()

    entities = list(window.document.all_entities())
    assert len(entities) == 1
    assert isinstance(entities[0], Line)


def test_import_pdf_multi_page_dialog_cancelled_does_nothing(tmp_path):
    _app()
    window = MainWindow()
    path = tmp_path / "multi2.pdf"
    _make_pdf(path, page_sizes=((200, 200), (200, 200)))

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PDF (*.pdf)"),
    ), patch(
        "newsicad.ui.main_window.QInputDialog.getInt",
        return_value=(1, False),
    ):
        window._start_import_pdf()

    assert len(window.document.entities) == 0
