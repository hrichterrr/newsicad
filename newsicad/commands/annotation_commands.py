"""Comandos de anotação: MTEXT, DIMLINEAR, DIMALIGNED, DIMANGULAR, DIMRADIUS,
DIMDIAMETER, DIMSTYLE e HATCH. Seguem o mesmo padrão gerador dos comandos em
draw_commands.py e modify_commands.py."""

from __future__ import annotations

from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.commands.modify_commands import _select_objects
from newsicad.core.entities import Arc, Circle, Dimension, Entity, Hatch, LWPolyline, Text

DEFAULT_TEXT_HEIGHT = 2.5


def mtext_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    insertion = yield Prompt("Specify insertion point:", kind="point")
    content = yield Prompt("Enter text:", kind="text")
    if content is ENTER:
        return
    text = str(content).strip("\r")
    if text == "":
        return
    ctx.document.add_entity(
        Text(insertion_point=insertion, content=text, height=DEFAULT_TEXT_HEIGHT, rotation=0.0)
    )


def dimlinear_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first extension line origin:", kind="point")
    p2 = yield Prompt("Specify second extension line origin:", kind="point")
    dim_line = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="linear", point1=p1, point2=p2, dim_line_point=dim_line)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimaligned_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first extension line origin:", kind="point")
    p2 = yield Prompt("Specify second extension line origin:", kind="point")
    dim_line = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="aligned", point1=p1, point2=p2, dim_line_point=dim_line)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimangular_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    vertex = yield Prompt("Specify angle vertex:", kind="point")
    p1 = yield Prompt("Specify first angle endpoint:", kind="point")
    p2 = yield Prompt("Specify second angle endpoint:", kind="point")
    arc_location = yield Prompt("Specify dimension arc line location:", kind="point")
    dim = Dimension(kind="angular", center=vertex, point1=p1, point2=p2, dim_line_point=arc_location)
    ctx.document.add_entity(dim)
    yield Prompt(f"Angle = {dim.measurement_text()}", kind="info")


def _select_circle_or_arc(
    ctx: CommandContext, message: str
) -> Generator[Prompt, object, Entity | None]:
    selected = yield from _select_objects(ctx, message)
    candidates = [e for e in selected if isinstance(e, (Circle, Arc))]
    return candidates[0] if candidates else None


def dimradius_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    target = yield from _select_circle_or_arc(ctx, "Select arc or circle:")
    if target is None:
        yield Prompt("Nenhum círculo/arco selecionado.", kind="info")
        return
    leader = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="radius", center=target.center, radius=target.radius, leader_point=leader)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimdiameter_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    target = yield from _select_circle_or_arc(ctx, "Select arc or circle:")
    if target is None:
        yield Prompt("Nenhum círculo/arco selecionado.", kind="info")
        return
    leader = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="diameter", center=target.center, radius=target.radius, leader_point=leader)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimstyle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    yield Prompt(
        "NewSIcad ainda só suporta o estilo de cota padrão "
        "(estilos de cota nomeados/customizados não são suportados nesta versão).",
        kind="info",
    )


def hatch_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(
        ctx, "Select a closed polyline as the hatch boundary:"
    )
    boundaries = [
        e for e in selected if isinstance(e, LWPolyline) and e.closed and len(e.points) >= 3
    ]
    if not boundaries:
        yield Prompt(
            "HATCH nesta versão só aceita uma LWPolyline fechada pré-existente como "
            "contorno (detecção automática de contorno é o comando BOUNDARY, "
            "ainda não implementado).",
            kind="info",
        )
        return
    for boundary in boundaries:
        ctx.document.add_entity(Hatch(layer=boundary.layer, boundary_points=list(boundary.points)))


def leader_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """LEADER simplificado: reusa LWPolyline (a linha poligonal terminando
    perto do texto, aproximando a seta) + Text (a anotação na ponta) em vez
    de criar um tipo de entidade dedicado — v1 suficiente pra um leader
    básico sem precisar de mais um Entity novo só pra isso."""
    first = yield Prompt("Specify leader start point:", kind="point")
    points = [first]
    while True:
        nxt = yield Prompt("Specify next point:", kind="point")
        if nxt is ENTER:
            break
        points.append(nxt)
    if len(points) < 2:
        return
    ctx.document.add_entity(LWPolyline(points=points, closed=False))

    content = yield Prompt("Enter leader annotation text:", kind="text")
    if content is ENTER:
        return
    text = str(content).strip("\r")
    if text == "":
        return
    ctx.document.add_entity(
        Text(insertion_point=points[-1], content=text, height=DEFAULT_TEXT_HEIGHT, rotation=0.0)
    )
