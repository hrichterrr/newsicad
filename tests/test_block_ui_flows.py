"""Testes de integração dos fluxos de UI de Prioridade 2/3/4: Block Editor
(BEDIT), referências externas (XREF/EXTERNALREFERENCES), imagem raster
(IMAGEATTACH). QFileDialog/QInputDialog são mockados (mesmo padrão de
tests/test_menu_file_actions.py) pra rodar sem diálogo real."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import BlockReference, Circle, ImageReference, Line, Point  # noqa: E402
from newsicad.io.dxf_io import save_dxf  # noqa: E402
from newsicad.ui.block_editor_dialog import BlockEditorDialog  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402
from newsicad.ui.xref_panel import XrefPanel  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------- #
# BEDIT / Block Editor
# ---------------------------------------------------------------------- #
def test_bedit_dialog_save_updates_block_definition_and_instances():
    app = _app()
    window = MainWindow()
    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 1))])
    window.document.add_entity(BlockReference(block_name="CHAIR", insertion_point=Point(0, 0)))

    dialog = BlockEditorDialog(window, "CHAIR")
    assert len(dialog.document.entities) == 1  # cópia da definição original

    dialog._handle_text_submitted("LINE")
    dialog._handle_canvas_point(Point(5, 5))
    dialog._handle_canvas_point(Point(6, 6))
    dialog._handle_text_submitted("")
    app.processEvents()
    assert len(dialog.document.entities) == 2

    dialog._save_and_close()
    assert len(window.document.block_definitions["CHAIR"]) == 2


def test_bedit_editing_temp_document_does_not_touch_original_until_save():
    app = _app()
    window = MainWindow()
    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 1))])

    dialog = BlockEditorDialog(window, "CHAIR")
    dialog._handle_text_submitted("ERASE")
    dialog._handle_text_submitted("")  # sem seleção -> não apaga nada, mas exercita o comando
    app.processEvents()

    # original intacta antes do Save
    assert len(window.document.block_definitions["CHAIR"]) == 1


def test_start_bedit_opens_dialog_for_chosen_block():
    # Nota: mockamos a CLASSE inteira (não um método individual como .exec())
    # — trocar um método de uma QDialog real via unittest.mock.patch mexe na
    # tabela de meta-objeto do shiboken e pode segfaultar na próxima
    # construção da classe; mockar a classe inteira evita instanciar QDialog.
    app = _app()
    window = MainWindow()
    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 1))])

    with patch("newsicad.ui.main_window.QInputDialog.getItem", return_value=("CHAIR", True)), patch(
        "newsicad.ui.main_window.BlockEditorDialog"
    ) as mock_dialog_cls:
        window._start_bedit()
        mock_dialog_cls.assert_called_once_with(window, "CHAIR")
        mock_dialog_cls.return_value.exec.assert_called_once()


def test_start_bedit_with_no_blocks_shows_message_instead_of_crashing():
    app = _app()
    window = MainWindow()

    with patch("newsicad.ui.main_window.QMessageBox.information") as mock_info:
        window._start_bedit()
        mock_info.assert_called_once()


# ---------------------------------------------------------------------- #
# XREF
# ---------------------------------------------------------------------- #
def test_xref_command_inserts_block_reference_marked_as_xref():
    app = _app()
    window = MainWindow()

    source_doc = Document()
    source_doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))

    with tempfile.TemporaryDirectory() as tmp_dir:
        xref_path = Path(tmp_dir) / "external.dxf"
        save_dxf(source_doc, xref_path)

        with patch(
            "newsicad.ui.main_window.QFileDialog.getOpenFileName",
            return_value=(str(xref_path), "DXF (*.dxf)"),
        ):
            window._start_xref()

        assert window.interpreter.active
        window._handle_canvas_point(Point(10, 10))

        refs = [e for e in window.document.all_entities() if isinstance(e, BlockReference)]
        assert len(refs) == 1
        assert refs[0].is_xref is True
        assert refs[0].xref_path == xref_path
        assert refs[0].insertion_point.as_tuple() == (10, 10)
        assert refs[0].block_name in window.document.block_definitions
        assert len(window.document.block_definitions[refs[0].block_name]) == 1


def test_xref_cancelled_dialog_does_nothing():
    app = _app()
    window = MainWindow()

    with patch("newsicad.ui.main_window.QFileDialog.getOpenFileName", return_value=("", "")):
        window._start_xref()

    assert not window.interpreter.active
    assert window.document.block_definitions == {}


def test_xref_panel_lists_and_reloads_reference():
    app = _app()
    window = MainWindow()

    source_doc = Document()
    source_doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))

    with tempfile.TemporaryDirectory() as tmp_dir:
        xref_path = Path(tmp_dir) / "ext.dxf"
        save_dxf(source_doc, xref_path)

        block_name = "XREF:ext"
        window.document.define_block(block_name, source_doc.all_entities())
        window.document.add_entity(
            BlockReference(
                block_name=block_name, insertion_point=Point(0, 0), is_xref=True, xref_path=xref_path
            )
        )

        panel = XrefPanel(window)
        assert panel.table.rowCount() == 1
        assert panel.table.item(0, 0).text() == block_name
        assert panel.table.item(0, 1).text() == str(xref_path)

        # o arquivo original "muda" (ganha mais uma entidade) e Reload deve
        # trazer a definição atualizada.
        source_doc.add_entity(Circle(center=Point(0, 0), radius=1))
        save_dxf(source_doc, xref_path)

        panel.table.selectRow(0)
        with patch("newsicad.ui.xref_panel.QMessageBox.information"):
            panel._reload_selected()

        assert len(window.document.block_definitions[block_name]) == 2


# ---------------------------------------------------------------------- #
# IMAGEATTACH
# ---------------------------------------------------------------------- #
def test_imageattach_inserts_image_reference_with_defaults():
    app = _app()
    window = MainWindow()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Conteúdo não precisa ser um PNG válido pro teste: ImageReference só
        # guarda o Path — a renderização (QPixmap) trata arquivo inválido
        # mostrando um retângulo tracejado (ver CanvasView._create_image_item).
        img_path = Path(tmp_dir) / "logo.png"
        img_path.write_bytes(b"not-a-real-png")

        with patch(
            "newsicad.ui.main_window.QFileDialog.getOpenFileName",
            return_value=(str(img_path), "Imagens (*.png)"),
        ):
            window._start_imageattach()

        assert window.interpreter.active
        window._handle_canvas_point(Point(2, 2))
        window._handle_text_submitted("")  # width default <100>
        window._handle_text_submitted("")  # height default <100>

        images = [e for e in window.document.all_entities() if isinstance(e, ImageReference)]
        assert len(images) == 1
        assert images[0].insertion_point.as_tuple() == (2, 2)
        assert images[0].width == 100.0
        assert images[0].height == 100.0
        assert images[0].path == img_path

        # Não deve travar renderizando com um arquivo de imagem inválido.
        window.canvas.refresh_entities()
        app.processEvents()


def test_imageattach_cancelled_dialog_does_nothing():
    app = _app()
    window = MainWindow()

    with patch("newsicad.ui.main_window.QFileDialog.getOpenFileName", return_value=("", "")):
        window._start_imageattach()

    assert not window.interpreter.active
    assert window.document.all_entities() == []
