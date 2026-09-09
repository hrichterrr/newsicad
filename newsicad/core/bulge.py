"""Arco dentro de polilinha ("bulge" do DXF).

Cada vértice de uma LWPOLYLINE carrega um número: o *bulge* do segmento que
começa nele. Zero é reta; qualquer outro valor é um arco, e o número é
`tan(θ/4)`, com θ o ângulo abrangido — positivo no sentido anti-horário,
negativo no horário. É assim que o AutoCAD desenha o Wi-Fi do keypad, o
"S" de um interruptor, os cantos redondos de um rack: uma polilinha só, com
arcos entre os vértices.

O NewSIcad lia só x e y (`get_points("xy")`) e jogava o resto fora: todo
arco virava a reta entre os dois vértices — o ícone do keypad da Casa Pau
Brasil aparecia como um "X" rabiscado (relato do Hamilton em 09/09/2026;
são 285 polilinhas com arco só dentro dos símbolos dessa planta). Este
módulo é a matemática compartilhada por leitura, gravação, tela,
transformações, EXPLODE e interseções, para ninguém reinventar o arco.
"""

from __future__ import annotations

import math

from newsicad.core.entities import Arc, Line, LWPolyline, Point

#: Abaixo disto o bulge é tratado como reta — evita raio astronômico.
_BULGE_ZERO = 1e-9


def bulge_to_arc(start: Point, end: Point, bulge: float) -> Arc:
    """Arco (sempre anti-horário de `start_angle` a `end_angle`, como o
    Arc do NewSIcad) equivalente ao bulge entre dois vértices. Mesma
    construção do `ezdxf.math.bulge_to_arc`: o ângulo abrangido é
    `4·atan(bulge)`, o raio sai da corda, e o centro fica a 90° − θ/2 da
    direção da corda, do lado que o sinal do bulge manda."""
    dx, dy = end.x - start.x, end.y - start.y
    corda = math.hypot(dx, dy)
    alpha = 2.0 * math.atan(bulge)  # metade do ângulo abrangido, com sinal
    raio = corda / 2.0 / math.sin(alpha)  # negativo quando o bulge é negativo
    direcao = math.atan2(dy, dx) + (math.pi / 2.0 - alpha)
    centro = Point(start.x + raio * math.cos(direcao), start.y + raio * math.sin(direcao))
    ang_inicio = math.atan2(start.y - centro.y, start.x - centro.x)
    ang_fim = math.atan2(end.y - centro.y, end.x - centro.x)
    if bulge < 0:
        # Horário de start para end = anti-horário de end para start.
        ang_inicio, ang_fim = ang_fim, ang_inicio
    return Arc(
        center=centro,
        radius=abs(raio),
        start_angle=ang_inicio % (2 * math.pi),
        end_angle=ang_fim % (2 * math.pi),
    )


def bulge_at(poly: LWPolyline, index: int) -> float:
    """Bulge do segmento que começa no vértice `index` (0 quando a polilinha
    não guarda bulge nenhum — o caso de toda polilinha desenhada aqui)."""
    bulges = poly.bulges
    if index < len(bulges):
        return float(bulges[index])
    return 0.0


def polyline_pieces(poly: LWPolyline) -> list[Line | Arc]:
    """A polilinha decomposta em peças Line/Arc, na ordem dos segmentos,
    respeitando os bulges. É o que a tela desenha, o TRIM cruza, o EXPLODE
    solta e o clique mede. As peças NÃO pertencem ao documento."""
    pts = poly.points
    if len(pts) < 2:
        return []
    pares = list(zip(range(len(pts) - 1), pts, pts[1:]))
    if poly.closed and len(pts) > 2:
        pares.append((len(pts) - 1, pts[-1], pts[0]))
    pecas: list[Line | Arc] = []
    for i, a, b in pares:
        bulge = bulge_at(poly, i)
        if abs(bulge) < _BULGE_ZERO or a.distance_to(b) < 1e-12:
            pecas.append(Line(start=a, end=b, layer=poly.layer, color=poly.color))
        else:
            arco = bulge_to_arc(a, b, bulge)
            arco.layer = poly.layer
            arco.color = poly.color
            pecas.append(arco)
    return pecas


def arc_midpoint(arc: Arc) -> Point:
    """Ponto do meio do arco (anti-horário de start a end)."""
    varredura = (arc.end_angle - arc.start_angle) % (2 * math.pi)
    meio = arc.start_angle + varredura / 2.0
    return Point(arc.center.x + arc.radius * math.cos(meio), arc.center.y + arc.radius * math.sin(meio))
