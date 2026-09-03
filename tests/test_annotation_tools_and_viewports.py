"""Testes dos itens pedidos por Hamilton em 2026-08-22: Annotation Scale,
Text Style (STYLE), Table Style (TABLESTYLE), Multileader Style
(MLEADERSTYLE), Find Text (FIND), Data Link (DATALINK) e Viewport
Configuration (VIEWPORTS/VM). Os comandos baseados em QDialog().exec() de
verdade (STYLE/TABLESTYLE/MLEADERSTYLE) não são exercitados via UI aqui —
mesmo padrão já usado pelo resto do projeto (LAYER/UNITS também nunca
tiveram teste de fluxo de diálogo, ver `_show_units_dialog`) — em vez disso
testamos que os comandos que CONSOMEM essas configurações (`Document.
text_styles`/`table_style`/`mleader_style`/`annotation_scale`) respeitam o
que está guardado no Document. FIND e DATALINK usam QInputDialog.getText/
QFileDialog.getOpenFileName, que SÃO mockáveis (mesmo padrão de
test_import_pdf_ui.py)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document, MLeaderStyle, TableStyle, TextStyle  # noqa: E402
from newsicad.core.entities import Line, Point, Table, Text  # noqa: E402
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# Annotation Scale + Text Style — MTEXT/LEADER/TABLE/FIELD respeitam Document
# ---------------------------------------------------------------------- #
def test_mtext_applies_current_text_style_and_annotation_scale():
    interp, doc = make_interpreter()
    doc.text_styles["Titulo"] = TextStyle(name="Titulo", font_family="Arial", height=5.0)
    doc.current_text_style = "Titulo"
    doc.annotation_scale = 2.0

    interp.start("MTEXT")
    interp.submit_point(Point(0, 0))
    interp.submit_text("Oi")
    assert not interp.active

    text = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert text.style == "Titulo"
    assert text.height == 2.5 * 2.0  # DEFAULT_TEXT_HEIGHT * annotation_scale


def test_leader_applies_mleader_style_height_and_scale():
    interp, doc = make_interpreter()
    doc.mleader_style = MLeaderStyle(text_height=4.0)
    doc.annotation_scale = 0.5

    interp.start("LEADER")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 5))
    interp.submit_text("")  # Enter termina pontos
    interp.submit_text("Nota")
    assert not interp.active

    text = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert text.height == 4.0 * 0.5


def test_table_applies_table_style_and_annotation_scale():
    interp, doc = make_interpreter()
    doc.table_style = TableStyle(show_borders=False, text_height=1.5)
    doc.annotation_scale = 2.0

    interp.start("TABLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # rows default
    interp.submit_text("")  # cols default
    interp.submit_text("")  # col_width default
    interp.submit_text("")  # row_height default
    interp.submit_text("EXIT")  # sai do preenchimento de células
    assert not interp.active

    table = next(e for e in doc.all_entities() if isinstance(e, Table))
    assert table.show_borders is False
    assert table.text_height == 1.5 * 2.0


def test_field_default_height_uses_annotation_scale():
    interp, doc = make_interpreter()
    doc.annotation_scale = 3.0

    interp.start("FIELD")
    interp.submit_text("Date")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # aceita a altura padrão sugerida
    assert not interp.active

    text = next(e for e in doc.all_entities() if isinstance(e, Text))
    assert text.height == 2.5 * 3.0


def test_table_without_borders_renders_no_grid_item():
    """Confere o lado do canvas de TABLESTYLE(show_borders=False): o grupo
    gráfico não deve ganhar o QGraphicsPathItem da grade."""
    _app()
    from newsicad.ui.canvas import CanvasView
    from newsicad.commands.interpreter import CommandInterpreter
    from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY

    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    canvas = CanvasView(doc, interp)

    table = doc.add_entity(
        Table(insertion_point=Point(0, 0), rows=2, cols=2, cells=[["a", "b"], ["c", "d"]], show_borders=False)
    )
    canvas.refresh_entities()
    group = canvas._entity_items[table.id]
    # só os 4 itens de texto de célula (QGraphicsPathItem com brush, ver
    # `_create_table_item`), nenhum item de grade (path só com pen)
    from PySide6.QtCore import Qt
    children = group.childItems()
    assert len(children) == 4
    assert all(child.brush().style() != Qt.BrushStyle.NoBrush for child in children)


# ---------------------------------------------------------------------- #
# FIND
# ---------------------------------------------------------------------- #
def test_find_selects_matching_text_entities():
    _app()
    window = MainWindow()
    match1 = window.document.add_entity(Text(insertion_point=Point(0, 0), content="Sala 101"))
    match2 = window.document.add_entity(Text(insertion_point=Point(10, 0), content="sala 202"))
    window.document.add_entity(Text(insertion_point=Point(20, 0), content="Corredor"))

    with patch("newsicad.ui.main_window.QInputDialog.getText", return_value=("sala", True)), patch(
        "newsicad.ui.main_window.QMessageBox.information"
    ):
        window._show_find_dialog()

    assert window.selection.ids == {match1.id, match2.id}


def test_find_with_no_matches_shows_info_and_selects_nothing():
    _app()
    window = MainWindow()
    window.document.add_entity(Text(insertion_point=Point(0, 0), content="Corredor"))

    with patch("newsicad.ui.main_window.QInputDialog.getText", return_value=("inexistente", True)), patch(
        "newsicad.ui.main_window.QMessageBox.information"
    ) as mock_info:
        window._show_find_dialog()

    assert not window.selection.ids
    mock_info.assert_called_once()


def test_find_cancelled_does_nothing():
    _app()
    window = MainWindow()
    window.document.add_entity(Text(insertion_point=Point(0, 0), content="Corredor"))

    with patch("newsicad.ui.main_window.QInputDialog.getText", return_value=("", False)):
        window._show_find_dialog()

    assert not window.selection.ids


# ---------------------------------------------------------------------- #
# DATALINK
# ---------------------------------------------------------------------- #
def test_datalink_imports_csv_as_table(tmp_path):
    _app()
    window = MainWindow()
    csv_path = tmp_path / "dados.csv"
    csv_path.write_text("Item,Qtd\nParafuso,100\nPorca,50\n", encoding="utf-8")

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(csv_path), "CSV Files (*.csv)"),
    ), patch("newsicad.ui.main_window.QMessageBox.information"):
        window._show_datalink_dialog()

    table = next(e for e in window.document.all_entities() if isinstance(e, Table))
    assert table.rows == 3
    assert table.cols == 2
    assert table.cells[0] == ["Item", "Qtd"]
    assert table.cells[1] == ["Parafuso", "100"]
    assert table.insertion_point.as_tuple() == (0.0, 0.0)


def test_datalink_cancelled_does_nothing():
    _app()
    window = MainWindow()
    with patch("newsicad.ui.main_window.QFileDialog.getOpenFileName", return_value=("", "")):
        window._show_datalink_dialog()
    assert not window.document.all_entities()


def test_datalink_empty_csv_warns_and_adds_nothing(tmp_path):
    _app()
    window = MainWindow()
    csv_path = tmp_path / "vazio.csv"
    csv_path.write_text("", encoding="utf-8")

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(csv_path), "CSV Files (*.csv)"),
    ), patch("newsicad.ui.main_window.QMessageBox.warning") as mock_warn:
        window._show_datalink_dialog()

    assert not window.document.all_entities()
    mock_warn.assert_called_once()


# ---------------------------------------------------------------------- #
# VIEWPORTS
# ---------------------------------------------------------------------- #
def test_apply_viewport_layout_two_vertical_creates_one_secondary_pane():
    _app()
    window = MainWindow()
    session = window._active_session()
    window._apply_viewport_layout(session, "Two: Vertical")
    try:
        assert len(session.viewport_panes) == 1
        assert session.tab_widget is not session.canvas
    finally:
        window._apply_viewport_layout(session, "Single")


def test_apply_viewport_layout_four_equal_creates_three_secondary_panes():
    _app()
    window = MainWindow()
    session = window._active_session()
    window._apply_viewport_layout(session, "Four: Equal")
    try:
        assert len(session.viewport_panes) == 3
    finally:
        window._apply_viewport_layout(session, "Single")


def test_apply_viewport_layout_single_removes_secondary_panes():
    _app()
    window = MainWindow()
    session = window._active_session()
    window._apply_viewport_layout(session, "Two: Horizontal")
    assert len(session.viewport_panes) == 1

    window._apply_viewport_layout(session, "Single")
    assert session.viewport_panes == []
    assert session.tab_widget is session.canvas


def test_secondary_viewport_panes_reflect_document_changes():
    """As panes extras têm timer de refresh próprio (400ms) — aqui
    chamamos refresh_entities() direto pra não depender de tempo real."""
    _app()
    window = MainWindow()
    session = window._active_session()
    window._apply_viewport_layout(session, "Two: Vertical")
    try:
        line = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
        window.canvas.refresh_entities()
        pane = session.viewport_panes[0]
        pane.refresh_entities()
        assert line.id in pane._entity_items
    finally:
        window._apply_viewport_layout(session, "Single")
