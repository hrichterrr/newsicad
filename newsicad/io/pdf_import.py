"""Importação de PDF (Insert > Import PDF...): extrai a geometria vetorial
(linhas, curvas, retângulos) e o texto de uma página do PDF como entidades
reais do NewSIcad — pra decalcar/editar por cima, em vez de só colar uma
imagem de fundo (isso já existe, é o IMAGEATTACH).

Usa PyMuPDF (`fitz`). Licença AGPL-3.0 — aceitável aqui porque o NewSIcad é
uso interno da New SI, não é revendido/distribuído a terceiros (decisão
tomada explicitamente com o Hamilton; se isso mudar no futuro, reavaliar).

Simplificação documentada: cada segmento de reta/curva do PDF vira uma
entidade independente (Line, ou vários Line tesselando uma curva de Bézier)
— não tenta reconstruir contornos conectados como uma única LWPolyline
fechada. Retângulos (o único caso "atômico" no modelo de path do PDF) viram
LWPolyline fechada diretamente. Texto rotacionado é importado na horizontal
(sem ler a direção do span) — outra simplificação de v1."""

from __future__ import annotations

import fitz

from newsicad.core.entities import Entity, Line, LWPolyline, Point, Text

_BEZIER_SEGMENTS = 16
_POINTS_TO_MM = 25.4 / 72.0  # PDF usa "points" (1/72 polegada); NewSIcad em mm


class PdfImportError(RuntimeError):
    pass


def pdf_page_count(path: str) -> int:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfImportError(f"Não foi possível abrir '{path}': {exc}") from exc
    count = doc.page_count
    doc.close()
    return count


def _to_point(pdf_point: fitz.Point, page_height: float, scale: float) -> Point:
    # PDF: eixo Y cresce pra baixo a partir do topo da página. CAD: Y pra
    # cima (mesma convenção do resto do NewSIcad) — precisa inverter.
    return Point(pdf_point.x * scale, (page_height - pdf_point.y) * scale)


def _bezier_to_lines(
    p0: fitz.Point, p1: fitz.Point, p2: fitz.Point, p3: fitz.Point,
    page_height: float, scale: float, layer: str,
) -> list[Line]:
    def eval_cubic(t: float) -> fitz.Point:
        mt = 1 - t
        x = mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x
        y = mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y
        return fitz.Point(x, y)

    pts = [_to_point(eval_cubic(i / _BEZIER_SEGMENTS), page_height, scale) for i in range(_BEZIER_SEGMENTS + 1)]
    return [Line(start=a, end=b, layer=layer) for a, b in zip(pts, pts[1:])]


def import_pdf_page(path: str, page_index: int, layer: str = "0") -> list[Entity]:
    """Extrai a página `page_index` (0-based) de `path` como uma lista de
    entidades (Line/LWPolyline/Text). Levanta PdfImportError se o arquivo
    não abrir ou a página não existir."""
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfImportError(f"Não foi possível abrir '{path}': {exc}") from exc

    page_count = doc.page_count
    if not (0 <= page_index < page_count):
        doc.close()
        raise PdfImportError(
            f"Página {page_index + 1} não existe (o PDF tem {page_count} página(s))."
        )

    page = doc[page_index]
    page_height = page.rect.height
    scale = _POINTS_TO_MM
    entities: list[Entity] = []

    for drawing in page.get_drawings():
        for item in drawing["items"]:
            kind = item[0]
            if kind == "l":
                _, p1, p2 = item
                entities.append(Line(
                    start=_to_point(p1, page_height, scale),
                    end=_to_point(p2, page_height, scale),
                    layer=layer,
                ))
            elif kind == "c":
                _, p0, p1, p2, p3 = item
                entities.extend(_bezier_to_lines(p0, p1, p2, p3, page_height, scale, layer))
            elif kind == "re":
                rect = item[1]
                corners = [
                    fitz.Point(rect.x0, rect.y0), fitz.Point(rect.x1, rect.y0),
                    fitz.Point(rect.x1, rect.y1), fitz.Point(rect.x0, rect.y1),
                ]
                points = [_to_point(c, page_height, scale) for c in corners]
                entities.append(LWPolyline(points=points, closed=True, layer=layer))
            elif kind == "qu":
                quad = item[1]
                corners = [quad.ul, quad.ur, quad.lr, quad.ll]
                points = [_to_point(c, page_height, scale) for c in corners]
                entities.append(LWPolyline(points=points, closed=True, layer=layer))

    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = bloco de texto (1 = imagem)
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                content = span.get("text", "").strip()
                if not content:
                    continue
                origin = fitz.Point(*span["origin"])
                entities.append(Text(
                    content=content,
                    insertion_point=_to_point(origin, page_height, scale),
                    height=max(span.get("size", 10.0) * scale, 0.5),
                    layer=layer,
                ))

    doc.close()
    return entities
