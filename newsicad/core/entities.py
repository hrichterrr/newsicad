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
class Text(Entity):
    """Texto simples ou multilinha (comando MTEXT). `content` pode conter
    "\\n" para múltiplas linhas."""

    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    content: str = ""
    height: float = 2.5
    rotation: float = 0.0  # radianos


@dataclass
class Dimension(Entity):
    """Cota (DIMLINEAR/DIMALIGNED/DIMANGULAR/DIMRADIUS/DIMDIAMETER), unificada
    num único tipo com `kind` selecionando a interpretação dos campos:

    - "linear"/"aligned": point1, point2 (origens das linhas de extensão) e
      dim_line_point (onde o usuário posicionou a linha de cota).
    - "radius"/"diameter": center + radius do círculo/arco medido, e
      leader_point (posição do texto/leader).
    - "angular": center é o vértice do ângulo, point1/point2 são os pontos
      que definem os dois lados, e dim_line_point é onde o arco da cota foi
      posicionado.
    """

    kind: str = "linear"
    point1: Point = field(default_factory=lambda: Point(0, 0))
    point2: Point = field(default_factory=lambda: Point(0, 0))
    dim_line_point: Point = field(default_factory=lambda: Point(0, 0))
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0
    leader_point: Point = field(default_factory=lambda: Point(0, 0))

    def is_horizontal(self) -> bool:
        return abs(self.point2.x - self.point1.x) >= abs(self.point2.y - self.point1.y)

    def measurement(self) -> float:
        if self.kind == "aligned":
            return self.point1.distance_to(self.point2)
        if self.kind == "linear":
            return (
                abs(self.point2.x - self.point1.x)
                if self.is_horizontal()
                else abs(self.point2.y - self.point1.y)
            )
        if self.kind == "radius":
            return self.radius
        if self.kind == "diameter":
            return self.radius * 2
        if self.kind == "angular":
            v1 = math.atan2(self.point1.y - self.center.y, self.point1.x - self.center.x)
            v2 = math.atan2(self.point2.y - self.center.y, self.point2.x - self.center.x)
            diff = abs((v2 - v1 + math.pi) % (2 * math.pi) - math.pi)
            return math.degrees(diff)
        return 0.0

    def measurement_text(self) -> str:
        if self.kind == "radius":
            return f"R{self.measurement():.2f}"
        if self.kind == "diameter":
            return f"Ø{self.measurement():.2f}"
        if self.kind == "angular":
            return f"{self.measurement():.2f}°"
        return f"{self.measurement():.2f}"


@dataclass
class Hatch(Entity):
    """Hachura por preenchimento de linhas diagonais paralelas dentro de um
    contorno fechado simples (v1: sempre o contorno de uma LWPolyline fechada
    pré-existente, copiado para `boundary_points` — detecção automática de
    contorno a partir de múltiplas entidades é o comando BOUNDARY, fora de
    escopo aqui)."""

    boundary_points: list[Point] = field(default_factory=list)
    angle: float = 0.7853981633974483  # 45°, radianos
    spacing: float = 1.0
