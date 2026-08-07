"""Comandos MODIFY (ERASE, MOVE, COPY, ROTATE, MIRROR, SCALE, TRIM, EXTEND,
OFFSET, FILLET, CHAMFER, JOIN, EXPLODE, STRETCH, DIVIDE, MEASURE) — todos
seguem o padrão do AutoCAD: "Select objects:" primeiro, depois os parâmetros
da transformação."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import Arc, Circle, Entity, Line, LWPolyline, Point
from newsicad.core.geometry_ops import (
    as_intersectable_pieces,
    chamfer_lines,
    clone_entity,
    entity_intersections,
    extend_point_to_arc,
    extend_point_to_boundary,
    extend_point_to_circle,
    fillet_lines,
    mirror_entity,
    nearest_entity,
    offset_arc,
    offset_circle,
    offset_line,
    offset_polyline,
    rotate_entity,
    scale_entity,
    segment_parameter,
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


# ------------------------------------------------------------------ #
# infraestrutura compartilhada por TRIM / EXTEND / OFFSET (localizar a
# entidade sob um clique sem depender de UI — usa ctx.view._hit_test se
# disponível, senão cai no fallback puro de geometry_ops.nearest_entity)
# ------------------------------------------------------------------ #
_HIT_TEST_FALLBACK_TOLERANCE = 0.5


def _hit_test_entity(ctx: CommandContext, point: Point) -> Entity | None:
    view = ctx.view
    if view is not None and hasattr(view, "_hit_test"):
        entity_id = view._hit_test(point)
        return ctx.document.get_entity(entity_id) if entity_id else None
    return nearest_entity(ctx.document, point, _HIT_TEST_FALLBACK_TOLERANCE)


def _cutting_pieces_excluding(edges: list[Entity], exclude_id: str) -> list[Line | Circle | Arc]:
    pieces: list[Line | Circle | Arc] = []
    for edge in edges:
        if edge.id == exclude_id:
            continue
        pieces.extend(as_intersectable_pieces(edge))
    return pieces


# ------------------------------------------------------------------ #
# TRIM
# ------------------------------------------------------------------ #
def _trim_line_at_point(
    line: Line, click_point: Point, cutting_pieces: list[Line | Circle | Arc]
) -> list[tuple[Point, Point]] | None:
    pts: list[Point] = []
    for piece in cutting_pieces:
        pts.extend(entity_intersections(line, piece))
    if not pts:
        return None

    eps = 1e-9
    ts = sorted({segment_parameter(pt, line.start, line.end) for pt in pts})
    ts = [t for t in ts if -eps <= t <= 1 + eps]
    if not ts:
        return None

    click_t = max(0.0, min(1.0, segment_parameter(click_point, line.start, line.end)))
    lo = max((t for t in ts if t <= click_t + eps), default=None)
    hi = min((t for t in ts if t >= click_t - eps), default=None)
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None and abs(lo - hi) <= eps:
        # clique bem em cima de uma interseção: escolhe o lado mais curto a apagar
        if click_t < 0.5:
            lo = None
        else:
            hi = None

    def point_at(t: float) -> Point:
        return Point(line.start.x + t * (line.end.x - line.start.x), line.start.y + t * (line.end.y - line.start.y))

    if lo is not None and hi is not None:
        return [(line.start, point_at(lo)), (point_at(hi), line.end)]
    if hi is not None:
        return [(point_at(hi), line.end)]
    return [(line.start, point_at(lo))]


def _apply_trim_line_pieces(ctx: CommandContext, line: Line, pieces: list[tuple[Point, Point]]) -> None:
    line.start, line.end = pieces[0]
    for extra_start, extra_end in pieces[1:]:
        ctx.document.add_entity(Line(start=extra_start, end=extra_end, layer=line.layer, color=line.color))


def _trim_circle_at_point(
    circle: Circle, click_point: Point, cutting_pieces: list[Line | Circle | Arc]
) -> Arc | None:
    pts: list[Point] = []
    for piece in cutting_pieces:
        pts.extend(entity_intersections(circle, piece))
    angles = sorted({circle.center.angle_to(pt) % (2 * math.pi) for pt in pts})
    if len(angles) < 2:
        return None

    click_angle = circle.center.angle_to(click_point) % (2 * math.pi)
    eps = 1e-9
    lo = max((a for a in angles if a <= click_angle + eps), default=angles[-1])
    hi = min((a for a in angles if a >= click_angle - eps), default=angles[0])
    if abs(lo - hi) <= eps:
        return None

    return Arc(
        center=Point(circle.center.x, circle.center.y), radius=circle.radius,
        start_angle=hi, end_angle=lo, layer=circle.layer, color=circle.color,
    )


def _trim_arc_at_point(
    arc: Arc, click_point: Point, cutting_pieces: list[Line | Circle | Arc]
) -> list[tuple[float, float]] | None:
    pts: list[Point] = []
    for piece in cutting_pieces:
        pts.extend(entity_intersections(arc, piece))
    if not pts:
        return None

    base = arc.start_angle
    total = (arc.end_angle - arc.start_angle) % (2 * math.pi)
    eps = 1e-9

    def sweep(angle: float) -> float:
        return (angle - base) % (2 * math.pi)

    sweeps = sorted({sweep(arc.center.angle_to(pt)) for pt in pts})
    sweeps = [s for s in sweeps if -eps <= s <= total + eps]
    if not sweeps:
        return None

    click_sweep = max(0.0, min(total, sweep(arc.center.angle_to(click_point))))
    lo = max((s for s in sweeps if s <= click_sweep + eps), default=None)
    hi = min((s for s in sweeps if s >= click_sweep - eps), default=None)
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None and abs(lo - hi) <= eps:
        if click_sweep < total / 2:
            lo = None
        else:
            hi = None

    if lo is not None and hi is not None:
        return [(base, (base + lo) % (2 * math.pi)), ((base + hi) % (2 * math.pi), arc.end_angle)]
    if hi is not None:
        return [((base + hi) % (2 * math.pi), arc.end_angle)]
    return [(base, (base + lo) % (2 * math.pi))]


def _apply_trim_arc_pieces(ctx: CommandContext, arc: Arc, pieces: list[tuple[float, float]]) -> None:
    arc.start_angle, arc.end_angle = pieces[0]
    for start_angle, end_angle in pieces[1:]:
        ctx.document.add_entity(Arc(
            center=Point(arc.center.x, arc.center.y), radius=arc.radius,
            start_angle=start_angle, end_angle=end_angle, layer=arc.layer, color=arc.color,
        ))


def trim_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    cutting = yield from _select_objects(ctx, "Select cutting edges ...\nSelect objects:")
    if not cutting:
        return
    ctx.selection.clear()

    while True:
        result = yield Prompt(
            "Select object to trim or [Undo] (Enter to finish):", kind="point", options=["Undo"],
            connect_to_last=False,
        )
        if result is ENTER:
            break
        if result == "UNDO":
            yield Prompt(
                "Undo dentro do TRIM ainda não é suportado nesta versão — use Ctrl+Z após terminar o comando.",
                kind="info",
            )
            continue

        click_point = result
        target = _hit_test_entity(ctx, click_point)
        if target is None:
            yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
            continue

        pieces_src = _cutting_pieces_excluding(cutting, target.id)

        if isinstance(target, Line):
            pieces = _trim_line_at_point(target, click_point, pieces_src)
            if pieces is None:
                yield Prompt("Nenhuma interseção encontrada com as arestas de corte.", kind="info")
                continue
            _apply_trim_line_pieces(ctx, target, pieces)
        elif isinstance(target, Circle):
            new_arc = _trim_circle_at_point(target, click_point, pieces_src)
            if new_arc is None:
                yield Prompt("É preciso pelo menos 2 pontos de interseção para aparar um círculo.", kind="info")
                continue
            ctx.document.remove_entity(target.id)
            ctx.document.add_entity(new_arc)
        elif isinstance(target, Arc):
            arc_pieces = _trim_arc_at_point(target, click_point, pieces_src)
            if arc_pieces is None:
                yield Prompt("Nenhuma interseção encontrada com as arestas de corte.", kind="info")
                continue
            _apply_trim_arc_pieces(ctx, target, arc_pieces)
        else:
            yield Prompt("TRIM nesta versão só apara Line, Circle e Arc.", kind="info")


# ------------------------------------------------------------------ #
# EXTEND (só Line — Arc/Circle como alvo fica para uma versão futura,
# mas podem ser usados como boundary edges)
# ------------------------------------------------------------------ #
def _extend_line_at_point(
    line: Line, click_point: Point, boundaries: list[Entity]
) -> tuple[Point, bool] | None:
    t_click = segment_parameter(click_point, line.start, line.end)
    moving_is_start = t_click <= 0.5
    anchor = line.end if moving_is_start else line.start
    moving_end = line.start if moving_is_start else line.end

    candidates: list[Point] = []
    for boundary in boundaries:
        for piece in as_intersectable_pieces(boundary):
            if isinstance(piece, Line):
                pt = extend_point_to_boundary(anchor, moving_end, piece.start, piece.end)
            elif isinstance(piece, Circle):
                pt = extend_point_to_circle(anchor, moving_end, piece.center, piece.radius)
            elif isinstance(piece, Arc):
                pt = extend_point_to_arc(anchor, moving_end, piece)
            else:
                pt = None
            if pt is not None:
                candidates.append(pt)

    if not candidates:
        return None
    nearest_pt = min(candidates, key=lambda pt: moving_end.distance_to(pt))
    return nearest_pt, moving_is_start


def extend_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    boundaries = yield from _select_objects(ctx, "Select boundary edges ...\nSelect objects:")
    if not boundaries:
        return
    ctx.selection.clear()

    while True:
        result = yield Prompt(
            "Select object to extend or [Undo] (Enter to finish):", kind="point", options=["Undo"],
            connect_to_last=False,
        )
        if result is ENTER:
            break
        if result == "UNDO":
            yield Prompt(
                "Undo dentro do EXTEND ainda não é suportado nesta versão — use Ctrl+Z após terminar o comando.",
                kind="info",
            )
            continue

        click_point = result
        target = _hit_test_entity(ctx, click_point)
        if target is None:
            yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
            continue
        if not isinstance(target, Line):
            yield Prompt("EXTEND nesta versão só estende objetos Line.", kind="info")
            continue

        relevant = [b for b in boundaries if b.id != target.id]
        extension = _extend_line_at_point(target, click_point, relevant)
        if extension is None:
            yield Prompt("Nenhuma borda encontrada na direção de extensão.", kind="info")
            continue
        new_point, moving_is_start = extension
        if moving_is_start:
            target.start = new_point
        else:
            target.end = new_point


# ------------------------------------------------------------------ #
# OFFSET
# ------------------------------------------------------------------ #
def offset_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    distance = yield Prompt("Specify offset distance:", kind="distance")
    if distance <= 0:
        yield Prompt("A distância de OFFSET deve ser positiva.", kind="info")
        return

    while True:
        result = yield Prompt(
            "Select object to offset or [Undo] (Enter to exit):", kind="point", options=["Undo"],
            connect_to_last=False,
        )
        if result is ENTER:
            break
        if result == "UNDO":
            yield Prompt("Undo dentro do OFFSET ainda não é suportado nesta versão.", kind="info")
            continue

        target = _hit_test_entity(ctx, result)
        if target is None:
            yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
            continue

        side_point = yield Prompt("Specify point on side to offset:", kind="point", connect_to_last=False)
        try:
            if isinstance(target, Line):
                new_entity: Entity = offset_line(target, distance, side_point)
            elif isinstance(target, Circle):
                new_entity = offset_circle(target, distance, side_point)
            elif isinstance(target, Arc):
                new_entity = offset_arc(target, distance, side_point)
            elif isinstance(target, LWPolyline):
                new_entity = offset_polyline(target, distance, side_point)
            else:
                yield Prompt("OFFSET nesta versão não suporta esse tipo de objeto.", kind="info")
                continue
        except ValueError as exc:
            yield Prompt(str(exc), kind="info")
            continue

        ctx.document.add_entity(new_entity)


# ------------------------------------------------------------------ #
# FILLET (Line-Line) — fluxo com sub-opção [Radius], igual ao AutoCAD
# ------------------------------------------------------------------ #
def fillet_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    radius = 0.0
    first: object = None
    while True:
        first = yield Prompt(
            f"Select first object or [Radius] (current radius = {radius:g}):",
            kind="point", options=["Radius"], connect_to_last=False,
        )
        if first == "RADIUS":
            radius = yield Prompt("Specify fillet radius:", kind="distance")
            continue
        break

    if radius <= 0:
        yield Prompt("Especifique um raio de FILLET maior que zero pela opção [Radius] antes de selecionar as linhas.", kind="info")
        return

    target1 = _hit_test_entity(ctx, first)
    if target1 is None or not isinstance(target1, Line):
        yield Prompt("FILLET nesta versão exige selecionar duas Lines (Line-Arc fica para uma versão futura).", kind="info")
        return

    click2 = yield Prompt("Select second object:", kind="point", connect_to_last=False)
    target2 = _hit_test_entity(ctx, click2)
    if target2 is None or not isinstance(target2, Line) or target2.id == target1.id:
        yield Prompt("FILLET nesta versão exige selecionar duas Lines diferentes.", kind="info")
        return

    try:
        arc = fillet_lines(target1, target2, radius)
    except ValueError as exc:
        yield Prompt(str(exc), kind="info")
        return
    ctx.document.add_entity(arc)


# ------------------------------------------------------------------ #
# CHAMFER (Line-Line) — fluxo com sub-opção [Distance]
# ------------------------------------------------------------------ #
def chamfer_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    dist1, dist2 = 0.0, 0.0
    first: object = None
    while True:
        first = yield Prompt(
            f"Select first line or [Distance] (current distances = {dist1:g}, {dist2:g}):",
            kind="point", options=["Distance"], connect_to_last=False,
        )
        if first == "DISTANCE":
            dist1 = yield Prompt("Specify first chamfer distance:", kind="distance")
            dist2 = yield Prompt("Specify second chamfer distance:", kind="distance")
            continue
        break

    if dist1 <= 0 or dist2 <= 0:
        yield Prompt("Especifique as duas distâncias de CHAMFER (opção [Distance]) antes de selecionar as linhas.", kind="info")
        return

    target1 = _hit_test_entity(ctx, first)
    if target1 is None or not isinstance(target1, Line):
        yield Prompt("CHAMFER nesta versão exige selecionar duas Lines.", kind="info")
        return

    click2 = yield Prompt("Select second line:", kind="point")
    target2 = _hit_test_entity(ctx, click2)
    if target2 is None or not isinstance(target2, Line) or target2.id == target1.id:
        yield Prompt("CHAMFER nesta versão exige selecionar duas Lines diferentes.", kind="info")
        return

    try:
        chamfer_line = chamfer_lines(target1, target2, dist1, dist2)
    except ValueError as exc:
        yield Prompt(str(exc), kind="info")
        return
    ctx.document.add_entity(chamfer_line)


# ------------------------------------------------------------------ #
# JOIN (Lines colineares conectadas nas pontas -> uma única Line)
# ------------------------------------------------------------------ #
def _join_collinear_lines(lines: list[Line]) -> tuple[Point, Point, set[str]] | None:
    base_a, base_b = lines[0].start, lines[0].end
    dx, dy = base_b.x - base_a.x, base_b.y - base_a.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    ux, uy = dx / length, dy / length

    def project(pt: Point) -> float:
        return (pt.x - base_a.x) * ux + (pt.y - base_a.y) * uy

    def perp_dist(pt: Point) -> float:
        return abs((pt.x - base_a.x) * (-uy) + (pt.y - base_a.y) * ux)

    tolerance = max(length, 1.0) * 1e-6
    intervals = []
    for line in lines:
        if perp_dist(line.start) > tolerance or perp_dist(line.end) > tolerance:
            return None
        t1, t2 = project(line.start), project(line.end)
        intervals.append((min(t1, t2), max(t1, t2), line.id))

    intervals.sort(key=lambda iv: iv[0])
    merged_lo, merged_hi = intervals[0][0], intervals[0][1]
    used = {intervals[0][2]}
    gap_tol = max(length, 1.0) * 1e-6
    for lo, hi, line_id in intervals[1:]:
        if lo > merged_hi + gap_tol:
            return None
        merged_hi = max(merged_hi, hi)
        used.add(line_id)

    start_pt = Point(base_a.x + ux * merged_lo, base_a.y + uy * merged_lo)
    end_pt = Point(base_a.x + ux * merged_hi, base_a.y + uy * merged_hi)
    return start_pt, end_pt, used


def join_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return

    lines = [e for e in selected if isinstance(e, Line)]
    if len(lines) < 2:
        yield Prompt("JOIN nesta versão exige selecionar 2 ou mais objetos Line colineares.", kind="info")
        ctx.selection.clear()
        return

    result = _join_collinear_lines(lines)
    if result is None:
        yield Prompt(
            "Os objetos selecionados não são colineares e conectados nas pontas — nada foi unido.",
            kind="info",
        )
        ctx.selection.clear()
        return

    new_start, new_end, used_ids = result
    survivor = lines[0]
    survivor.start, survivor.end = new_start, new_end
    for line in lines[1:]:
        if line.id in used_ids:
            ctx.document.remove_entity(line.id)
    ctx.selection.clear()


# ------------------------------------------------------------------ #
# EXPLODE (LWPolyline -> Lines individuais)
# ------------------------------------------------------------------ #
def explode_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return

    exploded_any = False
    for entity in selected:
        if isinstance(entity, LWPolyline):
            for a, b in entity.segments():
                ctx.document.add_entity(Line(
                    start=Point(a.x, a.y), end=Point(b.x, b.y), layer=entity.layer, color=entity.color,
                ))
            ctx.document.remove_entity(entity.id)
            exploded_any = True

    if not exploded_any:
        yield Prompt("EXPLODE nesta versão só funciona em objetos LWPolyline (retângulos/polilinhas).", kind="info")
    ctx.selection.clear()


# ------------------------------------------------------------------ #
# STRETCH — usa um prompt de janela crossing explícito (dois cantos), como
# o próprio AutoCAD faz para STRETCH (distinto da seleção genérica por
# clique/arrasto usada pelos outros comandos MODIFY). Isso mantém o comando
# 100% testável sem depender do CanvasView. Só move vértices de Line e
# LWPolyline que caem dentro da janela; outros tipos não são afetados.
# ------------------------------------------------------------------ #
def stretch_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    corner1 = yield Prompt(
        "Select objects to stretch by crossing-window...\nSpecify first corner:", kind="point",
        connect_to_last=False,
    )
    corner2 = yield Prompt("Specify opposite corner:", kind="point", connect_to_last=False)

    lo_x, hi_x = sorted((corner1.x, corner2.x))
    lo_y, hi_y = sorted((corner1.y, corner2.y))

    def inside(pt: Point) -> bool:
        return lo_x <= pt.x <= hi_x and lo_y <= pt.y <= hi_y

    affected: list[Entity] = []
    for entity in ctx.document.all_entities():
        if isinstance(entity, Line) and (inside(entity.start) or inside(entity.end)):
            affected.append(entity)
        elif isinstance(entity, LWPolyline) and any(inside(pt) for pt in entity.points):
            affected.append(entity)

    if not affected:
        yield Prompt("Nenhum vértice dentro da janela de seleção — nada para esticar.", kind="info")
        return

    base = yield Prompt("Specify base point:", kind="point")
    target = yield Prompt("Specify second point:", kind="point")
    dx, dy = target.x - base.x, target.y - base.y

    for entity in affected:
        if isinstance(entity, Line):
            if inside(entity.start):
                entity.start = Point(entity.start.x + dx, entity.start.y + dy)
            if inside(entity.end):
                entity.end = Point(entity.end.x + dx, entity.end.y + dy)
        elif isinstance(entity, LWPolyline):
            entity.points = [
                Point(pt.x + dx, pt.y + dy) if inside(pt) else pt for pt in entity.points
            ]


# ------------------------------------------------------------------ #
# DIVIDE / MEASURE — como não existe um tipo POINT no NewSIcad ainda, cada
# ponto de divisão/medida é representado por um Circle bem pequeno (raio
# fixo, ~0.05 unidade de desenho) — simplificação documentada no README.
# ------------------------------------------------------------------ #
_MARKER_RADIUS = 0.05


def divide_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx, "Select object to divide:")
    if len(selected) != 1:
        yield Prompt("DIVIDE exige selecionar exatamente um objeto.", kind="info")
        ctx.selection.clear()
        return

    target = selected[0]
    count = yield Prompt("Enter number of segments:", kind="distance")
    n = int(round(count))
    if n < 2:
        yield Prompt("O número de segmentos deve ser maior ou igual a 2.", kind="info")
        ctx.selection.clear()
        return

    points: list[Point] = []
    if isinstance(target, Line):
        dx, dy = target.end.x - target.start.x, target.end.y - target.start.y
        points = [Point(target.start.x + dx * i / n, target.start.y + dy * i / n) for i in range(1, n)]
    elif isinstance(target, Circle):
        points = [
            Point(target.center.x + target.radius * math.cos(2 * math.pi * i / n),
                  target.center.y + target.radius * math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
    elif isinstance(target, Arc):
        sweep = (target.end_angle - target.start_angle) % (2 * math.pi)
        points = [
            Point(target.center.x + target.radius * math.cos(target.start_angle + sweep * i / n),
                  target.center.y + target.radius * math.sin(target.start_angle + sweep * i / n))
            for i in range(1, n)
        ]
    else:
        yield Prompt("DIVIDE nesta versão suporta Line, Circle e Arc.", kind="info")
        ctx.selection.clear()
        return

    for pt in points:
        ctx.document.add_entity(Circle(center=pt, radius=_MARKER_RADIUS, layer=target.layer))
    ctx.selection.clear()


def measure_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx, "Select object to measure:")
    if len(selected) != 1:
        yield Prompt("MEASURE exige selecionar exatamente um objeto.", kind="info")
        ctx.selection.clear()
        return

    target = selected[0]
    seg_length = yield Prompt("Specify length of segment:", kind="distance")
    if seg_length <= 0:
        yield Prompt("O comprimento do segmento deve ser positivo.", kind="info")
        ctx.selection.clear()
        return

    points: list[Point] = []
    if isinstance(target, Line):
        total = target.length()
        n = int(total // seg_length + 1e-9)
        if n < 1:
            yield Prompt("Comprimento do segmento maior que o objeto selecionado.", kind="info")
            ctx.selection.clear()
            return
        ux, uy = (target.end.x - target.start.x) / total, (target.end.y - target.start.y) / total
        points = [Point(target.start.x + ux * seg_length * i, target.start.y + uy * seg_length * i) for i in range(1, n + 1)]
    elif isinstance(target, Arc):
        total = target.radius * ((target.end_angle - target.start_angle) % (2 * math.pi))
        n = int(total // seg_length + 1e-9)
        if n < 1:
            yield Prompt("Comprimento do segmento maior que o objeto selecionado.", kind="info")
            ctx.selection.clear()
            return
        sweep_per = seg_length / target.radius
        points = [
            Point(target.center.x + target.radius * math.cos(target.start_angle + sweep_per * i),
                  target.center.y + target.radius * math.sin(target.start_angle + sweep_per * i))
            for i in range(1, n + 1)
        ]
    else:
        yield Prompt("MEASURE nesta versão suporta Line e Arc.", kind="info")
        ctx.selection.clear()
        return

    for pt in points:
        ctx.document.add_entity(Circle(center=pt, radius=_MARKER_RADIUS, layer=target.layer))
    ctx.selection.clear()
