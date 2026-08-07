"""Testes do painel de camadas (comando LAYER/LA, newsicad/ui/layer_panel.py):
listagem, toggle de visibilidade/trava via checkbox, definir camada atual
por duplo clique, e criar camada nova."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox  # noqa: E402

from newsicad.ui.layer_panel import _COL_LOCKED, _COL_NAME, _COL_VISIBLE  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _row_of(window: MainWindow, layer_name: str) -> int:
    table = window.layer_dock.table
    for row in range(table.rowCount()):
        if table.item(row, _COL_NAME).text() == layer_name:
            return row
    raise AssertionError(f"Camada '{layer_name}' não está na tabela")


def test_layer_panel_lists_all_document_layers():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.document.add_layer("ELETRICA")
    window.layer_dock.refresh()

    names = {
        window.layer_dock.table.item(row, _COL_NAME).text()
        for row in range(window.layer_dock.table.rowCount())
    }
    assert names == {"0", "PAREDES", "ELETRICA"}


def test_current_layer_name_is_bold_and_others_are_not():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()

    current_row = _row_of(window, "0")
    other_row = _row_of(window, "PAREDES")
    assert window.layer_dock.table.item(current_row, _COL_NAME).font().bold()
    assert not window.layer_dock.table.item(other_row, _COL_NAME).font().bold()


def test_visible_checkbox_toggles_layer_and_refreshes_canvas():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()

    row = _row_of(window, "PAREDES")
    checkbox = window.layer_dock.table.cellWidget(row, _COL_VISIBLE).findChild(QCheckBox)
    assert checkbox.isChecked()

    checkbox.setChecked(False)
    assert window.document.layers["PAREDES"].visible is False


def test_locked_checkbox_toggles_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()

    row = _row_of(window, "PAREDES")
    checkbox = window.layer_dock.table.cellWidget(row, _COL_LOCKED).findChild(QCheckBox)
    assert not checkbox.isChecked()

    checkbox.setChecked(True)
    assert window.document.layers["PAREDES"].locked is True


def test_double_click_name_sets_current_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()
    assert window.document.current_layer == "0"

    row = _row_of(window, "PAREDES")
    window.layer_dock._handle_double_click(row, _COL_NAME)

    assert window.document.current_layer == "PAREDES"
    assert window.layer_dock.table.item(row, _COL_NAME).font().bold()


def test_new_layer_button_creates_layer():
    _app()
    window = MainWindow()
    assert "FORRO" not in window.document.layers

    window.layer_dock._create_layer_with_name("FORRO")
    assert "FORRO" in window.document.layers
    assert any(
        window.layer_dock.table.item(row, _COL_NAME).text() == "FORRO"
        for row in range(window.layer_dock.table.rowCount())
    )


def test_layer_command_shows_and_raises_the_dock():
    _app()
    window = MainWindow()
    window.show()
    window.layer_dock.hide()
    assert not window.layer_dock.isVisible()

    window._start_command("LAYER")
    assert window.layer_dock.isVisible()


# ---------------------------------------------------------------------- #
# renomear (REN / clique direito na tabela)
# ---------------------------------------------------------------------- #
def test_rename_layer_with_names_updates_document_and_table():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()

    window.layer_dock._rename_layer_with_names("PAREDES", "ALVENARIA")

    assert "ALVENARIA" in window.document.layers
    assert "PAREDES" not in window.document.layers
    names = {
        window.layer_dock.table.item(row, _COL_NAME).text()
        for row in range(window.layer_dock.table.rowCount())
    }
    assert "ALVENARIA" in names


def test_rename_layer_with_names_ignores_empty_or_unchanged_name():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()

    window.layer_dock._rename_layer_with_names("PAREDES", "  ")
    assert "PAREDES" in window.document.layers

    window.layer_dock._rename_layer_with_names("PAREDES", "PAREDES")
    assert "PAREDES" in window.document.layers


def test_rename_command_targets_current_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.document.set_current_layer("PAREDES")

    window.layer_dock.prompt_rename_current_layer = lambda: window.layer_dock._rename_layer_with_names(
        "PAREDES", "ALVENARIA"
    )
    window._start_command("RENAME")

    assert "ALVENARIA" in window.document.layers
    assert window.document.current_layer == "ALVENARIA"
