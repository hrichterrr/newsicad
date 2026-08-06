"""Geometria pura das entidades desenháveis (sem dependência de Qt)."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path


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
class Ellipse(Entity):
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius_major: float = 0.0
    radius_minor: float = 0.0
    rotation: float = 0.0  # radianos, ângulo do eixo maior


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


@dataclass
class BlockReference(Entity):
    """Instância de um bloco inserida no desenho (comando INSERT). A
    geometria de verdade fica em `Document.block_definitions[block_name]`
    (uma lista de entidades "template" com coordenadas relativas ao ponto
    base do bloco) — esta entidade só guarda a transformação de inserção.

    `is_xref`/`xref_path` marcam uma referência externa (comando XREF):
    tecnicamente é a mesma coisa que um bloco comum, mas a definição foi
    importada de um arquivo .dxf externo em vez de ter sido desenhada no
    documento atual. Ver README para as limitações (sem watch de arquivo)."""

    block_name: str = ""
    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    scale: float = 1.0
    rotation: float = 0.0  # radianos
    is_xref: bool = False
    xref_path: Path | None = None


@dataclass
class ImageReference(Entity):
    """Referência a uma imagem raster (.png/.jpg) inserida no desenho
    (comando IMAGEATTACH). Não sobrevive à gravação em .dxf — ver README."""

    path: Path = field(default_factory=Path)
    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    width: float = 100.0
    height: float = 100.0
