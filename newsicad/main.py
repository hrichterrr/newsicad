"""Entry point do NewSIcad — Developed by HRichter."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from newsicad.ui.main_window import MainWindow

# Tema escuro global pra diálogos (Units, Export PDF, confirmar descarte de
# alterações, Block Editor, etc.) — sem isso, ribbon/menu/abas/docks já
# ficam escuros (ver newsicad/ui/ribbon.py, menu_bar.py, main_window.py),
# mas qualquer QDialog/QMessageBox continuava com o branco nativo do
# Windows, destoando do resto — mesma paleta usada em todo o resto da UI.
# Escopo deliberadamente por CLASSE de controle (não um `QWidget { }` geral)
# pra não pisar nos estilos específicos que canvas/ribbon/docks já têm.
APP_STYLE = """
    QDialog, QMessageBox, QInputDialog {
        background-color: #2b2b2b;
        color: #d8d8d8;
    }
    QLabel {
        color: #d8d8d8;
        background-color: transparent;
    }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
        background-color: #1e1e1e;
        color: #e0e0e0;
        border: 1px solid #3a3a3a;
        padding: 3px;
        selection-background-color: #3a5a8c;
    }
    QComboBox {
        background-color: #333333;
        color: #d8d8d8;
        border: 1px solid #3a3a3a;
        padding: 3px 6px;
        border-radius: 2px;
    }
    QComboBox QAbstractItemView {
        background-color: #2b2b2b;
        color: #d8d8d8;
        selection-background-color: #3a5a8c;
        outline: none;
    }
    QPushButton {
        background-color: #3a3a3a;
        color: #d8d8d8;
        border: 1px solid #4a4a4a;
        padding: 5px 14px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #454545;
    }
    QPushButton:pressed {
        background-color: #2f2f2f;
    }
    QPushButton:default {
        border: 1px solid #4da3ff;
    }
    QCheckBox, QRadioButton {
        color: #d8d8d8;
        background-color: transparent;
    }
    QGroupBox {
        color: #d8d8d8;
        border: 1px solid #3a3a3a;
        border-radius: 3px;
        margin-top: 10px;
        padding-top: 6px;
    }
    QListWidget, QListView, QTreeView {
        background-color: #1e1e1e;
        color: #d8d8d8;
        border: 1px solid #3a3a3a;
    }
    QToolTip {
        background-color: #2b2b2b;
        color: #d8d8d8;
        border: 1px solid #4a4a4a;
        padding: 3px;
    }
    QScrollBar:vertical, QScrollBar:horizontal {
        background-color: #232323;
        border: none;
    }
    QScrollBar::handle {
        background-color: #4a4a4a;
        border-radius: 3px;
    }
    QScrollBar::handle:hover {
        background-color: #5a5a5a;
    }
"""


def _icon_path() -> Path:
    """Resolve o ícone (logo NewSI) tanto rodando a partir do código-fonte
    quanto empacotado com PyInstaller (onde os dados extras do
    build_windows.spec ficam soltos na raiz do bundle, sys._MEIPASS —
    mesmo padrão de newsicad/io/dwg_bridge.py:_bundled_bin_dir)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base / "resources" / "newsi_icon.ico"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NewSIcad")
    app.setWindowIcon(QIcon(str(_icon_path())))
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
