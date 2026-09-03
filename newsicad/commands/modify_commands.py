"""Comandos MODIFY (ERASE, MOVE, COPY, ROTATE, MIRROR, SCALE, TRIM, EXTEND,
OFFSET, FILLET, CHAMFER, JOIN, EXPLODE, STRETCH, DIVIDE, MEASURE) — todos
seguem o padrão do AutoCAD: "Select objects:" primeiro, depois os parâmetros
da transformação."""

from __future__ import annotations

import math
import pickle
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import (
    Arc,
    BlockReference,
    Circle,
    Entity,
    ImageReference,
    Line,
    LWPolyline,
    Point,
    PointEntity,
    Spline,
    Text,
    _new_id,
)
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
    rotate_point,
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
    if factor <= 0:
        # Fator 0 colapsa a geometria num ponto; fator negativo produz
        # raio/dimensão negativos que sobrevivem intactos a um round-trip de
        # .dxf sem nenhum aviso em lugar nenhum (bug real de auditoria,
        # 2026-08-22) — mesma guarda que OFFSET já tem pra distância.
        yield Prompt("SCALE: o fator de escala deve ser positivo.", kind="info")
        ctx.selection.clear()
        return
    for entity in selected:
        scale_entity(entity, base, factor)
    ctx.selection.clear()


def mirror_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    p1 = yield Prompt("Specify first point of mirror line:", kind="point")
    p2 = yield Prompt("Specify second point of mirror line:", kind="point")
    if p1.distance_to(p2) <= 1e-9:
        # Eixo degenerado (os dois cliques no mesmo lugar) faz mirror_point
        # dividir por zero internamente e devolver uma cópia idêntica
        # empilhada em cima do original, sem nenhum aviso — bug real de
        # auditoria, 2026-08-22.
        yield Prompt("MIRROR: os dois pontos do eixo de espelhamento não podem coincidir.", kind="info")
        ctx.selection.clear()
        return
    choice = yield Prompt("Erase source objects? [Yes/No] <N>:", kind="keyword", options=["Yes", "No"])

    for entity in selected:
        mirrored = mirror_entity(entity, p1, p2)
        mirrored.id = _new_id()
        ctx.document.add_entity(mirrored)

    if choice == "YES":
        for entity in selected:
            ctx.document.remove_entity(entity.id)

    ctx.selection.clear()


def align_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """ALIGN (AL): move/rotaciona (e opcionalmente escala) os objetos
    selecionados para alinhar um par de pontos de origem com um par de
    pontos de destino — mesmo cálculo do ALIGN de verdade do AutoCAD no modo
    2 pontos (o modo de 3 pontos/3D não é suportado nesta versão, já que o
    NewSIcad só tem um espaço de desenho 2D)."""
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    src1 = yield Prompt("Specify first source point:", kind="point")
    dst1 = yield Prompt("Specify first destination point:", kind="point")
    src2 = yield Prompt("Specify second source point:", kind="point")
    dst2 = yield Prompt("Specify second destination point:", kind="point")
    scale_choice = yield Prompt(
        "Scale objects based on alignment points? [Yes/No] <N>:", kind="keyword", options=["Yes", "No"]
    )

    dx, dy = dst1.x - src1.x, dst1.y - src1.y
    for entity in selected:
        translate_entity(entity, dx, dy)
    src2_translated = Point(src2.x + dx, src2.y + dy)

    angle = dst1.angle_to(dst2) - dst1.angle_to(src2_translated)
    for entity in selected:
        rotate_entity(entity, dst1, angle)

    if scale_choice == "YES":
        src_len = dst1.distance_to(src2_translated)
        dst_len = dst1.distance_to(dst2)
        if src_len > 1e-9:
            factor = dst_len / src_len
            for entity in selected:
                scale_entity(entity, dst1, factor)

    ctx.selection.clear()


def array_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """ARRAY (AR): array retangular (linhas/colunas + espaçamento) ou polar
    (centro + número de itens + ângulo total a preencher, sentido
    anti-horário), reaproveitando clone_entity/translate_entity/rotate_entity
    — igual a COPY/ROTATE feitos várias vezes. Simplificação documentada:
    sem edição associativa depois de criado (cada cópia é uma entidade
    independente, como se o usuário tivesse dado EXPLODE no array)."""
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    kind = yield Prompt(
        "Enter array type [Rectangular/Polar] <Rectangular>:", kind="keyword", options=["Rectangular", "Polar"]
    )
    new_ids: set[str] = set()

    if kind == "POLAR":
        center = yield Prompt("Specify center point of array:", kind="point")
        count_raw = yield Prompt("Enter number of items <6>:", kind="distance")
        count = 6 if count_raw is ENTER else max(1, int(count_raw))
        angle_raw = yield Prompt("Specify angle to fill <360>:", kind="distance")
        angle_total_deg = 360.0 if angle_raw is ENTER else angle_raw
        angle_total = math.radians(angle_total_deg)
        full_circle = abs(angle_total_deg % 360.0) < 1e-9
        step = angle_total / count if full_circle else (angle_total / (count - 1) if count > 1 else 0.0)
        for i in range(1, count):
            for entity in selected:
                clone = clone_entity(entity)
                rotate_entity(clone, center, step * i)
                ctx.document.add_entity(clone)
                new_ids.add(clone.id)
    else:
        rows_raw = yield Prompt("Enter number of rows <1>:", kind="distance")
        rows = 1 if rows_raw is ENTER else max(1, int(rows_raw))
        cols_raw = yield Prompt("Enter number of columns <1>:", kind="distance")
        cols = 1 if cols_raw is ENTER else max(1, int(cols_raw))
        row_spacing = 0.0
        if rows > 1:
            row_spacing = yield Prompt("Specify distance between rows:", kind="distance")
        col_spacing = 0.0
        if cols > 1:
            col_spacing = yield Prompt("Specify distance between columns:", kind="distance")
        for row in range(rows):
            for col in range(cols):
                if row == 0 and col == 0:
                    continue
                dx, dy = col * col_spacing, row * row_spacing
                for entity in selected:
                    clone = clone_entity(entity)
                    translate_entity(clone, dx, dy)
                    ctx.document.add_entity(clone)
                    new_ids.add(clone.id)

    ctx.selection.set(new_ids)


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
def _lines_collinear(a: Line, b: Line) -> bool:
    dx, dy = a.end.x - a.start.x, a.end.y - a.start.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return False
    ux, uy = dx / length, dy / length
    tolerance = max(length, 1.0) * 1e-6

    def perp_dist(pt: Point) -> float:
        return abs((pt.x - a.start.x) * (-uy) + (pt.y - a.start.y) * ux)

    return perp_dist(b.start) <= tolerance and perp_dist(b.end) <= tolerance


def _join_collinear_runs(lines: list[Line]) -> list[list[Line]]:
    """Agrupa `lines` em "runs" — grupos colineares E conectados ponta-a-
    ponta sem gap (mesmo critério de tolerância de antes). Uma linha solta
    que não é colinear/conectada a nenhuma outra vira seu próprio run de
    tamanho 1, em vez de bloquear a união das demais: antes, uma única linha
    fora do padrão na seleção fazia o JOIN inteiro falhar (tudo-ou-nada),
    mesmo quando o resto da seleção formava pares válidos (bug real de
    auditoria, 2026-08-22)."""
    clusters: list[list[Line]] = []
    for line in lines:
        for cluster in clusters:
            if _lines_collinear(cluster[0], line):
                cluster.append(line)
                break
        else:
            clusters.append([line])

    runs: list[list[Line]] = []
    for cluster in clusters:
        if len(cluster) == 1:
            runs.append(cluster)
            continue

        base_a, base_b = cluster[0].start, cluster[0].end
        dx, dy = base_b.x - base_a.x, base_b.y - base_a.y
        length = math.hypot(dx, dy)
        if length < 1e-9:
            runs.extend([line] for line in cluster)
            continue
        ux, uy = dx / length, dy / length

        def project(pt: Point) -> float:
            return (pt.x - base_a.x) * ux + (pt.y - base_a.y) * uy

        gap_tol = max(length, 1.0) * 1e-6
        entries = sorted(
            ((min(project(line.start), project(line.end)), max(project(line.start), project(line.end)), line)
             for line in cluster),
            key=lambda entry: entry[0],
        )
        current_run = [entries[0]]
        current_hi = entries[0][1]
        for lo, hi, line in entries[1:]:
            if lo > current_hi + gap_tol:
                runs.append([e[2] for e in current_run])
                current_run = [(lo, hi, line)]
                current_hi = hi
            else:
                current_run.append((lo, hi, line))
                current_hi = max(current_hi, hi)
        runs.append([e[2] for e in current_run])

    return runs


def join_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx)
    if not selected:
        return

    lines = [e for e in selected if isinstance(e, Line)]
    if len(lines) < 2:
        yield Prompt("JOIN nesta versão exige selecionar 2 ou mais objetos Line colineares.", kind="info")
        ctx.selection.clear()
        return

    runs = _join_collinear_runs(lines)
    joined_count = 0
    untouched_count = 0
    merged_objects = 0
    for run in runs:
        if len(run) < 2:
            untouched_count += len(run)
            continue

        base_a, base_b = run[0].start, run[0].end
        dx, dy = base_b.x - base_a.x, base_b.y - base_a.y
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length

        def project(pt: Point) -> float:
            return (pt.x - base_a.x) * ux + (pt.y - base_a.y) * uy

        lo = min(min(project(line.start), project(line.end)) for line in run)
        hi = max(max(project(line.start), project(line.end)) for line in run)

        survivor = run[0]
        survivor.start = Point(base_a.x + ux * lo, base_a.y + uy * lo)
        survivor.end = Point(base_a.x + ux * hi, base_a.y + uy * hi)
        for line in run[1:]:
            ctx.document.remove_entity(line.id)
        joined_count += len(run)
        merged_objects += 1

    ctx.selection.clear()
    if joined_count == 0:
        yield Prompt(
            "Os objetos selecionados não são colineares e conectados nas pontas — nada foi unido.",
            kind="info",
        )
        return

    message = f"JOIN: {joined_count} linha(s) unida(s) em {merged_objects} objeto(s)."
    if untouched_count:
        message += f" {untouched_count} objeto(s) não colinear(es)/conectado(s) ficaram como estavam."
    yield Prompt(message, kind="info")


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

    # Entidades de "ponto único" (sem vértice parcial possível): a janela
    # captura o objeto inteiro ou não captura nada, igual ao STRETCH de
    # verdade do AutoCAD tratando Circle/bloco/texto pelo ponto que os
    # define. Antes só Line/LWPolyline eram reconhecidas — esticar uma
    # parede (Line) deixava portas/sensores/câmeras (Circle/PointEntity/
    # BlockReference/Text) pra trás, em silêncio (bug real de auditoria,
    # 2026-08-22).
    affected: list[Entity] = []
    for entity in ctx.document.all_entities():
        if isinstance(entity, Line) and (inside(entity.start) or inside(entity.end)):
            affected.append(entity)
        elif isinstance(entity, (LWPolyline, Spline)) and any(inside(pt) for pt in entity.points):
            affected.append(entity)
        elif isinstance(entity, (Circle, Arc)) and inside(entity.center):
            affected.append(entity)
        elif isinstance(entity, PointEntity) and inside(entity.location):
            affected.append(entity)
        elif isinstance(entity, (BlockReference, Text)) and inside(entity.insertion_point):
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
        elif isinstance(entity, (LWPolyline, Spline)):
            entity.points = [
                Point(pt.x + dx, pt.y + dy) if inside(pt) else pt for pt in entity.points
            ]
        elif isinstance(entity, (Circle, Arc)):
            entity.center = Point(entity.center.x + dx, entity.center.y + dy)
        elif isinstance(entity, PointEntity):
            entity.location = Point(entity.location.x + dx, entity.location.y + dy)
        elif isinstance(entity, (BlockReference, Text)):
            entity.insertion_point = Point(entity.insertion_point.x + dx, entity.insertion_point.y + dy)


# ------------------------------------------------------------------ #
# DIVIDE / MEASURE — cada ponto de divisão/medida é um PointEntity real
# (comando POINT, ver core/entities.py). Antes de PointEntity existir, cada
# ponto era um Circle minúsculo (_MARKER_RADIUS) — histórico, não mais usado.
# ------------------------------------------------------------------ #


def divide_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx, "Select object to divide:")
    if len(selected) != 1:
        yield Prompt("DIVIDE exige selecionar exatamente um objeto.", kind="info")
        ctx.selection.clear()
        return

    target = selected[0]
    count = yield Prompt("Enter number of segments:", kind="distance")
    if count is ENTER:
        yield Prompt("DIVIDE exige um número de segmentos — não há valor padrão.", kind="info")
        ctx.selection.clear()
        return
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
        ctx.document.add_entity(PointEntity(location=pt, layer=target.layer))
    ctx.selection.clear()


# ------------------------------------------------------------------ #
# BREAK / BREAK AT POINT (Line/Arc/Circle) — mesmo espírito do TRIM: remove
# o trecho entre dois pontos ao longo da própria entidade (não usa arestas de
# corte de outros objetos). BREAK AT POINT é o caso particular de dividir em
# dois pedaços sem remover material (os dois pontos coincidem).
# ------------------------------------------------------------------ #
def _line_point_at(line: Line, t: float) -> Point:
    return Point(line.start.x + t * (line.end.x - line.start.x), line.start.y + t * (line.end.y - line.start.y))


def _break_line_pieces(line: Line, p1: Point, p2: Point) -> list[tuple[Point, Point]]:
    t1 = max(0.0, min(1.0, segment_parameter(p1, line.start, line.end)))
    t2 = max(0.0, min(1.0, segment_parameter(p2, line.start, line.end)))
    lo, hi = sorted((t1, t2))
    eps = 1e-9
    pieces: list[tuple[Point, Point]] = []
    if lo > eps:
        pieces.append((line.start, _line_point_at(line, lo)))
    if hi < 1 - eps:
        pieces.append((_line_point_at(line, hi), line.end))
    return pieces


def _break_arc_pieces(arc: Arc, p1: Point, p2: Point) -> list[tuple[float, float]]:
    base = arc.start_angle
    total = (arc.end_angle - arc.start_angle) % (2 * math.pi)

    def sweep(pt: Point) -> float:
        return max(0.0, min(total, (arc.center.angle_to(pt) - base) % (2 * math.pi)))

    lo, hi = sorted((sweep(p1), sweep(p2)))
    eps = 1e-9
    pieces: list[tuple[float, float]] = []
    if lo > eps:
        pieces.append((base, (base + lo) % (2 * math.pi)))
    if hi < total - eps:
        pieces.append(((base + hi) % (2 * math.pi), arc.end_angle))
    return pieces


def _break_circle_arc(circle: Circle, p1: Point, p2: Point) -> Arc | None:
    a1 = circle.center.angle_to(p1) % (2 * math.pi)
    a2 = circle.center.angle_to(p2) % (2 * math.pi)
    if abs(a1 - a2) < 1e-9:
        return None
    return Arc(
        center=Point(circle.center.x, circle.center.y), radius=circle.radius,
        start_angle=a2, end_angle=a1, layer=circle.layer, color=circle.color,
    )


def _apply_break(ctx: CommandContext, target: Entity, p1: Point, p2: Point) -> bool:
    if isinstance(target, Line):
        pieces = _break_line_pieces(target, p1, p2)
        if not pieces:
            ctx.document.remove_entity(target.id)
            return True
        target.start, target.end = pieces[0]
        for extra_start, extra_end in pieces[1:]:
            ctx.document.add_entity(Line(start=extra_start, end=extra_end, layer=target.layer, color=target.color))
        return True
    if isinstance(target, Arc):
        pieces = _break_arc_pieces(target, p1, p2)
        if not pieces:
            ctx.document.remove_entity(target.id)
            return True
        target.start_angle, target.end_angle = pieces[0]
        for start_angle, end_angle in pieces[1:]:
            ctx.document.add_entity(Arc(
                center=Point(target.center.x, target.center.y), radius=target.radius,
                start_angle=start_angle, end_angle=end_angle, layer=target.layer, color=target.color,
            ))
        return True
    if isinstance(target, Circle):
        new_arc = _break_circle_arc(target, p1, p2)
        if new_arc is None:
            return False
        ctx.document.remove_entity(target.id)
        ctx.document.add_entity(new_arc)
        return True
    return False


def break_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    first = yield Prompt("Select object:", kind="point", connect_to_last=False)
    target = _hit_test_entity(ctx, first)
    if target is None:
        yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
        return
    if not isinstance(target, (Line, Arc, Circle)):
        yield Prompt("BREAK nesta versão só funciona em Line, Arc e Circle.", kind="info")
        return

    first_point = first
    second = yield Prompt(
        "Specify second break point or [First point]:", kind="point",
        options=["First point"], connect_to_last=False,
    )
    if second == "FIRST POINT":
        first_point = yield Prompt("Specify first break point:", kind="point", connect_to_last=False)
        second = yield Prompt("Specify second break point:", kind="point", connect_to_last=False)

    if not _apply_break(ctx, target, first_point, second):
        yield Prompt("Não foi possível calcular o BREAK com os pontos informados.", kind="info")


def breakatpoint_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """BREAK AT POINT: divide a entidade em dois pedaços no ponto informado,
    sem remover material (os dois "lados" ficam com a mesma ponta). Só
    funciona em Line e Arc — igual ao AutoCAD, Circle não é um alvo válido
    (não há como dividir um círculo num único ponto sem virar arco quase
    completo, o que aqui é feito pelo BREAK normal com dois pontos)."""
    first = yield Prompt("Select object:", kind="point", connect_to_last=False)
    target = _hit_test_entity(ctx, first)
    if target is None:
        yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
        return
    if not isinstance(target, (Line, Arc)):
        yield Prompt("BREAK AT POINT nesta versão só funciona em Line e Arc.", kind="info")
        return

    point = yield Prompt("Specify break point:", kind="point", connect_to_last=False)
    if not _apply_break(ctx, target, point, point):
        yield Prompt("O ponto informado coincide com uma das pontas — nada para dividir.", kind="info")


# ------------------------------------------------------------------ #
# LENGTHEN (Line/Arc) — sub-opções [DElta/Percent/Total], como no AutoCAD.
# Alonga/encurta a partir da ponta mais próxima do clique, mantendo a outra
# ponta fixa (mesma lógica de "qual ponta se move" do EXTEND).
# ------------------------------------------------------------------ #
def _lengthen_new_length(current: float, mode: str, value: float) -> float:
    if mode == "PERCENT":
        return current * value / 100.0
    if mode == "TOTAL":
        return value
    return current + value  # DELTA


def _apply_lengthen_line(line: Line, pick: Point, mode: str, value: float) -> None:
    current = line.length()
    new_length = _lengthen_new_length(current, mode, value)
    if new_length <= 1e-9:
        raise ValueError("O comprimento resultante do LENGTHEN deve ser maior que zero.")

    t = segment_parameter(pick, line.start, line.end)
    moving_is_start = t <= 0.5
    anchor = line.end if moving_is_start else line.start
    moving = line.start if moving_is_start else line.end
    ux, uy = moving.x - anchor.x, moving.y - anchor.y
    length = math.hypot(ux, uy)
    if length < 1e-9:
        raise ValueError("Não é possível aplicar LENGTHEN numa linha de comprimento zero.")
    ux, uy = ux / length, uy / length
    new_point = Point(anchor.x + ux * new_length, anchor.y + uy * new_length)
    if moving_is_start:
        line.start = new_point
    else:
        line.end = new_point


def _apply_lengthen_arc(arc: Arc, pick: Point, mode: str, value: float) -> None:
    sweep_total = (arc.end_angle - arc.start_angle) % (2 * math.pi)
    current = arc.radius * sweep_total
    new_length = _lengthen_new_length(current, mode, value)
    if arc.radius <= 1e-9:
        raise ValueError("Não é possível aplicar LENGTHEN num arco de raio zero.")
    new_sweep = new_length / arc.radius
    if new_sweep <= 1e-9 or new_sweep >= 2 * math.pi:
        raise ValueError("O comprimento resultante do LENGTHEN é inválido para este arco.")

    moving_is_start = pick.distance_to(arc.start_point()) <= pick.distance_to(arc.end_point())
    if moving_is_start:
        arc.start_angle = (arc.end_angle - new_sweep) % (2 * math.pi)
    else:
        arc.end_angle = (arc.start_angle + new_sweep) % (2 * math.pi)


def lengthen_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    mode = "DELTA"
    value = 0.0
    while True:
        pick = yield Prompt(
            f"Select an object to change or [DElta/Percent/Total] (Enter to exit) <{mode}>:",
            kind="point", options=["DElta", "Percent", "Total"], connect_to_last=False,
        )
        if pick is ENTER:
            return
        if pick == "DELTA":
            value = yield Prompt("Enter delta length:", kind="distance")
            mode = "DELTA"
            continue
        if pick == "PERCENT":
            value = yield Prompt("Enter percentage length (100 = sem mudança):", kind="distance")
            mode = "PERCENT"
            continue
        if pick == "TOTAL":
            value = yield Prompt("Specify total length:", kind="distance")
            mode = "TOTAL"
            continue

        target = _hit_test_entity(ctx, pick)
        if target is None:
            yield Prompt("Nenhum objeto encontrado sob o clique.", kind="info")
            continue
        try:
            if isinstance(target, Line):
                _apply_lengthen_line(target, pick, mode, value)
            elif isinstance(target, Arc):
                _apply_lengthen_arc(target, pick, mode, value)
            else:
                yield Prompt("LENGTHEN nesta versão só funciona em Line e Arc.", kind="info")
        except ValueError as exc:
            yield Prompt(str(exc), kind="info")


def pedit_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """PEDIT (PE): edição básica de uma LWPolyline já desenhada, em loop de
    opções igual ao PEDIT de verdade do AutoCAD — mas sem o submenu completo
    de edição de vértice (Next/Previous/Break/Tangent etc., que dependeria
    de marcadores de vértice interativos no canvas). Opções suportadas:
    [Close/Open/Add vertex/Remove vertex/eXit]. "Add vertex" sempre
    acrescenta no FINAL da polilinha (não insere no meio); "Remove vertex"
    remove o vértice mais próximo do ponto clicado."""
    selected = yield from _select_objects(ctx, "Select polyline:")
    polylines = [e for e in selected if isinstance(e, LWPolyline)]
    if not polylines:
        yield Prompt("PEDIT: nenhuma polilinha selecionada.", kind="info")
        return
    poly = polylines[0]

    while True:
        option = yield Prompt(
            "Enter an option [Close/Open/Add vertex/Remove vertex/eXit] <eXit>:",
            kind="keyword",
            options=["Close", "Open", "Add vertex", "Remove vertex", "eXit"],
        )
        if option is ENTER or option == "EXIT":
            return
        if option == "CLOSE":
            poly.closed = True
        elif option == "OPEN":
            poly.closed = False
        elif option == "ADD VERTEX":
            point = yield Prompt(
                "Specify new vertex (added at the end):", kind="point", connect_to_last=False
            )
            poly.points.append(point)
        elif option == "REMOVE VERTEX":
            if len(poly.points) <= 2:
                yield Prompt("PEDIT: a polilinha precisa de pelo menos 2 vértices.", kind="info")
                continue
            point = yield Prompt(
                "Specify vertex to remove (click near it):", kind="point", connect_to_last=False
            )
            nearest_index = min(range(len(poly.points)), key=lambda i: poly.points[i].distance_to(point))
            poly.points.pop(nearest_index)


def measure_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(ctx, "Select object to measure:")
    if len(selected) != 1:
        yield Prompt("MEASURE exige selecionar exatamente um objeto.", kind="info")
        ctx.selection.clear()
        return

    target = selected[0]
    seg_length = yield Prompt("Specify length of segment:", kind="distance")
    if seg_length is ENTER or seg_length <= 0:
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
    elif isinstance(target, Circle):
        total = 2 * math.pi * target.radius
        n = int(total // seg_length + 1e-9)
        if n < 1:
            yield Prompt("Comprimento do segmento maior que o objeto selecionado.", kind="info")
            ctx.selection.clear()
            return
        angle_per = seg_length / target.radius
        points = [
            Point(target.center.x + target.radius * math.cos(angle_per * i),
                  target.center.y + target.radius * math.sin(angle_per * i))
            for i in range(n)
        ]
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
        yield Prompt("MEASURE nesta versão suporta Line, Arc e Circle.", kind="info")
        ctx.selection.clear()
        return

    for pt in points:
        ctx.document.add_entity(PointEntity(location=pt, layer=target.layer))


# ------------------------------------------------------------------ #
# CLIP / CLIPOFF (recorte de bloco/xref/imagem)
# ------------------------------------------------------------------ #
def _world_point_to_block_local(entity: BlockReference, world: Point) -> Point:
    """Converte um ponto do mundo para o referencial LOCAL do bloco (origem
    no ponto base, sem a rotação/escala da instância) — mesmo referencial em
    que `Document.block_definitions[block_name]` guarda seus filhos, e em que
    `BlockReference.clip_boundary` é guardado (ver core/entities.py)."""
    offset = Point(world.x - entity.insertion_point.x, world.y - entity.insertion_point.y)
    unrotated = rotate_point(offset, Point(0, 0), -entity.rotation)
    sx, sy = entity.scale_xy()
    return Point(unrotated.x / sx, unrotated.y / sy)


def _world_point_to_image_local(entity: ImageReference, world: Point) -> Point:
    """ImageReference não tem rotação/escala própria (só width/height) — o
    referencial local é só uma translação a partir do ponto de inserção."""
    return Point(world.x - entity.insertion_point.x, world.y - entity.insertion_point.y)


def clip_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """CLIP (XCLIP): recorta a área visível de um bloco, referência externa
    (XREF — que é um BlockReference com `is_xref=True`, ver core/entities.py)
    ou imagem, escondendo tudo fora de um retângulo escolhido na hora —
    mesma ideia do XCLIP do AutoCAD, mas só com contorno retangular (o de
    verdade também aceita polígono à mão livre). Chamar CLIP de novo sobre o
    mesmo objeto substitui o contorno anterior; CLIPOFF remove."""
    first = yield Prompt("Select block, xref or image to clip:", kind="point", connect_to_last=False)
    target = _hit_test_entity(ctx, first)
    if not isinstance(target, (BlockReference, ImageReference)):
        yield Prompt("CLIP: selecione um bloco, referência externa (xref) ou imagem.", kind="info")
        return

    corner1 = yield Prompt("Specify first clip boundary corner:", kind="point")
    corner2 = yield Prompt("Specify opposite corner:", kind="point", connect_to_last=True)

    if isinstance(target, BlockReference):
        local1 = _world_point_to_block_local(target, corner1)
        local2 = _world_point_to_block_local(target, corner2)
    else:
        local1 = _world_point_to_image_local(target, corner1)
        local2 = _world_point_to_image_local(target, corner2)

    target.clip_boundary = [local1, Point(local2.x, local1.y), local2, Point(local1.x, local2.y)]


def clipoff_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """CLIPOFF: remove o contorno de recorte aplicado por CLIP, voltando o
    bloco/xref/imagem a aparecer inteiro."""
    first = yield Prompt("Select clipped object:", kind="point", connect_to_last=False)
    target = _hit_test_entity(ctx, first)
    if not isinstance(target, (BlockReference, ImageReference)):
        yield Prompt("CLIPOFF: selecione um bloco, referência externa (xref) ou imagem.", kind="info")
        return
    target.clip_boundary = None


# ------------------------------------------------------------------ #
# COPYCLIP / CUTCLIP / PASTECLIP (clipboard do Windows)
# ------------------------------------------------------------------ #
#: MIME type próprio pro clipboard do SO — só o próprio NewSIcad grava e lê
#: (Ctrl+C num app qualquer não vira "cola" aqui, e vice-versa: colar num
#: Word depois de um Ctrl+C no NewSIcad não traz nada, já que não geramos
#: nenhum formato de imagem/texto junto — ver docstring de copyclip_command).
_CLIPBOARD_MIME_TYPE = "application/x-newsicad-entities"


def _write_clipboard(entities: list[Entity], base: Point) -> None:
    from PySide6.QtCore import QByteArray, QMimeData
    from PySide6.QtWidgets import QApplication

    # pickle em vez de um serializador JSON próprio: os dataclasses de
    # entidade (com Point/Path/listas aninhadas) já são pickláveis de graça,
    # e é o mesmo mecanismo que o undo/redo usa (core/undo.py) pra clonar o
    # documento inteiro — clipboard só entre instâncias do próprio NewSIcad
    # no mesmo computador, sem canal de rede envolvido.
    payload = pickle.dumps(([clone_entity(e) for e in entities], base))
    mime = QMimeData()
    mime.setData(_CLIPBOARD_MIME_TYPE, QByteArray(payload))
    QApplication.clipboard().setMimeData(mime)


def _read_clipboard() -> tuple[list[Entity], Point] | None:
    from PySide6.QtWidgets import QApplication

    mime = QApplication.clipboard().mimeData()
    if mime is None or not mime.hasFormat(_CLIPBOARD_MIME_TYPE):
        return None
    try:
        return pickle.loads(bytes(mime.data(_CLIPBOARD_MIME_TYPE)))
    except Exception:
        return None


def copyclip_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """COPYCLIP (Ctrl+C): copia os objetos selecionados pro clipboard do
    Windows num formato próprio do NewSIcad — cola de volta com PASTECLIP
    (Ctrl+V), na mesma aba, em outra aba ou até em outra instância do
    NewSIcad aberta ao mesmo tempo."""
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    _write_clipboard(selected, base)


def cutclip_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """CUTCLIP (Ctrl+X): como COPYCLIP, mas também apaga os objetos do
    desenho atual (equivalente a COPYCLIP + ERASE)."""
    selected = yield from _select_objects(ctx)
    if not selected:
        return
    base = yield Prompt("Specify base point:", kind="point")
    _write_clipboard(selected, base)
    for entity in selected:
        ctx.document.remove_entity(entity.id)
    ctx.selection.clear()


def pasteclip_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """PASTECLIP (Ctrl+V): cola os objetos copiados/recortados por
    COPYCLIP/CUTCLIP na posição escolhida, deslocados a partir do ponto base
    guardado na cópia. IDs são regenerados pra nunca colidir com os já
    presentes no documento — inclusive ao colar de volta na MESMA aba onde
    foi copiado (ver `newsicad.core.entities._new_id`)."""
    payload = _read_clipboard()
    if payload is None:
        yield Prompt("PASTECLIP: clipboard vazio ou sem objetos do NewSIcad.", kind="info")
        return
    entities, base = payload

    insertion = yield Prompt("Specify insertion point:", kind="point")
    dx, dy = insertion.x - base.x, insertion.y - base.y

    pasted_ids: set[str] = set()
    for entity in entities:
        clone = clone_entity(entity)
        clone.id = _new_id()
        translate_entity(clone, dx, dy)
        ctx.document.add_entity(clone)
        pasted_ids.add(clone.id)
    ctx.selection.set(pasted_ids)
