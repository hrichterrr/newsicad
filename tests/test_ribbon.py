"""Testes do ribbon estilo AutoCAD: abas presentes e botões disparando os
mesmos comandos que a linha de comando/menu clássico."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ribbon_has_expected_tabs():
    _app()
    window = MainWindow()
    tabs = [window.ribbon.tabText(i) for i in range(window.ribbon.count())]
    assert tabs == ["File", "Home", "Insert", "Annotate", "View"]


def _find_button(window: MainWindow, text: str) -> QToolButton:
    for button in window.ribbon.findChildren(QToolButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Botão '{text}' não encontrado no ribbon")


def test_draw_button_starts_matching_command():
    _app()
    window = MainWindow()
    _find_button(window, "Circle").click()
    assert window.interpreter.active
    assert window.interpreter.last_command_name == "CIRCLE"


def test_modify_button_disabled_without_implementation():
    _app()
    window = MainWindow()
    button = _find_button(window, "Match Prop")
    assert not button.isEnabled()


def test_view_tab_zoom_buttons_call_canvas_methods():
    _app()
    window = MainWindow()
    initial_scale = window.canvas.transform().m11()
    _find_button(window, "Zoom In").click()
    assert window.canvas.transform().m11() > initial_scale


def test_annotate_buttons_start_matching_commands():
    _app()
    window = MainWindow()
    cases = [
        ("Multiline Text", "MTEXT"),
        ("Linear", "DIMLINEAR"),
        ("Aligned", "DIMALIGNED"),
        ("Angular", "DIMANGULAR"),
        ("Radius", "DIMRADIUS"),
        ("Diameter", "DIMDIAMETER"),
        ("Leader", "LEADER"),
    ]
    for label, command in cases:
        window.interpreter.cancel()
        _find_button(window, label).click()
        assert window.interpreter.active, f"botão '{label}' não iniciou nenhum comando"
        assert window.interpreter.last_command_name == command


def test_hatch_button_starts_hatch_command():
    _app()
    window = MainWindow()
    _find_button(window, "Hatch").click()
    assert window.interpreter.active
    assert window.interpreter.last_command_name == "HATCH"


def test_grid_toggle_syncs_with_status_bar_button():
    _app()
    window = MainWindow()
    ribbon_grid = _find_button(window, "Grid")
    assert ribbon_grid.isChecked() == window.grid_button.isChecked()

    ribbon_grid.toggle()
    assert window.grid_button.isChecked() == ribbon_grid.isChecked()
    assert window.canvas.grid_visible == ribbon_grid.isChecked()
