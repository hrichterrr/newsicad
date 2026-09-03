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


@dataclass
class TextStyle:
    """STYLE (Text Style): nome + fonte + altura padrão — versão simplificada
    do Text Style de verdade do AutoCAD (sem largura/oblíquo/efeitos
    invertido/espelhado). `Text.style` referencia uma entrada aqui pelo
    nome; `CanvasView` usa `font_family` em vez do "Menlo" fixo de antes."""

    name: str = "Standard"
    font_family: str = "Menlo"
    height: float = 2.5
    #: Fator de largura do STYLE (group code 41 — "Width factor" do AutoCAD;
    #: 1.0 = normal). Antes era descartado na leitura do .dxf; agora vai
    #: pro `QFont.setStretch` do render (WP-B 2026-09).
    width: float = 1.0
    #: Nome do arquivo de fonte como está no .dxf (ex.: "romans.shx",
    #: "arial.ttf"), preservado pra (a) regravar o STYLE igual e (b) o canvas
    #: saber que ".shx" é uma fonte de traço do AutoCAD que nunca existe
    #: no sistema — e escolher uma substituta estreita em vez de deixar o Qt
    #: cair numa fonte larga qualquer (Tahoma no Windows). "" = desconhecido
    #: (estilo criado no NewSIcad): grava `font_family + ".ttf"` como antes.
    font_file: str = ""


@dataclass
class DimStyle:
    """DIMSTYLE simplificado: tamanho do texto e da marca de seta usados pra
    RENDERIZAR as `Dimension` nativas do NewSIcad (canvas) e gravá-las no
    .dxf (`$DIMTXT`/`$DIMASZ`). Os valores padrão são os históricos do canvas
    (`DIM_TEXT_HEIGHT` 2.0 / tick 0.6, pensados pra desenho em mm); ao abrir
    um .dxf eles passam a vir do próprio arquivo (dimstyle atual e/ou a
    altura real das cotas importadas) pra uma cota nova numa planta em
    METROS não sair 1000x maior que a planta (WP-B 2026-09)."""

    text_height: float = 2.0
    arrow_size: float = 0.6


@dataclass
class TableStyle:
    """TABLESTYLE: valores padrão usados pelo próximo comando TABLE — não é
    um estilo "vivo" ligado às tabelas já criadas (mudar isso aqui não
    altera tabelas existentes, só as próximas), mesma simplificação de
    DIMSTYLE."""

    show_borders: bool = True
    text_height: float = 0.5


@dataclass
class MLeaderStyle:
    """MLEADERSTYLE: valores padrão usados pelo próximo comando LEADER —
    mesma simplificação de TABLESTYLE/DIMSTYLE (LEADER nesta versão é uma
    LWPolyline + Text, não uma entidade MULTILEADER de verdade, ver
    annotation_commands.py)."""

    text_height: float = 2.5


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
        # Revisão GLOBAL das definições de bloco: bumpada sempre que qualquer
        # definição muda (define_block — BEDIT/BLOCK/XREF reload — ou PURGE).
        # Consumidores que fazem cache de algo derivado do CONTEÚDO das
        # definições (ex.: as impressões digitais de render em
        # CanvasView.refresh_entities) comparam este número pra saber quando
        # o cache inteiro venceu. Global de propósito: invalidação por nome
        # exigiria propagar mudanças de blocos ANINHADOS pros pais (A contém
        # B, B muda, cache de A fica podre) — mudança de definição é rara o
        # bastante pra "joga tudo fora" ser a troca certa. Transiente, não
        # vai pro .dxf.
        self.block_defs_revision: int = 0
        # Estado transiente do LAYISO/LAYUNISO (utility_commands.py) — quais
        # camadas o LAYISO mais recente escondeu, pra o LAYUNISO conseguir
        # reverter. Não é salvo no .dxf (é estado de sessão, não do desenho).
        self.isolated_layers: list[str] | None = None
        # STYLE: estilos de texto nomeados, sempre com "Standard" disponível
        # (igual ao AutoCAD, que nunca deixa apagar o estilo padrão).
        self.text_styles: dict[str, TextStyle] = {"Standard": TextStyle()}
        self.current_text_style: str = "Standard"
        # TABLESTYLE / MLEADERSTYLE: um único estilo global cada (não
        # nomeado/múltiplo como no AutoCAD de verdade) — valores lidos como
        # default por table_command/leader_command na hora de criar.
        self.table_style = TableStyle()
        self.mleader_style = MLeaderStyle()
        # DIMSTYLE simplificado (tamanho de texto/seta das cotas nativas) —
        # ver DimStyle acima; lido do .dxf em `load_dxf`.
        self.dim_style = DimStyle()
        # Escala de anotação global e simplificada (sem representações
        # múltiplas por objeto/viewport como o Annotation Scale de verdade
        # do AutoCAD, que não se aplica sem paper space) — multiplica a
        # altura padrão de Text/Dimension/Table/Leader na hora de criar.
        self.annotation_scale: float = 1.0

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
        self.block_defs_revision += 1  # invalida caches de conteúdo, ver __init__

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
        if not new_name or not new_name.strip():
            raise ValueError("O novo nome da camada não pode ser vazio.")
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
        if removable:
            self.block_defs_revision += 1  # invalida caches de conteúdo
        return removable
