"""Contexto passado a todo comando: o documento e a seleção atual."""

from __future__ import annotations

from dataclasses import dataclass

from newsicad.core.document import Document
from newsicad.core.selection import Selection


@dataclass
class CommandContext:
    document: Document
    selection: Selection
