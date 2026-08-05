"""Janela principal: junta o canvas, a linha de comando (dock inferior) e a
barra de status estilo AutoCAD (coordenadas + toggles SNAP/GRID/ORTHO/POLAR/OSNAP)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QWidget,
)

from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Point
from newsicad.ui.canvas import CanvasView
from newsicad.ui.command_line import CommandLineWidget

APP_TITLE = "NewSIcad — Developed by HRichter"

STATUS_TOGGLE_STYLE = """
    QPushButton {
        background-color: #2b2b2b;
        color: #a0a0a0;
        border: 1px solid #3a3a3a;
        padding: 2px 8px;
        font-size: 11px;
    }
    QPushButton:checked {
        background-color: #3a5a8c;
        color: #ffffff;
    }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        self._last_cursor_point: Point | None = None

        self.document = Document()
        self.interpreter = CommandInterpreter(self.document, COMMAND_REGISTRY, ALIASES)

        self.canvas = CanvasView(self.document, self.interpreter)
        self.canvas.on_point = self._handle_canvas_point
        self.canvas.on_enter = self._handle_enter
        self.canvas.on_cancel = self._handle_cancel
        self.canvas.mouse_moved.connect(self._handle_mouse_moved)
        self.setCentralWidget(self.canvas)

        self._build_command_dock()
        self._build_status_bar()
        self._refresh_prompt()
        self.command_line.focus_input()

    # ------------------------------------------------------------------ #
    # construção da UI
    # ------------------------------------------------------------------ #
    def _build_command_dock(self) -> None:
        self.command_line = CommandLineWidget()
        self.command_line.text_submitted.connect(self._handle_text_submitted)
        self.command_line.cancel_requested.connect(self._handle_cancel)

        dock = QDockWidget("", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())
        dock.setWidget(self.command_line)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)

        self.coord_label = QLabel("0.00, 0.00")
        self.coord_label.setStyleSheet("color: #d8d8d8; font-family: Menlo; padding: 0 8px;")
        status.addWidget(self.coord_label)

        status.addPermanentWidget(self._make_toggle("GRID", "F7", self._toggle_grid, checked=True))
        status.addPermanentWidget(self._make_toggle("SNAP", "F9", self._toggle_snap))
        status.addPermanentWidget(self._make_toggle("ORTHO", "F8", self._toggle_ortho))
        status.addPermanentWidget(
            self._make_toggle(
                "POLAR", "F10", self._toggle_polar,
                tooltip="Rastreamento polar (em desenvolvimento)",
            )
        )
        status.addPermanentWidget(
            self._make_toggle(
                "OSNAP", "F3", self._toggle_osnap,
                tooltip="Snap a objetos (em desenvolvimento)",
            )
        )

        brand = QLabel("NewSIcad · Developed by HRichter")
        brand.setStyleSheet("color: #6a8fc9; font-family: Menlo; font-size: 11px; padding: 0 10px;")
        status.addPermanentWidget(brand)

    def _make_toggle(self, label, shortcut, handler, checked=False, tooltip=None) -> QPushButton:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setStyleSheet(STATUS_TOGGLE_STYLE)
        button.setToolTip(tooltip or f"{label} ({shortcut})")
        button.toggled.connect(handler)

        action = QAction(self)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(button.toggle)
        self.addAction(action)

        return button

    # ------------------------------------------------------------------ #
    # toggles da barra de status
    # ------------------------------------------------------------------ #
    def _toggle_grid(self, checked: bool) -> None:
        self.canvas.set_grid_visible(checked)

    def _toggle_snap(self, checked: bool) -> None:
        self.canvas.set_snap_enabled(checked)

    def _toggle_ortho(self, checked: bool) -> None:
        self.canvas.set_ortho_enabled(checked)

    def _toggle_polar(self, checked: bool) -> None:
        pass  # reservado: rastreamento polar entra num próximo marco

    def _toggle_osnap(self, checked: bool) -> None:
        pass  # reservado: snap a objetos (endpoint/midpoint/center) entra no marco de TRIM/EXTEND

    # ------------------------------------------------------------------ #
    # ligação canvas <-> interpretador de comandos <-> linha de comando
    # ------------------------------------------------------------------ #
    def _handle_canvas_point(self, point: Point) -> None:
        if self.interpreter.active:
            self.interpreter.submit_point(point)
        self._after_interpreter_step()

    def _handle_enter(self) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text("")
        else:
            self.interpreter.repeat_last()
        self._after_interpreter_step()

    def _handle_cancel(self) -> None:
        if self.interpreter.active:
            self.interpreter.cancel()
        self._after_interpreter_step()

    def _handle_text_submitted(self, text: str) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text(text, cursor_point=self._last_cursor_point)
        elif text.strip() == "":
            self.interpreter.repeat_last()
        else:
            self.interpreter.start(text)
        self._after_interpreter_step()

    def _handle_mouse_moved(self, point: Point) -> None:
        self._last_cursor_point = point
        self.coord_label.setText(f"{point.x:.2f}, {point.y:.2f}")

    def _after_interpreter_step(self) -> None:
        self.canvas.refresh_entities()
        self.canvas.viewport().update()
        self._refresh_prompt()
        self.command_line.focus_input()

    def _refresh_prompt(self) -> None:
        self.command_line.set_log(self.interpreter.log)
        if self.interpreter.active and self.interpreter.current_prompt is not None:
            self.command_line.set_prompt(self.interpreter.current_prompt.message)
        else:
            self.command_line.set_prompt("Command:")
