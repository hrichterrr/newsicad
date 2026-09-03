"""Comandos de anotação: MTEXT, DIMLINEAR, DIMALIGNED, DIMANGULAR, DIMRADIUS,
DIMDIAMETER, DIMSTYLE e HATCH. Seguem o mesmo padrão gerador dos comandos em
draw_commands.py e modify_commands.py."""

from __future__ import annotations

import math
from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.commands.modify_commands import _hit_test_entity, _select_objects
from newsicad.core.entities import (
    TEXT_JUSTIFY_OPTIONS,
    Arc,
    Circle,
    Dimension,
    Entity,
    Hatch,
    Line,
    LWPolyline,
    Point,
    Table,
    Text,
)
from newsicad.core.fields import FIELD_TYPES, compute_field_value, field_supports_reference
from newsicad.core.geometry_ops import (
    as_intersectable_pieces,
    dimension_line_segment,
    entity_intersections,
    split_segment_with_gaps,
)

DEFAULT_TEXT_HEIGHT = 2.5


def mtext_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """MTEXT (T/MT): pede o ponto de inserção com uma sub-opção [Justify]
    (loop igual ao [Radius] do FILLET) pra escolher qual dos 9 attachment
    points de MTEXT (ver `TEXT_JUSTIFY_OPTIONS`) fica ancorado no ponto
    clicado — "TL" (Top Left) é o padrão, mesmo comportamento de antes da
    justificação existir."""
    justify = "TL"
    insertion = None
    while True:
        insertion = yield Prompt(
            f"Specify insertion point or [Justify] <{justify}>:", kind="point", options=["Justify"],
        )
        if insertion == "JUSTIFY":
            choice = yield Prompt(
                f"Enter justification [{'/'.join(TEXT_JUSTIFY_OPTIONS)}] <{justify}>:",
                kind="keyword", options=list(TEXT_JUSTIFY_OPTIONS),
            )
            if choice is not ENTER:
                justify = choice
            continue
        break

    content = yield Prompt("Enter text:", kind="text")
    if content is ENTER:
        return
    text = str(content).strip("\r")
    if text == "":
        return
    ctx.document.add_entity(
        Text(
            insertion_point=insertion,
            content=text,
            height=DEFAULT_TEXT_HEIGHT * ctx.document.annotation_scale,
            rotation=0.0,
            justify=justify,
            layer=ctx.document.current_layer,
            style=ctx.document.current_text_style,
        )
    )


def dimlinear_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first extension line origin:", kind="point")
    p2 = yield Prompt("Specify second extension line origin:", kind="point")
    dim_line = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="linear", point1=p1, point2=p2, dim_line_point=dim_line, layer=ctx.document.current_layer)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimaligned_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    p1 = yield Prompt("Specify first extension line origin:", kind="point")
    p2 = yield Prompt("Specify second extension line origin:", kind="point")
    dim_line = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(kind="aligned", point1=p1, point2=p2, dim_line_point=dim_line, layer=ctx.document.current_layer)
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimangular_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    vertex = yield Prompt("Specify angle vertex:", kind="point")
    p1 = yield Prompt("Specify first angle endpoint:", kind="point")
    p2 = yield Prompt("Specify second angle endpoint:", kind="point")
    arc_location = yield Prompt("Specify dimension arc line location:", kind="point")
    dim = Dimension(
        kind="angular",
        center=vertex,
        point1=p1,
        point2=p2,
        dim_line_point=arc_location,
        layer=ctx.document.current_layer,
    )
    ctx.document.add_entity(dim)
    yield Prompt(f"Angle = {dim.measurement_text()}", kind="info")


def _select_circle_or_arc(
    ctx: CommandContext, message: str
) -> Generator[Prompt, object, Entity | None]:
    selected = yield from _select_objects(ctx, message)
    candidates = [e for e in selected if isinstance(e, (Circle, Arc))]
    return candidates[0] if candidates else None


def dimradius_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    target = yield from _select_circle_or_arc(ctx, "Select arc or circle:")
    if target is None:
        yield Prompt("Nenhum círculo/arco selecionado.", kind="info")
        return
    leader = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(
        kind="radius",
        center=target.center,
        radius=target.radius,
        leader_point=leader,
        layer=ctx.document.current_layer,
    )
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimdiameter_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    target = yield from _select_circle_or_arc(ctx, "Select arc or circle:")
    if target is None:
        yield Prompt("Nenhum círculo/arco selecionado.", kind="info")
        return
    leader = yield Prompt("Specify dimension line location:", kind="point")
    dim = Dimension(
        kind="diameter",
        center=target.center,
        radius=target.radius,
        leader_point=leader,
        layer=ctx.document.current_layer,
    )
    ctx.document.add_entity(dim)
    yield Prompt(f"Dimension text = {dim.measurement_text()}", kind="info")


def dimstyle_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    yield Prompt(
        "NewSIcad ainda só suporta o estilo de cota padrão "
        "(estilos de cota nomeados/customizados não são suportados nesta versão).",
        kind="info",
    )


def hatch_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    selected = yield from _select_objects(
        ctx, "Select a closed polyline as the hatch boundary:"
    )
    boundaries = [
        e for e in selected if isinstance(e, LWPolyline) and e.closed and len(e.points) >= 3
    ]
    if not boundaries:
        yield Prompt(
            "HATCH nesta versão só aceita uma LWPolyline fechada pré-existente como "
            "contorno — use BOUNDARY pra gerar uma automaticamente a partir de "
            "outras entidades que fecham uma área.",
            kind="info",
        )
        return
    for boundary in boundaries:
        ctx.document.add_entity(Hatch(layer=boundary.layer, boundary_points=list(boundary.points)))

    label = "hachura" if len(boundaries) == 1 else "hachuras"
    yield Prompt(
        f"HATCH: {len(boundaries)} {label} criada(s) — padrão único de linhas diagonais "
        "(sem os outros padrões do AutoCAD de verdade). Use HATCHEDIT pra ajustar ângulo/espaçamento.",
        kind="info",
    )


def hatchedit_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """HATCHEDIT (HE): edita ângulo e espaçamento das linhas de uma hachura
    já desenhada — hatch_command não expunha esses parâmetros até agora
    (sempre usava os valores padrão do dataclass Hatch), então HATCHEDIT é
    o primeiro jeito de ajustá-los depois de criada. Simplificação: não
    reatribui o contorno (pra isso, apague e refaça com HATCH/BOUNDARY)."""
    selected = yield from _select_objects(ctx, "Select hatch object:")
    hatches = [e for e in selected if isinstance(e, Hatch)]
    if not hatches:
        yield Prompt("HATCHEDIT: nenhuma hachura selecionada.", kind="info")
        return
    hatch = hatches[0]

    angle_deg = yield Prompt(
        f"Specify new hatch angle <{math.degrees(hatch.angle):.0f}>:", kind="distance"
    )
    if angle_deg is not ENTER:
        hatch.angle = math.radians(angle_deg)

    spacing = yield Prompt(
        f"Specify new hatch spacing <{hatch.spacing:.2f}>:", kind="distance"
    )
    if spacing is not ENTER and spacing > 0:
        hatch.spacing = spacing


def leader_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """LEADER simplificado: reusa LWPolyline (a linha poligonal terminando
    perto do texto, aproximando a seta) + Text (a anotação na ponta) em vez
    de criar um tipo de entidade dedicado — v1 suficiente pra um leader
    básico sem precisar de mais um Entity novo só pra isso."""
    first = yield Prompt("Specify leader start point:", kind="point")
    points = [first]
    while True:
        nxt = yield Prompt("Specify next point:", kind="point")
        if nxt is ENTER:
            break
        points.append(nxt)
    if len(points) < 2:
        return
    ctx.document.add_entity(LWPolyline(points=points, closed=False, layer=ctx.document.current_layer))

    content = yield Prompt("Enter leader annotation text:", kind="text")
    if content is ENTER:
        return
    text = str(content).strip("\r")
    if text == "":
        return
    ctx.document.add_entity(
        Text(
            insertion_point=points[-1],
            content=text,
            height=ctx.document.mleader_style.text_height * ctx.document.annotation_scale,
            rotation=0.0,
            layer=ctx.document.current_layer,
            style=ctx.document.current_text_style,
        )
    )


def centermark_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """CENTERMARK (DIMCENTER): marca cruzada no centro de um Circle/Arc
    clicado — repete até Enter, igual ao AutoCAD real. Simplificação: só a
    cruz central (2 Line curtas), sem as linhas de centro estendidas além do
    contorno que o CENTERLINE de verdade também desenha."""
    while True:
        result = yield Prompt(
            "Select circle or arc (Enter to exit):", kind="point", connect_to_last=False
        )
        if result is ENTER:
            break
        target = _hit_test_entity(ctx, result)
        if target is None or not isinstance(target, (Circle, Arc)):
            yield Prompt("CENTERMARK: selecione um Circle ou Arc.", kind="info")
            continue
        size = max(target.radius * 0.15, 0.05)
        c = target.center
        ctx.document.add_entity(
            Line(start=Point(c.x - size, c.y), end=Point(c.x + size, c.y), layer=ctx.document.current_layer)
        )
        ctx.document.add_entity(
            Line(start=Point(c.x, c.y - size), end=Point(c.x, c.y + size), layer=ctx.document.current_layer)
        )


def dimbreak_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """DIMBREAK: interrompe a linha de cota (Linear/Aligned) onde ela cruza
    os objetos selecionados — mesmo fluxo do DIMBREAK de verdade: seleciona
    a cota, depois os objetos que cruzam. Simplificação documentada: só
    cotas Linear/Aligned (a linha de cota delas é um segmento reto simples;
    Radius/Diameter/Angular não são suportadas nesta versão)."""
    dim_selected = yield from _select_objects(ctx, "Select dimension to break:")
    dims = [e for e in dim_selected if isinstance(e, Dimension) and e.kind in ("linear", "aligned")]
    if not dims:
        yield Prompt("DIMBREAK nesta versão só funciona em cotas Linear/Aligned.", kind="info")
        return
    dim = dims[0]

    crossing = yield from _select_objects(ctx, "Select objects that cross the dimension:")
    if not crossing:
        return

    segment = dimension_line_segment(dim)
    if segment is None:
        return
    d1, d2 = segment

    break_points: list[Point] = []
    probe = Line(start=d1, end=d2)
    for entity in crossing:
        for piece in as_intersectable_pieces(entity):
            break_points.extend(entity_intersections(probe, piece))

    if not break_points:
        yield Prompt("DIMBREAK: nenhuma interseção encontrada com a linha de cota.", kind="info")
        return

    dim.break_points = list(dim.break_points) + break_points
    yield Prompt(f"DIMBREAK: {len(break_points)} quebra(s) adicionada(s).", kind="info")


_TABLE_DEFAULT_ROWS = 3
_TABLE_DEFAULT_COLS = 3
_TABLE_DEFAULT_COL_WIDTH = 2.5
_TABLE_DEFAULT_ROW_HEIGHT = 1.0


def table_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """TABLE (TB): grade uniforme de células com texto — ver `Table` em
    core/entities.py pras simplificações documentadas (sem estilos
    nomeados, sem largura/altura por coluna/linha). Depois de definir
    tamanho/dimensões, entra num loop preenchendo célula por célula em
    ordem (linha 0 esquerda->direita, depois linha 1...) — Enter deixa a
    célula em branco e continua pra próxima; [eXit] para o preenchimento a
    qualquer momento e cria a tabela com o que já foi digitado (o resto
    fica em branco, editável depois só recriando a tabela nesta versão)."""
    insertion = yield Prompt("Specify insertion point:", kind="point")

    rows_raw = yield Prompt(f"Enter number of rows <{_TABLE_DEFAULT_ROWS}>:", kind="distance")
    rows = _TABLE_DEFAULT_ROWS if rows_raw is ENTER else max(1, int(rows_raw))
    cols_raw = yield Prompt(f"Enter number of columns <{_TABLE_DEFAULT_COLS}>:", kind="distance")
    cols = _TABLE_DEFAULT_COLS if cols_raw is ENTER else max(1, int(cols_raw))
    col_width_raw = yield Prompt(f"Specify column width <{_TABLE_DEFAULT_COL_WIDTH}>:", kind="distance")
    col_width = _TABLE_DEFAULT_COL_WIDTH if col_width_raw is ENTER else col_width_raw
    row_height_raw = yield Prompt(f"Specify row height <{_TABLE_DEFAULT_ROW_HEIGHT}>:", kind="distance")
    row_height = _TABLE_DEFAULT_ROW_HEIGHT if row_height_raw is ENTER else row_height_raw

    if col_width <= 0 or row_height <= 0:
        yield Prompt("TABLE: largura de coluna e altura de linha devem ser positivas.", kind="info")
        return

    cells = [["" for _ in range(cols)] for _ in range(rows)]
    exited_early = False
    for r in range(rows):
        for c in range(cols):
            content = yield Prompt(
                f"Enter text for cell ({r + 1},{c + 1}) or [eXit]:", kind="text", options=["eXit"]
            )
            if content == "EXIT":
                exited_early = True
                break
            if content is ENTER:
                continue
            cells[r][c] = str(content).strip("\r")
        if exited_early:
            break

    ctx.document.add_entity(
        Table(
            insertion_point=insertion, rows=rows, cols=cols,
            col_width=col_width, row_height=row_height, cells=cells,
            text_height=ctx.document.table_style.text_height * ctx.document.annotation_scale,
            show_borders=ctx.document.table_style.show_borders,
            layer=ctx.document.current_layer,
        )
    )


def field_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """FIELD: insere um `Text` vinculado a um valor calculado em vez de
    digitado — AREA/LENGTH (referenciando uma entidade selecionada na hora)
    ou DATE (data de hoje, sem referência). O valor exibido é recalculado a
    cada redesenho por `CanvasView.refresh_entities()` (ver
    `newsicad/core/fields.py`), então continua correto se a entidade
    referenciada for movida/editada depois — só some se ela for apagada
    (mostra "#REF!", igual ao FIELD de verdade do AutoCAD)."""
    field_type = yield Prompt(
        f"Select field type [{'/'.join(FIELD_TYPES)}]:", kind="keyword", options=list(FIELD_TYPES)
    )

    ref_id: str | None = None
    if field_supports_reference(field_type):
        pick = yield Prompt("Select object to link:", kind="point", connect_to_last=False)
        target = _hit_test_entity(ctx, pick)
        if target is None:
            yield Prompt("FIELD: nenhum objeto encontrado sob o clique.", kind="info")
            return
        ref_id = target.id

    insertion = yield Prompt("Specify insertion point:", kind="point")
    default_height = DEFAULT_TEXT_HEIGHT * ctx.document.annotation_scale
    height_raw = yield Prompt(f"Specify text height <{default_height:.2f}>:", kind="distance")
    height = default_height if height_raw is ENTER else height_raw

    text = Text(
        insertion_point=insertion,
        content=compute_field_value(field_type, ctx.document, ref_id),
        height=height,
        layer=ctx.document.current_layer,
        field_type=field_type,
        field_ref=ref_id,
        style=ctx.document.current_text_style,
    )
    ctx.document.add_entity(text)
