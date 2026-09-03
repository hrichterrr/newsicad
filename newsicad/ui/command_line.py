"""Linha de comando ancorada na parte inferior, estilo AutoCAD: histórico
rolável em cima, prompt + campo de entrada logo abaixo. Enter/Espaço
confirma, Esc cancela, ↑/↓ navegam o histórico de entradas digitadas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget

MONO_FONT_FAMILY = "Menlo"

HISTORY_STYLE = f"""
    QTextEdit {{
        background-color: #141414;
        color: #d8d8d8;
        border: 1px solid #333333;
        font-family: "{MONO_FONT_FAMILY}";
        font-size: 12px;
    }}
"""

PROMPT_LABEL_STYLE = f"""
    QLabel {{
        color: #ffd479;
        font-family: "{MONO_FONT_FAMILY}";
        font-size: 12px;
        padding-left: 2px;
    }}
"""

INPUT_STYLE = f"""
    QLineEdit {{
        background-color: #141414;
        color: #ffffff;
        border: 1px solid #333333;
        font-family: "{MONO_FONT_FAMILY}";
        font-size: 12px;
        padding: 2px 4px;
    }}
"""


class CommandLineEdit(QLineEdit):
    submitted = Signal(str)
    cancelled = Signal()
    history_prev = Signal()
    history_next = Signal()
    undo_requested = Signal()
    redo_requested = Signal()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        # QLineEdit tem undo/redo NATIVO de texto embutido em Ctrl+Z/Ctrl+Y —
        # sem interceptar aqui, ele "rouba" o atalho antes do Undo/Redo do
        # desenho (QAction global do menu Edit) ter qualquer chance de disparar,
        # sempre que a linha de comando estiver com foco (o caso comum, já que
        # focus_input() é chamado depois de cada comando). Bug real reportado:
        # Ctrl+Z parecia "não funcionar" — na verdade desfazia só o texto
        # digitado, nunca o desenho.
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo_requested.emit()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo_requested.emit()
            return
        if key == Qt.Key.Key_Escape:
            self.clear()
            self.cancelled.emit()
            return
        if key == Qt.Key.Key_Space and not self.text():
            self.submitted.emit("")
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text()
            self.clear()
            self.submitted.emit(text)
            return
        if key == Qt.Key.Key_Up:
            self.history_prev.emit()
            return
        if key == Qt.Key.Key_Down:
            self.history_next.emit()
            return
        super().keyPressEvent(event)


class CommandLineWidget(QWidget):
    text_submitted = Signal(str)
    cancel_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._history_pos = 0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(2)

        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setFixedHeight(110)
        self.history_view.setStyleSheet(HISTORY_STYLE)
        layout.addWidget(self.history_view)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.prompt_label = QLabel("Command:")
        self.prompt_label.setStyleSheet(PROMPT_LABEL_STYLE)
        input_row.addWidget(self.prompt_label)

        self.input_edit = CommandLineEdit()
        self.input_edit.setStyleSheet(INPUT_STYLE)
        self.input_edit.setFont(QFont(MONO_FONT_FAMILY, 10))
        self.input_edit.submitted.connect(self._on_submitted)
        self.input_edit.cancelled.connect(self.cancel_requested)
        self.input_edit.undo_requested.connect(self.undo_requested)
        self.input_edit.redo_requested.connect(self.redo_requested)
        self.input_edit.history_prev.connect(self._history_prev)
        self.input_edit.history_next.connect(self._history_next)
        input_row.addWidget(self.input_edit, stretch=1)

        layout.addLayout(input_row)

    def _on_submitted(self, text: str) -> None:
        raw = text.strip()
        if raw:
            self._history.append(raw)
        self._history_pos = len(self._history)
        self.text_submitted.emit(text)

    def _history_prev(self) -> None:
        if not self._history:
            return
        self._history_pos = max(0, self._history_pos - 1)
        self.input_edit.setText(self._history[self._history_pos])

    def _history_next(self) -> None:
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self.input_edit.setText(self._history[self._history_pos])
        else:
            self._history_pos = len(self._history)
            self.input_edit.clear()

    def set_prompt(self, text: str) -> None:
        self.prompt_label.setText(text)

    def set_log(self, lines: list[str]) -> None:
        self.history_view.setPlainText("\n".join(lines))
        cursor = self.history_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.history_view.setTextCursor(cursor)
        self.history_view.ensureCursorVisible()

    def focus_input(self) -> None:
        self.input_edit.setFocus()
