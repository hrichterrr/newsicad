"""Entry point do NewSIcad — Developed by HRichter."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from newsicad.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NewSIcad")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
