"""Geometria pura das entidades desenháveis (sem dependência de Qt)."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.hypot(other.x - self.x, other.y - self.y)

    def angle_to(self, other: "Point") -> float:
        return math.atan2(other.y - self.y, other.x - self.x)

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Entity:
    layer: str = "0"
    color: str | None = None  # None = ByLayer
    id: str = field(default_factory=_new_id)


@dataclass
class Line(Entity):
    start: Point = field(default_factory=lambda: Point(0, 0))
    end: Point = field(default_factory=lambda: Point(0, 0))

    def length(self) -> float:
        return self.start.distance_to(self.end)

    def midpoint(self) -> Point:
        return Point((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)


@dataclass
class Circle(Entity):
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0


@dataclass
class Arc(Entity):
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0
    start_angle: float = 0.0  # radianos
    end_angle: float = 0.0  # radianos

    def start_point(self) -> Point:
        return Point(
            self.center.x + self.radius * math.cos(self.start_angle),
            self.center.y + self.radius * math.sin(self.start_angle),
        )

    def end_point(self) -> Point:
        return Point(
            self.center.x + self.radius * math.cos(self.end_angle),
            self.center.y + self.radius * math.sin(self.end_angle),
        )


@dataclass
class LWPolyline(Entity):
    points: list[Point] = field(default_factory=list)
    closed: bool = False

    def segments(self) -> list[tuple[Point, Point]]:
        pts = self.points
        pairs = list(zip(pts, pts[1:]))
        if self.closed and len(pts) > 2:
            pairs.append((pts[-1], pts[0]))
        return pairs
