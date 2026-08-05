"""Conjunto de entidades selecionadas, usado pelos comandos MODIFY
(estilo "Select objects:" do AutoCAD) e pelo destaque visual no canvas."""

from __future__ import annotations

from newsicad.core.document import Document
from newsicad.core.entities import Entity


class Selection:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    def clear(self) -> None:
        self.ids.clear()

    def add(self, entity_id: str) -> None:
        self.ids.add(entity_id)

    def remove(self, entity_id: str) -> None:
        self.ids.discard(entity_id)

    def toggle(self, entity_id: str) -> None:
        if entity_id in self.ids:
            self.ids.discard(entity_id)
        else:
            self.ids.add(entity_id)

    def set(self, entity_ids: set[str]) -> None:
        self.ids = set(entity_ids)

    def entities(self, document: Document) -> list[Entity]:
        result = []
        for entity_id in self.ids:
            entity = document.get_entity(entity_id)
            if entity is not None:
                result.append(entity)
        return result
