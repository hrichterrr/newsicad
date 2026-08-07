"""Comandos utilitários de consulta/organização: AREA (AA), ID, DDEDIT (ED) e
PURGE (PU). Seguem o mesmo padrão gerador dos outros módulos de comando."""

from __future__ import annotations

from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.commands.modify_commands import _select_objects
from newsicad.core.entities import Circle, LWPolyline, Text
from newsicad.core.geometry_ops import polygon_area, polygon_perimeter

import math


def id_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    point = yield Prompt("Specify point:", kind="point")
    yield Prompt(f"X = {point.x:.4f}  Y = {point.y:.4f}  Z = 0.0000", kind="info")


def area_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """AREA (AA): soma a área/perímetro de círculos e polilinhas fechadas
    selecionados. Simplificação documentada no README: não tem o modo
    "clicar pontos pra definir um polígono" do AREA de verdade do AutoCAD —
    só funciona em cima de entidades já desenhadas (normalmente uma
    LWPolyline fechada representando o contorno de um ambiente)."""
    selected = yield from _select_objects(ctx, "Select objects:")

    total_area = 0.0
    total_perimeter = 0.0
    counted = 0
    for entity in selected:
        if isinstance(entity, Circle):
            total_area += math.pi * entity.radius**2
            total_perimeter += 2 * math.pi * entity.radius
            counted += 1
        elif isinstance(entity, LWPolyline) and entity.closed and len(entity.points) >= 3:
            total_area += polygon_area(entity.points)
            total_perimeter += polygon_perimeter(entity.points, closed=True)
            counted += 1

    if counted == 0:
        yield Prompt(
            "AREA: nenhum círculo ou polilinha fechada selecionado (contornos abertos e "
            "outros tipos de entidade não são suportados nesta versão).",
            kind="info",
        )
        return

    label = "Área" if counted == 1 else "Área total"
    yield Prompt(f"{label} = {total_area:.4f}   Perímetro = {total_perimeter:.4f}", kind="info")


def _select_text(ctx: CommandContext, message: str) -> Generator[Prompt, object, Text | None]:
    selected = yield from _select_objects(ctx, message)
    texts = [e for e in selected if isinstance(e, Text)]
    return texts[0] if texts else None


def edit_text_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """DDEDIT (ED): edita o conteúdo de um Text (MTEXT/LEADER) já colocado no
    desenho. Simplificação documentada no README: só edita `Text` — cotas
    (Dimension) não têm campo de texto sobreposto no modelo do NewSIcad (o
    texto exibido é sempre calculado a partir da medição real), então
    selecionar uma cota aqui não faz nada."""
    target = yield from _select_text(ctx, "Select an annotation object or [Undo]:")
    if target is None:
        yield Prompt("ED: nenhum texto selecionado (cotas não têm texto editável nesta versão).", kind="info")
        return

    new_content = yield Prompt("Enter new text:", kind="text")
    if new_content is ENTER:
        return
    text = str(new_content).strip("\r")
    if text == "":
        return
    target.content = text


def purge_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """PURGE (PU): remove camadas e definições de bloco não usadas em lugar
    nenhum do desenho (nem no espaço do modelo, nem dentro de outro bloco).
    Camada "0" nunca é removida (igual ao AutoCAD); se a camada atual for
    removida, a camada atual volta a ser "0"."""
    removed_layers = ctx.document.purge_unused_layers()
    removed_blocks = ctx.document.purge_unused_blocks()

    if not removed_layers and not removed_blocks:
        yield Prompt("PURGE: nada para remover — nenhuma camada ou bloco não usado.", kind="info")
        return

    parts = []
    if removed_layers:
        parts.append(f"{len(removed_layers)} camada(s): {', '.join(removed_layers)}")
    if removed_blocks:
        parts.append(f"{len(removed_blocks)} bloco(s): {', '.join(removed_blocks)}")
    yield Prompt("PURGE removeu " + "; ".join(parts) + ".", kind="info")
