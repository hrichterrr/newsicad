"""Menu superior estilo AutoCAD (File, Edit, View, Insert, Draw, Dimension,
Modify, Help). Itens que ainda não têm comando implementado ficam
desabilitados, com tooltip explicando isso — não somem da interface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QMenuBar, QMessageBox

from newsicad.ui.icon_utils import FAMILY_NEUTRAL, command_icon, svg_icon

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

GITHUB_URL = "https://github.com/hrichterrr/newsicad"
NOT_IMPLEMENTED_TIP = "Ainda não implementado — previsto para um próximo marco do NewSIcad."

# Tema escuro pro menu clássico — sem isso, o QMenuBar/QMenu usa o estilo
# nativo do Windows (fundo branco), destoando de todo o resto da interface
# (ribbon, abas, canvas, docks), que já é escuro. Mesma paleta usada no
# ribbon/abas de documento (newsicad/ui/ribbon.py, main_window.py).
MENU_BAR_STYLE = """
    QMenuBar {
        background-color: #232323;
        color: #d0d0d0;
        border-bottom: 1px solid #333333;
        padding: 1px 0px;
    }
    QMenuBar::item {
        background-color: transparent;
        padding: 4px 10px;
    }
    QMenuBar::item:selected {
        background-color: #3a3a3a;
    }
    QMenu {
        background-color: #2b2b2b;
        color: #d8d8d8;
        border: 1px solid #3a3a3a;
        padding: 3px 0px;
    }
    QMenu::item {
        padding: 5px 28px 5px 10px;
    }
    QMenu::icon {
        padding-left: 6px;
    }
    QMenu::item:selected {
        background-color: #3a5a8c;
        color: #ffffff;
    }
    QMenu::item:disabled {
        color: #5a5a5a;
    }
    QMenu::separator {
        height: 1px;
        background: #3a3a3a;
        margin: 4px 8px;
    }
"""


def _add_command_action(menu, label: str, command_name: str, window: "MainWindow", shortcut: str | None = None) -> QAction:
    action = QAction(label, window)
    action.setIcon(command_icon(command_name))
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
    menu_bar.setStyleSheet(MENU_BAR_STYLE)

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
    new_action.setIcon(svg_icon("new", FAMILY_NEUTRAL, 16))
    new_action.setShortcut(QKeySequence("Ctrl+N"))
    new_action.triggered.connect(window._new_document)
    menu.addAction(new_action)

    open_action = QAction("Open...", window)
    open_action.setIcon(svg_icon("open", FAMILY_NEUTRAL, 16))
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(window._open_file)
    menu.addAction(open_action)

    save_action = QAction("Save", window)
    save_action.setIcon(svg_icon("save", FAMILY_NEUTRAL, 16))
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.triggered.connect(window._save_file)
    menu.addAction(save_action)

    save_as_action = QAction("Save As...", window)
    save_as_action.setIcon(svg_icon("saveas", FAMILY_NEUTRAL, 16))
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.triggered.connect(window._save_file_as)
    menu.addAction(save_as_action)

    menu.addSeparator()
    close_tab_action = QAction("Close Tab", window)
    close_tab_action.setIcon(svg_icon("closetab", FAMILY_NEUTRAL, 16))
    close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
    close_tab_action.triggered.connect(window._close_current_tab)
    menu.addAction(close_tab_action)

    menu.addSeparator()
    export_pdf_action = QAction("Print/Export PDF...", window)
    export_pdf_action.setIcon(svg_icon("plot", FAMILY_NEUTRAL, 16))
    export_pdf_action.setShortcut(QKeySequence("Ctrl+P"))
    export_pdf_action.triggered.connect(window._export_pdf)
    menu.addAction(export_pdf_action)

    export_dwg_action = QAction("Export DWG...", window)
    export_dwg_action.setIcon(svg_icon("exportdwg", FAMILY_NEUTRAL, 16))
    export_dwg_action.triggered.connect(window._export_dwg)
    menu.addAction(export_dwg_action)

    menu.addSeparator()
    _add_command_action(menu, "Purge Unused...", "PURGE", window)
    _add_command_action(menu, "Drawing Units...", "UNITS", window)

    menu.addSeparator()
    exit_action = QAction("Exit", window)
    exit_action.triggered.connect(window.close)
    menu.addAction(exit_action)


def _build_edit_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Edit")

    undo_action = QAction("Undo", window)
    undo_action.setIcon(svg_icon("undo", FAMILY_NEUTRAL, 16))
    undo_action.setShortcut(QKeySequence("Ctrl+Z"))
    undo_action.triggered.connect(window._do_undo)
    menu.addAction(undo_action)

    redo_action = QAction("Redo", window)
    redo_action.setIcon(svg_icon("redo", FAMILY_NEUTRAL, 16))
    redo_action.setShortcut(QKeySequence("Ctrl+Y"))
    redo_action.triggered.connect(window._do_redo)
    menu.addAction(redo_action)

    menu.addSeparator()
    _add_command_action(menu, "Cut", "CUTCLIP", window, shortcut="Ctrl+X")
    _add_command_action(menu, "Copy", "COPYCLIP", window, shortcut="Ctrl+C")
    _add_command_action(menu, "Paste", "PASTECLIP", window, shortcut="Ctrl+V")

    menu.addSeparator()
    copy_base_action = QAction("Copy with Base Point", window)
    copy_base_action.setIcon(svg_icon("copybase", FAMILY_NEUTRAL, 16))
    copy_base_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
    copy_base_action.setToolTip(
        "Duplica os objetos DENTRO do desenho atual (comando COPY) — diferente de "
        "Ctrl+C, que copia pra área de transferência do Windows (COPYCLIP)."
    )
    copy_base_action.triggered.connect(lambda: window._start_command("COPY"))
    menu.addAction(copy_base_action)

    menu.addSeparator()
    select_all_action = QAction("Select All", window)
    select_all_action.setIcon(svg_icon("gsel", FAMILY_NEUTRAL, 16))
    select_all_action.setShortcut(QKeySequence("Ctrl+A"))
    select_all_action.triggered.connect(window._select_all)
    menu.addAction(select_all_action)

    select_similar_action = QAction("Select Similar", window)
    select_similar_action.setIcon(svg_icon("selsim", FAMILY_NEUTRAL, 16))
    select_similar_action.triggered.connect(lambda: window._start_command("SELECTSIMILAR"))
    menu.addAction(select_similar_action)

    menu.addSeparator()
    find_action = QAction("Find...", window)
    find_action.setIcon(svg_icon("find", FAMILY_NEUTRAL, 16))
    find_action.setShortcut(QKeySequence("Ctrl+F"))
    find_action.triggered.connect(lambda: window._start_command("FIND"))
    menu.addAction(find_action)


def _build_view_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&View")

    zoom_in = QAction("Zoom In", window)
    zoom_in.setIcon(svg_icon("zoomin", FAMILY_NEUTRAL, 16))
    zoom_in.triggered.connect(lambda: window.canvas.zoom_in())
    menu.addAction(zoom_in)

    zoom_out = QAction("Zoom Out", window)
    zoom_out.setIcon(svg_icon("zoomout", FAMILY_NEUTRAL, 16))
    zoom_out.triggered.connect(lambda: window.canvas.zoom_out())
    menu.addAction(zoom_out)

    zoom_extents = QAction("Zoom Extents", window)
    zoom_extents.setIcon(svg_icon("zoomext", FAMILY_NEUTRAL, 16))
    zoom_extents.triggered.connect(lambda: window.canvas.zoom_extents())
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
        action.setEnabled(button.isEnabled())
        button.toggled.connect(action.setChecked)
        action.toggled.connect(button.setChecked)
        menu.addAction(action)

    menu.addSeparator()
    cmdline_action = QAction("Command Line", window)
    cmdline_action.setIcon(svg_icon("cmdline", FAMILY_NEUTRAL, 16))
    cmdline_action.setCheckable(True)
    cmdline_action.setChecked(True)
    cmdline_action.setShortcut(QKeySequence("Ctrl+9"))
    cmdline_action.toggled.connect(window.command_dock.setVisible)
    menu.addAction(cmdline_action)

    history_action = QAction("Command History...", window)
    history_action.setIcon(svg_icon("history", FAMILY_NEUTRAL, 16))
    history_action.setShortcut(QKeySequence("F2"))
    history_action.triggered.connect(window._show_command_history)
    menu.addAction(history_action)

    properties_action = QAction("Properties", window)
    properties_action.setIcon(svg_icon("props", FAMILY_NEUTRAL, 16))
    properties_action.setCheckable(True)
    properties_action.setChecked(True)
    properties_action.setShortcut(QKeySequence("Ctrl+1"))
    properties_action.toggled.connect(window.properties_dock.setVisible)
    menu.addAction(properties_action)

    layers_action = QAction("Layers...", window)
    layers_action.setIcon(svg_icon("layers", FAMILY_NEUTRAL, 16))
    layers_action.triggered.connect(lambda: window._start_command("LAYER"))
    menu.addAction(layers_action)

    rename_layer_action = QAction("Rename Current Layer...", window)
    rename_layer_action.setIcon(svg_icon("rename", FAMILY_NEUTRAL, 16))
    rename_layer_action.triggered.connect(lambda: window._start_command("RENAME"))
    menu.addAction(rename_layer_action)

    menu.addSeparator()
    _add_command_action(menu, "Viewport Configuration...", "VIEWPORTS", window)


def _build_insert_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Insert")
    _add_command_action(menu, "Insert Block...", "INSERT", window)
    menu.addSeparator()
    _add_command_action(menu, "Attach Image...", "IMAGEATTACH", window)
    _add_command_action(menu, "Import PDF...", "IMPORTPDF", window)
    _add_command_action(menu, "External Reference (XREF)...", "XREF", window)
    _add_command_action(menu, "External References Panel...", "EXTERNALREFERENCES", window)
    _add_command_action(menu, "Clip Reference/Image (XCLIP)...", "CLIP", window)
    _add_command_action(menu, "Remove Clip Boundary (CLIPOFF)", "CLIPOFF", window)
    menu.addSeparator()
    _add_command_action(menu, "Field...", "FIELD", window)
    _add_command_action(menu, "Data Link...", "DATALINK", window)
    _add_disabled(menu, "OLE Object...")


def _build_draw_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Draw")
    _add_command_action(menu, "Line", "LINE", window)
    _add_command_action(menu, "Polyline", "PLINE", window)
    _add_command_action(menu, "Circle", "CIRCLE", window)
    _add_command_action(menu, "Rectangle", "RECTANG", window)
    _add_command_action(menu, "Arc", "ARC", window)
    _add_command_action(menu, "Ellipse", "ELLIPSE", window)
    _add_command_action(menu, "Polygon", "POLYGON", window)
    _add_command_action(menu, "Spline", "SPLINE", window)
    _add_command_action(menu, "Donut", "DONUT", window)
    _add_command_action(menu, "Point", "POINT", window)
    menu.addSeparator()
    _add_command_action(menu, "Multiline", "MLINE", window)
    _add_command_action(menu, "Construction Line (XLINE)", "XLINE", window)
    _add_command_action(menu, "Ray", "RAY", window)
    menu.addSeparator()
    _add_command_action(menu, "Revision Cloud", "REVCLOUD", window)
    _add_command_action(menu, "Wipeout", "WIPEOUT", window)
    menu.addSeparator()
    _add_command_action(menu, "Hatch...", "HATCH", window)
    _add_command_action(menu, "Boundary...", "BOUNDARY", window)
    _add_command_action(menu, "Create Block...", "BLOCK", window)
    _add_command_action(menu, "Edit Block Definition (BEDIT)...", "BEDIT", window)
    _add_disabled(menu, "Region")
    menu.addSeparator()
    _add_command_action(menu, "Multiline Text...", "MTEXT", window)
    _add_command_action(menu, "Text Style...", "STYLE", window)
    _add_command_action(menu, "Multileader Style...", "MLEADERSTYLE", window)
    _add_command_action(menu, "Table...", "TABLE", window)
    _add_command_action(menu, "Table Style...", "TABLESTYLE", window)


def _build_dimension_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("Di&mension")
    _add_command_action(menu, "Linear", "DIMLINEAR", window)
    _add_command_action(menu, "Aligned", "DIMALIGNED", window)
    _add_command_action(menu, "Angular", "DIMANGULAR", window)
    _add_command_action(menu, "Radius", "DIMRADIUS", window)
    _add_command_action(menu, "Diameter", "DIMDIAMETER", window)
    menu.addSeparator()
    _add_command_action(menu, "Center Mark", "CENTERMARK", window)
    _add_command_action(menu, "Dimension Break", "DIMBREAK", window)
    menu.addSeparator()
    _add_command_action(menu, "Leader", "LEADER", window)
    _add_command_action(menu, "Style...", "DIMSTYLE", window)
    menu.addSeparator()
    _add_command_action(menu, "Distance", "DIST", window)
    _add_command_action(menu, "Area", "AREA", window)
    _add_command_action(menu, "Point Coordinates (ID)", "ID", window)


def _build_modify_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Modify")
    _add_command_action(menu, "Erase", "ERASE", window)
    _add_command_action(menu, "Copy", "COPY", window)
    _add_command_action(menu, "Move", "MOVE", window)
    _add_command_action(menu, "Rotate", "ROTATE", window)
    _add_command_action(menu, "Scale", "SCALE", window)
    _add_command_action(menu, "Mirror", "MIRROR", window)
    _add_command_action(menu, "Align", "ALIGN", window)
    _add_command_action(menu, "Array", "ARRAY", window)
    menu.addSeparator()
    _add_command_action(menu, "Trim", "TRIM", window)
    _add_command_action(menu, "Extend", "EXTEND", window)
    _add_command_action(menu, "Offset", "OFFSET", window)
    _add_command_action(menu, "Fillet", "FILLET", window)
    _add_command_action(menu, "Chamfer", "CHAMFER", window)
    _add_command_action(menu, "Break", "BREAK", window)
    _add_command_action(menu, "Break at Point", "BREAKATPOINT", window)
    _add_command_action(menu, "Lengthen", "LENGTHEN", window)
    _add_command_action(menu, "Explode", "EXPLODE", window)
    _add_command_action(menu, "Join", "JOIN", window)
    _add_command_action(menu, "Stretch", "STRETCH", window)
    _add_command_action(menu, "Edit Polyline (PEDIT)...", "PEDIT", window)
    menu.addSeparator()
    _add_command_action(menu, "Divide", "DIVIDE", window)
    _add_command_action(menu, "Measure", "MEASURE", window)
    menu.addSeparator()
    _add_command_action(menu, "Edit Text...", "DDEDIT", window)
    _add_command_action(menu, "Edit Hatch (HATCHEDIT)...", "HATCHEDIT", window)
    menu.addSeparator()
    _add_command_action(menu, "Quick Select...", "QSELECT", window)
    _add_command_action(menu, "Match Layer", "LAYMCH", window)
    _add_command_action(menu, "Isolate Layer(s)", "LAYISO", window)
    _add_command_action(menu, "Unisolate Layer(s)", "LAYUNISO", window)
    menu.addSeparator()
    _add_command_action(menu, "Match Properties", "MATCHPROP", window)


def _build_help_menu(menu_bar: QMenuBar, window: "MainWindow") -> None:
    menu = menu_bar.addMenu("&Help")

    about_action = QAction("About NewSIcad...", window)
    about_action.setIcon(svg_icon("help", FAMILY_NEUTRAL, 16))

    def show_about() -> None:
        QMessageBox.about(
            window,
            "NewSIcad",
            "<b>NewSIcad</b><br>CAD 2D com comandos estilo AutoCAD.<br><br>Developed by HRichter",
        )

    about_action.triggered.connect(show_about)
    menu.addAction(about_action)

    readme_action = QAction("Ver README no GitHub (Help)", window)
    readme_action.setIcon(svg_icon("help", FAMILY_NEUTRAL, 16))
    readme_action.setShortcut(QKeySequence("F1"))
    readme_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
    menu.addAction(readme_action)
