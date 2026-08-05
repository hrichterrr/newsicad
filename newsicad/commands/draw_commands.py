"""Comandos de desenho (LINE, CIRCLE, ARC, RECTANGLE, PLINE) com prompts
sequenciais idênticos aos do AutoCAD."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point


def line_command(doc: Document) -> Generator[Prompt, object, None]:
    first = yield Prompt("Specify first point:", kind="point")
    prev = first
    while True:
        nxt = yield Prompt("Specify next point or [Undo]:", kind="point", options=["Undo"])
        if nxt is ENTER:
            return
        if nxt == "UNDO":
            continue
        doc.add_entity(Line(start=prev, end=nxt))
        prev = nxt


def circle_command(doc: Document) -> Generator[Prompt, object, None]:
    center = yield Prompt("Specify center point for circle:", kind="point")
    radius = yield Prompt("Specify radius of circle:", kind="distance")
    doc.add_entity(Circle(center=center, radius=radius))


def arc_command(doc: Document) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify start point of arc:", kind="point")
    p2 = yield Prompt("Specify second point of arc:", kind="point")
    p3 = yield Prompt("Specify end point of arc:", kind="point")
    center, radius, start_angle, end_angle = _arc_from_3_points(p1, p2, p3)
    doc.add_entity(Arc(center=center, radius=radius, start_angle=start_angle, end_angle=end_angle))


def rectangle_command(doc: Document) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first corner point:", kind="point")
    p2 = yield Prompt("Specify other corner point:", kind="point")
    points = [Point(p1.x, p1.y), Point(p2.x, p1.y), Point(p2.x, p2.y), Point(p1.x, p2.y)]
    doc.add_entity(LWPolyline(points=points, closed=True))


def pline_command(doc: Document) -> Generator[Prompt, object, None]:
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
        doc.add_entity(LWPolyline(points=points, closed=False))


def _circumcenter(p1: Point, p2: Point, p3: Point) -> Point:
    ax, ay = p1.x, p1.y
    bx, by = p2.x, p2.y
    cx, cy = p3.x, p3.y
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        raise ValueError("Os três pontos são colineares e não formam um arco")
    ux = (
        (ax**2 + ay**2) * (by - cy)
        + (bx**2 + by**2) * (cy - ay)
        + (cx**2 + cy**2) * (ay - by)
    ) / d
    uy = (
        (ax**2 + ay**2) * (cx - bx)
        + (bx**2 + by**2) * (ax - cx)
        + (cx**2 + cy**2) * (bx - ax)
    ) / d
    return Point(ux, uy)


def _arc_from_3_points(p1: Point, p2: Point, p3: Point) -> tuple[Point, float, float, float]:
    """Retorna (center, radius, start_angle, end_angle) em radianos, sentido
    anti-horário de start_angle para end_angle, passando por p2."""
    center = _circumcenter(p1, p2, p3)
    radius = center.distance_to(p1)

    def norm(a: float) -> float:
        return a % (2 * math.pi)

    a1 = norm(center.angle_to(p1))
    a2 = norm(center.angle_to(p2))
    a3 = norm(center.angle_to(p3))

    def ccw_diff(a: float, b: float) -> float:
        return (b - a) % (2 * math.pi)

    if ccw_diff(a1, a2) <= ccw_diff(a1, a3):
        return center, radius, a1, a3
    return center, radius, a3, a1
