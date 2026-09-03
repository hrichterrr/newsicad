"""Comandos utilitários de consulta/organização: AREA (AA), ID, DDEDIT (ED) e
PURGE (PU). Seguem o mesmo padrão gerador dos outros módulos de comando."""

from __future__ import annotations

from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.commands.modify_commands import _select_objects
from newsicad.core.entities import (
    Arc,
    BlockReference,
    Circle,
    Dimension,
    Ellipse,
    Hatch,
    Line,
    LWPolyline,
    PointEntity,
    Ray,
    Spline,
    Text,
    XLine,
)
from newsicad.core.geometry_ops import polygon_area, polygon_perimeter

# Nomes reconhecidos pelo QSELECT (ver qselect_command) — mesmos nomes das
# classes em core/entities.py, digitados em CAIXA ALTA como qualquer alias.
_QSELECT_TYPES = {
    "LINE": Line, "CIRCLE": Circle, "ARC": Arc, "ELLIPSE": Ellipse,
    "LWPOLYLINE": LWPolyline, "POLYLINE": LWPolyline, "SPLINE": Spline,
    "TEXT": Text, "MTEXT": Text, "DIMENSION": Dimension, "HATCH": Hatch,
    "BLOCK": BlockReference, "INSERT": BlockReference,
    "POINT": PointEntity, "XLINE": XLine, "RAY": Ray,
}

import math


def id_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    point = yield Prompt("Specify point:", kind="point", connect_to_last=False)
    yield Prompt(f"X = {point.x:.4f}  Y = {point.y:.4f}  Z = 0.0000", kind="info")


def area_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """AREA (AA): soma a área/perímetro de círculos e polilinhas fechadas
    selecionados. Simplificação documentada no README: não tem o modo
    "clicar pontos pra definir um polígono" do AREA de verdade do AutoCAD —
    só funciona em cima de entidades já desenhadas (normalmente uma
    LWPolyline fechada representando o contorno de um ambiente)."""
    selected = yield from _select_objects(ctx, "Select objects:")

    total_area = 0.0
    total_perimeter = 0.0
    counted = 0
    for entity in selected:
        if isinstance(entity, Circle):
            total_area += math.pi * entity.radius**2
            total_perimeter += 2 * math.pi * entity.radius
            counted += 1
        elif isinstance(entity, LWPolyline) and entity.closed and len(entity.points) >= 3:
            total_area += polygon_area(entity.points)
            total_perimeter += polygon_perimeter(entity.points, closed=True)
            counted += 1

    if counted == 0:
        yield Prompt(
            "AREA: nenhum círculo ou polilinha fechada selecionado (contornos abertos e "
            "outros tipos de entidade não são suportados nesta versão).",
            kind="info",
        )
        return

    label = "Área" if counted == 1 else "Área total"
    yield Prompt(f"{label} = {total_area:.4f}   Perímetro = {total_perimeter:.4f}", kind="info")


def _select_text(ctx: CommandContext, message: str) -> Generator[Prompt, object, Text | None]:
    selected = yield from _select_objects(ctx, message)
    texts = [e for e in selected if isinstance(e, Text)]
    return texts[0] if texts else None


def edit_text_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """DDEDIT (ED): edita o conteúdo de um Text (MTEXT/LEADER) já colocado no
    desenho. Simplificação documentada no README: só edita `Text` — cotas
    (Dimension) não têm campo de texto sobreposto no modelo do NewSIcad (o
    texto exibido é sempre calculado a partir da medição real), então
    selecionar uma cota aqui não faz nada."""
    target = yield from _select_text(ctx, "Select an annotation object or [Undo]:")
    if target is None:
        yield Prompt("ED: nenhum texto selecionado (cotas não têm texto editável nesta versão).", kind="info")
        return

    new_content = yield Prompt("Enter new text:", kind="text")
    if new_content is ENTER:
        return
    text = str(new_content).strip("\r")
    if text == "":
        return
    target.content = text
    if target.field_type is not None:
        # Editar manualmente um FIELD "quebra" o vínculo — igual ao DDEDIT
        # de verdade do AutoCAD, que converte o campo em texto estático ao
        # editar. Sem isso, CanvasView.refresh_entities() recalculava o
        # conteúdo a partir do campo a cada redesenho e a edição manual
        # sumia sozinha no próximo redraw, sem nenhum aviso (bug real de
        # auditoria, 2026-08-22).
        target.field_type = None
        target.field_ref = None


def matchprop_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """MATCHPROP (MA): copia layer e cor do objeto de origem para os objetos
    de destino selecionados. Simplificação documentada: só layer/cor — o
    MATCHPROP de verdade do AutoCAD também copia estilo de texto/cota/hachura
    e outras propriedades específicas de cada tipo de entidade, que o
    NewSIcad não modela como "estilos" nomeados nesta versão."""
    source_list = yield from _select_objects(ctx, "Select source object:")
    if not source_list:
        return
    source = source_list[0]
    targets = yield from _select_objects(ctx, "Select destination object(s):")
    if not targets:
        return
    for entity in targets:
        entity.layer = source.layer
        entity.color = source.color
    ctx.selection.clear()


def select_similar_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """SELECTSIMILAR (SIM): seleciona um objeto de referência e marca todos
    os outros do mesmo tipo no desenho. Simplificação documentada: compara só
    o tipo da entidade (Line com Line, Circle com Circle etc.) — o
    SELECTSIMILAR de verdade do AutoCAD tem critérios configuráveis
    (SELECTSIMILARMODE: layer, cor, linetype...), que o NewSIcad não expõe
    nesta versão."""
    if ctx.selection.ids:
        # Já tinha objeto(s) selecionado(s) antes de digitar o comando (o
        # fluxo natural: clica no objeto, depois digita SIM) — usa isso
        # direto como referência, sem pedir uma seleção nova. Bug real
        # reportado: SELECTSIMILAR "não funcionava" porque sempre limpava a
        # seleção atual e pedia pra selecionar de novo do zero.
        seed = ctx.selection.entities(ctx.document)
    else:
        seed = yield from _select_objects(ctx, "Select objects:")
    if not seed:
        return
    types = {type(entity) for entity in seed}
    matched = {entity.id for entity in ctx.document.all_entities() if type(entity) in types}
    ctx.selection.set(matched)
    yield Prompt(f"SELECTSIMILAR: {len(matched)} objeto(s) selecionado(s).", kind="info")


def laymch_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """LAYMCH (Match Layer): muda só a CAMADA dos objetos de destino pra
    igualar a de um objeto de origem — MATCHPROP também copia a cor; este
    aqui é o caso mais restrito (só layer), útil quando os objetos já têm a
    cor certa e só precisam ir pra outra camada."""
    source_list = yield from _select_objects(ctx, "Select object on destination layer:")
    if not source_list:
        return
    source = source_list[0]
    targets = yield from _select_objects(ctx, "Select object(s) to change:")
    if not targets:
        return
    for entity in targets:
        entity.layer = source.layer
    ctx.selection.clear()
    yield Prompt(f"LAYMCH: {len(targets)} objeto(s) movido(s) para a camada '{source.layer}'.", kind="info")


def layiso_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """LAYISO (Isolate): esconde toda camada que NÃO tenha nenhum dos
    objetos selecionados (mesmo espírito do LAYISO de verdade — "mostra só
    isso"). Lembra quais camadas escondeu em `document.isolated_layers` pra
    o LAYUNISO conseguir desfazer; chamar LAYISO de novo sobre outra seleção
    substitui o estado anterior (mesmo comportamento do AutoCAD: só o
    isolamento mais recente é desfazível)."""
    selected = yield from _select_objects(ctx, "Select objects on the layer(s) to isolate:")
    if not selected:
        return
    # Restaura qualquer isolamento anterior ANTES de calcular o novo. Sem
    # isso, chamar LAYISO de novo empilhava em cima do isolamento anterior
    # em vez de substituí-lo: uma camada já escondida pela primeira chamada
    # tinha `layer.visible` já False, então o filtro abaixo pulava ela — ela
    # nunca entrava na lista nova e ficava "órfã", e LAYUNISO só conseguia
    # recuperar o isolamento mais recente (bug real de auditoria,
    # 2026-08-22). Isso também é o que a própria docstring já prometia.
    if ctx.document.isolated_layers:
        for name in ctx.document.isolated_layers:
            layer = ctx.document.layers.get(name)
            if layer is not None:
                layer.visible = True

    keep = {entity.layer for entity in selected}
    hidden: list[str] = []
    for name, layer in ctx.document.layers.items():
        if name not in keep and layer.visible:
            layer.visible = False
            hidden.append(name)
    ctx.document.isolated_layers = hidden
    ctx.selection.clear()
    if hidden:
        yield Prompt(f"LAYISO: {len(hidden)} camada(s) escondida(s). Use LAYUNISO pra reverter.", kind="info")
    else:
        yield Prompt("LAYISO: nenhuma outra camada pra esconder.", kind="info")


def layuniso_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """LAYUNISO: desfaz o isolamento mais recente feito por LAYISO nesta
    sessão, tornando visíveis de novo as camadas que ele escondeu."""
    hidden = ctx.document.isolated_layers
    if not hidden:
        yield Prompt("LAYUNISO: nenhum isolamento de camada pra desfazer.", kind="info")
        return
    restored = 0
    for name in hidden:
        layer = ctx.document.layers.get(name)
        if layer is not None:
            layer.visible = True
            restored += 1
    ctx.document.isolated_layers = None
    yield Prompt(f"LAYUNISO: {restored} camada(s) tornada(s) visível(is) de novo.", kind="info")


def qselect_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """QSELECT: versão simplificada — filtra por TIPO de entidade (Line,
    Circle, Arc...), digitado por nome. O QSELECT de verdade do AutoCAD
    filtra por qualquer propriedade + operador (cor = vermelho, altura de
    texto > 5 etc.); esse filtro completo fica pra uma versão futura, com um
    diálogo dedicado."""
    types_list = ", ".join(sorted({cls.__name__ for cls in _QSELECT_TYPES.values()}))
    type_name = yield Prompt(f"Enter object type ({types_list}):", kind="text")
    if type_name is ENTER:
        return
    cls = _QSELECT_TYPES.get(str(type_name).strip().upper())
    if cls is None:
        yield Prompt(f"QSELECT: tipo desconhecido {type_name!r}.", kind="info")
        return
    matched = {entity.id for entity in ctx.document.all_entities() if isinstance(entity, cls)}
    ctx.selection.set(matched)
    yield Prompt(f"QSELECT: {len(matched)} objeto(s) selecionado(s).", kind="info")


def purge_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    """PURGE (PU): remove camadas e definições de bloco não usadas em lugar
    nenhum do desenho (nem no espaço do modelo, nem dentro de outro bloco).
    Camada "0" nunca é removida (igual ao AutoCAD); se a camada atual for
    removida, a camada atual volta a ser "0"."""
    removed_layers = ctx.document.purge_unused_layers()
    removed_blocks = ctx.document.purge_unused_blocks()

    if not removed_layers and not removed_blocks:
        yield Prompt("PURGE: nada para remover — nenhuma camada ou bloco não usado.", kind="info")
        return

    parts = []
    if removed_layers:
        parts.append(f"{len(removed_layers)} camada(s): {', '.join(removed_layers)}")
    if removed_blocks:
        parts.append(f"{len(removed_blocks)} bloco(s): {', '.join(removed_blocks)}")
    yield Prompt("PURGE removeu " + "; ".join(parts) + ".", kind="info")
