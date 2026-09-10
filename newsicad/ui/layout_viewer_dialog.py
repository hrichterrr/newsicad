"""Ver pranchas (View > Ver pranchas...) — abordagem escolhida e limitações:

Mesmo padrão do Block Editor (newsicad/ui/block_editor_dialog.py, ver a nota
lá): o NewSIcad não tem um conceito de "espaço" (Model/Layout) dentro do
mesmo Document/canvas principal, então este diálogo abre um MINI-CANVAS
independente — um `Document` próprio com seu próprio CommandInterpreter/
CanvasView/CommandLineWidget, os MESMOS componentes da MainWindow.

Diferença em relação ao Block Editor: aqui `layers`/`block_definitions`/
`text_styles`/`dim_style`/`table_style`/`mleader_style`/`units` são
COMPARTILHADOS POR REFERÊNCIA com o documento principal — são do ARQUIVO
INTEIRO, não da prancha (um bloco ou camada usado na prancha e no Model é o
MESMO bloco/camada, igual no AutoCAD de verdade). Só `entities` é uma cópia
(clone_entity) do conteúdo da prancha (`document.layouts[nome]`).

"Save" grava a cópia (clonada de novo) de volta em `document.layouts[nome]`
e marca o documento principal como alterado (Document.touch()) — a
gravação de verdade no arquivo só acontece no próximo File > Save da janela
principal, igual a qualquer outra edição. "Cancel" descarta tudo.

Limitações documentadas (ver README, mesma linha do Block Editor):
- Sem undo/redo dentro do mini-editor — Cancel é o "desfazer tudo"
  disponível.
- Um VIEWPORT (a "janela" que a prancha normalmente tem pra mostrar um
  recorte/escala do Model space) ainda não é desenhado — só o resto do
  conteúdo desenhado direto na prancha aparece (ver newsicad/io/dxf_io.py).
"""

from __future__ import annotations

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


class LayoutViewerDialog(QDialog):
    def __init__(self, main_document: Document, layout_name: str, parent=None) -> None:
        super().__init__(parent)
        self.main_document = main_document
        self.layout_name = layout_name
        self.setWindowTitle(f"Prancha (Paper Space) — {layout_name}")
        self.resize(1100, 750)

        self.document = Document()
        # Compartilhado por referência de propósito — ver docstring do
        # módulo: camada/bloco/estilo são do arquivo inteiro, não da
        # prancha. Uma camada nova criada aqui dentro (ex.: LAYER) já fica
        # visível no Model ao fechar o diálogo, sem precisar de nenhum
        # passo extra de sincronização.
        self.document.layers = main_document.layers
        self.document.block_definitions = main_document.block_definitions
        self.document.text_styles = main_document.text_styles
        self.document.dim_style = main_document.dim_style
        self.document.table_style = main_document.table_style
        self.document.mleader_style = main_document.mleader_style
        self.document.units = main_document.units
        self.document.current_layer = main_document.current_layer
        for entity in main_document.layouts.get(layout_name, {}).values():
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
            f'Prancha "{self.layout_name}" (paper space), num mini-desenho à parte — camadas e '
            "blocos são os mesmos do desenho principal (Model).\n"
            "Um eventual VIEWPORT (recorte do Model space) desta prancha ainda não é desenhado. "
            "Save grava as alterações de volta na prancha; Cancel descarta."
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
        new_entities = {entity.id: entity for entity in (clone_entity(e) for e in self.document.all_entities())}
        self.main_document.layouts[self.layout_name] = new_entities
        self.main_document.touch()
        self.accept()

    # ------------------------------------------------------------------ #
    # mesma ligação canvas <-> interpretador <-> linha de comando do Block
    # Editor (newsicad/ui/block_editor_dialog.py), só escopada a este
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
