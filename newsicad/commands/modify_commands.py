"""Comandos MODIFY (ERASE, MOVE, COPY, ROTATE, MIRROR, SCALE) — todos seguem
o padrão do AutoCAD: "Select objects:" primeiro, depois os parâmetros da
transformação."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import Entity
from newsicad.core.geometry_ops import (
    clone_entity,
    mirror_entity,
    rotate_entity,
    scale_entity,
    translate_entity,
)


def _select_objects(ctx: CommandContext, message: str = "Select objects:") -> Generator[Prompt, object, list[Entity]]:
    ctx.selection.clear()
    yield Prompt(message, kind="selection")
    return list(ctx.selection.entities(ctx.document))


def erase_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    for entity in selected:
        ctx.document.remove_entity(entity.id)
    ctx.selection.clear()


def move_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    target = yield Prompt("Specify second point:", kind="point")
    dx, dy = target.x - base.x, target.y - base.y
    for entity in selected:
        translate_entity(entity, dx, dy)
    ctx.selection.clear()


def copy_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    target = yield Prompt("Specify second point:", kind="point")
    dx, dy = target.x - base.x, target.y - base.y
    new_ids = set()
    for entity in selected:
        clone = clone_entity(entity)
        translate_entity(clone, dx, dy)
        ctx.document.add_entity(clone)
        new_ids.add(clone.id)
    ctx.selection.set(new_ids)


def rotate_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    angle_deg = yield Prompt("Specify rotation angle:", kind="distance")
    angle_rad = math.radians(angle_deg)
    for entity in selected:
        rotate_entity(entity, base, angle_rad)
    ctx.selection.clear()


def scale_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    factor = yield Prompt("Specify scale factor:", kind="distance")
    for entity in selected:
        scale_entity(entity, base, factor)
    ctx.selection.clear()


def mirror_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    p1 = yield Prompt("Specify first point of mirror line:", kind="point")
    p2 = yield Prompt("Specify second point of mirror line:", kind="point")
    choice = yield Prompt("Erase source objects? [Yes/No] <N>:", kind="keyword", options=["Yes", "No"])

    for entity in selected:
        ctx.document.add_entity(mirror_entity(entity, p1, p2))

    if choice == "YES":
        for entity in selected:
            ctx.document.remove_entity(entity.id)

    ctx.selection.clear()
