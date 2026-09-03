"""Comandos de desenho e medição (LINE, CIRCLE, ARC, RECTANGLE, PLINE,
ELLIPSE, DIST) com prompts sequenciais idênticos aos do AutoCAD."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import (
    Arc,
    Circle,
    Ellipse,
    Hatch,
    Line,
    LWPolyline,
    Point,
    PointEntity,
    Ray,
    Spline,
    XLine,
)
from newsicad.core.geometry_ops import (
    arc_from_3_points,
    offset_polyline,
    point_in_polygon,
    trace_simple_line_loop,
)


def line_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    first = yield Prompt("Specify first point:", kind="point")
    prev = first
    # Cada segmento vira uma Line independente na hora (diferente de PLINE,
    # que só grava UMA entidade no final) — [Undo] precisa remover de volta
    # o último segmento já gravado, não só re-perguntar. Sem isso a opção
    # era só decorativa: o segmento ficava no desenho mesmo escolhendo
    # "Undo" (bug real de auditoria, 2026-08-22).
    segments: list[tuple[str, Point]] = []
    while True:
        nxt = yield Prompt("Specify next point or [Undo]:", kind="point", options=["Undo"])
        if nxt is ENTER:
            return
        if nxt == "UNDO":
            if segments:
                last_id, last_start = segments.pop()
                ctx.document.remove_entity(last_id)
                prev = last_start
            continue
        entity = ctx.document.add_entity(Line(start=prev, end=nxt, layer=ctx.document.current_layer))
        segments.append((entity.id, prev))
        prev = nxt


def circle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    center = yield Prompt("Specify center point for circle:", kind="point")
    radius = yield Prompt("Specify radius of circle:", kind="distance")
    ctx.document.add_entity(Circle(center=center, radius=radius, layer=ctx.document.current_layer))


def arc_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify start point of arc:", kind="point")
    p2 = yield Prompt("Specify second point of arc:", kind="point")
    p3 = yield Prompt("Specify end point of arc:", kind="point")
    try:
        center, radius, start_angle, end_angle = arc_from_3_points(p1, p2, p3)
    except ValueError as exc:
        # 3 pontos colineares (ou 2 coincidentes) — circumcenter() levanta
        # ValueError; sem esse catch o comando travava com uma exceção não
        # tratada (bug real de auditoria, 2026-08-22), diferente de OFFSET/
        # FILLET/CHAMFER/MLINE, que já protegem o caso equivalente.
        yield Prompt(str(exc), kind="info")
        return
    ctx.document.add_entity(
        Arc(
            center=center,
            radius=radius,
            start_angle=start_angle,
            end_angle=end_angle,
            layer=ctx.document.current_layer,
        )
    )


def rectangle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first corner point:", kind="point")
    p2 = yield Prompt("Specify other corner point:", kind="point")
    points = [Point(p1.x, p1.y), Point(p2.x, p1.y), Point(p2.x, p2.y), Point(p1.x, p2.y)]
    ctx.document.add_entity(LWPolyline(points=points, closed=True, layer=ctx.document.current_layer))


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
        ctx.document.add_entity(LWPolyline(points=points, closed=False, layer=ctx.document.current_layer))


def ellipse_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    center = yield Prompt("Specify center of ellipse:", kind="point")
    axis_end = yield Prompt("Specify endpoint of axis:", kind="point")
    minor_radius = yield Prompt("Specify distance to other axis:", kind="distance")

    major_radius = center.distance_to(axis_end)
    if major_radius <= 0 or minor_radius <= 0:
        # Centro igual ao ponto do eixo (ou distância 0 pro outro eixo) cria
        # uma Ellipse de raio 0 sem nenhum aviso — o desenho parecia normal
        # até apertar Ctrl+S, quando o ezdxf recusava a entidade e travava o
        # Save do arquivo inteiro (bug real de auditoria, 2026-08-22).
        yield Prompt("ELLIPSE: os dois raios devem ser maiores que zero.", kind="info")
        return
    rotation = center.angle_to(axis_end)
    ctx.document.add_entity(
        Ellipse(
            center=center,
            radius_major=major_radius,
            radius_minor=minor_radius,
            rotation=rotation,
            layer=ctx.document.current_layer,
        )
    )


def polygon_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """POLYGON (POL): desenha um polígono regular como uma LWPolyline fechada
    (mesmo caminho de RECTANG). Suporta as duas opções do POLYGON de verdade
    do AutoCAD — Inscribed in circle (vértices no raio informado) e
    Circumscribed about circle (raio informado é a distância do centro até o
    meio de cada lado, os vértices ficam num raio maior)."""
    sides_raw = yield Prompt("Enter number of sides <4>:", kind="distance")
    sides = 4 if sides_raw is ENTER else max(3, int(sides_raw))
    center = yield Prompt("Specify center of polygon:", kind="point")
    option = yield Prompt(
        "Enter an option [Inscribed in circle/Circumscribed about circle] <Inscribed>:",
        kind="keyword",
        options=["Inscribed", "Circumscribed"],
    )
    radius = yield Prompt("Specify radius of circle:", kind="distance")
    vertex_radius = radius / math.cos(math.pi / sides) if option == "CIRCUMSCRIBED" else radius
    points = [
        Point(
            center.x + vertex_radius * math.cos(2 * math.pi * i / sides),
            center.y + vertex_radius * math.sin(2 * math.pi * i / sides),
        )
        for i in range(sides)
    ]
    ctx.document.add_entity(LWPolyline(points=points, closed=True, layer=ctx.document.current_layer))


def spline_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """SPLINE (SP): curva suave por pontos de ajuste — entrada de pontos
    igual a PLINE ([Undo] desfaz o último ponto, Enter termina), com opção
    [Close] pra fechar a curva de volta ao primeiro ponto. Não é uma NURBS
    de verdade como o SPLINE do AutoCAD (ver Spline em core/entities.py e
    catmull_rom_bezier em core/geometry_ops.py), mas é uma curva suave
    interpolante de verdade, passando exatamente pelos pontos informados."""
    first = yield Prompt("Specify first point:", kind="point")
    points = [first]
    closed = False
    while True:
        nxt = yield Prompt(
            "Specify next point or [Close/Undo]:", kind="point", options=["Close", "Undo"]
        )
        if nxt is ENTER:
            break
        if nxt == "CLOSE":
            if len(points) >= 3:
                closed = True
            else:
                yield Prompt("SPLINE: [Close] precisa de pelo menos 3 pontos — criada aberta.", kind="info")
            break
        if nxt == "UNDO":
            if len(points) > 1:
                points.pop()
            continue
        points.append(nxt)
    if len(points) >= 2:
        ctx.document.add_entity(Spline(points=points, closed=closed, layer=ctx.document.current_layer))


def boundary_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """BOUNDARY (BO): gera uma LWPolyline fechada a partir de um ponto
    clicado dentro de uma área fechada. Cobre três casos, nesta ordem: (1)
    o ponto está dentro de uma LWPolyline já fechada — gera uma cópia
    independente dela; (2) o ponto está dentro de um Circle — aproxima como
    um polígono de 64 lados (Hatch/AREA trabalham com lista de pontos, não
    com um tipo "boundary circular" dedicado); (3) o ponto está dentro de um
    laço fechado SIMPLES formado por Line soltas (paredes), sem bifurcação/
    junção em T — ver geometry_ops.trace_simple_line_loop. Laços com junção
    em T (ex.: parede interna encostando numa externa) não são resolvidos
    automaticamente nesta versão — desenhe/selecione o contorno já fechado
    nesse caso."""
    point = yield Prompt("Pick internal point:", kind="point", connect_to_last=False)

    for entity in ctx.document.all_entities():
        if isinstance(entity, LWPolyline) and entity.closed and len(entity.points) >= 3:
            if point_in_polygon(point, entity.points):
                ctx.document.add_entity(
                    LWPolyline(points=list(entity.points), closed=True, layer=ctx.document.current_layer)
                )
                return

    for entity in ctx.document.all_entities():
        if isinstance(entity, Circle) and point.distance_to(entity.center) <= entity.radius:
            n = 64
            pts = [
                Point(
                    entity.center.x + entity.radius * math.cos(2 * math.pi * i / n),
                    entity.center.y + entity.radius * math.sin(2 * math.pi * i / n),
                )
                for i in range(n)
            ]
            ctx.document.add_entity(LWPolyline(points=pts, closed=True, layer=ctx.document.current_layer))
            return

    lines = [e for e in ctx.document.all_entities() if isinstance(e, Line)]
    loop = trace_simple_line_loop(lines, point)
    if loop is not None:
        ctx.document.add_entity(LWPolyline(points=loop, closed=True, layer=ctx.document.current_layer))
        return

    yield Prompt(
        "BOUNDARY: nenhum contorno fechado encontrado nesse ponto (funciona com uma "
        "LWPolyline já fechada, um Circle, ou um laço simples de Line sem bifurcações).",
        kind="info",
    )


def point_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """POINT (PO): cria um PointEntity real (não mais o marcador Circle
    minúsculo usado por DIVIDE/MEASURE antes deste tipo existir)."""
    location = yield Prompt("Specify a point:", kind="point")
    ctx.document.add_entity(PointEntity(location=location, layer=ctx.document.current_layer))


def xline_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """XLINE (XL): linha de construção infinita nas duas direções. Igual ao
    AutoCAD, o ponto base fica fixo e o comando aceita vários "through
    points" em sequência (uma XLine por ponto), até Enter."""
    base = yield Prompt("Specify a point:", kind="point")
    while True:
        through = yield Prompt(
            "Specify through point (Enter to exit):", kind="point", connect_to_last=False
        )
        if through is ENTER:
            break
        if base.distance_to(through) <= 1e-9:
            # Ponto de referência igual ao ponto base: angle_to() cai no caso
            # degenerado atan2(0,0)=0 e criava uma XLine horizontal do nada,
            # sem nenhum aviso (bug real de auditoria, 2026-08-22).
            yield Prompt("XLINE: o ponto de referência não pode coincidir com o ponto base.", kind="info")
            continue
        angle = base.angle_to(through)
        ctx.document.add_entity(
            XLine(point=Point(base.x, base.y), angle=angle, layer=ctx.document.current_layer)
        )


def ray_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """RAY: linha de construção infinita numa única direção — mesmo fluxo do
    XLINE acima."""
    base = yield Prompt("Specify start point:", kind="point")
    while True:
        through = yield Prompt(
            "Specify through point (Enter to exit):", kind="point", connect_to_last=False
        )
        if through is ENTER:
            break
        if base.distance_to(through) <= 1e-9:
            yield Prompt("RAY: o ponto de referência não pode coincidir com o ponto inicial.", kind="info")
            continue
        angle = base.angle_to(through)
        ctx.document.add_entity(
            Ray(point=Point(base.x, base.y), angle=angle, layer=ctx.document.current_layer)
        )


def donut_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """DONUT (DO): anel preenchido — ver `Circle.inner_radius` em
    core/entities.py. Igual ao AutoCAD, pede diâmetro interno/externo uma vez
    e depois aceita vários centros em sequência até Enter."""
    inside_raw = yield Prompt("Specify inside diameter of donut <0.5>:", kind="distance")
    inside = 0.5 if inside_raw is ENTER else inside_raw
    outside_raw = yield Prompt("Specify outside diameter of donut <1.0>:", kind="distance")
    outside = 1.0 if outside_raw is ENTER else outside_raw
    if outside <= 0 or inside < 0 or inside >= outside:
        yield Prompt("O diâmetro externo deve ser maior que o interno (e ambos >= 0).", kind="info")
        return

    while True:
        center = yield Prompt("Specify center of donut (Enter to exit):", kind="point")
        if center is ENTER:
            break
        ctx.document.add_entity(
            Circle(
                center=center, radius=outside / 2, inner_radius=inside / 2,
                layer=ctx.document.current_layer,
            )
        )


def _mline_side_point(a: Point, b: Point, sign: float) -> Point:
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    mid = Point((a.x + b.x) / 2, (a.y + b.y) / 2)
    offset = 1e-3
    return Point(mid.x + nx * offset * sign, mid.y + ny * offset * sign)


def mline_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """MLINE (ML): parede de linhas paralelas — simplificação documentada no
    README: não é uma entidade MLINE de verdade com MLSTYLE (múltiplos
    elementos com offsets/cores próprias), só duas LWPolyline independentes
    (uma de cada lado do eixo desenhado), deslocadas ± metade da largura
    total via `geometry_ops.offset_polyline` (mesma função que já resolve os
    cantos/junções do comando OFFSET). Entrada de pontos igual a PLINE."""
    width = yield Prompt("Specify total width of the wall:", kind="distance")
    if width <= 0:
        yield Prompt("A largura da MLINE deve ser positiva.", kind="info")
        return

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

    if len(points) < 2:
        return

    path = LWPolyline(points=points, closed=False)
    half = width / 2
    pos_side = _mline_side_point(points[0], points[1], 1.0)
    neg_side = _mline_side_point(points[0], points[1], -1.0)
    try:
        line1 = offset_polyline(path, half, pos_side)
        line2 = offset_polyline(path, half, neg_side)
    except ValueError as exc:
        yield Prompt(str(exc), kind="info")
        return
    line1.layer = line2.layer = ctx.document.current_layer
    ctx.document.add_entity(line1)
    ctx.document.add_entity(line2)


_REVCLOUD_BULGE = 0.15  # fração da corda que cada arco "estufa" pra fora


def revcloud_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """REVCLOUD: nuvem de revisão. Simplificação documentada: entrada por
    cliques (como PLINE), não por arrastar o mouse em modo livre como o
    REVCLOUD de verdade do AutoCAD — cada trecho entre dois pontos clicados
    consecutivos vira UM arco estufado pra fora (não vários arcos pequenos
    uniformes), fechando de volta no primeiro ponto ao terminar. Cada arco é
    uma entidade `Arc` real e independente."""
    first = yield Prompt("Specify start point:", kind="point")
    points = [first]
    while True:
        nxt = yield Prompt(
            "Specify next point or [Undo] (Enter to close):", kind="point", options=["Undo"]
        )
        if nxt is ENTER:
            break
        if nxt == "UNDO":
            if len(points) > 1:
                points.pop()
            continue
        points.append(nxt)

    if len(points) < 2:
        return
    loop = points + [points[0]]
    for a, b in zip(loop, loop[1:]):
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        mid = Point((a.x + b.x) / 2, (a.y + b.y) / 2)
        nx, ny = -dy / length, dx / length
        bulge_pt = Point(mid.x + nx * length * _REVCLOUD_BULGE, mid.y + ny * length * _REVCLOUD_BULGE)
        try:
            center, radius, start_angle, end_angle = arc_from_3_points(a, bulge_pt, b)
        except ValueError:
            continue
        ctx.document.add_entity(
            Arc(center=center, radius=radius, start_angle=start_angle, end_angle=end_angle,
                layer=ctx.document.current_layer)
        )


def wipeout_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """WIPEOUT: área que oculta o que está atrás dela. Implementado como um
    `Hatch` com `wipeout=True` (e `solid_fill=True`) em vez de um tipo de
    entidade dedicado — reaproveita toda a infraestrutura de contorno/
    renderização/seleção que o Hatch já tem (ver core/entities.py:Hatch e
    ui/canvas.py), só trocando o preenchimento por linhas diagonais por um
    preenchimento sólido na cor de fundo do canvas. Fica por cima do que já
    existia porque o canvas desenha na ordem de criação (ver
    `CanvasView.refresh_entities`); grava/lê como WIPEOUT de verdade no .dxf."""
    first = yield Prompt("Specify start point:", kind="point")
    points = [first]
    while True:
        nxt = yield Prompt(
            "Specify next point or [Undo] (Enter to close):", kind="point", options=["Undo"]
        )
        if nxt is ENTER:
            break
        if nxt == "UNDO":
            if len(points) > 1:
                points.pop()
            continue
        points.append(nxt)

    if len(points) < 3:
        yield Prompt("WIPEOUT precisa de pelo menos 3 pontos.", kind="info")
        return
    ctx.document.add_entity(
        Hatch(boundary_points=points, solid_fill=True, wipeout=True, layer=ctx.document.current_layer)
    )


def dist_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first point:", kind="point")
    p2 = yield Prompt("Specify second point:", kind="point")
    distance = p1.distance_to(p2)
    angle = math.degrees(p1.angle_to(p2)) % 360
    yield Prompt(f"Distância = {distance:.4f}   Ângulo no plano XY = {angle:.2f}°", kind="info")
