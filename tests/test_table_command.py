"""Testes do comando TABLE/TB (core/entities.py:Table, geometria em
core/geometry_ops.py, renderização em ui/canvas.py, gravação decomposta em
Line+Text em io/dxf_io.py)."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Line, Point, Table, Text  # noqa: E402
from newsicad.core.geometry_ops import mirror_entity, rotate_entity, scale_entity, translate_entity  # noqa: E402
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------- #
# comando
# ---------------------------------------------------------------------- #
def test_table_command_creates_table_with_typed_cells():
    interp, doc = make_interpreter()
    interp.start("TB")
    interp.submit_point(Point(0, 0))
    interp.submit_text("2")  # rows
    interp.submit_text("2")  # cols
    interp.submit_text("3")  # col width
    interp.submit_text("1")  # row height
    interp.submit_text("A1")
    interp.submit_text("B1")
    interp.submit_text("A2")
    interp.submit_text("B2")
    assert not interp.active

    tables = [e for e in doc.all_entities() if isinstance(e, Table)]
    assert len(tables) == 1
    table = tables[0]
    assert table.rows == 2 and table.cols == 2
    assert table.col_width == pytest.approx(3)
    assert table.row_height == pytest.approx(1)
    assert table.cells == [["A1", "B1"], ["A2", "B2"]]


def test_table_command_enter_leaves_cell_blank():
    interp, doc = make_interpreter()
    interp.start("TABLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("1")
    interp.submit_text("2")
    interp.submit_text("2")
    interp.submit_text("1")
    interp.submit_text("")  # célula (1,1) em branco
    interp.submit_text("valor")
    assert not interp.active

    table = next(e for e in doc.all_entities() if isinstance(e, Table))
    assert table.cells == [["", "valor"]]


def test_table_command_exit_early_stops_filling_but_creates_table():
    interp, doc = make_interpreter()
    interp.start("TABLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("2")
    interp.submit_text("2")
    interp.submit_text("2")
    interp.submit_text("1")
    interp.submit_text("primeira")
    interp.submit_text("eXit")
    assert not interp.active

    table = next(e for e in doc.all_entities() if isinstance(e, Table))
    assert table.cells == [["primeira", ""], ["", ""]]


def test_table_command_uses_defaults_on_enter():
    interp, doc = make_interpreter()
    interp.start("TABLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # rows default 3
    interp.submit_text("")  # cols default 3
    interp.submit_text("")  # col width default 2.5
    interp.submit_text("")  # row height default 1.0
    for _ in range(9):
        interp.submit_text("")
    assert not interp.active
    table = next(e for e in doc.all_entities() if isinstance(e, Table))
    assert (table.rows, table.cols) == (3, 3)
    assert table.col_width == pytest.approx(2.5)
    assert table.row_height == pytest.approx(1.0)


def test_table_command_rejects_non_positive_dimensions():
    interp, doc = make_interpreter()
    interp.start("TABLE")
    interp.submit_point(Point(0, 0))
    interp.submit_text("2")
    interp.submit_text("2")
    interp.submit_text("0")
    interp.submit_text("1")
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, Table)]


# ---------------------------------------------------------------------- #
# geometria (translate/rotate/scale/mirror)
# ---------------------------------------------------------------------- #
def test_translate_table_moves_insertion_point():
    table = Table(insertion_point=Point(0, 0), rows=2, cols=2, col_width=1, row_height=1)
    translate_entity(table, 5, 3)
    assert table.insertion_point == Point(5, 3)


def test_rotate_table_updates_point_and_rotation():
    table = Table(insertion_point=Point(1, 0), rows=1, cols=1, col_width=1, row_height=1)
    rotate_entity(table, Point(0, 0), math.pi / 2)
    assert table.insertion_point.x == pytest.approx(0)
    assert table.insertion_point.y == pytest.approx(1)
    assert table.rotation == pytest.approx(math.pi / 2)


def test_scale_table_scales_dimensions():
    table = Table(insertion_point=Point(0, 0), rows=1, cols=1, col_width=2, row_height=1, text_height=0.5)
    scale_entity(table, Point(0, 0), 2.0)
    assert table.col_width == pytest.approx(4)
    assert table.row_height == pytest.approx(2)
    assert table.text_height == pytest.approx(1.0)


def test_mirror_table_reflects_point():
    table = Table(insertion_point=Point(2, 3), rows=1, cols=1, col_width=1, row_height=1)
    mirrored = mirror_entity(table, Point(0, 0), Point(0, 1))
    assert mirrored.insertion_point.x == pytest.approx(-2)
    assert mirrored.insertion_point.y == pytest.approx(3)


# ---------------------------------------------------------------------- #
# canvas: renderização / hit-test / bbox
# ---------------------------------------------------------------------- #
def test_table_renders_and_is_hit_testable():
    app = _app()
    window = MainWindow()
    table = window.document.add_entity(
        Table(insertion_point=Point(0, 0), rows=2, cols=2, col_width=4, row_height=2, cells=[["a", "b"], ["c", "d"]])
    )
    window.canvas.refresh_entities()
    app.processEvents()

    assert table.id in window.canvas._entity_items
    # ponto dentro da grade (canto sup.-esq. em (0,0), estende +x e -y)
    assert window.canvas._hit_test(Point(2, -1)) == table.id
    # ponto bem fora
    assert window.canvas._hit_test(Point(100, 100)) is None


def test_table_bbox_accounts_for_size():
    app = _app()
    window = MainWindow()
    window.document.add_entity(
        Table(insertion_point=Point(0, 0), rows=2, cols=3, col_width=2, row_height=1)
    )
    window.canvas.refresh_entities()
    app.processEvents()

    table = next(e for e in window.document.all_entities() if isinstance(e, Table))
    bbox = window.canvas._entity_bbox_scene(table)
    assert bbox.width() == pytest.approx(6)  # 3 cols * 2
    assert bbox.height() == pytest.approx(2)  # 2 rows * 1


def test_table_deselect_restores_own_color():
    app = _app()
    window = MainWindow()
    window.document.add_layer("TABELAS", color="#00ffff")
    table = window.document.add_entity(
        Table(insertion_point=Point(0, 0), rows=1, cols=1, col_width=1, row_height=1, layer="TABELAS")
    )
    window.canvas.refresh_entities()
    app.processEvents()

    window.selection.set({table.id})
    window.canvas.refresh_selection_highlight()
    window.selection.clear()
    window.canvas.refresh_selection_highlight()

    item = window.canvas._entity_items[table.id]
    grid_child = item.childItems()[0]
    assert grid_child.pen().color().name() == "#00ffff"


# ---------------------------------------------------------------------- #
# DXF: decomposto em Line (grade) + Text (células) — não volta como Table
# ---------------------------------------------------------------------- #
def test_table_saves_as_lines_and_texts(tmp_path):
    from newsicad.io.dxf_io import load_dxf, save_dxf

    doc = Document()
    doc.add_entity(
        Table(insertion_point=Point(0, 0), rows=2, cols=2, col_width=3, row_height=1, cells=[["x", ""], ["", "y"]])
    )
    path = tmp_path / "table.dxf"
    save_dxf(doc, path)
    reloaded, skipped = load_dxf(path)

    assert skipped == 0
    lines = [e for e in reloaded.all_entities() if isinstance(e, Line)]
    texts = [e for e in reloaded.all_entities() if isinstance(e, Text)]
    # grade: (rows+1) horizontais + (cols+1) verticais = 3 + 3 = 6
    assert len(lines) == 6
    assert {t.content for t in texts} == {"x", "y"}
