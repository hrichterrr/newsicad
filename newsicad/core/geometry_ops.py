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
    Dimension,
    Entity,
    Hatch,
    ImageReference,
    Line,
    LWPolyline,
    Point,
    Text,
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
    elif isinstance(entity, BlockReference):
        entity.insertion_point = rotate_point(entity.insertion_point, base, angle_rad)
        entity.rotation = (entity.rotation + angle_rad) % (2 * math.pi)
    elif isinstance(entity, ImageReference):
        # Imagens não têm campo de rotação própria (ver ImageReference) —
        # só o ponto de inserção acompanha o giro do grupo selecionado.
        entity.insertion_point = rotate_point(entity.insertion_point, base, angle_rad)
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
    elif isinstance(entity, BlockReference):
        entity.insertion_point = scale_point(entity.insertion_point, base, factor)
        entity.scale *= factor
    elif isinstance(entity, ImageReference):
        entity.insertion_point = scale_point(entity.insertion_point, base, factor)
        entity.width *= factor
        entity.height *= factor
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
    elif isinstance(mirrored, BlockReference):
        # Simplificação: espelha o ponto de inserção e o ângulo, mas não
        # inverte o conteúdo do bloco em si (exigiria escala negativa por
        # eixo, que BlockReference não modela — ver README).
        mirrored.insertion_point = mirror_point(entity.insertion_point, p1, p2)
        mirrored.rotation = (-entity.rotation) % (2 * math.pi)
    elif isinstance(mirrored, ImageReference):
        mirrored.insertion_point = mirror_point(entity.insertion_point, p1, p2)
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


# ---------------------------------------------------------------------- #
# distância ponto -> entidade (puro, sem Qt — usado por OSNAP e pelos
# comandos TRIM/EXTEND para localizar a entidade mais próxima de um clique
# quando não há CanvasView disponível, ex.: em testes unitários)
# ---------------------------------------------------------------------- #
def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return p.distance_to(a)
    t = max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length_sq))
    proj = Point(a.x + t * dx, a.y + t * dy)
    return p.distance_to(proj)


def segment_parameter(p: Point, a: Point, b: Point) -> float:
    """Parâmetro t (não limitado a [0,1]) da projeção ortogonal de `p` sobre
    a reta a->b, tal que a projeção = a + t*(b-a)."""
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return 0.0
    return ((p.x - a.x) * dx + (p.y - a.y) * dy) / length_sq


def point_circle_distance(p: Point, center: Point, radius: float) -> float:
    return abs(p.distance_to(center) - radius)


def _angle_in_arc(angle: float, start_angle: float, end_angle: float) -> bool:
    span = (end_angle - start_angle) % (2 * math.pi)
    rel = (angle - start_angle) % (2 * math.pi)
    return rel <= span + 1e-9


def point_arc_distance(p: Point, arc: Arc) -> float | None:
    radial = abs(p.distance_to(arc.center) - arc.radius)
    angle = arc.center.angle_to(p)
    return radial if _angle_in_arc(angle, arc.start_angle, arc.end_angle) else None


def point_entity_distance(p: Point, entity: Entity) -> float | None:
    """Versão pura (sem Qt) da distância ponto->entidade — usada pelos
    comandos TRIM/EXTEND para localizar a entidade sob o clique quando não
    há CanvasView (ex.: testes). O CanvasView tem sua própria versão
    (`_distance_to_entity`) com tolerância em pixels, usada na UI real."""
    if isinstance(entity, Line):
        return point_segment_distance(p, entity.start, entity.end)
    if isinstance(entity, Circle):
        return point_circle_distance(p, entity.center, entity.radius)
    if isinstance(entity, Arc):
        return point_arc_distance(p, entity)
    if isinstance(entity, LWPolyline):
        best: float | None = None
        for seg_a, seg_b in entity.segments():
            d = point_segment_distance(p, seg_a, seg_b)
            if best is None or d < best:
                best = d
        return best
    return None


def nearest_entity(document, p: Point, tolerance: float) -> Entity | None:
    """Entidade mais próxima de `p` dentro de `tolerance` (unidades do
    desenho). Fallback puro usado pelos comandos quando ctx.view (CanvasView)
    não está disponível."""
    best_entity: Entity | None = None
    best_dist = tolerance
    for entity in document.entities.values():
        dist = point_entity_distance(p, entity)
        if dist is not None and dist <= best_dist:
            best_dist = dist
            best_entity = entity
    return best_entity


# ---------------------------------------------------------------------- #
# interseções (puras) — usadas por TRIM, EXTEND, OSNAP (Intersection) e
# FILLET/CHAMFER (interseção das retas suporte para achar o "canto")
# ---------------------------------------------------------------------- #
def _seg_intersect_params(p1: Point, p2: Point, p3: Point, p4: Point) -> tuple[float, float] | None:
    """t, u tais que p1 + t*(p2-p1) == p3 + u*(p4-p3). None se as retas são
    paralelas (ou um dos segmentos tem comprimento zero)."""
    d1x, d1y = p2.x - p1.x, p2.y - p1.y
    d2x, d2y = p4.x - p3.x, p4.y - p3.y
    denom = d1x * d2y - d1y * d2x
    if abs(denom) < 1e-12:
        return None
    dx, dy = p3.x - p1.x, p3.y - p1.y
    t = (dx * d2y - dy * d2x) / denom
    u = (dx * d1y - dy * d1x) / denom
    return t, u


def segment_intersection(
    p1: Point, p2: Point, p3: Point, p4: Point,
    bounded1: bool = True, bounded2: bool = True,
) -> Point | None:
    """Interseção entre a reta/segmento p1-p2 e a reta/segmento p3-p4.
    `bounded1`/`bounded2` = False trata o respectivo par de pontos como reta
    infinita em vez de segmento (usado por EXTEND e por FILLET/CHAMFER, que
    precisam da interseção das retas suporte além das pontas reais)."""
    params = _seg_intersect_params(p1, p2, p3, p4)
    if params is None:
        return None
    t, u = params
    eps = 1e-9
    if bounded1 and not (-eps <= t <= 1 + eps):
        return None
    if bounded2 and not (-eps <= u <= 1 + eps):
        return None
    return Point(p1.x + t * (p2.x - p1.x), p1.y + t * (p2.y - p1.y))


def _line_circle_intersection_params(
    p1: Point, p2: Point, center: Point, radius: float
) -> list[tuple[float, Point]]:
    """Lista (t, ponto) ordenada por t crescente, t ao longo da reta infinita
    p1->p2 (t=0 em p1, t=1 em p2), sem limitar t a [0,1]."""
    dx, dy = p2.x - p1.x, p2.y - p1.y
    fx, fy = p1.x - center.x, p1.y - center.y
    a = dx * dx + dy * dy
    if a < 1e-12:
        return []
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4 * a * c
    if disc < -1e-9:
        return []
    disc = max(disc, 0.0)
    sqrt_disc = math.sqrt(disc)
    ts = sorted({(-b - sqrt_disc) / (2 * a), (-b + sqrt_disc) / (2 * a)})
    return [(t, Point(p1.x + t * dx, p1.y + t * dy)) for t in ts]


def segment_circle_intersections(p1: Point, p2: Point, center: Point, radius: float) -> list[Point]:
    eps = 1e-9
    return [
        pt for t, pt in _line_circle_intersection_params(p1, p2, center, radius)
        if -eps <= t <= 1 + eps
    ]


def line_arc_intersections(p1: Point, p2: Point, arc: Arc) -> list[Point]:
    pts = segment_circle_intersections(p1, p2, arc.center, arc.radius)
    return [pt for pt in pts if _angle_in_arc(arc.center.angle_to(pt), arc.start_angle, arc.end_angle)]


def circle_circle_intersections(center1: Point, r1: float, center2: Point, r2: float) -> list[Point]:
    d = center1.distance_to(center2)
    if d < 1e-9 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h_sq = r1 * r1 - a * a
    h = math.sqrt(max(h_sq, 0.0))
    xm = center1.x + a * (center2.x - center1.x) / d
    ym = center1.y + a * (center2.y - center1.y) / d
    if h < 1e-9:
        return [Point(xm, ym)]
    rx = -(center2.y - center1.y) * (h / d)
    ry = (center2.x - center1.x) * (h / d)
    return [Point(xm + rx, ym + ry), Point(xm - rx, ym - ry)]


def as_intersectable_pieces(entity: Entity) -> list[Line | Circle | Arc]:
    """Decompõe uma entidade em peças Line/Circle/Arc usáveis por
    `entity_intersections` (LWPolyline vira uma Line temporária por
    segmento — não é adicionada ao Document, só serve para a matemática de
    interseção). Compartilhada por TRIM/EXTEND (modify_commands.py) e pelo
    OSNAP "Intersection" (ui/canvas.py) para não duplicar essa lógica."""
    if isinstance(entity, LWPolyline):
        return [Line(start=a, end=b) for a, b in entity.segments()]
    if isinstance(entity, (Line, Circle, Arc)):
        return [entity]
    return []


def entity_intersections(a: Entity, b: Entity) -> list[Point]:
    """Pontos de interseção entre duas entidades Line/Circle/Arc, limitados
    aos segmentos/arcos reais (não às retas/círculos suporte infinitos).
    LWPolyline não é aceita diretamente — decomponha em Lines por segmento
    antes de chamar (ver `_iter_intersectable` em modify_commands.py)."""
    if isinstance(a, Line) and isinstance(b, Line):
        pt = segment_intersection(a.start, a.end, b.start, b.end)
        return [pt] if pt is not None else []
    if isinstance(a, Line) and isinstance(b, Circle):
        return segment_circle_intersections(a.start, a.end, b.center, b.radius)
    if isinstance(a, Circle) and isinstance(b, Line):
        return segment_circle_intersections(b.start, b.end, a.center, a.radius)
    if isinstance(a, Line) and isinstance(b, Arc):
        return line_arc_intersections(a.start, a.end, b)
    if isinstance(a, Arc) and isinstance(b, Line):
        return line_arc_intersections(b.start, b.end, a)
    if isinstance(a, Circle) and isinstance(b, Circle):
        return circle_circle_intersections(a.center, a.radius, b.center, b.radius)
    if isinstance(a, Arc) and isinstance(b, Arc):
        pts = circle_circle_intersections(a.center, a.radius, b.center, b.radius)
        return [
            pt for pt in pts
            if _angle_in_arc(a.center.angle_to(pt), a.start_angle, a.end_angle)
            and _angle_in_arc(b.center.angle_to(pt), b.start_angle, b.end_angle)
        ]
    if isinstance(a, Circle) and isinstance(b, Arc):
        pts = circle_circle_intersections(a.center, a.radius, b.center, b.radius)
        return [pt for pt in pts if _angle_in_arc(b.center.angle_to(pt), b.start_angle, b.end_angle)]
    if isinstance(a, Arc) and isinstance(b, Circle):
        pts = circle_circle_intersections(a.center, a.radius, b.center, b.radius)
        return [pt for pt in pts if _angle_in_arc(a.center.angle_to(pt), a.start_angle, a.end_angle)]
    return []


def extend_point_to_boundary(anchor: Point, moving_end: Point, boundary_a: Point, boundary_b: Point) -> Point | None:
    """Estende o segmento anchor->moving_end além de moving_end (t>1) até
    encontrar a reta suporte do segmento boundary_a-boundary_b, respeitando
    os limites do boundary (0<=u<=1) mas não os do segmento sendo estendido.
    Usado pelo EXTEND."""
    params = _seg_intersect_params(anchor, moving_end, boundary_a, boundary_b)
    if params is None:
        return None
    t, u = params
    eps = 1e-9
    if t <= 1 + eps:
        return None
    if not (-eps <= u <= 1 + eps):
        return None
    return Point(anchor.x + t * (moving_end.x - anchor.x), anchor.y + t * (moving_end.y - anchor.y))


def extend_point_to_circle(anchor: Point, moving_end: Point, center: Point, radius: float) -> Point | None:
    """Igual a `extend_point_to_boundary`, mas o contorno é um círculo
    (ou o círculo suporte de um Arc, com o `arc` opcional filtrando o
    resultado ao alcance angular real do arco)."""
    candidates = [
        pt for t, pt in _line_circle_intersection_params(anchor, moving_end, center, radius)
        if t > 1 + 1e-9
    ]
    return candidates[0] if candidates else None


def extend_point_to_arc(anchor: Point, moving_end: Point, arc: Arc) -> Point | None:
    candidates = [
        pt for t, pt in _line_circle_intersection_params(anchor, moving_end, arc.center, arc.radius)
        if t > 1 + 1e-9 and _angle_in_arc(arc.center.angle_to(pt), arc.start_angle, arc.end_angle)
    ]
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------- #
# OFFSET
# ---------------------------------------------------------------------- #
def offset_line(line: Line, distance: float, side_point: Point) -> Line:
    dx, dy = line.end.x - line.start.x, line.end.y - line.start.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        raise ValueError("Não é possível fazer OFFSET de uma linha de comprimento zero")
    nx, ny = -dy / length, dx / length
    cross = dx * (side_point.y - line.start.y) - dy * (side_point.x - line.start.x)
    sign = 1.0 if cross > 0 else -1.0
    ox, oy = nx * distance * sign, ny * distance * sign
    return Line(
        start=Point(line.start.x + ox, line.start.y + oy),
        end=Point(line.end.x + ox, line.end.y + oy),
        layer=line.layer, color=line.color,
    )


def offset_circle(circle: Circle, distance: float, side_point: Point) -> Circle:
    inside = circle.center.distance_to(side_point) < circle.radius
    new_radius = circle.radius - distance if inside else circle.radius + distance
    if new_radius <= 1e-9:
        raise ValueError("OFFSET colapsa o círculo (raio resultante <= 0)")
    return Circle(
        center=Point(circle.center.x, circle.center.y),
        radius=new_radius, layer=circle.layer, color=circle.color,
    )


def offset_arc(arc: Arc, distance: float, side_point: Point) -> Arc:
    inside = arc.center.distance_to(side_point) < arc.radius
    new_radius = arc.radius - distance if inside else arc.radius + distance
    if new_radius <= 1e-9:
        raise ValueError("OFFSET colapsa o arco (raio resultante <= 0)")
    return Arc(
        center=Point(arc.center.x, arc.center.y),
        radius=new_radius, start_angle=arc.start_angle, end_angle=arc.end_angle,
        layer=arc.layer, color=arc.color,
    )


def offset_polyline(poly: LWPolyline, distance: float, side_point: Point) -> LWPolyline:
    """Aproximação razoável: desloca cada segmento perpendicularmente (mesmo
    lado escolhido globalmente a partir do segmento mais próximo do clique) e
    reconecta segmentos consecutivos pela interseção das retas suporte
    deslocadas. Não trata perfeitamente polilinhas que colapsam ou
    auto-intersectam após o offset."""
    segs = poly.segments()
    if not segs:
        raise ValueError("Polilinha sem segmentos para OFFSET")

    nearest = min(segs, key=lambda s: point_segment_distance(side_point, s[0], s[1]))
    ndx, ndy = nearest[1].x - nearest[0].x, nearest[1].y - nearest[0].y
    cross = ndx * (side_point.y - nearest[0].y) - ndy * (side_point.x - nearest[0].x)
    flip = cross < 0

    offset_segs: list[tuple[Point, Point]] = []
    for a, b in segs:
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        nx, ny = -dy / length, dx / length
        if flip:
            nx, ny = -nx, -ny
        offset_segs.append((
            Point(a.x + nx * distance, a.y + ny * distance),
            Point(b.x + nx * distance, b.y + ny * distance),
        ))

    if not offset_segs:
        raise ValueError("OFFSET não pôde ser calculado (segmentos degenerados)")

    n = len(offset_segs)
    new_points = [offset_segs[0][0]]
    for i in range(n - 1):
        a1, b1 = offset_segs[i]
        a2, b2 = offset_segs[i + 1]
        joint = segment_intersection(a1, b1, a2, b2, bounded1=False, bounded2=False)
        new_points.append(joint if joint is not None else b1)
    new_points.append(offset_segs[-1][1])

    closed = poly.closed and len(poly.points) > 2 and n == len(poly.points)
    if closed:
        a1, b1 = offset_segs[-1]
        a2, b2 = offset_segs[0]
        joint = segment_intersection(a1, b1, a2, b2, bounded1=False, bounded2=False)
        if joint is not None:
            new_points[0] = joint
        new_points = new_points[:-1]

    return LWPolyline(points=new_points, closed=poly.closed, layer=poly.layer, color=poly.color)


# ---------------------------------------------------------------------- #
# FILLET / CHAMFER (Line-Line)
# ---------------------------------------------------------------------- #
def _corner_setup(line1: Line, line2: Line):
    """Interseção das retas suporte de line1/line2 (o "canto") + vetor
    unitário de cada linha, do canto até a ponta mais distante (a que fica
    intocada), + qual ponta (start/end) fica mais perto do canto (a que será
    substituída pelo ponto de tangência/chanfro)."""
    p = segment_intersection(line1.start, line1.end, line2.start, line2.end, bounded1=False, bounded2=False)
    if p is None:
        raise ValueError("As retas selecionadas são paralelas — não é possível calcular FILLET/CHAMFER")

    def far_and_near(line: Line):
        d_start, d_end = p.distance_to(line.start), p.distance_to(line.end)
        return (line.end, True) if d_end >= d_start else (line.start, False)

    far1, near1_is_start = far_and_near(line1)
    far2, near2_is_start = far_and_near(line2)

    u1x, u1y = far1.x - p.x, far1.y - p.y
    len1 = math.hypot(u1x, u1y)
    u2x, u2y = far2.x - p.x, far2.y - p.y
    len2 = math.hypot(u2x, u2y)
    if len1 < 1e-9 or len2 < 1e-9:
        raise ValueError("Linha de comprimento zero não pode ser usada em FILLET/CHAMFER")
    u1x, u1y = u1x / len1, u1y / len1
    u2x, u2y = u2x / len2, u2y / len2

    return p, (u1x, u1y, len1, near1_is_start), (u2x, u2y, len2, near2_is_start)


def fillet_lines(line1: Line, line2: Line, radius: float) -> Arc:
    """Arredonda o canto entre line1 e line2 com um arco tangente de raio
    `radius`, mutando as duas linhas em memória (a ponta mais próxima do
    canto vira o ponto de tangência) e retornando o novo Arc (o chamador
    deve adicioná-lo ao Document)."""
    if radius <= 0:
        raise ValueError("O raio do FILLET deve ser positivo")

    p, (u1x, u1y, len1, near1_is_start), (u2x, u2y, len2, near2_is_start) = _corner_setup(line1, line2)

    dot = max(-1.0, min(1.0, u1x * u2x + u1y * u2y))
    theta = math.acos(dot)
    if theta < 1e-6 or theta > math.pi - 1e-6:
        raise ValueError("Retas colineares/paralelas — não é possível calcular FILLET")

    dist_to_tangent = radius / math.tan(theta / 2)
    if dist_to_tangent > len1 or dist_to_tangent > len2:
        raise ValueError("Raio de FILLET grande demais para o comprimento das linhas selecionadas")

    tangent1 = Point(p.x + u1x * dist_to_tangent, p.y + u1y * dist_to_tangent)
    tangent2 = Point(p.x + u2x * dist_to_tangent, p.y + u2y * dist_to_tangent)

    bx, by = u1x + u2x, u1y + u2y
    blen = math.hypot(bx, by)
    if blen < 1e-9:
        raise ValueError("Não foi possível determinar a bissetriz do canto (retas opostas)")
    bx, by = bx / blen, by / blen
    center_dist = radius / math.sin(theta / 2)
    center = Point(p.x + bx * center_dist, p.y + by * center_dist)

    belly_dx, belly_dy = p.x - center.x, p.y - center.y
    belly_len = math.hypot(belly_dx, belly_dy)
    belly = Point(center.x + belly_dx / belly_len * radius, center.y + belly_dy / belly_len * radius)

    arc_center, arc_radius, start_angle, end_angle = arc_from_3_points(tangent1, belly, tangent2)

    if near1_is_start:
        line1.start = tangent1
    else:
        line1.end = tangent1
    if near2_is_start:
        line2.start = tangent2
    else:
        line2.end = tangent2

    return Arc(center=arc_center, radius=arc_radius, start_angle=start_angle, end_angle=end_angle,
               layer=line1.layer, color=line1.color)


def chamfer_lines(line1: Line, line2: Line, dist1: float, dist2: float) -> Line:
    """Corta o canto entre line1 e line2 com uma linha reta a `dist1`/`dist2`
    do canto ao longo de cada linha, mutando as duas em memória e retornando
    a nova Line de chanfro (o chamador deve adicioná-la ao Document)."""
    if dist1 <= 0 or dist2 <= 0:
        raise ValueError("As distâncias do CHAMFER devem ser positivas")

    p, (u1x, u1y, len1, near1_is_start), (u2x, u2y, len2, near2_is_start) = _corner_setup(line1, line2)

    if dist1 > len1 or dist2 > len2:
        raise ValueError("Distância de CHAMFER maior que o comprimento das linhas selecionadas")

    point1 = Point(p.x + u1x * dist1, p.y + u1y * dist1)
    point2 = Point(p.x + u2x * dist2, p.y + u2y * dist2)

    if near1_is_start:
        line1.start = point1
    else:
        line1.end = point1
    if near2_is_start:
        line2.start = point2
    else:
        line2.end = point2

    return Line(start=point1, end=point2, layer=line1.layer, color=line1.color)


# ---------------------------------------------------------------------- #
# área/perímetro de polígono — usado pelo comando AREA (AA)
# ---------------------------------------------------------------------- #
def polygon_area(points: list[Point]) -> float:
    """Área de um polígono fechado pela fórmula do shoelace (assume que o
    último ponto se conecta de volta ao primeiro, mesmo sem repeti-lo em
    `points`)."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        total += a.x * b.y - b.x * a.y
    return abs(total) / 2.0


def polygon_perimeter(points: list[Point], closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    return sum(a.distance_to(b) for a, b in pairs)
