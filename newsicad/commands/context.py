"""Contexto passado a todo comando: o documento, a seleção atual e
(opcionalmente) a view — usada só por comandos de navegação (ZOOM/PAN) que
precisam manipular a câmera do canvas, não o desenho em si."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from newsicad.core.document import Document
from newsicad.core.selection import Selection


@dataclass
class CommandContext:
    document: Document
    selection: Selection
    # Expõe zoom_extents()/zoom_window(p1, p2) — normalmente é o CanvasView.
    # Tipado como Any pra não criar dependência de newsicad.ui em
    # newsicad.commands (ui importa commands, não o contrário).
    view: Any = None
    #: Havia objetos selecionados quando o comando começou, e nenhuma etapa
    #: de seleção os consumiu ainda. É o "pré-seleção" do AutoCAD: escolher
    #: os objetos no canvas e SÓ ENTÃO digitar o comando (ou usar o menu de
    #: contexto, que só abre com objetos selecionados). Marcado por
    #: `CommandInterpreter.start` e consumido pela primeira etapa de seleção
    #: do comando — a segunda etapa, num comando que pede duas (DIMBREAK
    #: pede a cota e depois o que a cruza), volta a perguntar normalmente.
    preselection_available: bool = False
