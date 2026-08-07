"""Modelo de documento: camadas e coleção de entidades."""

from __future__ import annotations

from dataclasses import dataclass, field

from newsicad.core.entities import BlockReference, Entity

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

    def is_layer_visible(self, entity: Entity) -> bool:
        layer = self.layers.get(entity.layer)
        return layer is None or layer.visible

    def is_layer_locked(self, entity: Entity) -> bool:
        layer = self.layers.get(entity.layer)
        return layer is not None and layer.locked

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

    def rename_layer(self, old_name: str, new_name: str) -> None:
        """RENAME (REN): renomeia uma camada, atualizando toda entidade que a
        referencia (no desenho e dentro de definições de bloco) e o
        current_layer se for o caso. Camada "0" nunca pode ser renomeada
        (igual ao AutoCAD — é a camada padrão de qualquer desenho)."""
        if old_name == "0":
            raise ValueError('A camada "0" não pode ser renomeada.')
        if old_name not in self.layers:
            raise ValueError(f"Camada '{old_name}' não existe.")
        if new_name in self.layers:
            raise ValueError(f"Já existe uma camada chamada '{new_name}'.")

        layer = self.layers.pop(old_name)
        layer.name = new_name
        self.layers[new_name] = layer

        for entity in self.entities.values():
            if entity.layer == old_name:
                entity.layer = new_name
        for entities in self.block_definitions.values():
            for entity in entities:
                if entity.layer == old_name:
                    entity.layer = new_name

        if self.current_layer == old_name:
            self.current_layer = new_name

    def _used_layer_names(self) -> set[str]:
        used = {entity.layer for entity in self.entities.values()}
        for entities in self.block_definitions.values():
            used.update(entity.layer for entity in entities)
        return used

    def purge_unused_layers(self) -> list[str]:
        """PURGE (PU): remove camadas sem nenhuma entidade (no desenho ou
        dentro de blocos) — nunca a camada "0". Retorna os nomes removidos.
        Se a camada atual for removida, current_layer volta a ser "0"."""
        used = self._used_layer_names()
        removable = sorted(name for name in self.layers if name != "0" and name not in used)
        for name in removable:
            del self.layers[name]
            if self.current_layer == name:
                self.current_layer = "0"
        return removable

    def purge_unused_blocks(self) -> list[str]:
        """PURGE (PU): remove definições de bloco sem nenhuma BlockReference
        apontando pra elas (nem no desenho, nem dentro de outro bloco).
        Retorna os nomes removidos."""
        referenced: set[str] = set()
        for entity in self.entities.values():
            if isinstance(entity, BlockReference):
                referenced.add(entity.block_name)
        for entities in self.block_definitions.values():
            for entity in entities:
                if isinstance(entity, BlockReference):
                    referenced.add(entity.block_name)

        removable = sorted(name for name in self.block_definitions if name not in referenced)
        for name in removable:
            del self.block_definitions[name]
        return removable
