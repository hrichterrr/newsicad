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
