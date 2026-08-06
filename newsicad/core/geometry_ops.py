"""Operações geométricas puras usadas pelos comandos de desenho e de
modificação (MOVE, COPY, ROTATE, MIRROR, SCALE)."""

from __future__ import annotations

import copy
import math
import uuid

from newsicad.core.entities import (
    Arc,
    BlockReference,
    Circle,
    Entity,
    ImageReference,
    Line,
    LWPolyline,
    Point,
)


# ---------------------------------------------------------------------- #
# círculo/arco por 3 pontos (usado por ARC e por MIRROR de Arc)
# ---------------------------------------------------------------------- #
def circumcenter(p1: Point, p2: Point, p3: Point) -> Point:
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


def arc_from_3_points(p1: Point, p2: Point, p3: Point) -> tuple[Point, float, float, float]:
    """Retorna (center, radius, start_angle, end_angle) em radianos, sentido
    anti-horário de start_angle para end_angle, passando por p2."""
    center = circumcenter(p1, p2, p3)
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


# ---------------------------------------------------------------------- #
# transformações de ponto
# ---------------------------------------------------------------------- #
def translate_point(p: Point, dx: float, dy: float) -> Point:
    return Point(p.x + dx, p.y + dy)


def rotate_point(p: Point, base: Point, angle_rad: float) -> Point:
    dx, dy = p.x - base.x, p.y - base.y
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    return Point(base.x + dx * cos_a - dy * sin_a, base.y + dx * sin_a + dy * cos_a)


def scale_point(p: Point, base: Point, factor: float) -> Point:
    return Point(base.x + (p.x - base.x) * factor, base.y + (p.y - base.y) * factor)


def mirror_point(p: Point, p1: Point, p2: Point) -> Point:
    dx, dy = p2.x - p1.x, p2.y - p1.y
    denom = dx * dx + dy * dy
    if denom < 1e-12:
        return Point(p.x, p.y)
    a = (dx * dx - dy * dy) / denom
    b = 2 * dx * dy / denom
    px, py = p.x - p1.x, p.y - p1.y
    return Point(a * px + b * py + p1.x, b * px - a * py + p1.y)


# ---------------------------------------------------------------------- #
# clonagem
# ---------------------------------------------------------------------- #
def clone_entity(entity: Entity) -> Entity:
    clone = copy.deepcopy(entity)
    clone.id = uuid.uuid4().hex
    return clone


# ---------------------------------------------------------------------- #
# transformações de entidade (mutam em memória)
# ---------------------------------------------------------------------- #
def translate_entity(entity: Entity, dx: float, dy: float) -> None:
    if isinstance(entity, Line):
        entity.start = translate_point(entity.start, dx, dy)
        entity.end = translate_point(entity.end, dx, dy)
    elif isinstance(entity, (Circle, Arc)):
        entity.center = translate_point(entity.center, dx, dy)
    elif isinstance(entity, LWPolyline):
        entity.points = [translate_point(p, dx, dy) for p in entity.points]
    elif isinstance(entity, (BlockReference, ImageReference)):
        entity.insertion_point = translate_point(entity.insertion_point, dx, dy)
    else:
        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")


def rotate_entity(entity: Entity, base: Point, angle_rad: float) -> None:
    if isinstance(entity, Line):
        entity.start = rotate_point(entity.start, base, angle_rad)
        entity.end = rotate_point(entity.end, base, angle_rad)
    elif isinstance(entity, Circle):
        entity.center = rotate_point(entity.center, base, angle_rad)
    elif isinstance(entity, Arc):
        entity.center = rotate_point(entity.center, base, angle_rad)
        entity.start_angle = (entity.start_angle + angle_rad) % (2 * math.pi)
        entity.end_angle = (entity.end_angle + angle_rad) % (2 * math.pi)
    elif isinstance(entity, LWPolyline):
        entity.points = [rotate_point(p, base, angle_rad) for p in entity.points]
    elif isinstance(entity, BlockReference):
        entity.insertion_point = rotate_point(entity.insertion_point, base, angle_rad)
        entity.rotation = (entity.rotation + angle_rad) % (2 * math.pi)
    elif isinstance(entity, ImageReference):
        # Imagens não têm campo de rotação própria (ver ImageReference) —
        # só o ponto de inserção acompanha o giro do grupo selecionado.
        entity.insertion_point = rotate_point(entity.insertion_point, base, angle_rad)
    else:
        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")


def scale_entity(entity: Entity, base: Point, factor: float) -> None:
    if isinstance(entity, Line):
        entity.start = scale_point(entity.start, base, factor)
        entity.end = scale_point(entity.end, base, factor)
    elif isinstance(entity, Circle):
        entity.center = scale_point(entity.center, base, factor)
        entity.radius *= factor
    elif isinstance(entity, Arc):
        entity.center = scale_point(entity.center, base, factor)
        entity.radius *= factor
    elif isinstance(entity, LWPolyline):
        entity.points = [scale_point(p, base, factor) for p in entity.points]
    elif isinstance(entity, BlockReference):
        entity.insertion_point = scale_point(entity.insertion_point, base, factor)
        entity.scale *= factor
    elif isinstance(entity, ImageReference):
        entity.insertion_point = scale_point(entity.insertion_point, base, factor)
        entity.width *= factor
        entity.height *= factor
    else:
        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")


def mirror_entity(entity: Entity, p1: Point, p2: Point) -> Entity:
    """Retorna uma NOVA entidade espelhada (o original não é alterado)."""
    mirrored = clone_entity(entity)

    if isinstance(mirrored, Line):
        mirrored.start = mirror_point(entity.start, p1, p2)
        mirrored.end = mirror_point(entity.end, p1, p2)
    elif isinstance(mirrored, Circle):
        mirrored.center = mirror_point(entity.center, p1, p2)
    elif isinstance(mirrored, Arc):
        mid_angle = entity.start_angle + ((entity.end_angle - entity.start_angle) % (2 * math.pi)) / 2
        start_pt = entity.start_point()
        mid_pt = Point(
            entity.center.x + entity.radius * math.cos(mid_angle),
            entity.center.y + entity.radius * math.sin(mid_angle),
        )
        end_pt = entity.end_point()
        m1, m2, m3 = (
            mirror_point(start_pt, p1, p2),
            mirror_point(mid_pt, p1, p2),
            mirror_point(end_pt, p1, p2),
        )
        center, radius, start_angle, end_angle = arc_from_3_points(m1, m2, m3)
        mirrored.center = center
        mirrored.radius = radius
        mirrored.start_angle = start_angle
        mirrored.end_angle = end_angle
    elif isinstance(mirrored, LWPolyline):
        mirrored.points = [mirror_point(p, p1, p2) for p in entity.points]
    elif isinstance(mirrored, BlockReference):
        # Simplificação: espelha o ponto de inserção e o ângulo, mas não
        # inverte o conteúdo do bloco em si (exigiria escala negativa por
        # eixo, que BlockReference não modela — ver README).
        mirrored.insertion_point = mirror_point(entity.insertion_point, p1, p2)
        mirrored.rotation = (-entity.rotation) % (2 * math.pi)
    elif isinstance(mirrored, ImageReference):
        mirrored.insertion_point = mirror_point(entity.insertion_point, p1, p2)
    else:
        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")

    return mirrored
