"""Testes do LayoutViewerDialog (View > Ver pranchas...) — achado do grupo
de feedback do NewSicad em 09/09/2026: arquivos onde o Model space vinha
quase vazio e o desenho de verdade estava todo em pranchas de paper space
(plantas FABIO E JULIANA e PATRICIA E FABIO). Mesmo padrão de teste do
Block Editor (tests/test_block_ui_flows.py): QApplication offscreen,
QInputDialog/a própria classe do diálogo mockados quando aplicável."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.ui.layout_viewer_dialog import LayoutViewerDialog  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _document_with_layout() -> Document:
    document = Document()
    document.add_layer("MODEL_LAYER")
    document.define_block("LOGO", [Line(start=Point(0, 0), end=Point(1, 1))])
    document.layouts["01 - Planta"] = {
        "a": Circle(layer="0", center=Point(5, 5), radius=2),
    }
    return document


def test_layout_viewer_dialog_loads_layout_entities_as_clones():
    _app()
    document = _document_with_layout()

    dialog = LayoutViewerDialog(document, "01 - Planta")

    assert len(dialog.document.entities) == 1
    loaded = next(iter(dialog.document.entities.values()))
    assert isinstance(loaded, Circle)
    assert loaded.center.x == 5
    # clone_entity gera um id novo — não é o mesmo objeto do original.
    original = document.layouts["01 - Planta"]["a"]
    assert loaded is not original
    assert loaded.id != original.id


def test_layout_viewer_dialog_shares_layers_and_blocks_by_reference():
    """Camada e bloco são do ARQUIVO INTEIRO, não da prancha — precisam ser
    o MESMO objeto do documento principal, não uma cópia, senão uma camada
    nova criada dentro da prancha nunca apareceria no Model ao fechar."""
    _app()
    document = _document_with_layout()

    dialog = LayoutViewerDialog(document, "01 - Planta")

    assert dialog.document.layers is document.layers
    assert dialog.document.block_definitions is document.block_definitions
    assert "MODEL_LAYER" in dialog.document.layers
    assert "LOGO" in dialog.document.block_definitions


def test_layout_viewer_save_writes_edits_back_to_main_document():
    app = _app()
    document = _document_with_layout()
    dialog = LayoutViewerDialog(document, "01 - Planta")

    dialog._handle_text_submitted("LINE")
    dialog._handle_canvas_point(Point(0, 0))
    dialog._handle_canvas_point(Point(10, 10))
    dialog._handle_text_submitted("")
    app.processEvents()
    assert len(dialog.document.entities) == 2

    # documento principal intacto antes do Save
    assert len(document.layouts["01 - Planta"]) == 1
    revision_before = document.revision

    dialog._save_and_close()

    assert len(document.layouts["01 - Planta"]) == 2
    assert document.revision > revision_before


def test_layout_viewer_cancel_does_not_touch_main_document():
    app = _app()
    document = _document_with_layout()
    dialog = LayoutViewerDialog(document, "01 - Planta")

    dialog._handle_text_submitted("ERASE")
    dialog._handle_text_submitted("")  # sem seleção -> não apaga nada
    app.processEvents()

    dialog.reject()

    assert len(document.layouts["01 - Planta"]) == 1


def test_show_layouts_dialog_with_no_layouts_shows_message_instead_of_crashing():
    _app()
    window = MainWindow()

    with patch("newsicad.ui.main_window.QMessageBox.information") as mock_info:
        window._show_layouts_dialog()
        mock_info.assert_called_once()


def test_show_layouts_dialog_with_single_layout_skips_the_choice_prompt():
    _app()
    window = MainWindow()
    window.document.layouts["01 - Planta"] = {"a": Circle(layer="0", center=Point(0, 0), radius=1)}

    with patch("newsicad.ui.main_window.QInputDialog.getItem") as mock_get_item, patch(
        "newsicad.ui.main_window.LayoutViewerDialog"
    ) as mock_dialog_cls:
        window._show_layouts_dialog()
        mock_get_item.assert_not_called()
        mock_dialog_cls.assert_called_once_with(window.document, "01 - Planta", parent=window)
        mock_dialog_cls.return_value.exec.assert_called_once()


def test_show_layouts_dialog_with_multiple_layouts_prompts_choice():
    _app()
    window = MainWindow()
    window.document.layouts["00 - Capa"] = {"a": Circle(layer="0", center=Point(0, 0), radius=1)}
    window.document.layouts["01 - Planta"] = {"b": Circle(layer="0", center=Point(1, 1), radius=1)}

    with patch(
        "newsicad.ui.main_window.QInputDialog.getItem", return_value=("01 - Planta", True)
    ) as mock_get_item, patch("newsicad.ui.main_window.LayoutViewerDialog") as mock_dialog_cls:
        window._show_layouts_dialog()
        mock_get_item.assert_called_once()
        mock_dialog_cls.assert_called_once_with(window.document, "01 - Planta", parent=window)


def test_show_layouts_dialog_cancelled_choice_does_nothing():
    _app()
    window = MainWindow()
    window.document.layouts["00 - Capa"] = {"a": Circle(layer="0", center=Point(0, 0), radius=1)}
    window.document.layouts["01 - Planta"] = {"b": Circle(layer="0", center=Point(1, 1), radius=1)}

    with patch("newsicad.ui.main_window.QInputDialog.getItem", return_value=("", False)), patch(
        "newsicad.ui.main_window.LayoutViewerDialog"
    ) as mock_dialog_cls:
        window._show_layouts_dialog()
        mock_dialog_cls.assert_not_called()
