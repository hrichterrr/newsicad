"""Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension,
Modify, Help). Itens que ainda não têm comando implementado ficam
desabilitados, com tooltip explicando isso — não somem da interface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QMenuBar, QMessageBox

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

GITHUB_URL = "https://github.com/hrichterrr/newsicad"
NOT_IMPLEMENTED_TIP = "Ainda não implementado — previsto para um próximo marco do NewSIcad."


def _add_command_action(menu, label: str, command_name: str, window: "MainWindow", shortcut: str | None = None) -> QAction:
    action = QAction(label, window)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
    action.triggered.connect(lambda: window._start_command(command_name))
    menu.addAction(action)
    return action


def _add_disabled(menu, label: str) -> QAction:
    action = QAction(label, menu)
    action.setEnabled(False)
    action.setToolTip(NOT_IMPLEMENTED_TIP)
    action.setStatusTip(NOT_IMPLEMENTED_TIP)
    menu.addAction(action)
    return action


def build_menu_bar(window: "MainWindow") -> QMenuBar:
    menu_bar = QMenuBar(window)

    _build_file_menu(menu_bar, window)
    _build_edit_menu(menu_bar, window)
    _build_view_menu(menu_bar, window)
    _build_insert_menu(menu_bar, window)
    _build_draw_menu(menu_bar, window)
    _build_dimension_menu(menu_bar, window)
    _build_modify_menu(menu_bar, window)
    _build_help_menu(menu_bar, window)

    return menu_bar


def _build_file_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&File")

    new_action = QAction("New", window)
    new_action.setShortcut(QKeySequence("Ctrl+N"))
    new_action.triggered.connect(window._new_document)
    menu.addAction(new_action)

    open_action = QAction("Open...", window)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(window._open_file)
    menu.addAction(open_action)

    save_action = QAction("Save", window)
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.triggered.connect(window._save_file)
    menu.addAction(save_action)

    save_as_action = QAction("Save As...", window)
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.triggered.connect(window._save_file_as)
    menu.addAction(save_as_action)

    menu.addSeparator()
    export_pdf_action = QAction("Print/Export PDF...", window)
    export_pdf_action.setShortcut(QKeySequence("Ctrl+P"))
    export_pdf_action.triggered.connect(window._export_pdf)
    menu.addAction(export_pdf_action)

    menu.addSeparator()
    exit_action = QAction("Exit", window)
    exit_action.triggered.connect(window.close)
    menu.addAction(exit_action)


def _build_edit_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Edit")

    undo_action = QAction("Undo", window)
    undo_action.setShortcut(QKeySequence("Ctrl+Z"))
    undo_action.triggered.connect(window._do_undo)
    menu.addAction(undo_action)

    redo_action = QAction("Redo", window)
    redo_action.setShortcut(QKeySequence("Ctrl+Y"))
    redo_action.triggered.connect(window._do_redo)
    menu.addAction(redo_action)

    menu.addSeparator()
    copy_base_action = QAction("Copy with Base Point", window)
    copy_base_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
    copy_base_action.triggered.connect(lambda: window._start_command("COPY"))
    menu.addAction(copy_base_action)

    menu.addSeparator()
    select_all_action = QAction("Select All", window)
    select_all_action.setShortcut(QKeySequence("Ctrl+A"))
    select_all_action.triggered.connect(window._select_all)
    menu.addAction(select_all_action)


def _build_view_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&View")

    zoom_in = QAction("Zoom In", window)
    zoom_in.triggered.connect(window.canvas.zoom_in)
    menu.addAction(zoom_in)

    zoom_out = QAction("Zoom Out", window)
    zoom_out.triggered.connect(window.canvas.zoom_out)
    menu.addAction(zoom_out)

    zoom_extents = QAction("Zoom Extents", window)
    zoom_extents.triggered.connect(window.canvas.zoom_extents)
    menu.addAction(zoom_extents)

    menu.addSeparator()
    for label, button, shortcut in [
        ("Grid", window.grid_button, "F7"),
        ("Snap", window.snap_button, "F9"),
        ("Ortho", window.ortho_button, "F8"),
        ("Polar Tracking", window.polar_button, "F10"),
        ("Object Snap", window.osnap_button, "F3"),
        ("Object Snap Tracking", window.osnap_tracking_button, "F11"),
        ("Dynamic Input", window.dynamic_input_button, "F12"),
    ]:
        # O atalho (F7 etc.) já está registrado no botão da barra de status
        # (window._make_toggle); aqui só mostramos o texto do atalho como
        # dica, sem registrar de novo — Qt não permite dois QAction com o
        # mesmo shortcut ativos na mesma janela.
        action = QAction(f"{label}\t{shortcut}", window)
        action.setCheckable(True)
        action.setChecked(button.isChecked())
        button.toggled.connect(action.setChecked)
        action.toggled.connect(button.setChecked)
        menu.addAction(action)

    menu.addSeparator()
    cmdline_action = QAction("Command Line", window)
    cmdline_action.setCheckable(True)
    cmdline_action.setChecked(True)
    cmdline_action.setShortcut(QKeySequence("Ctrl+9"))
    cmdline_action.toggled.connect(window.command_dock.setVisible)
    menu.addAction(cmdline_action)

    history_action = QAction("Command History...", window)
    history_action.setShortcut(QKeySequence("F2"))
    history_action.triggered.connect(window._show_command_history)
    menu.addAction(history_action)

    properties_action = QAction("Properties", window)
    properties_action.setCheckable(True)
    properties_action.setChecked(True)
    properties_action.setShortcut(QKeySequence("Ctrl+1"))
    properties_action.toggled.connect(window.properties_dock.setVisible)
    menu.addAction(properties_action)


def _build_insert_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Insert")
    _add_command_action(menu, "Insert Block...", "INSERT", window)
    menu.addSeparator()
    _add_command_action(menu, "Attach Image...", "IMAGEATTACH", window)
    _add_command_action(menu, "External Reference (XREF)...", "XREF", window)
    _add_command_action(menu, "External References Panel...", "EXTERNALREFERENCES", window)


def _build_draw_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Draw")
    _add_command_action(menu, "Line", "LINE", window)
    _add_command_action(menu, "Polyline", "PLINE", window)
    _add_command_action(menu, "Circle", "CIRCLE", window)
    _add_command_action(menu, "Rectangle", "RECTANG", window)
    _add_command_action(menu, "Arc", "ARC", window)
    _add_command_action(menu, "Ellipse", "ELLIPSE", window)
    menu.addSeparator()
    _add_command_action(menu, "Hatch...", "HATCH", window)
    _add_command_action(menu, "Create Block...", "BLOCK", window)
    _add_command_action(menu, "Edit Block Definition (BEDIT)...", "BEDIT", window)
    _add_disabled(menu, "Region")
    menu.addSeparator()
    _add_command_action(menu, "Multiline Text...", "MTEXT", window)


def _build_dimension_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("Di&mension")
    _add_command_action(menu, "Linear", "DIMLINEAR", window)
    _add_command_action(menu, "Aligned", "DIMALIGNED", window)
    _add_command_action(menu, "Angular", "DIMANGULAR", window)
    _add_command_action(menu, "Radius", "DIMRADIUS", window)
    _add_command_action(menu, "Diameter", "DIMDIAMETER", window)
    menu.addSeparator()
    _add_command_action(menu, "Leader", "LEADER", window)
    _add_command_action(menu, "Style...", "DIMSTYLE", window)
    menu.addSeparator()
    _add_command_action(menu, "Distance", "DIST", window)


def _build_modify_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Modify")
    _add_command_action(menu, "Erase", "ERASE", window)
    _add_command_action(menu, "Copy", "COPY", window)
    _add_command_action(menu, "Move", "MOVE", window)
    _add_command_action(menu, "Rotate", "ROTATE", window)
    _add_command_action(menu, "Scale", "SCALE", window)
    _add_command_action(menu, "Mirror", "MIRROR", window)
    menu.addSeparator()
    _add_command_action(menu, "Trim", "TRIM", window)
    _add_command_action(menu, "Extend", "EXTEND", window)
    _add_command_action(menu, "Offset", "OFFSET", window)
    _add_command_action(menu, "Fillet", "FILLET", window)
    _add_command_action(menu, "Chamfer", "CHAMFER", window)
    _add_command_action(menu, "Explode", "EXPLODE", window)
    _add_command_action(menu, "Join", "JOIN", window)
    _add_command_action(menu, "Stretch", "STRETCH", window)
    menu.addSeparator()
    _add_command_action(menu, "Divide", "DIVIDE", window)
    _add_command_action(menu, "Measure", "MEASURE", window)
    menu.addSeparator()
    _add_disabled(menu, "Match Properties")


def _build_help_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Help")

    about_action = QAction("About NewSIcad...", window)

    def show_about() -> None:
        QMessageBox.about(
            window,
            "NewSIcad",
            "<b>NewSIcad</b><br>CAD 2D com comandos estilo AutoCAD.<br><br>Developed by HRichter",
        )

    about_action.triggered.connect(show_about)
    menu.addAction(about_action)

    readme_action = QAction("Ver README no GitHub (Help)", window)
    readme_action.setShortcut(QKeySequence("F1"))
    readme_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
    menu.addAction(readme_action)
