"""Comandos de desenho e medição (LINE, CIRCLE, ARC, RECTANGLE, PLINE,
ELLIPSE, DIST) com prompts sequenciais idênticos aos do AutoCAD."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import Arc, Circle, Ellipse, Line, LWPolyline, Point
from newsicad.core.geometry_ops import arc_from_3_points


def line_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    first = yield Prompt("Specify first point:", kind="point")
    prev = first
    while True:
        nxt = yield Prompt("Specify next point or [Undo]:", kind="point", options=["Undo"])
        if nxt is ENTER:
            return
        if nxt == "UNDO":
            continue
        ctx.document.add_entity(Line(start=prev, end=nxt))
        prev = nxt


def circle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    center = yield Prompt("Specify center point for circle:", kind="point")
    radius = yield Prompt("Specify radius of circle:", kind="distance")
    ctx.document.add_entity(Circle(center=center, radius=radius))


def arc_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify start point of arc:", kind="point")
    p2 = yield Prompt("Specify second point of arc:", kind="point")
    p3 = yield Prompt("Specify end point of arc:", kind="point")
    center, radius, start_angle, end_angle = arc_from_3_points(p1, p2, p3)
    ctx.document.add_entity(Arc(center=center, radius=radius, start_angle=start_angle, end_angle=end_angle))


def rectangle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first corner point:", kind="point")
    p2 = yield Prompt("Specify other corner point:", kind="point")
    points = [Point(p1.x, p1.y), Point(p2.x, p1.y), Point(p2.x, p2.y), Point(p1.x, p2.y)]
    ctx.document.add_entity(LWPolyline(points=points, closed=True))


def pline_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    first = yield Prompt("Specify start point:", kind="point")
    points = [first]
    while True:
        nxt = yield Prompt("Specify next point or [Undo]:", kind="point", options=["Undo"])
        if nxt is ENTER:
            break
        if nxt == "UNDO":
            if len(points) > 1:
                points.pop()
            continue
        points.append(nxt)
    if len(points) >= 2:
        ctx.document.add_entity(LWPolyline(points=points, closed=False))


def ellipse_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    center = yield Prompt("Specify center of ellipse:", kind="point")
    axis_end = yield Prompt("Specify endpoint of axis:", kind="point")
    minor_radius = yield Prompt("Specify distance to other axis:", kind="distance")

    major_radius = center.distance_to(axis_end)
    rotation = center.angle_to(axis_end)
    ctx.document.add_entity(
        Ellipse(center=center, radius_major=major_radius, radius_minor=minor_radius, rotation=rotation)
    )


def dist_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first point:", kind="point")
    p2 = yield Prompt("Specify second point:", kind="point")
    distance = p1.distance_to(p2)
    angle = math.degrees(p1.angle_to(p2)) % 360
    yield Prompt(f"Distância = {distance:.4f}   Ângulo no plano XY = {angle:.2f}°", kind="info")
