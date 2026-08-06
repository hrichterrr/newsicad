"""Operações geométricas puras usadas pelos comandos de desenho e de
modificação (MOVE, COPY, ROTATE, MIRROR, SCALE)."""

from __future__ import annotations

import copy
import math
import uuid

from newsicad.core.entities import Arc, Circle, Dimension, Entity, Hatch, Line, LWPolyline, Point, Text


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
    elif isinstance(entity, Text):
        entity.insertion_point = translate_point(entity.insertion_point, dx, dy)
    elif isinstance(entity, Dimension):
        entity.point1 = translate_point(entity.point1, dx, dy)
        entity.point2 = translate_point(entity.point2, dx, dy)
        entity.dim_line_point = translate_point(entity.dim_line_point, dx, dy)
        entity.center = translate_point(entity.center, dx, dy)
        entity.leader_point = translate_point(entity.leader_point, dx, dy)
    elif isinstance(entity, Hatch):
        entity.boundary_points = [translate_point(p, dx, dy) for p in entity.boundary_points]
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
    elif isinstance(entity, Text):
        entity.insertion_point = rotate_point(entity.insertion_point, base, angle_rad)
        entity.rotation = (entity.rotation + angle_rad) % (2 * math.pi)
    elif isinstance(entity, Dimension):
        entity.point1 = rotate_point(entity.point1, base, angle_rad)
        entity.point2 = rotate_point(entity.point2, base, angle_rad)
        entity.dim_line_point = rotate_point(entity.dim_line_point, base, angle_rad)
        entity.center = rotate_point(entity.center, base, angle_rad)
        entity.leader_point = rotate_point(entity.leader_point, base, angle_rad)
    elif isinstance(entity, Hatch):
        entity.boundary_points = [rotate_point(p, base, angle_rad) for p in entity.boundary_points]
        entity.angle = (entity.angle + angle_rad) % math.pi
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
    elif isinstance(entity, Text):
        entity.insertion_point = scale_point(entity.insertion_point, base, factor)
        entity.height *= factor
    elif isinstance(entity, Dimension):
        entity.point1 = scale_point(entity.point1, base, factor)
        entity.point2 = scale_point(entity.point2, base, factor)
        entity.dim_line_point = scale_point(entity.dim_line_point, base, factor)
        entity.center = scale_point(entity.center, base, factor)
        entity.leader_point = scale_point(entity.leader_point, base, factor)
        entity.radius *= factor
    elif isinstance(entity, Hatch):
        entity.boundary_points = [scale_point(p, base, factor) for p in entity.boundary_points]
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
    elif isinstance(mirrored, Text):
        mirrored.insertion_point = mirror_point(entity.insertion_point, p1, p2)
        line_angle = p1.angle_to(p2)
        mirrored.rotation = (2 * line_angle - entity.rotation) % (2 * math.pi)
    elif isinstance(mirrored, Dimension):
        mirrored.point1 = mirror_point(entity.point1, p1, p2)
        mirrored.point2 = mirror_point(entity.point2, p1, p2)
        mirrored.dim_line_point = mirror_point(entity.dim_line_point, p1, p2)
        mirrored.center = mirror_point(entity.center, p1, p2)
        mirrored.leader_point = mirror_point(entity.leader_point, p1, p2)
    elif isinstance(mirrored, Hatch):
        mirrored.boundary_points = [mirror_point(p, p1, p2) for p in entity.boundary_points]
    else:
        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")

    return mirrored


# ---------------------------------------------------------------------- #
# geometria de renderização de Dimension — usada tanto pelo canvas (desenho)
# quanto pelo hit-test/bbox de seleção, pra garantir que "onde é desenhado" e
# "onde clicar seleciona" nunca divirjam.
# ---------------------------------------------------------------------- #
def _unit_direction(a: Point, b: Point) -> tuple[float, float]:
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0
    return dx / length, dy / length


def _arrow_ticks(a: Point, b: Point, size: float = 0.6) -> list[tuple[Point, Point]]:
    """Duas marcas curtas em ângulo em cada ponta do segmento a-b, no lugar
    de uma seta preenchida (suficiente pra indicar visualmente os limites da
    linha de cota)."""
    ux, uy = _unit_direction(a, b)
    px, py = -uy, ux
    ticks: list[tuple[Point, Point]] = []
    for origin, sign in ((a, 1.0), (b, -1.0)):
        back_x = origin.x + sign * ux * size
        back_y = origin.y + sign * uy * size
        ticks.append((origin, Point(back_x + px * size * 0.4, back_y + py * size * 0.4)))
        ticks.append((origin, Point(back_x - px * size * 0.4, back_y - py * size * 0.4)))
    return ticks


def dimension_geometry(dim: Dimension) -> tuple[list[tuple[Point, Point]], Point]:
    """Retorna (segmentos de linha, ponto de ancoragem do texto) em
    coordenadas CAD, para desenhar/hit-testar uma Dimension sem duplicar a
    geometria entre newsicad/ui/canvas.py e a seleção."""
    if dim.kind == "linear":
        p1, p2, dl = dim.point1, dim.point2, dim.dim_line_point
        if dim.is_horizontal():
            d1, d2 = Point(p1.x, dl.y), Point(p2.x, dl.y)
        else:
            d1, d2 = Point(dl.x, p1.y), Point(dl.x, p2.y)
        segments = [(p1, d1), (p2, d2), (d1, d2), *_arrow_ticks(d1, d2)]
        text_anchor = Point((d1.x + d2.x) / 2, (d1.y + d2.y) / 2)
        return segments, text_anchor

    if dim.kind == "aligned":
        p1, p2, dl = dim.point1, dim.point2, dim.dim_line_point
        ux, uy = _unit_direction(p1, p2)
        nx, ny = -uy, ux
        offset = (dl.x - p1.x) * nx + (dl.y - p1.y) * ny
        d1 = Point(p1.x + nx * offset, p1.y + ny * offset)
        d2 = Point(p2.x + nx * offset, p2.y + ny * offset)
        segments = [(p1, d1), (p2, d2), (d1, d2), *_arrow_ticks(d1, d2)]
        text_anchor = Point((d1.x + d2.x) / 2, (d1.y + d2.y) / 2)
        return segments, text_anchor

    if dim.kind in ("radius", "diameter"):
        ux, uy = _unit_direction(dim.center, dim.leader_point)
        edge = Point(dim.center.x + ux * dim.radius, dim.center.y + uy * dim.radius)
        if dim.kind == "diameter":
            far_edge = Point(dim.center.x - ux * dim.radius, dim.center.y - uy * dim.radius)
            segments = [(far_edge, edge), (edge, dim.leader_point)]
        else:
            segments = [(dim.center, edge), (edge, dim.leader_point)]
        return segments, dim.leader_point

    if dim.kind == "angular":
        vertex = dim.center
        arc_radius = vertex.distance_to(dim.dim_line_point) or vertex.distance_to(dim.point1) or 1.0
        a1 = math.atan2(dim.point1.y - vertex.y, dim.point1.x - vertex.x)
        a2 = math.atan2(dim.point2.y - vertex.y, dim.point2.x - vertex.x)
        sweep = (a2 - a1) % (2 * math.pi)
        steps = 16
        arc_points = [
            Point(
                vertex.x + arc_radius * math.cos(a1 + sweep * i / steps),
                vertex.y + arc_radius * math.sin(a1 + sweep * i / steps),
            )
            for i in range(steps + 1)
        ]
        segments = [(vertex, dim.point1), (vertex, dim.point2)]
        segments += list(zip(arc_points, arc_points[1:]))
        mid = arc_points[len(arc_points) // 2]
        return segments, mid

    return [], dim.dim_line_point
