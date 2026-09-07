"""Comandos de blocos e referências (BLOCK, INSERT) + fábricas de generator
usadas pela MainWindow para XREF/IMAGEATTACH depois de um QFileDialog
(newsicad/ui/main_window.py) — essas duas precisam de uma etapa de UI
(escolher arquivo) que não cabe no sistema de Prompt (só point/distance/
text/keyword/selection/info), então a MainWindow resolve o arquivo primeiro
e injeta o generator já fechado sobre esse valor via
`CommandInterpreter.start_generator` (ver newsicad/commands/interpreter.py).

BLOCK segue o comportamento padrão do AutoCAD: "consome" as entidades
selecionadas (viram a definição do bloco, com coordenadas relativas ao ponto
base) e as remove do desenho, substituindo-as por uma única BlockReference no
ponto base — para não fazer o desenho do usuário "sumir" visualmente."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.commands.modify_commands import _select_objects
from newsicad.core.entities import BlockReference, Entity, ImageReference
from newsicad.core.geometry_ops import clone_entity, translate_entity


def block_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    name = yield Prompt("Enter block name:", kind="text")
    if name is ENTER or not str(name).strip():
        yield Prompt("BLOCK cancelado: nome de bloco vazio.", kind="info")
        return
    name = str(name).strip()

    base_point = yield Prompt("Specify base point:", kind="point")

    selected = yield from _select_objects(ctx, "Select objects for the block:")
    if not selected:
        yield Prompt("BLOCK cancelado: nenhum objeto selecionado.", kind="info")
        return

    redefining = name in ctx.document.block_definitions

    definition: list[Entity] = []
    for entity in selected:
        clone = clone_entity(entity)
        translate_entity(clone, -base_point.x, -base_point.y)
        definition.append(clone)
    ctx.document.define_block(name, definition)

    for entity in selected:
        ctx.document.remove_entity(entity.id)
    ctx.selection.clear()

    ctx.document.add_entity(
        BlockReference(block_name=name, insertion_point=base_point, layer=ctx.document.current_layer)
    )

    if redefining:
        yield Prompt(f'Bloco "{name}" redefinido.', kind="info")


def insert_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    while True:
        name = yield Prompt("Enter block name to insert:", kind="text")
        if name is ENTER or not str(name).strip():
            yield Prompt("INSERT cancelado.", kind="info")
            return
        name = str(name).strip()
        if name in ctx.document.block_definitions:
            break
        yield Prompt(
            f'Bloco "{name}" não foi definido neste desenho. Use BLOCK primeiro.',
            kind="info",
        )

    insertion_point = yield Prompt("Specify insertion point:", kind="point")

    # Escala uniforme, ou [XY] para uma por eixo. Valor NEGATIVO é como o DXF
    # representa um bloco espelhado (flip), e escala diferente por eixo é como
    # chega um bloco dinâmico esticado do AutoCAD — o canvas e o gravador já
    # sabiam lidar com os dois (ver BlockReference.scale_xy e
    # `_create_block_reference_item`), só este comando é que recusava, então
    # um símbolo espelhado do acervo da New SI não podia ser reinserido pelo
    # próprio programa (achado no teste de duas plantas, 2026-09-06).
    scale_raw = yield Prompt("Specify scale factor or [XY] <1>:", kind="distance", options=["XY"])
    if scale_raw == "XY":
        x_raw = yield Prompt("Specify X scale factor <1>:", kind="distance")
        scale = 1.0 if x_raw is ENTER else float(x_raw)
        y_raw = yield Prompt(f"Specify Y scale factor <{scale:g}>:", kind="distance")
        scale_y = scale if y_raw is ENTER else float(y_raw)
    else:
        scale = 1.0 if scale_raw is ENTER else float(scale_raw)
        scale_y = scale

    if scale == 0 or scale_y == 0:
        # Zero continua proibido: o ezdxf recusa xscale/yscale igual a zero na
        # gravação e volta silenciosamente para 1.0 ao regravar — um bloco
        # "escondido" com escala 0 reaparecia em tamanho normal ao reabrir o
        # arquivo, sem nenhum aviso (bug real de auditoria, 2026-08-22).
        # Negativo, ao contrário, atravessa a ida e volta intacto (conferido
        # em 2026-09-06) e é justamente o espelhamento.
        yield Prompt("INSERT: o fator de escala não pode ser zero (negativo espelha).", kind="info")
        return

    rotation_raw = yield Prompt("Specify rotation angle <0>:", kind="distance")
    rotation_deg = 0.0 if rotation_raw is ENTER else float(rotation_raw)

    ctx.document.add_entity(
        BlockReference(
            block_name=name,
            insertion_point=insertion_point,
            scale=scale,
            # `None` = uniforme (ver BlockReference.scale_y).
            scale_y=None if scale_y == scale else scale_y,
            rotation=math.radians(rotation_deg),
            layer=ctx.document.current_layer,
        )
    )


def place_reference_command(
    ctx: CommandContext,
    block_name: str,
    *,
    is_xref: bool = False,
    xref_path: Path | None = None,
) -> Generator[Prompt, object, None]:
    """Só pede o ponto de inserção — usado depois que a MainWindow já
    resolveu o nome do bloco/arquivo externo (XREF) via QFileDialog."""
    point = yield Prompt(f'Specify insertion point for "{block_name}":', kind="point")
    ctx.document.add_entity(
        BlockReference(
            block_name=block_name,
            insertion_point=point,
            is_xref=is_xref,
            xref_path=xref_path,
            layer=ctx.document.current_layer,
        )
    )


def place_image_command(ctx: CommandContext, path: Path) -> Generator[Prompt, object, None]:
    """Só pede ponto/largura/altura — a MainWindow já resolveu o arquivo de
    imagem via QFileDialog antes de injetar este generator."""
    point = yield Prompt("Specify insertion point:", kind="point")

    width_raw = yield Prompt("Specify width <100>:", kind="distance")
    width = 100.0 if width_raw is ENTER else float(width_raw)

    height_raw = yield Prompt("Specify height <100>:", kind="distance")
    height = 100.0 if height_raw is ENTER else float(height_raw)

    ctx.document.add_entity(
        ImageReference(
            path=path, insertion_point=point, width=width, height=height, layer=ctx.document.current_layer
        )
    )
