"""Block Editor (comandos BEDIT/REFEDIT) — abordagem escolhida e limitações:

O NewSIcad não tem um conceito de "espaço de bloco" isolado dentro do mesmo
Document/canvas principal (isso exigiria um sistema de "espaços" completo).
Em vez disso, este diálogo abre um MINI-CANVAS independente: um `Document`
temporário populado com cópias das entidades da definição do bloco, com seu
próprio `CommandInterpreter`/`CanvasView`/`CommandLineWidget` — os MESMOS
componentes usados pela MainWindow, então dentro do editor funcionam todos os
comandos normais (LINE, CIRCLE, ERASE, MOVE, outro BLOCK/INSERT aninhado...).

"Save" copia as entidades do documento temporário de volta para
`document.block_definitions[nome]` (substituindo a definição inteira) e
atualiza todas as BlockReferences existentes automaticamente — como elas só
guardam o nome do bloco, não a geometria, o próximo `refresh_entities()` já
renderiza a versão editada em todas as instâncias no desenho principal.
"Cancel" simplesmente fecha sem tocar na definição original.

Limitações documentadas (ver README):
- Não há um "bloco dentro do bloco selecionável por clique" como o REFEDIT
  de verdade do AutoCAD (que edita a referência escolhida no próprio
  desenho, in-place). REFEDIT aqui reusa este mesmo diálogo, escolhendo o
  bloco por NOME numa lista, não clicando numa instância no canvas.
- Não há undo/redo dentro do mini-editor (o UndoStack do NewSIcad é por
  Document, e criar um aqui seria mais complexidade do que o valor
  entregue nesta versão) — o botão Cancel é o "desfazer tudo" disponível.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Point
from newsicad.core.geometry_ops import clone_entity
from newsicad.core.selection import Selection
from newsicad.ui.canvas import CanvasView
from newsicad.ui.command_line import CommandLineWidget

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow


class BlockEditorDialog(QDialog):
    def __init__(self, window: "MainWindow", block_name: str) -> None:
        super().__init__(window)
        self.main_window = window
        self.block_name = block_name
        self.setWindowTitle(f"Block Editor — {block_name}")
        self.resize(900, 650)

        self.document = Document()
        for entity in window.document.get_block_definition(block_name):
            self.document.add_entity(clone_entity(entity))

        self.selection = Selection()
        self.context = CommandContext(document=self.document, selection=self.selection)
        self.interpreter = CommandInterpreter(self.context, COMMAND_REGISTRY, ALIASES)

        self.canvas = CanvasView(self.document, self.interpreter)
        self.canvas.on_point = self._handle_canvas_point
        self.canvas.on_enter = self._handle_enter
        self.canvas.on_cancel = self._handle_cancel
        self.canvas.on_selection_changed = lambda: None
        self.context.view = self.canvas

        self.command_line = CommandLineWidget()
        self.command_line.text_submitted.connect(self._handle_text_submitted)
        self.command_line.cancel_requested.connect(self._handle_cancel)

        self._build_ui()
        self.canvas.refresh_entities()
        self.canvas.zoom_extents()
        self._refresh_prompt()
        self.command_line.focus_input()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        note = QLabel(
            f'Editando a definição do bloco "{self.block_name}" num mini-desenho à parte.\n'
            "Use os comandos normais (LINE, CIRCLE, ERASE, MOVE, ...). "
            "Save grava de volta na definição e atualiza todas as instâncias no desenho principal."
        )
        note.setStyleSheet("color: #a0a0a0; font-size: 11px; padding: 4px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.command_line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

    def _save_and_close(self) -> None:
        new_definition = [clone_entity(e) for e in self.document.all_entities()]
        self.main_window.document.define_block(self.block_name, new_definition)
        self.main_window.canvas.refresh_entities()
        self.main_window.canvas.viewport().update()
        self.accept()

    # ------------------------------------------------------------------ #
    # mesma ligação canvas <-> interpretador <-> linha de comando da
    # MainWindow (newsicad/ui/main_window.py), só que escopada a este
    # Document/canvas temporários.
    # ------------------------------------------------------------------ #
    def _handle_canvas_point(self, point: Point) -> None:
        if self.interpreter.active:
            self.interpreter.submit_point(point)
        self._after_interpreter_step()

    def _handle_enter(self) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text("")
            self._after_interpreter_step()

    def _handle_cancel(self) -> None:
        if self.interpreter.active:
            self.interpreter.cancel()
        self._after_interpreter_step()

    def _handle_text_submitted(self, text: str) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text(text)
            self._after_interpreter_step()
        elif text.strip():
            self.interpreter.start(text)
            self._after_interpreter_step()

    def _after_interpreter_step(self) -> None:
        self.canvas.refresh_entities()
        if not self.interpreter.active:
            self.canvas.clear_transient_overlays()
        self.canvas.viewport().update()
        self._refresh_prompt()
        self.command_line.focus_input()

    def _refresh_prompt(self) -> None:
        self.command_line.set_log(self.interpreter.log)
        if self.interpreter.active and self.interpreter.current_prompt is not None:
            self.command_line.set_prompt(self.interpreter.current_prompt.message)
        else:
            self.command_line.set_prompt("Command:")
