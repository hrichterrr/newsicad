"""Modelo de documento: camadas e coleção de entidades."""

from __future__ import annotations

from dataclasses import dataclass, field

from newsicad.core.entities import Entity

DEFAULT_LAYER_COLOR = "#FFFFFF"


@dataclass
class Layer:
    name: str
    color: str = DEFAULT_LAYER_COLOR
    visible: bool = True
    locked: bool = False


class Document:
    """Mantém as camadas e entidades de um desenho."""

    def __init__(self) -> None:
        self.layers: dict[str, Layer] = {"0": Layer(name="0")}
        self.current_layer: str = "0"
        self.entities: dict[str, Entity] = {}
        self.units: str = "mm"
        # Definições de bloco: nome -> lista de entidades "template" com
        # coordenadas relativas ao ponto base do bloco (ver BlockReference
        # em newsicad/core/entities.py). Não são entidades do desenho —
        # só as instâncias (BlockReference) aparecem em `self.entities`.
        self.block_definitions: dict[str, list[Entity]] = {}

    def add_layer(self, name: str, color: str = DEFAULT_LAYER_COLOR) -> Layer:
        layer = self.layers.get(name)
        if layer is None:
            layer = Layer(name=name, color=color)
            self.layers[name] = layer
        return layer

    def set_current_layer(self, name: str) -> None:
        if name not in self.layers:
            raise ValueError(f"Camada '{name}' não existe")
        self.current_layer = name

    def add_entity(self, entity: Entity) -> Entity:
        if not entity.layer:
            entity.layer = self.current_layer
        self.add_layer(entity.layer)
        self.entities[entity.id] = entity
        return entity

    def remove_entity(self, entity_id: str) -> Entity | None:
        return self.entities.pop(entity_id, None)

    def get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    def all_entities(self) -> list[Entity]:
        return list(self.entities.values())

    def clear(self) -> None:
        self.entities.clear()
        self.block_definitions.clear()

    def define_block(self, name: str, entities: list[Entity]) -> None:
        self.block_definitions[name] = entities

    def get_block_definition(self, name: str) -> list[Entity]:
        return self.block_definitions.get(name, [])
