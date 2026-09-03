"""Um desenho aberto = uma `DocumentSession`: agrupa tudo que hoje era estado
solto direto em `MainWindow` (document, selection, context, interpreter,
undo_stack, canvas, current_path...) — a peça que faltava pra várias abas de
documento independentes conviverem na mesma janela (ver `MainWindow`, que
mantém uma lista de sessões + um `QTabWidget` cujas páginas SÃO os
`CanvasView` de cada sessão).

Cada sessão é 100% independente das outras: desenho próprio, pilha de undo
própria, log de comandos próprio (cada aba tem seu próprio histórico na linha
de comando ao voltar pra ela) — nada é compartilhado entre abas."""

from __future__ import annotations

import copy
from pathlib import Path

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Point
from newsicad.core.selection import Selection
from newsicad.core.undo import UndoStack
from newsicad.ui.canvas import CanvasView


class DocumentSession:
    def __init__(self, untitled_label: str) -> None:
        self.current_path: Path | None = None
        self.untitled_label = untitled_label
        self.last_cursor_point: Point | None = None

        self.document = Document()
        self.selection = Selection()
        self.context = CommandContext(document=self.document, selection=self.selection)
        self.interpreter = CommandInterpreter(self.context, COMMAND_REGISTRY, ALIASES)
        self.undo_stack = UndoStack(self.document)

        self.canvas = CanvasView(self.document, self.interpreter)
        self.context.view = self.canvas

        # VPORTS (Viewport Configuration): `canvas` continua sendo a ÚNICA
        # viewport interativa (recebe clique/comando) mesmo com múltiplas
        # panes na tela — `viewport_panes` guarda as extras (só visuais, tela
        # cheia é lógica de MainWindow._apply_viewport_layout). `tab_widget`
        # é o que está de fato dentro de `MainWindow.doc_tabs` agora (o
        # `canvas` sozinho, ou o QSplitter com todas as panes).
        self.viewport_panes: list[CanvasView] = []
        self.viewport_layout: str = "Single"
        self.tab_widget = self.canvas

        self.saved_snapshot = self.snapshot_state()

    def snapshot_state(self) -> tuple:
        return (
            copy.deepcopy(self.document.entities),
            copy.deepcopy(self.document.layers),
            self.document.units,
            copy.deepcopy(self.document.block_definitions),
        )

    def is_dirty(self) -> bool:
        return self.snapshot_state() != self.saved_snapshot

    def mark_saved(self) -> None:
        self.saved_snapshot = self.snapshot_state()

    def display_name(self) -> str:
        return self.current_path.name if self.current_path else self.untitled_label

    def tab_label(self) -> str:
        name = self.display_name()
        return f"{name} *" if self.is_dirty() else name
