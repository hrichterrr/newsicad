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
    assert tabs == ["Home", "Insert", "Annotate", "View", "Manage", "Output"]


def _find_button(window: MainWindow, text: str) -> QToolButton:
    # Rótulos de botão grande podem ter duas linhas ("Match\nProperties");
    # botões só-ícone mantêm o rótulo em text() sem desenhá-lo.
    for button in window.ribbon.findChildren(QToolButton):
        if button.text().replace("\n", " ") == text:
            return button
    raise AssertionError(f"Botão '{text}' não encontrado no ribbon")


def test_draw_button_starts_matching_command():
    _app()
    window = MainWindow()
    _find_button(window, "Circle").click()
    assert window.interpreter.active
    assert window.interpreter.last_command_name == "CIRCLE"


def test_match_prop_button_starts_matchprop_command():
    _app()
    window = MainWindow()
    _find_button(window, "Match Properties").click()
    assert window.interpreter.active
    assert window.interpreter.last_command_name == "MATCHPROP"


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


def test_home_tab_follows_autocad_panel_order():
    """Aba Home com os dez painéis do AutoCAD 2020, na ordem dele (proposta
    aprovada em docs/design/ribbon-proposta-2026-09.html)."""
    from PySide6.QtWidgets import QWidget

    _app()
    window = MainWindow()
    home = window.ribbon.widget(0)
    titles = []
    for widget in home.findChildren(QWidget):  # ordem da árvore = da esquerda pra direita
        if widget.objectName() == "panelTitle":
            titles.append(widget.text().replace(" ▾", ""))
    assert titles == [
        "Draw", "Modify", "Annotation", "Layers", "Block",
        "Properties", "Groups", "Utilities", "Clipboard", "View",
    ]


def test_not_implemented_buttons_are_disabled_with_tooltip():
    from newsicad.ui.ribbon import NOT_IMPLEMENTED_TIP

    _app()
    window = MainWindow()
    group = _find_button(window, "Group")
    assert not group.isEnabled()
    assert group.toolTip() == NOT_IMPLEMENTED_TIP


def test_layer_combo_sets_current_layer_and_follows_panel():
    _app()
    window = MainWindow()
    window.document.add_layer("PAREDES")
    window.layer_dock.refresh()
    combo = window.layer_combo
    assert combo.findText("PAREDES") >= 0

    combo.setCurrentIndex(combo.findText("PAREDES"))
    combo.activated.emit(combo.currentIndex())
    assert window.document.current_layer == "PAREDES"

    window.document.set_current_layer("0")
    window.layer_dock.refresh()
    assert combo.currentText() == "0"


def test_status_bar_toggles_have_icons():
    _app()
    window = MainWindow()
    for button in (window.grid_button, window.snap_button, window.ortho_button, window.polar_button,
                   window.osnap_button, window.dynamic_input_button):
        assert not button.icon().isNull()


def test_svg_icons_render_for_every_ribbon_button():
    _app()
    window = MainWindow()
    for button in window.ribbon.findChildren(QToolButton):
        if button.objectName() in ("big", "small", "iconOnly"):
            assert not button.icon().isNull(), f"botão '{button.text()}' sem ícone"


def test_split_buttons_keep_their_flyout_menus():
    """QToolButton.setMenu não toma posse do QMenu — sem parent o menu era
    coletado e o ▾ do split-button ficava morto (bug pego no redesenho)."""
    import gc

    _app()
    window = MainWindow()
    gc.collect()
    trim = _find_button(window, "Trim")
    assert trim.menu() is not None
    labels = [a.text() for a in trim.menu().actions()]
    assert labels == ["Trim", "Extend"]

    window.interpreter.cancel()
    trim.menu().actions()[1].trigger()
    assert window.interpreter.last_command_name == "EXTEND"


def test_panel_slide_out_lists_secondary_commands():
    from PySide6.QtWidgets import QFrame

    _app()
    window = MainWindow()
    home = window.ribbon.widget(0)
    draw_title = [b for b in home.findChildren(QToolButton) if b.text() == "Draw ▾"][0]
    slide = draw_title.parent()._slide_out
    assert isinstance(slide, QFrame)
    labels = {b.text() for b in slide.findChildren(QToolButton)}
    assert {"Spline", "Construction Line", "Ray", "Donut", "Multiline", "Boundary"} <= labels
