"""Parser de entrada de coordenadas no estilo AutoCAD.

Formatos suportados:
    "10,20"      -> ponto absoluto (x=10, y=20)
    "@10,20"     -> ponto relativo ao último ponto (dx=10, dy=20)
    "50<45"      -> ponto absoluto em coordenadas polares a partir da origem
                    (distância 50, ângulo 45° medido a partir do eixo X, anti-horário)
    "@50<45"     -> ponto relativo ao último ponto, polar (distância + ângulo)
    "50"         -> distância direta: usa o último ponto e a direção do cursor
"""

from __future__ import annotations

import math

from newsicad.core.entities import Point


class CoordParseError(ValueError):
    pass


def _to_radians(degrees: float) -> float:
    return math.radians(degrees)


def parse_coordinate(
    text: str,
    last_point: Point | None = None,
    cursor_point: Point | None = None,
) -> Point:
    """Converte a string digitada pelo usuário em um Point absoluto.

    `last_point` é o último ponto especificado no comando atual (necessário para
    entradas relativas `@` e para distância direta).
    `cursor_point` é a posição atual do mouse no desenho (necessário só para
    distância direta, ex.: digitar "50" e mover o mouse para indicar a direção).
    """
    raw = text.strip()
    if not raw:
        raise CoordParseError("Entrada vazia")

    relative = raw.startswith("@")
    body = raw[1:] if relative else raw

    if relative and last_point is None:
        raise CoordParseError("Coordenada relativa '@' exige um ponto anterior")

    if "<" in body:
        return _parse_polar(body, relative, last_point)

    if "," in body:
        return _parse_cartesian(body, relative, last_point)

    return _parse_direct_distance(body, last_point, cursor_point)


def _parse_cartesian(body: str, relative: bool, last_point: Point | None) -> Point:
    parts = body.split(",")
    if len(parts) != 2:
        raise CoordParseError(f"Coordenada cartesiana inválida: '{body}'")
    try:
        x, y = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise CoordParseError(f"Coordenada cartesiana inválida: '{body}'") from exc

    if relative:
        assert last_point is not None
        return Point(last_point.x + x, last_point.y + y)
    return Point(x, y)


def _parse_polar(body: str, relative: bool, last_point: Point | None) -> Point:
    parts = body.split("<")
    if len(parts) != 2:
        raise CoordParseError(f"Coordenada polar inválida: '{body}'")
    try:
        distance, angle_deg = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise CoordParseError(f"Coordenada polar inválida: '{body}'") from exc

    angle = _to_radians(angle_deg)
    dx = distance * math.cos(angle)
    dy = distance * math.sin(angle)

    origin = last_point if relative else Point(0.0, 0.0)
    assert origin is not None
    return Point(origin.x + dx, origin.y + dy)


def _parse_direct_distance(
    body: str, last_point: Point | None, cursor_point: Point | None
) -> Point:
    try:
        distance = float(body)
    except ValueError as exc:
        raise CoordParseError(f"Entrada inválida: '{body}'") from exc

    if last_point is None or cursor_point is None:
        raise CoordParseError(
            "Distância direta exige um ponto anterior e a posição do cursor"
        )

    angle = last_point.angle_to(cursor_point)
    return Point(
        last_point.x + distance * math.cos(angle),
        last_point.y + distance * math.sin(angle),
    )
