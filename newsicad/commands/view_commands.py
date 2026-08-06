"""Comandos de navegação (ZOOM, PAN). Diferente dos comandos de desenho e
modificação, estes não alteram o Document — manipulam a câmera do canvas via
`ctx.view` (ver newsicad/commands/context.py)."""

from __future__ import annotations

from typing import Generator

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import ENTER, Prompt
from newsicad.core.entities import Point


def zoom_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    first = yield Prompt(
        "Specify corner of window, enter a scale factor, or [All/Extents]:",
        kind="point",
        options=["All", "Extents"],
    )
    if first is ENTER:
        return

    if isinstance(first, str):
        if ctx.view is not None:
            ctx.view.zoom_extents()
        return

    second = yield Prompt("Specify opposite corner:", kind="point")
    if isinstance(second, Point) and ctx.view is not None:
        ctx.view.zoom_window(first, second)


def pan_command(ctx: CommandContext) -> Generator[Prompt, object, None]:
    yield Prompt(
        "Pressione e arraste o botão do meio do mouse para navegar (pan em "
        "tempo real via teclado ainda não está disponível).",
        kind="info",
    )
