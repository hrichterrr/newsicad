"""Canvas 2D estilo AutoCAD: fundo escuro, grid adaptativo, crosshair curto
(tamanho configurável, igual ao CURSORSIZE do AutoCAD), zoom no scroll, pan no
botão do meio, preview ao vivo dos comandos de desenho, dynamic input
(distância/ângulo) perto do cursor, e seleção de objetos (clique único +
janela/crossing) para os comandos MODIFY."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QPageSize,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QStyleOptionGraphicsItem,
)

from newsicad.commands.interpreter import CommandInterpreter
from newsicad.core.document import Document
from newsicad.core.entities import (
    BYBLOCK,
    Arc,
    BlockReference,
    Circle,
    Dimension,
    Ellipse,
    Entity,
    Hatch,
    ImageReference,
    Line,
    LWPolyline,
    Point,
    PointEntity,
    Ray,
    Spline,
    Table,
    Text,
    XLine,
)
from newsicad.core.fields import resolve_field_text
from newsicad.core.geometry_ops import (
    as_intersectable_pieces,
    catmull_rom_bezier,
    dimension_geometry,
    entity_intersections,
    point_infinite_line_distance,
    point_ray_distance,
)

# Limite de profundidade para blocos aninhados (bloco cujo conteúdo referencia
# outro bloco) — evita recursão infinita se um desenho malformado tiver um
# ciclo (bloco A contém referência a B que contém referência a A).
_MAX_BLOCK_NESTING = 8

BACKGROUND_COLOR = "#1e1e1e"
GRID_MINOR_COLOR = "#3a3a3a"
GRID_AXIS_COLOR = "#5a5a5a"
CROSSHAIR_COLOR = "#d0d0d0"
# Tamanho do crosshair como % da viewport (mesma semântica da variável
# CURSORSIZE do AutoCAD, que por padrão é 5 — uma cruz curta perto do cursor,
# não cobrindo a tela inteira). Antes o crosshair sempre ia de borda a borda
# da viewport (100%); Albert (grupo de testers) pediu um cursor menor, "tipo
# o do AutoCad".
CROSSHAIR_SIZE_PERCENT = 5
#: Folga (px) somada à caixa repintada ao redor do cursor: cobre o texto
#: do dynamic input, que fica ao lado do cursor, e o marcador de OSNAP.
_CURSOR_REGION_PADDING_PX = 16
#: Janela (ms) em que os eventos de roda do mouse são acumulados num único
#: passo de zoom — ver CanvasView.wheelEvent.
_ZOOM_COALESCE_MS = 10
ENTITY_COLOR = "#e8e8e8"
# Chave arbitrária pra QGraphicsItem.setData/.data — QGraphicsItem não é um
# QObject (diferente da maioria dos outros widgets Qt), então não tem
# setProperty/property; setData(key, value) é o mecanismo de dado genérico
# equivalente. Usado só pra guardar a cor "de base" de cada item, restaurada
# ao desselecionar (ver CanvasView._restore_base_pen).
_BASE_COLOR_DATA_KEY = 0
#: Chave de dados onde cada item de PRIMEIRO NÍVEL guarda o id da entidade
#: que ele representa. Usada pelo pré-filtro de hit-test: a cena devolve
#: wrappers Python novos a cada consulta, então comparar por identidade de
#: objeto (ou `id()`) não funciona — o dado fica do lado do Qt e sobrevive.
_ENTITY_ID_DATA_KEY = 1
# Ordem de desenho: cada entidade do modelspace recebe zValue = (posição no
# dict do Document) x este passo, então a cena empilha na mesma ordem em que
# as entidades estão no documento (= ordem de criação, ou a ordem de desenho
# do AutoCAD ao abrir um .dxf — ver dxf_io.load_dxf). É isso que faz um
# WIPEOUT (Hatch.wipeout) cobrir só o que já existia quando ele foi criado
# — antes o WIPEOUT tinha zValue fixo 100 "por cima de tudo", e TODA hachura
# sólida era tratada como WIPEOUT. O passo é minúsculo pra nunca passar dos
# zValues das camadas de UI (dynamic input = 1000).
_DRAW_ORDER_Z_STEP = 1e-6
# Máximo de linhas do padrão geradas por hachura no canvas: acima disso o
# espaçamento é aumentado proporcionalmente (fidelidade visual, não exata).
# Um .dwg real de 2026-09-01 tem milhares de hachuras — sem limite, uma única
# hachura grande com espaçamento pequeno geraria centenas de milhares de
# segmentos e travaria o refresh.
_MAX_HATCH_LINES = 2000
PREVIEW_COLOR = "#4da3ff"
DYNAMIC_INPUT_COLOR = "#ffd479"
SELECTION_COLOR = "#ff9f1c"
WINDOW_SELECT_COLOR = "#4da3ff"
CROSSING_SELECT_COLOR = "#4caf50"
OSNAP_MARKER_COLOR = "#39ff14"

_GRID_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
_HIT_TOLERANCE_PX = 6.0
# Altura histórica do texto das cotas nativas (desenho em mm). Só um padrão:
# o valor usado de verdade é `Document.dim_style.text_height` (mesmo default,
# ver DimStyle em core/document.py), lido do .dxf ao abrir.
DIM_TEXT_HEIGHT = 2.0
HATCH_LINE_COLOR = "#5a7fa8"
_OSNAP_TOLERANCE_PX = 10.0
_OSNAP_MARKER_SIZE_PX = 9.0
_PICKBOX_SIZE_PX = 8.0
_POLAR_STEP_DEG = 15.0
_POLAR_TOLERANCE_DEG = 3.0
# XLine/Ray guardam ponto+ângulo (semântica "infinita" real, ver
# core/entities.py) — o canvas desenha um segmento bem comprido (dentro do
# sceneRect de ±100000, ver CanvasView.__init__) só pra fins de renderização;
# bbox/zoom-extents ignoram esse comprimento (ver _entity_bbox_scene).
_CONSTRUCTION_LINE_RENDER_LENGTH = 100000.0
_POINT_MARKER_SIZE_PX = 6.0

# Tamanhos de folha padrão pra Export PDF (série ISO 216, do menor A4 até o
# A0 usado em pranchas arquitetônicas de verdade) — nome exibido na UI -> id
# do Qt.
PDF_PAGE_SIZES: dict[str, QPageSize.PageSizeId] = {
    "A4": QPageSize.PageSizeId.A4,
    "A3": QPageSize.PageSizeId.A3,
    "A2": QPageSize.PageSizeId.A2,
    "A1": QPageSize.PageSizeId.A1,
    "A0": QPageSize.PageSizeId.A0,
}


def cad_to_scene(point: Point) -> QPointF:
    """Converte um ponto do desenho (Y para cima) em coordenadas de cena Qt (Y para baixo)."""
    return QPointF(point.x, -point.y)


def scene_to_cad(pt: QPointF) -> Point:
    return Point(pt.x(), -pt.y())


def _pick_grid_step(scale: float, min_px: float = 20.0) -> float:
    for step in _GRID_STEPS:
        if step * scale >= min_px:
            return step
    return _GRID_STEPS[-1]


def _entity_pen(color: str = ENTITY_COLOR) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidth(0)
    return pen


def _selected_pen() -> QPen:
    pen = QPen(QColor(SELECTION_COLOR))
    pen.setWidth(0)
    pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _rect_contains(outer: QRectF, inner: QRectF) -> bool:
    """Substitui QRectF.contains(QRectF): a versão do Qt retorna False para
    um retângulo interno com largura OU altura zero (ex.: a bounding box de
    uma linha perfeitamente horizontal/vertical) mesmo quando ele está
    geometricamente dentro — comum demais em CAD pra deixar passar."""
    return (
        inner.left() >= outer.left()
        and inner.right() <= outer.right()
        and inner.top() >= outer.top()
        and inner.bottom() <= outer.bottom()
    )


def _rect_intersects(a: QRectF, b: QRectF) -> bool:
    """Substitui QRectF.intersects(QRectF) pelo mesmo motivo de _rect_contains."""
    return not (a.right() < b.left() or a.left() > b.right() or a.bottom() < b.top() or a.top() > b.bottom())


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return p.distance_to(a)
    t = max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length_sq))
    proj = Point(a.x + t * dx, a.y + t * dy)
    return p.distance_to(proj)


def _polygon_segments(points: list[Point]) -> list[tuple[Point, Point]]:
    pairs = list(zip(points, points[1:]))
    if len(points) > 2:
        pairs.append((points[-1], points[0]))
    return pairs


def _point_in_polygon(p: Point, points: list[Point]) -> bool:
    inside = False
    n = len(points)
    for i in range(n):
        a = points[i]
        b = points[(i + 1) % n]
        crosses = (a.y > p.y) != (b.y > p.y)
        if crosses:
            x_at_y = (b.x - a.x) * (p.y - a.y) / ((b.y - a.y) or 1e-12) + a.x
            if p.x < x_at_y:
                inside = not inside
    return inside


# ---------------------------------------------------------------------- #
# Texto: fonte de referência, métricas reais e layout
# ---------------------------------------------------------------------- #
# A altura CAD de um texto NÃO é um tamanho de fonte em pontos. A fonte é
# sempre criada num tamanho fixo de referência em pixels (grande o bastante
# pra métricas estáveis) e o item é ESCALADO pra que a altura de caixa-alta
# (capHeight) da tinta seja exatamente `Text.height` em unidades de desenho
# — razão tinta/altura medida em 1.03 (Arial/Tahoma) de h=2.5 até h=0.001.
# Antes, `font.setPointSizeF(height)` tratava 0.18 m como 0.18 pt: no
# Windows (GDI/DirectWrite) uma fonte com menos de 1 px não pinta NADA e o
# boundingRect fica 0x0 (não seleciona, não entra no zoom extents); de 0.5 a
# 1 pt vira 1 px; e em mm (1.8 pt) o hinting quebrava os avanços ("LEG
# ENDA"). Numa planta em metros isso deixava 84-88% dos textos invisíveis
# (achado text-invisivel-windows-pointsize, WP-B 2026-09). A plataforma
# offscreen (onde a suíte roda) e o macOS clampam em ~1 px e escalam, por
# isso passou despercebido nos testes.
_TEXT_REF_PX = 100
# Espaçamento simples entre linhas de MTEXT no AutoCAD = 5/3 da altura.
_TEXT_LINE_PITCH = 5.0 / 3.0
# Fontes .shx (romans/txt/simplex/isocp...) são fontes de traço do próprio
# AutoCAD, nunca instaladas no sistema. O Qt cai então na fonte padrão da
# plataforma (Tahoma no Windows), 30-50% mais larga que o romans.shx —
# textos que cabiam numa célula de legenda passam a invadir a vizinha.
# Substituímos por uma TTF garantida e "estreitada" (stretch 85%).
_SHX_STRETCH = 85
_SHX_FAMILIES = frozenset({
    "txt", "simplex", "romans", "romand", "romanc", "romant", "italic", "italicc",
    "italict", "monotxt", "complex", "scripts", "scriptc", "gothice", "gothicg",
    "gothici", "greeks", "greekc", "isocp", "isocp2", "isocp3", "isocpeur",
    "isocpeui", "isoct", "isoct2", "isoct3", "iso", "cibt", "cobt", "rom", "romb",
    "romi", "sas", "sasb", "sasbo", "saso", "txtb", "stylu", "standard",
})
_FALLBACK_FAMILIES = ("Arial", "Liberation Sans", "Helvetica", "DejaVu Sans")
# "Menlo" é o padrão histórico do NewSIcad (fonte mono do macOS): no
# Windows preferimos outra mono instalada a deixar o Qt escolher Tahoma.
_MONO_FAMILIES = ("Menlo", "Consolas", "DejaVu Sans Mono", "Courier New")
_installed_families: dict[str, str] | None = None
_font_cache: dict[tuple[str, str, int], QFont] = {}
_metrics_cache: dict[str, QFontMetricsF] = {}


def _installed() -> dict[str, str]:
    """Famílias instaladas (minúsculas -> nome real), lidas uma única vez
    do QFontDatabase (precisa de QApplication viva — só é chamada de dentro
    do canvas). Vazio na plataforma offscreen desta máquina: tudo cai na
    fonte padrão do Qt, que ainda pinta e mede."""
    global _installed_families
    if _installed_families is None:
        try:
            _installed_families = {f.lower(): f for f in QFontDatabase.families()}
        except Exception:  # sem QApplication: não cacheia, tenta de novo depois
            return {}
    return _installed_families


def _first_installed(candidates: tuple[str, ...]) -> str | None:
    installed = _installed()
    for name in candidates:
        real = installed.get(name.lower())
        if real:
            return real
    return None


def resolve_font_family(family: str, font_file: str = "") -> tuple[str, int]:
    """(família de fonte instalada, stretch base em %) pra um STYLE do
    desenho — tabela de substituição SHX/desconhecida do achado
    fontes-shx-fallback-e-metricas: TTF instalada (arial.ttf -> Arial) é
    mantida; .shx ou nome de fonte SHX conhecido vira a primeira de
    `_FALLBACK_FAMILIES` com `_SHX_STRETCH`; "Menlo" (padrão do NewSIcad)
    tenta as monoespaçadas; qualquer outra desconhecida vira Arial (ou a
    fonte padrão do Qt se nem Arial existir)."""
    key = (family or "").strip().lower()
    file_key = (font_file or "").strip().lower()
    installed = _installed()
    if key in installed and not file_key.endswith(".shx"):
        return installed[key], 100
    if file_key.endswith(".shx") or key in _SHX_FAMILIES:
        return _first_installed(_FALLBACK_FAMILIES) or QFont().family(), _SHX_STRETCH
    if key == "menlo":
        return _first_installed(_MONO_FAMILIES) or _first_installed(_FALLBACK_FAMILIES) or QFont().family(), 100
    return _first_installed(_FALLBACK_FAMILIES) or QFont().family(), 100


def text_font(style, width_factor: float = 1.0) -> QFont:
    """QFont de referência (`_TEXT_REF_PX` px) pro `TextStyle` dado (None =
    padrão "Menlo"), com o fator de largura do estilo × o da entidade
    aplicado via `setStretch`. Cacheada por (família, arquivo, stretch)."""
    family = style.font_family if style is not None else "Menlo"
    font_file = getattr(style, "font_file", "") if style is not None else ""
    style_width = getattr(style, "width", 1.0) if style is not None else 1.0
    real, base_stretch = resolve_font_family(family, font_file)
    stretch = int(round(base_stretch * (style_width or 1.0) * (width_factor or 1.0)))
    stretch = max(1, min(4000, stretch))
    cache_key = (real, font_file, stretch)
    cached = _font_cache.get(cache_key)
    if cached is not None:
        return QFont(cached)
    font = QFont(real)
    font.setPixelSize(_TEXT_REF_PX)
    font.setStretch(stretch)
    # Contornos sem hinting: o glifo é escalado depois, então qualquer
    # arredondamento a pixel inteiro da fonte de referência viraria erro.
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    _font_cache[cache_key] = QFont(font)
    return font


def _metrics(font: QFont) -> QFontMetricsF:
    key = font.key()
    metrics = _metrics_cache.get(key)
    if metrics is None:
        metrics = QFontMetricsF(font)
        _metrics_cache[key] = metrics
    return metrics


@dataclass
class TextLayout:
    """Resultado de `text_layout`: linhas já quebradas e as medidas REAIS do
    bloco de texto em unidades CAD. A caixa local tem origem no canto
    superior-esquerdo, `width` x `height`; o topo é a linha de caixa-alta da
    primeira linha (baseline + `cap`), a base é a última baseline menos
    `descent`; baselines a cada `pitch`."""

    font: QFont
    lines: list[str]
    scale: float  # unidades CAD por px da fonte de referência
    line_widths: list[float]
    width: float
    height: float
    pitch: float
    cap: float
    descent: float

    def baseline_offset(self, index: int) -> float:
        """Distância (CAD, positiva pra baixo) do topo da caixa até a
        baseline da linha `index`."""
        return self.cap + index * self.pitch


def _wrap_paragraph(paragraph: str, metrics: QFontMetricsF, max_px: float) -> list[str]:
    words = paragraph.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and metrics.horizontalAdvance(candidate) > max_px:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def text_layout(entity: Text, font: QFont) -> TextLayout:
    """Mede o texto com as métricas reais da fonte de referência e devolve
    o layout em unidades CAD (ver `TextLayout`). Com `entity.width` > 0
    (caixa do MTEXT) cada parágrafo é quebrado por palavras nessa largura
    ANTES de justificar — uma palavra maior que a caixa fica sozinha na
    linha, como no AutoCAD."""
    metrics = _metrics(font)
    cap_px = max(metrics.capHeight(), 1e-6)
    scale = max(entity.height, 0.0) / cap_px
    paragraphs = entity.content.split("\n")
    if entity.width > 0 and scale > 0:
        lines: list[str] = []
        for paragraph in paragraphs:
            lines.extend(_wrap_paragraph(paragraph, metrics, entity.width / scale))
    else:
        lines = paragraphs
    widths = [metrics.horizontalAdvance(line) * scale for line in lines]
    pitch = _TEXT_LINE_PITCH * entity.height * (entity.line_spacing_factor or 1.0)
    descent = metrics.descent() * scale
    width = max(widths) if widths else 0.0
    height = (len(lines) - 1) * pitch + entity.height + descent
    return TextLayout(
        font=font,
        lines=lines,
        scale=scale,
        line_widths=widths,
        width=width,
        height=height,
        pitch=pitch,
        cap=entity.height,
        descent=descent,
    )


def _text_local_extent(entity: Text, layout: TextLayout) -> tuple[float, float]:
    """Retângulo local (largura, altura) do texto, em unidades CAD, ancorado
    no canto superior-esquerdo (ver `_text_top_left_world`) — medido com as
    métricas reais da fonte, não mais a estimativa 0.6·h por caractere."""
    return max(layout.width, 1e-6), max(layout.height, 1e-6)


_JUSTIFY_COL_FRAC = {"L": 0.0, "C": 0.5, "R": 1.0}
_JUSTIFY_ROW_FRAC = {"T": 0.0, "M": 0.5, "B": 1.0}


def _text_anchor_local(entity: Text, layout: TextLayout) -> tuple[float, float]:
    """Posição do `insertion_point` dentro da caixa local do texto (origem
    no canto superior-esquerdo, Y pra cima, sem rotação), segundo
    `entity.justify`. Linha "B?" = baseline da última linha de texto
    (convenção do TEXT/ATTRIB do DXF — ver Text em core/entities.py), não a
    borda inferior da caixa."""
    width, height = _text_local_extent(entity, layout)
    row = entity.justify[0] if entity.justify else "T"
    col = entity.justify[1] if len(entity.justify) > 1 else "L"
    jx = width * _JUSTIFY_COL_FRAC.get(col, 0.0)
    if row == "B":
        jy = -layout.baseline_offset(max(len(layout.lines) - 1, 0))
    else:
        jy = -height * _JUSTIFY_ROW_FRAC.get(row, 0.0)
    return jx, jy


def _text_top_left_world(entity: Text, layout: TextLayout) -> Point:
    """Canto superior-esquerdo real do bloco de texto em coordenadas CAD,
    considerando `entity.justify` (ver TEXT_JUSTIFY_OPTIONS em
    core/entities.py) — para "TL" (padrão) é o próprio `insertion_point`;
    para as outras 8 opções, `insertion_point` ancora um ponto diferente do
    retângulo do texto (ex.: "MC" = centro, "BL" = baseline), então o canto
    superior-esquerdo precisa ser deslocado (e rotacionado) a partir dele
    antes de desenhar/hit-testar — todo o resto do código (_create_item,
    _distance_to_entity, _entity_bbox_scene) trata esse canto como origem
    local."""
    jx, jy = _text_anchor_local(entity, layout)
    dx, dy = -jx, -jy
    cos_a, sin_a = math.cos(entity.rotation), math.sin(entity.rotation)
    return Point(
        entity.insertion_point.x + dx * cos_a - dy * sin_a,
        entity.insertion_point.y + dx * sin_a + dy * cos_a,
    )


def _scaled_text_path(font: QFont, text: str, scale: float) -> tuple[QPainterPath, float]:
    """(path do texto com a baseline em y=0 e o início em x=0, já escalado
    pra unidades CAD de cena; largura em unidades CAD) — usado pelo texto da
    cota e das células de tabela, que não passam por `TextLayout`."""
    path = QPainterPath()
    path.addText(0.0, 0.0, font, text)
    transform = QTransform()
    transform.scale(scale, scale)
    return transform.map(path), _metrics(font).horizontalAdvance(text) * scale


#: Abaixo deste tamanho em PIXELS na tela, uma hachura é pintada como um
#: preenchimento chapado translúcido em vez de linha a linha: o padrão não é
#: distinguível nesse zoom e o custo de desenhar centenas de segmentos por
#: hachura, a cada repintura, é o que travava o mover do mouse numa planta
#: real (medido em 2026-09-03 na planta Ana Beatriz: 97 mil `drawLine` em 40
#: movimentos de mouse, 40 ms por movimento).
_HATCH_LOD_MIN_PIXELS = 24.0


class _HatchItem(QGraphicsPathItem):
    """QGraphicsPathItem cujo path é o contorno da hachura; o preenchimento
    (linhas diagonais paralelas) é desenhado por cima, recortado ao contorno
    via QPainter.setClipPath — mais simples e robusto do que tentar recortar
    cada segmento de linha manualmente contra o polígono.

    As linhas são guardadas num ÚNICO `QPainterPath` (`_lines_path`), não numa
    lista de pares de pontos: um `drawPath` por repintura no lugar de um
    `drawLine` por segmento. Some com a maior parte do custo por repintura sem
    mudar nada do que aparece na tela."""

    def __init__(self, boundary_path: QPainterPath) -> None:
        super().__init__(boundary_path)
        self._hatch_lines: list[tuple[QPointF, QPointF]] = []
        self._lines_path: QPainterPath | None = None

    def set_hatch_lines(self, lines: list[tuple[QPointF, QPointF]]) -> None:
        self._hatch_lines = lines
        if lines:
            path = QPainterPath()
            for a, b in lines:
                path.moveTo(a)
                path.lineTo(b)
            self._lines_path = path
        else:
            self._lines_path = None

    def paint(self, painter, option, widget=None) -> None:  # noqa: D401
        super().paint(painter, option, widget)
        if self._lines_path is None:
            return
        # Tamanho aparente da hachura na tela: `option.levelOfDetailFromTransform`
        # é a escala do mundo pra pixels na transformação atual da view.
        try:
            lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
        except Exception:  # pragma: no cover - salvaguarda de plataforma
            lod = 1.0
        rect = self.boundingRect()
        on_screen = max(rect.width(), rect.height()) * lod
        painter.save()
        painter.setClipPath(self.path())
        if on_screen < _HATCH_LOD_MIN_PIXELS:
            # Longe demais pra distinguir o padrão: chapa translúcida, uma
            # operação só (mesma leitura visual, custo constante).
            color = QColor(HATCH_LINE_COLOR)
            color.setAlpha(90)
            painter.fillPath(self.path(), QBrush(color))
        else:
            pen = QPen(QColor(HATCH_LINE_COLOR))
            pen.setWidth(0)
            painter.setPen(pen)
            painter.drawPath(self._lines_path)
        painter.restore()


def _hatch_fill_lines(boundary_scene: list[QPointF], angle_rad: float, spacing_world: float) -> list[tuple[QPointF, QPointF]]:
    """Gera segmentos de linha (em coords de cena, que são as mesmas unidades
    "mundo" usadas pelo resto do canvas, só com Y invertido) cobrindo a
    bounding box do contorno, num padrão diagonal com o ângulo/espaçamento
    pedidos. O clipping ao contorno de verdade acontece no paint() via
    setClipPath — essas linhas não precisam ser exatas, só cobrir a área."""
    if len(boundary_scene) < 3:
        return []
    xs = [pt.x() for pt in boundary_scene]
    ys = [pt.y() for pt in boundary_scene]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    diag = math.hypot(max_x - min_x, max_y - min_y) or 1.0
    spacing_scene = max(spacing_world, 1e-3)

    # ângulo em coords de cena (Y invertido em relação ao CAD)
    scene_angle = -angle_rad
    ux, uy = math.cos(scene_angle), math.sin(scene_angle)
    # direção perpendicular, usada para varrer paralelas cobrindo a diagonal
    px, py = -uy, ux

    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    lines: list[tuple[QPointF, QPointF]] = []
    n_steps = int(diag / spacing_scene) + 2
    if 2 * n_steps + 1 > _MAX_HATCH_LINES:
        # Contorno grande demais pro espaçamento pedido: abre o espaçamento
        # até caber em _MAX_HATCH_LINES (ver comentário da constante).
        n_steps = _MAX_HATCH_LINES // 2
        spacing_scene = diag / max(n_steps - 2, 1)
    for i in range(-n_steps, n_steps + 1):
        ox, oy = cx + px * spacing_scene * i, cy + py * spacing_scene * i
        a = QPointF(ox - ux * diag, oy - uy * diag)
        b = QPointF(ox + ux * diag, oy + uy * diag)
        lines.append((a, b))
    return lines


def _hatch_boundary_path(entity: Hatch) -> tuple[QPainterPath, list[QPointF]]:
    """QPainterPath com TODOS os anéis da hachura (`Hatch.fill_paths()`:
    externo + furos/ilhas) e regra even-odd, pra que o preenchimento — sólido
    ou por linhas recortadas via setClipPath — deixe os furos vazios.
    Devolve também os pontos de cena do contorno externo (base das linhas do
    padrão)."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    outer_scene: list[QPointF] = []
    for index, ring in enumerate(entity.fill_paths()):
        pts_scene = [cad_to_scene(p) for p in ring]
        if index == 0:
            outer_scene = pts_scene
        if not pts_scene:
            continue
        path.moveTo(pts_scene[0])
        for pt in pts_scene[1:]:
            path.lineTo(pt)
        path.closeSubpath()
    return path, outer_scene


class _ClippedGroup(QGraphicsItemGroup):
    """QGraphicsItemGroup cujo shape()/boundingRect() é um contorno FIXO (não
    a união dos filhos, como o QGraphicsItemGroup normal calcularia) —
    combinado com o flag `ItemClipsChildrenToShape`, isso faz os filhos serem
    literalmente recortados na tela fora desse contorno. Usado pelo comando
    CLIP/XCLIP (ver `BlockReference.clip_boundary`/`ImageReference.
    clip_boundary` em core/entities.py e `_create_block_reference_item`/
    `_create_image_item` abaixo)."""

    def __init__(self, clip_path: QPainterPath) -> None:
        super().__init__()
        self._clip_path = clip_path
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

    def boundingRect(self) -> QRectF:
        return self._clip_path.boundingRect()

    def shape(self) -> QPainterPath:
        return self._clip_path


class CanvasView(QGraphicsView):
    mouse_moved = Signal(object)  # emite Point (coordenadas CAD)

    def __init__(self, document: Document, interpreter: CommandInterpreter, parent=None):
        super().__init__(parent)
        self.document = document
        self.interpreter = interpreter

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # `DontSavePainterState`: não salvar/restaurar o estado do QPainter a
        # cada item (o canvas configura a caneta em todo paint, não depende do
        # estado herdado). `DontAdjustForAntialiasing`: não inflar a área
        # repintada de cada item por causa do antialias. `SmartViewportUpdate`:
        # o Qt decide entre repintar as regiões sujas ou a viewport toda,
        # conforme o que sai mais barato. Juntos: zoom de 91 ms para 38 ms na
        # planta NEWSI-ANA BEATRIZ-R01 (medição de 2026-09-03).
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontSavePainterState
            | QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        # Zoom com a roda: um repaint por rajada, não um por evento — ver
        # `wheelEvent`.
        self._pending_zoom_factor = 1.0
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(_ZOOM_COALESCE_MS)
        self._zoom_timer.timeout.connect(self._apply_pending_zoom)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setSceneRect(-100000, -100000, 200000, 200000)
        self.scale(20, 20)

        self._entity_items: dict[str, QGraphicsItem] = {}
        #: ids cujo item está com a caneta de seleção aplicada agora —
        #: ver refresh_selection_highlight.
        self._highlighted_ids: set[str] = set()
        #: id da entidade -> "impressão digital" do estado com que o item
        #: gráfico dela foi criado (ver refresh_entities) — permite pular a
        #: recriação de itens cujas entidades não mudaram desde o último
        #: refresh.
        self._entity_fingerprints: dict[str, str] = {}
        #: Cache ENTRE refreshes da impressão digital das definições de
        #: bloco (nome -> digest) — elas são o grosso do custo num .dwg real
        #: (milhares de entidades dentro das definições) e só mudam via
        #: define_block/PURGE, que bumpam Document.block_defs_revision;
        #: quando a revisão muda, o cache inteiro é descartado.
        self._def_fp_cache: dict[str, str] = {}
        self._def_fp_cache_revision: int = -1
        #: Última posição do cursor no viewport (px) — usada pra invalidar
        #: só a região do crosshair/pickbox no mouseMoveEvent em vez do
        #: viewport inteiro (ver comentário lá).
        self._last_cursor_viewport_pos = None
        self._mouse_scene_pos: QPointF | None = None
        self._preview_path: QPainterPath | None = None
        self._panning = False
        self._pan_start = QPointF()

        self._selection_drag_start_scene: QPointF | None = None
        self._selection_drag_current_scene: QPointF | None = None

        self.grid_visible = True
        self.snap_enabled = False
        self.ortho_enabled = False
        self.dynamic_input_enabled = True
        self.snap_spacing = 10.0
        self.osnap_enabled = False
        self.polar_enabled = False
        self._osnap_marker: tuple[Point, str] | None = None

        self._dyn_text = QGraphicsSimpleTextItem()
        self._dyn_text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self._dyn_text.setBrush(QBrush(QColor(DYNAMIC_INPUT_COLOR)))
        self._dyn_text.setFont(QFont("Menlo", 10))
        self._dyn_text.setZValue(1000)
        self._dyn_text.hide()
        self._scene.addItem(self._dyn_text)

        # callbacks ligados pela MainWindow
        self.on_point: Callable[[Point], None] | None = None
        self.on_enter: Callable[[], None] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.on_delete: Callable[[], None] | None = None
        self.on_selection_changed: Callable[[], None] | None = None
        self.on_context_menu: Callable[[], None] | None = None

    # ------------------------------------------------------------------ #
    # sincronização com o Document
    # ------------------------------------------------------------------ #
    def refresh_entities(self) -> None:
        doc_ids = set(self.document.entities.keys())
        existing_ids = set(self._entity_items.keys())

        for stale_id in existing_ids - doc_ids:
            item = self._entity_items.pop(stale_id)
            self._entity_fingerprints.pop(stale_id, None)
            self._scene.removeItem(item)

        # MOVE/ROTATE/SCALE mutam a entidade em memória sem trocar de id —
        # não dá pra saber por diff de ids se a geometria mudou. A versão
        # antiga resolvia isso recriando TODOS os itens a cada chamada, com
        # um comentário de "custo desprezível" que a medição desmentiu: num
        # .dwg real de arquiteto (~7 mil entidades → ~35 mil QGraphicsItems),
        # cada refresh custava 6-8s, e `_after_interpreter_step` chama isto
        # a CADA passo de comando (auditoria 2026-08-28 — a "lentidão"
        # reportada pelos testers). Agora cada entidade ganha uma "impressão
        # digital" barata (repr do dataclass + cor efetiva + definição do
        # bloco, se houver) e o item só é recriado quando ela muda — um
        # refresh sem mudanças vira só o custo de calcular os reprs.
        if self._def_fp_cache_revision != self.document.block_defs_revision:
            self._def_fp_cache.clear()
            self._def_fp_cache_revision = self.document.block_defs_revision

        def definition_fp(block_name: str, _visiting: frozenset[str] = frozenset()) -> str:
            if block_name in _visiting:
                return ""  # definição cíclica: corta, igual ao render faz
            cached = self._def_fp_cache.get(block_name)
            if cached is not None:
                return cached
            parts: list[str] = []
            for child in self.document.block_definitions.get(block_name, []):
                parts.append(repr(child))
                if isinstance(child, BlockReference):
                    parts.append(definition_fp(child.block_name, _visiting | {block_name}))
            # Guarda só um resumo (hash) — a string completa de uma definição
            # grande (milhares de entidades) seria concatenada na impressão
            # digital de CADA instância do bloco, custo real medido num .dwg
            # de arquiteto. O cache vive ENTRE refreshes; qualquer mudança de
            # definição (define_block/PURGE bumpam block_defs_revision)
            # descarta ele inteiro logo acima.
            fp = f"{hash(chr(0).join(parts)):x}"
            self._def_fp_cache[block_name] = fp
            return fp

        # Mudança em qualquer camada (cor/visibilidade/trava) pode afetar a
        # cor dos FILHOS de um bloco (resolvida na criação do item), então
        # entra na impressão digital de tudo — na prática, mexer no painel
        # de camadas volta a reconstruir tudo (raro e era o comportamento
        # antigo de qualquer forma).
        layers_fp = f"{hash(chr(0).join(f'{la.name}|{la.color}|{la.visible}|{la.locked}' for la in self.document.layers.values())):x}"

        # Percorre na ORDEM do dict (ordem de criação / ordem de desenho do
        # arquivo), não num set: a posição vira o zValue do item (ver
        # _DRAW_ORDER_Z_STEP), então a cena empilha igual ao documento.
        for index, (entity_id, entity) in enumerate(self.document.entities.items()):
            if isinstance(entity, Text) and entity.field_type:
                # FIELD (comando FIELD): recalcula o valor vivo a cada
                # refresh, ANTES da impressão digital ser calculada (o
                # conteúdo novo entra no repr) e antes de qualquer código
                # ler `entity.content` — hit-test/bbox/render usam esse
                # mesmo atributo (ver `_text_top_left_world`).
                entity.content = resolve_field_text(entity, self.document)
            if not self.document.is_layer_visible(entity):
                # Camada desligada no painel de camadas: a entidade some do
                # canvas (não só fica "acinzentada") e também fica de fora
                # de hit-test/seleção/zoom-extents — ver os outros métodos
                # que checam `is_layer_visible`.
                old_item = self._entity_items.pop(entity_id, None)
                if old_item is not None:
                    self._scene.removeItem(old_item)
                self._entity_fingerprints.pop(entity_id, None)
                continue

            fingerprint = f"{entity!r}\x00{self._effective_color(entity)}\x00{layers_fp}"
            if isinstance(entity, BlockReference):
                fingerprint += "\x00" + definition_fp(entity.block_name)
            z_value = index * _DRAW_ORDER_Z_STEP
            if (
                self._entity_fingerprints.get(entity_id) == fingerprint
                and entity_id in self._entity_items
            ):
                self._entity_items[entity_id].setZValue(z_value)
                continue

            old_item = self._entity_items.pop(entity_id, None)
            if old_item is not None:
                self._scene.removeItem(old_item)
            item = self._create_item(entity)
            item.setZValue(z_value)
            item.setData(_ENTITY_ID_DATA_KEY, entity_id)
            self._scene.addItem(item)
            self._entity_items[entity_id] = item
            self._entity_fingerprints[entity_id] = fingerprint

        self.refresh_selection_highlight(changed_only=False)

    def _effective_color(self, entity: Entity, inherited: tuple[str, str] | None = None) -> str:
        """Cor de verdade com que a entidade deve ser desenhada — regra do
        AutoCAD, inclusive dentro de blocos:

        - cor própria ("#RRGGBB") -> ela mesma;
        - `BYBLOCK` (cor 0 do DXF) -> a cor efetiva do INSERT que a contém
          (`inherited[0]`); fora de um bloco, cai na cor da camada;
        - ByLayer (`None`) na camada "0" dentro de um bloco -> a cor da
          CAMADA do INSERT (`inherited[1]`, já resolvida pra blocos
          aninhados) — é assim que a biblioteca de símbolos da New SI muda
          de cor conforme a camada em que o ícone é inserido;
        - ByLayer nas demais camadas -> a cor da própria camada;
        - `ENTITY_COLOR` só como último recurso (camada não encontrada).

        `inherited` = (cor efetiva do INSERT, camada efetiva do INSERT) e só
        é passado por `_create_block_reference_item`. Usado tanto na criação
        do item (`_create_item`) quanto ao restaurar a cor de base ao
        desselecionar (`_restore_base_pen`) — mesma fonte de verdade nos dois
        lugares, pra nunca divergir. Antes disso, BYBLOCK era descartado na
        leitura e filhos na camada "0" saíam na cor da camada 0 (branco): o
        corpo de todo ícone de rack/legenda dos .dwg reais abria branco."""
        if entity.color and entity.color != BYBLOCK:
            return entity.color
        layer_name = entity.layer
        if inherited is not None:
            if entity.color == BYBLOCK:
                return inherited[0]
            if layer_name == "0":
                layer_name = inherited[1]
        layer = self.document.layers.get(layer_name)
        return layer.color if layer is not None else ENTITY_COLOR

    def _block_child_visible(self, child: Entity, inherited_layer: str) -> bool:
        """Visibilidade de um filho de bloco: na camada "0" ele segue a camada
        (efetiva) do INSERT; em outra camada, some se ela estiver desligada
        — igual ao AutoCAD."""
        layer_name = inherited_layer if child.layer == "0" else child.layer
        layer = self.document.layers.get(layer_name)
        return layer is None or layer.visible

    def refresh_selection_highlight(self, changed_only: bool = True) -> None:
        """Aplica/remove a caneta de destaque nos itens selecionados.

        `changed_only` (padrão) toca apenas os ids que ENTRARAM ou SAÍRAM da
        seleção desde a última chamada — antes disso todo clique varria os
        itens do desenho inteiro, descendo em cada bloco, o que custava ~0,6 s
        por clique numa planta real (medição de 2026-09-03). Passe False
        depois de recriar itens (refresh_entities), quando o que está na tela
        não corresponde mais ao que foi destacado antes."""
        selected_ids = set(self.interpreter.context.selection.ids)
        if changed_only:
            to_select = selected_ids - self._highlighted_ids
            to_restore = self._highlighted_ids - selected_ids
        else:
            to_select = selected_ids
            to_restore = set(self._entity_items) - selected_ids
        for entity_id in to_select:
            item = self._entity_items.get(entity_id)
            if item is not None:
                self._apply_pen(item, _selected_pen())
        for entity_id in to_restore:
            item = self._entity_items.get(entity_id)
            if item is not None:
                self._restore_base_pen(item)
        self._highlighted_ids = selected_ids & set(self._entity_items)

    def _apply_pen(self, item: QGraphicsItem, pen: QPen) -> None:
        """`QGraphicsItemGroup` (usado por BlockReference) e
        `QGraphicsPixmapItem` (usado por ImageReference) não têm setPen —
        propaga pra baixo nos filhos do grupo, ignora silenciosamente pra
        itens de imagem (destaque de seleção de imagem fica só um "sem
        efeito visual" nesta versão, ver README)."""
        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                self._apply_pen(child, pen)
        elif hasattr(item, "setPen"):
            item.setPen(pen)

    def _restore_base_pen(self, item: QGraphicsItem) -> None:
        """Contraparte de `_apply_pen` pra desselecionar: cada item guarda a
        própria cor "de base" (`baseColor`, setada em `_create_item`) como
        propriedade Qt no momento em que foi criado — precisa ser por item
        individual (não um pen único pro grupo inteiro) porque um
        BlockReference pode ter filhos em camadas/cores diferentes entre si."""
        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                self._restore_base_pen(child)
        elif hasattr(item, "setPen"):
            color = item.data(_BASE_COLOR_DATA_KEY)
            item.setPen(_entity_pen(color if color else ENTITY_COLOR))

    def _create_item(self, entity: Entity, color: str | None = None) -> QGraphicsItem:
        """QGraphicsItem de uma entidade. `color` = cor efetiva já resolvida
        (passada por `_create_block_reference_item` pros filhos de bloco, que
        herdam do INSERT); `None` = resolve pela regra de `_effective_color`
        como entidade de topo."""
        if color is None:
            color = self._effective_color(entity)

        if isinstance(entity, Line):
            p1 = cad_to_scene(entity.start)
            p2 = cad_to_scene(entity.end)
            item = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Circle) and entity.inner_radius > 1e-9:
            # DONUT: anel preenchido — even-odd fill entre o círculo externo
            # e o interno (ver Circle.inner_radius em core/entities.py).
            c = cad_to_scene(entity.center)
            path = QPainterPath()
            path.addEllipse(c, entity.radius, entity.radius)
            path.addEllipse(c, entity.inner_radius, entity.inner_radius)
            path.setFillRule(Qt.FillRule.OddEvenFill)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setBrush(QBrush(QColor(color)))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Circle):
            c = cad_to_scene(entity.center)
            r = entity.radius
            item = QGraphicsEllipseItem(c.x() - r, c.y() - r, 2 * r, 2 * r)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Arc):
            c = cad_to_scene(entity.center)
            r = entity.radius
            start_deg = -math.degrees(entity.start_angle)
            sweep_world_deg = math.degrees((entity.end_angle - entity.start_angle) % (2 * math.pi))
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            path = QPainterPath()
            path.arcMoveTo(rect, start_deg)
            path.arcTo(rect, start_deg, -sweep_world_deg)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Ellipse):
            c = cad_to_scene(entity.center)
            path = QPainterPath()
            path.addEllipse(QPointF(0, 0), entity.radius_major, entity.radius_minor)
            transform = QTransform()
            transform.translate(c.x(), c.y())
            transform.rotate(-math.degrees(entity.rotation))
            item = QGraphicsPathItem(transform.map(path))
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, LWPolyline):
            path = QPainterPath()
            pts = [cad_to_scene(p) for p in entity.points]
            if pts:
                path.moveTo(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                if entity.closed:
                    path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Spline):
            path = QPainterPath()
            pts = entity.points
            if len(pts) == 1:
                path.moveTo(cad_to_scene(pts[0]))
            elif pts:
                segments = catmull_rom_bezier(pts, entity.closed)
                path.moveTo(cad_to_scene(segments[0][0]))
                for _p0, ctrl1, ctrl2, p3 in segments:
                    path.cubicTo(cad_to_scene(ctrl1), cad_to_scene(ctrl2), cad_to_scene(p3))
                if entity.closed:
                    path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, BlockReference):
            return self._create_block_reference_item(entity)

        if isinstance(entity, ImageReference):
            return self._create_image_item(entity)

        if isinstance(entity, Table):
            return self._create_table_item(entity, color)

        if isinstance(entity, Text):
            return self._create_text_item(entity, color)

        if isinstance(entity, Dimension):
            dim_style = self.document.dim_style
            segments, text_anchor = dimension_geometry(entity, tick_size=dim_style.arrow_size)
            path = QPainterPath()
            for a, b in segments:
                path.moveTo(cad_to_scene(a))
                path.lineTo(cad_to_scene(b))
            # Texto da medida com a mesma receita do Text (fonte de
            # referência escalada pela altura de caixa-alta) e tamanho vindo
            # do DimStyle do documento — não mais os 2.0 fixos de
            # DIM_TEXT_HEIGHT, que numa planta em metros davam um texto 20x
            # maior que a própria cota.
            text_height = dim_style.text_height
            if text_height > 1e-6:
                font = text_font(self.document.text_styles.get("Standard"))
                scale = text_height / max(_metrics(font).capHeight(), 1e-6)
                text_path, text_width = _scaled_text_path(font, entity.measurement_text(), scale)
                anchor_scene = cad_to_scene(text_anchor)
                text_path.translate(anchor_scene.x() - text_width / 2, anchor_scene.y() - text_height * 0.4)
                path.addPath(text_path)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Hatch) and entity.wipeout:
            # WIPEOUT (comando WIPEOUT ou entidade WIPEOUT do .dxf):
            # preenchimento sólido na cor de fundo do canvas. Fica por cima
            # só do que vem ANTES dele no documento — a ordem de desenho é o
            # zValue dado em refresh_entities (dentro de um bloco, a ordem
            # dos filhos no grupo), igual ao AutoCAD.
            path, _outer = _hatch_boundary_path(entity)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setBrush(QBrush(QColor(BACKGROUND_COLOR)))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Hatch) and entity.solid_fill:
            # HATCH sólida (ou SOLID/TRACE do .dxf): preenchimento na cor
            # efetiva da entidade, furos vazios (even-odd), contorno fino na
            # mesma cor. Antes TODA hachura sólida era tratada como WIPEOUT
            # (pintada na cor do fundo, por cima de tudo) — o corpo de cada
            # ícone de legenda/rack dos .dwg reais sumia e ainda cobria as
            # linhas e textos do próprio bloco.
            path, _outer = _hatch_boundary_path(entity)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setBrush(QBrush(QColor(color)))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, Hatch):
            path, outer_scene = _hatch_boundary_path(entity)
            item = _HatchItem(path)
            item.setPen(_entity_pen(color))
            item.set_hatch_lines(_hatch_fill_lines(outer_scene, entity.angle, entity.spacing))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, PointEntity):
            # Cruz de tamanho constante em pixels de tela, estilo marcador
            # OSNAP — não um Circle minúsculo (ver core/entities.py).
            c = cad_to_scene(entity.location)
            path = QPainterPath()
            half = _POINT_MARKER_SIZE_PX / (2 * max(self.transform().m11(), 1e-6))
            path.moveTo(c.x() - half, c.y())
            path.lineTo(c.x() + half, c.y())
            path.moveTo(c.x(), c.y() - half)
            path.lineTo(c.x(), c.y() + half)
            item = QGraphicsPathItem(path)
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        if isinstance(entity, (XLine, Ray)):
            c = cad_to_scene(entity.point)
            ux, uy = math.cos(entity.angle), math.sin(entity.angle)
            length = _CONSTRUCTION_LINE_RENDER_LENGTH
            if isinstance(entity, XLine):
                p1 = QPointF(c.x() - ux * length, c.y() + uy * length)
                p2 = QPointF(c.x() + ux * length, c.y() - uy * length)
            else:
                p1 = c
                p2 = QPointF(c.x() + ux * length, c.y() - uy * length)
            item = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            item.setPen(_entity_pen(color))
            item.setData(_BASE_COLOR_DATA_KEY, color)
            return item

        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")

    # ------------------------------------------------------------------ #
    # texto (ver o bloco "Texto: fonte de referência..." no topo do módulo)
    # ------------------------------------------------------------------ #
    def _text_font(self, entity: Text) -> QFont:
        return text_font(self.document.text_styles.get(entity.style), entity.width_factor)

    def _text_layout(self, entity: Text) -> TextLayout:
        return text_layout(entity, self._text_font(entity))

    def _create_text_item(self, entity: Text, color: str) -> QGraphicsItem:
        """Texto como QGraphicsPathItem: contornos dos glifos da fonte de
        referência (`_TEXT_REF_PX`), uma linha por baseline, com a escala
        altura/capHeight e a rotação compostas num único QTransform e o
        canto superior-esquerdo da caixa em `_text_top_left_world`. Linhas
        de um bloco justificado ao centro/direita são alinhadas dentro da
        caixa (o QGraphicsSimpleTextItem de antes só alinhava à esquerda).
        Altura <= 1e-6 ou conteúdo vazio: item vazio (o AutoCAD também não
        desenha) — sem o piso `max(h, 0.1)` antigo, que virava um texto de
        tamanho arbitrário."""
        path = QPainterPath()
        transform: QTransform | None = None
        pos = cad_to_scene(entity.insertion_point)
        if entity.height > 1e-6 and entity.content.strip():
            layout = self._text_layout(entity)
            col = entity.justify[1] if len(entity.justify) > 1 else "L"
            col_frac = _JUSTIFY_COL_FRAC.get(col, 0.0)
            for index, (line, line_width) in enumerate(zip(layout.lines, layout.line_widths)):
                if not line.strip():
                    continue
                x_px = (layout.width - line_width) * col_frac / layout.scale
                y_px = layout.baseline_offset(index) / layout.scale
                path.addText(x_px, y_px, layout.font, line)
            transform = QTransform()
            # inverte o ângulo: rotação anti-horária em CAD (Y pra cima) vira
            # horária em coords de cena (Y pra baixo) — mesmo ajuste que
            # Arc/Ellipse já fazem.
            transform.rotate(-math.degrees(entity.rotation))
            transform.scale(layout.scale, layout.scale)
            pos = cad_to_scene(_text_top_left_world(entity, layout))
        item = QGraphicsPathItem(path)
        if transform is not None:
            item.setTransform(transform)
        item.setPos(pos)
        item.setBrush(QBrush(QColor(color)))
        item.setPen(_entity_pen(color))
        item.setData(_BASE_COLOR_DATA_KEY, color)
        return item

    def _create_table_item(self, entity: Table, color: str) -> QGraphicsItem:
        """Grade (linhas) + texto de cada célula não-vazia, num
        QGraphicsItemGroup posicionado/rotacionado como um todo — mesmo
        padrão de `_create_block_reference_item`. Coordenadas locais dos
        filhos já em convenção de cena (Y cresce pra baixo = linha seguinte
        pra baixo), não precisam de `cad_to_scene` individual; só o grupo
        inteiro é que vai de CAD pra cena via `entity.insertion_point`."""
        group = QGraphicsItemGroup()
        total_w = entity.cols * entity.col_width
        total_h = entity.rows * entity.row_height

        if entity.show_borders:
            grid_path = QPainterPath()
            grid_path.addRect(0, 0, total_w, total_h)
            for r in range(1, entity.rows):
                y = r * entity.row_height
                grid_path.moveTo(0, y)
                grid_path.lineTo(total_w, y)
            for c in range(1, entity.cols):
                x = c * entity.col_width
                grid_path.moveTo(x, 0)
                grid_path.lineTo(x, total_h)
            grid_item = QGraphicsPathItem(grid_path)
            grid_item.setPen(_entity_pen(color))
            grid_item.setData(_BASE_COLOR_DATA_KEY, color)
            group.addToGroup(grid_item)

        # Texto das células com a mesma receita do Text (fonte de referência
        # escalada pela altura de caixa-alta, ver `text_layout`) — o
        # `setPointSizeF(text_height)` antigo sumia no Windows pra qualquer
        # tabela em metros.
        font = text_font(self.document.text_styles.get("Standard"))
        metrics = _metrics(font)
        scale = entity.text_height / max(metrics.capHeight(), 1e-6)
        pad = min(entity.col_width, entity.row_height) * 0.1
        for r, row_cells in enumerate(entity.cells[: entity.rows]):
            for c, text in enumerate(row_cells[: entity.cols]):
                if not text or entity.text_height <= 1e-6:
                    continue
                text_path, _width = _scaled_text_path(font, text, scale)
                # baseline em y=0 no path: desce uma altura de caixa-alta pra
                # o topo das maiúsculas ficar no canto superior-esquerdo da
                # célula (+ pad), como o QGraphicsSimpleTextItem de antes.
                text_path.translate(c * entity.col_width + pad, r * entity.row_height + pad + entity.text_height)
                text_item = QGraphicsPathItem(text_path)
                text_item.setPen(_entity_pen(color))
                text_item.setBrush(QBrush(QColor(color)))
                text_item.setData(_BASE_COLOR_DATA_KEY, color)
                group.addToGroup(text_item)

        pos = cad_to_scene(entity.insertion_point)
        group.setPos(pos)
        group.setRotation(-math.degrees(entity.rotation))
        group.setData(_BASE_COLOR_DATA_KEY, color)
        return group

    def _create_block_reference_item(
        self,
        entity: BlockReference,
        _depth: int = 0,
        ctx: tuple[str, str] | None = None,
    ) -> QGraphicsItem:
        """Renderiza a instância criando os QGraphicsItem de cada entidade da
        definição do bloco (coordenadas relativas ao ponto base) dentro de um
        QGraphicsItemGroup, e aplicando a transformação de inserção no grupo
        (translação/escala/rotação) — não achata a geometria em memória.

        `ctx` = (cor efetiva, camada efetiva) do INSERT PAI quando esta
        instância é um bloco aninhado (None no topo). Cada filho recebe a cor
        já resolvida por `_effective_color(child, (cor do INSERT, camada do
        INSERT))` — BYBLOCK e "camada 0 ByLayer" herdam da instância — e só
        é desenhado se `_block_child_visible`; a recursão propaga o mesmo par
        pros blocos aninhados.

        Se `entity.clip_boundary` estiver setado (comando CLIP), o grupo é um
        `_ClippedGroup`: o contorno já está no mesmo referencial LOCAL do
        bloco (ver `clip_command`/`_world_point_to_block_local` em
        modify_commands.py), então basta passar cada ponto por `cad_to_scene`
        sem nenhum ajuste extra — o `group.setPos/.setRotation/.setScale`
        logo abaixo cuida do resto, igual já faz pros filhos."""
        if entity.clip_boundary:
            path = QPainterPath()
            scene_pts = [cad_to_scene(p) for p in entity.clip_boundary]
            path.moveTo(scene_pts[0])
            for pt in scene_pts[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            group: QGraphicsItemGroup = _ClippedGroup(path)
        else:
            group = QGraphicsItemGroup()
        if _depth >= _MAX_BLOCK_NESTING:
            return group

        insert_color = self._effective_color(entity, ctx)
        insert_layer = ctx[1] if (ctx is not None and entity.layer == "0") else entity.layer
        child_ctx = (insert_color, insert_layer)

        definition = self.document.block_definitions.get(entity.block_name, [])
        merged_paths: dict[str, QPainterPath] = {}
        for child_entity in definition:
            if not self._block_child_visible(child_entity, insert_layer):
                continue
            try:
                if isinstance(child_entity, BlockReference):
                    child_item = self._create_block_reference_item(child_entity, _depth + 1, child_ctx)
                    child_color = None
                else:
                    child_color = self._effective_color(child_entity, child_ctx)
                    child_item = self._create_item(child_entity, child_color)
            except TypeError:
                continue
            # Fusão por cor: o item puramente geométrico NÃO entra no grupo —
            # seu traçado é acumulado e vira um item só por cor no fim. Antes
            # a fusão criava tudo e depois removia um a um, e cada
            # removeFromGroup recalcula o grupo inteiro: numa planta com
            # blocos grandes (NEWSI-CASA PAU BRASIL-R01, 110 mil segmentos em
            # definições) montar a cena passou de 17 s para 5 MINUTOS.
            path = None if child_color is None else self._plain_geometry_path(child_item)
            if path is not None:
                merged_paths.setdefault(child_color, QPainterPath()).addPath(path)
                continue
            group.addToGroup(child_item)

        for merged_color, merged_path in merged_paths.items():
            merged_item = QGraphicsPathItem(merged_path)
            merged_item.setPen(_entity_pen(merged_color))
            merged_item.setData(_BASE_COLOR_DATA_KEY, merged_color)
            group.addToGroup(merged_item)

        pos = cad_to_scene(entity.insertion_point)
        group.setPos(pos)
        # setRotation+setScale só cobrem escala uniforme; escala por eixo
        # (blocos dinâmicos importados, inclusive negativa = espelhado)
        # precisa de um QTransform explícito. Ordem: rotação POR FORA da
        # escala (rot·scale aplicado ao ponto local), igual ao INSERT do
        # DXF define — com escala não-uniforme essa ordem deixa de comutar,
        # então trocar as chamadas abaixo quebraria blocos esticados. O eixo
        # Y da cena é invertido (cad_to_scene), mas como o flip é diagonal
        # ele conjuga rot(θ)→rot(−θ) e mantém scale(sx,sy) — daí o ângulo
        # negativo, mesma convenção do resto do canvas.
        sx, sy = entity.scale_xy()
        transform = QTransform()
        transform.rotate(-math.degrees(entity.rotation))
        transform.scale(sx, sy)
        group.setTransform(transform)
        return group

    @staticmethod
    def _plain_geometry_path(item: QGraphicsItem) -> QPainterPath | None:
        """Traçado de um item cuja aparência é só "uma caneta" — ou None.

        Itens com preenchimento (texto vetorizado, hachura), grupos e imagens
        ficam de fora: fundi-los perderia brush/recorte."""
        brush = getattr(item, "brush", None)
        if brush is not None and brush().style() != Qt.BrushStyle.NoBrush:
            return None
        if type(item) is QGraphicsLineItem:
            line = item.line()
            path = QPainterPath(QPointF(line.x1(), line.y1()))
            path.lineTo(QPointF(line.x2(), line.y2()))
            return path
        if type(item) is QGraphicsPathItem:
            return QPainterPath(item.path())
        if type(item) is QGraphicsEllipseItem:
            path = QPainterPath()
            path.addEllipse(item.rect())
            return path
        if type(item) is QGraphicsRectItem:
            path = QPainterPath()
            path.addRect(item.rect())
            return path
        return None

    def _create_image_item(self, entity: ImageReference) -> QGraphicsItem:
        """ImageReference: insertion_point é o canto inferior-esquerdo (em
        coordenadas CAD, Y para cima) do retângulo width x height."""
        pixmap = QPixmap(str(entity.path))
        top_left_cad = Point(entity.insertion_point.x, entity.insertion_point.y + entity.height)
        pos = cad_to_scene(top_left_cad)

        if pixmap.isNull():
            # Arquivo ausente/corrompido: mostra um retângulo tracejado no
            # lugar em vez de deixar a imagem sumir silenciosamente.
            item = QGraphicsRectItem(pos.x(), pos.y(), entity.width, entity.height)
            pen = QPen(QColor(ENTITY_COLOR))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(0)
            item.setPen(pen)
        else:
            item = QGraphicsPixmapItem(pixmap)
            item.setPos(pos)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            if pixmap.width() > 0 and pixmap.height() > 0:
                item.setScale(1.0)
                transform = QTransform()
                transform.scale(entity.width / pixmap.width(), entity.height / pixmap.height())
                item.setTransform(transform)

        if not entity.clip_boundary:
            return item

        # ImageReference não tem transformação própria de grupo (ao
        # contrário de BlockReference) — o `_ClippedGroup` fica com pos/
        # rotação identidade, então o contorno precisa estar em coordenadas
        # de CENA absolutas (ponto de inserção + offset local, ver
        # `_world_point_to_image_local` em modify_commands.py).
        path = QPainterPath()
        scene_pts = [
            cad_to_scene(Point(entity.insertion_point.x + p.x, entity.insertion_point.y + p.y))
            for p in entity.clip_boundary
        ]
        path.moveTo(scene_pts[0])
        for pt in scene_pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        group = _ClippedGroup(path)
        group.addToGroup(item)
        return group

    # ------------------------------------------------------------------ #
    # hit-testing / seleção
    # ------------------------------------------------------------------ #
    def _hit_tolerance_world(self) -> float:
        scale = max(self.transform().m11(), 1e-6)
        return _HIT_TOLERANCE_PX / scale

    def _hit_test(self, cad_point: Point) -> str | None:
        tolerance = self._hit_tolerance_world()
        best_id: str | None = None
        best_dist = tolerance
        for entity_id, entity in self._hit_candidates(cad_point, tolerance):
            if not self.document.is_layer_visible(entity) or self.document.is_layer_locked(entity):
                continue
            dist = self._distance_to_entity(cad_point, entity)
            if dist is not None and dist <= best_dist:
                best_dist = dist
                best_id = entity_id
        return best_id

    def _hit_candidates(self, cad_point: Point, tolerance: float):
        """(id, entidade) das entidades que PODEM estar sob o ponto, usando o
        índice espacial da cena como pré-filtro.

        O teste exato (`_distance_to_entity`) é caro para BlockReference: ele
        desce em toda a definição do bloco, e uma planta de arquitetura tem
        centenas de instâncias de móveis com milhares de segmentos cada. A
        cena do Qt já sabe, por índice, quais itens gráficos cruzam a
        vizinhança do clique — o resto nem precisa ser testado (0,8 s por
        clique antes disso, medição de 2026-09-03).

        Se a cena ainda não estiver montada (ou o clique cair fora dela),
        devolve tudo: correção nunca depende do pré-filtro."""
        scene_point = cad_to_scene(cad_point)
        rect = QRectF(
            scene_point.x() - tolerance,
            scene_point.y() - tolerance,
            tolerance * 2,
            tolerance * 2,
        )
        if len(self._entity_items) != len(self.document.entities):
            # Cena ainda não montada ou desatualizada (entidade criada no meio
            # de um comando, antes do refresh): sem pré-filtro confiável.
            return self.document.entities.items()
        items = self._scene.items(rect)
        seen: set[str] = set()
        candidates = []
        for item in items:
            # Sobe até o item de primeiro nível: os filhos de um bloco têm
            # forma própria (é isso que permite descartar o bloco inteiro
            # quando o clique cai num vão dele), mas quem é selecionável é a
            # entidade dona.
            top = item
            parent = top.parentItem()
            while parent is not None:
                top = parent
                parent = top.parentItem()
            entity_id = top.data(_ENTITY_ID_DATA_KEY)
            if entity_id is None or entity_id in seen:
                continue
            entity = self.document.entities.get(entity_id)
            if entity is None:
                continue
            seen.add(entity_id)
            candidates.append((entity_id, entity))
        # Lista vazia aqui significa "não há nada desenhado perto do clique",
        # não "não sei" — a cena está em dia (checado acima).
        return candidates


    def _distance_to_entity(self, p: Point, entity: Entity) -> float | None:
        if isinstance(entity, Line):
            return _point_segment_distance(p, entity.start, entity.end)
        if isinstance(entity, Circle):
            return abs(p.distance_to(entity.center) - entity.radius)
        if isinstance(entity, Arc):
            radial = abs(p.distance_to(entity.center) - entity.radius)
            angle = entity.center.angle_to(p) % (2 * math.pi)
            sweep = (entity.end_angle - entity.start_angle) % (2 * math.pi)
            within = ((angle - entity.start_angle) % (2 * math.pi)) <= sweep
            return radial if within else None
        if isinstance(entity, Ellipse):
            dx, dy = p.x - entity.center.x, p.y - entity.center.y
            cos_a, sin_a = math.cos(-entity.rotation), math.sin(-entity.rotation)
            lx = dx * cos_a - dy * sin_a
            ly = dx * sin_a + dy * cos_a
            a, b = entity.radius_major, entity.radius_minor
            if a <= 0 or b <= 0:
                return None
            normalized = math.hypot(lx / a, ly / b)
            return abs(normalized - 1.0) * min(a, b)
        if isinstance(entity, LWPolyline):
            best: float | None = None
            for seg_a, seg_b in entity.segments():
                d = _point_segment_distance(p, seg_a, seg_b)
                if best is None or d < best:
                    best = d
            return best
        if isinstance(entity, Spline):
            # Aproximação: distância até o polígono de controle (pontos de
            # ajuste ligados por retas), não até a curva suave de verdade —
            # tolerância boa o bastante pro clique/hit-test, já que a curva
            # não se afasta muito dos fit points.
            pts = entity.points
            segments = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if entity.closed and len(pts) > 2 else [])
            best_spline: float | None = None
            for seg_a, seg_b in segments:
                d = _point_segment_distance(p, seg_a, seg_b)
                if best_spline is None or d < best_spline:
                    best_spline = d
            return best_spline
        if isinstance(entity, BlockReference):
            return self._distance_to_block_reference(p, entity)
        if isinstance(entity, ImageReference):
            return self._distance_to_image(p, entity)
        if isinstance(entity, Text):
            layout = self._text_layout(entity)
            width, height = _text_local_extent(entity, layout)
            top_left = _text_top_left_world(entity, layout)
            dx, dy = p.x - top_left.x, p.y - top_left.y
            cos_a, sin_a = math.cos(-entity.rotation), math.sin(-entity.rotation)
            lx = dx * cos_a - dy * sin_a
            ly = dx * sin_a + dy * cos_a
            if 0.0 <= lx <= width and -height <= ly <= 0.0:
                return 0.0
            cx = min(max(lx, 0.0), width)
            cy = min(max(ly, -height), 0.0)
            return math.hypot(lx - cx, ly - cy)
        if isinstance(entity, Dimension):
            segments, _ = dimension_geometry(entity, tick_size=self.document.dim_style.arrow_size)
            if not segments:
                return None
            return min(_point_segment_distance(p, a, b) for a, b in segments)
        if isinstance(entity, Hatch) and len(entity.boundary_points) >= 3:
            if _point_in_polygon(p, entity.boundary_points):
                return 0.0
            return min(
                _point_segment_distance(p, a, b)
                for a, b in _polygon_segments(entity.boundary_points)
            )
        if isinstance(entity, PointEntity):
            return p.distance_to(entity.location)
        if isinstance(entity, XLine):
            return point_infinite_line_distance(p, entity.point, entity.angle)
        if isinstance(entity, Ray):
            return point_ray_distance(p, entity.point, entity.angle)
        if isinstance(entity, Table):
            total_w = entity.cols * entity.col_width
            total_h = entity.rows * entity.row_height
            dx, dy = p.x - entity.insertion_point.x, p.y - entity.insertion_point.y
            cos_a, sin_a = math.cos(-entity.rotation), math.sin(-entity.rotation)
            lx = dx * cos_a - dy * sin_a
            ly = dx * sin_a + dy * cos_a
            if 0.0 <= lx <= total_w and -total_h <= ly <= 0.0:
                return 0.0
            cx = min(max(lx, 0.0), total_w)
            cy = min(max(ly, -total_h), 0.0)
            return math.hypot(lx - cx, ly - cy)
        return None

    def _distance_to_block_reference(self, p: Point, entity: BlockReference, _depth: int = 0) -> float | None:
        """Aproxima a distância transformando o ponto de teste para o espaço
        local da definição (desfaz translação/rotação/escala da inserção) e
        reaproveita `_distance_to_entity` em cada entidade do bloco, depois
        reescala o resultado de volta pra unidades do mundo. Exato para
        escala uniforme; para escala por eixo (bloco dinâmico importado) a
        volta usa a média dos módulos das escalas — aproximação boa o
        suficiente pra tolerância de clique, documentada aqui de propósito."""
        if _depth >= _MAX_BLOCK_NESTING:
            return None
        sx, sy = entity.scale_xy()
        dx, dy = p.x - entity.insertion_point.x, p.y - entity.insertion_point.y
        cos_a, sin_a = math.cos(-entity.rotation), math.sin(-entity.rotation)
        # Dividir pelo valor COM SINAL desfaz o espelhamento corretamente.
        local = Point((dx * cos_a - dy * sin_a) / sx, (dx * sin_a + dy * cos_a) / sy)
        back_scale = (abs(sx) + abs(sy)) / 2

        best: float | None = None
        for child in self.document.block_definitions.get(entity.block_name, []):
            if isinstance(child, BlockReference):
                d = self._distance_to_block_reference(local, child, _depth + 1)
            else:
                d = self._distance_to_entity(local, child)
            if d is None:
                continue
            d_world = d * back_scale
            if best is None or d_world < best:
                best = d_world
        return best

    def _distance_to_image(self, p: Point, entity: ImageReference) -> float | None:
        x0, y0 = entity.insertion_point.x, entity.insertion_point.y
        x1, y1 = x0 + entity.width, y0 + entity.height
        corners = [Point(x0, y0), Point(x1, y0), Point(x1, y1), Point(x0, y1)]
        best: float | None = None
        for a, b in zip(corners, corners[1:] + corners[:1]):
            d = _point_segment_distance(p, a, b)
            if best is None or d < best:
                best = d
        return best

    def _entity_bbox_scene(self, entity: Entity) -> QRectF:
        if isinstance(entity, Line):
            p1, p2 = cad_to_scene(entity.start), cad_to_scene(entity.end)
            return QRectF(
                min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                abs(p2.x() - p1.x()), abs(p2.y() - p1.y()),
            )
        if isinstance(entity, (Circle, Arc)):
            c = cad_to_scene(entity.center)
            r = entity.radius
            return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        if isinstance(entity, Ellipse):
            c = cad_to_scene(entity.center)
            r = max(entity.radius_major, entity.radius_minor)
            return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        if isinstance(entity, LWPolyline) and entity.points:
            pts = [cad_to_scene(p) for p in entity.points]
            xs = [pt.x() for pt in pts]
            ys = [pt.y() for pt in pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if isinstance(entity, Spline) and entity.points:
            pts = [cad_to_scene(p) for p in entity.points]
            xs = [pt.x() for pt in pts]
            ys = [pt.y() for pt in pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if isinstance(entity, BlockReference):
            return self._block_reference_bbox_scene(entity)
        if isinstance(entity, ImageReference):
            pos = cad_to_scene(Point(entity.insertion_point.x, entity.insertion_point.y + entity.height))
            return QRectF(pos.x(), pos.y(), entity.width, entity.height)
        if isinstance(entity, Text):
            layout = self._text_layout(entity)
            width, height = _text_local_extent(entity, layout)
            top_left = _text_top_left_world(entity, layout)
            local_corners = [(0.0, 0.0), (width, 0.0), (width, -height), (0.0, -height)]
            cos_a, sin_a = math.cos(entity.rotation), math.sin(entity.rotation)
            world_pts = [
                cad_to_scene(
                    Point(
                        top_left.x + lx * cos_a - ly * sin_a,
                        top_left.y + lx * sin_a + ly * cos_a,
                    )
                )
                for lx, ly in local_corners
            ]
            xs = [pt.x() for pt in world_pts]
            ys = [pt.y() for pt in world_pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if isinstance(entity, Dimension):
            segments, text_anchor = dimension_geometry(entity, tick_size=self.document.dim_style.arrow_size)
            pts = [text_anchor] + [pt for seg in segments for pt in seg]
            if not pts:
                return QRectF()
            scene_pts = [cad_to_scene(pt) for pt in pts]
            xs = [pt.x() for pt in scene_pts]
            ys = [pt.y() for pt in scene_pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if isinstance(entity, Hatch) and entity.boundary_points:
            pts = [cad_to_scene(p) for p in entity.boundary_points]
            xs = [pt.x() for pt in pts]
            ys = [pt.y() for pt in pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if isinstance(entity, PointEntity):
            # Pequena margem (não um retângulo de área zero) pra
            # zoom_extents não colapsar quando o desenho só tem PointEntity —
            # QRectF.isEmpty() (usado por compute_extents_rect) é True para
            # largura OU altura zero.
            c = cad_to_scene(entity.location)
            eps = 1e-2
            return QRectF(c.x() - eps, c.y() - eps, 2 * eps, 2 * eps)
        if isinstance(entity, (XLine, Ray)):
            # Zoom-extents/seleção por janela consideram só o ponto de
            # ancoragem, não o comprimento de renderização artificial (ver
            # _CONSTRUCTION_LINE_RENDER_LENGTH) — senão qualquer XLine/Ray
            # "explodiria" o zoom extents do desenho inteiro.
            c = cad_to_scene(entity.point)
            eps = 1e-2
            return QRectF(c.x() - eps, c.y() - eps, 2 * eps, 2 * eps)
        if isinstance(entity, Table):
            total_w = entity.cols * entity.col_width
            total_h = entity.rows * entity.row_height
            local_corners = [(0.0, 0.0), (total_w, 0.0), (total_w, -total_h), (0.0, -total_h)]
            cos_a, sin_a = math.cos(entity.rotation), math.sin(entity.rotation)
            world_pts = [
                cad_to_scene(
                    Point(
                        entity.insertion_point.x + lx * cos_a - ly * sin_a,
                        entity.insertion_point.y + lx * sin_a + ly * cos_a,
                    )
                )
                for lx, ly in local_corners
            ]
            xs = [pt.x() for pt in world_pts]
            ys = [pt.y() for pt in world_pts]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return QRectF()

    def _block_reference_bbox_scene(self, entity: BlockReference, _depth: int = 0) -> QRectF:
        if _depth >= _MAX_BLOCK_NESTING:
            return QRectF()
        local_rect: QRectF | None = None
        for child in self.document.block_definitions.get(entity.block_name, []):
            child_rect = (
                self._block_reference_bbox_scene(child, _depth + 1)
                if isinstance(child, BlockReference)
                else self._entity_bbox_scene(child)
            )
            if child_rect.isNull():
                continue
            local_rect = child_rect if local_rect is None else local_rect.united(child_rect)
        if local_rect is None:
            return QRectF()

        transform = QTransform()
        pos = cad_to_scene(entity.insertion_point)
        transform.translate(pos.x(), pos.y())
        transform.rotate(-math.degrees(entity.rotation))
        sx, sy = entity.scale_xy()
        transform.scale(sx, sy)
        return transform.mapRect(local_rect)

    def _handle_selection_press(self, event) -> None:
        scene_pos = self.mapToScene(self._event_pos(event))
        cad_point = scene_to_cad(scene_pos)
        hit_id = self._hit_test(cad_point)
        selection = self.interpreter.context.selection

        if hit_id is not None:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if shift:
                selection.toggle(hit_id)
            else:
                selection.add(hit_id)
            self.refresh_selection_highlight()
            self.viewport().update()
            if self.on_selection_changed is not None:
                self.on_selection_changed()
        else:
            self._selection_drag_start_scene = scene_pos
            self._selection_drag_current_scene = scene_pos

    def _finish_selection_drag(self, event) -> None:
        start = self._selection_drag_start_scene
        end = self.mapToScene(self._event_pos(event))
        self._selection_drag_start_scene = None
        self._selection_drag_current_scene = None
        self.viewport().update()

        if start is None:
            return

        drag_rect = QRectF(start, end).normalized()
        if drag_rect.width() < 1e-9 and drag_rect.height() < 1e-9:
            return

        window_mode = start.x() <= end.x()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        selection = self.interpreter.context.selection

        for entity_id, entity in self.document.entities.items():
            if not self.document.is_layer_visible(entity) or self.document.is_layer_locked(entity):
                continue
            bbox = self._entity_bbox_scene(entity)
            matched = _rect_contains(drag_rect, bbox) if window_mode else _rect_intersects(drag_rect, bbox)
            if matched:
                selection.remove(entity_id) if shift else selection.add(entity_id)

        self.refresh_selection_highlight()
        if self.on_selection_changed is not None:
            self.on_selection_changed()

    # ------------------------------------------------------------------ #
    # grid / crosshair / preview
    # ------------------------------------------------------------------ #
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(BACKGROUND_COLOR))
        if not self.grid_visible:
            return

        scale = max(self.transform().m11(), 1e-6)
        step = _pick_grid_step(scale)

        pen_minor = QPen(QColor(GRID_MINOR_COLOR))
        pen_minor.setWidth(0)
        painter.setPen(pen_minor)

        left = math.floor(rect.left() / step) * step
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step

        top = math.floor(rect.top() / step) * step
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

        pen_axis = QPen(QColor(GRID_AXIS_COLOR))
        pen_axis.setWidth(0)
        painter.setPen(pen_axis)
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if self._mouse_scene_pos is not None:
            pen = QPen(QColor(CROSSHAIR_COLOR))
            pen.setWidth(0)
            painter.setPen(pen)
            x, y = self._mouse_scene_pos.x(), self._mouse_scene_pos.y()
            half_w = rect.width() * CROSSHAIR_SIZE_PERCENT / 100 / 2
            half_h = rect.height() * CROSSHAIR_SIZE_PERCENT / 100 / 2
            painter.drawLine(QPointF(x - half_w, y), QPointF(x + half_w, y))
            painter.drawLine(QPointF(x, y - half_h), QPointF(x, y + half_h))

            # Pickbox no centro do crosshair — igual ao cursor padrão do
            # AutoCAD (mira + quadradinho de seleção), tamanho constante em
            # pixels de tela independente do zoom.
            scale = max(self.transform().m11(), 1e-6)
            half = _PICKBOX_SIZE_PX / 2 / scale
            painter.drawRect(QRectF(x - half, y - half, half * 2, half * 2))

        if self._preview_path is not None and not self._preview_path.isEmpty():
            pen = QPen(QColor(PREVIEW_COLOR))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(0)
            painter.setPen(pen)
            painter.drawPath(self._preview_path)

        if self._osnap_marker is not None:
            self._draw_osnap_marker(painter)

        if self._selection_drag_start_scene is not None and self._selection_drag_current_scene is not None:
            drag_rect = QRectF(self._selection_drag_start_scene, self._selection_drag_current_scene).normalized()
            window_mode = self._selection_drag_start_scene.x() <= self._selection_drag_current_scene.x()
            color = QColor(WINDOW_SELECT_COLOR if window_mode else CROSSING_SELECT_COLOR)
            pen = QPen(color)
            pen.setWidth(0)
            pen.setStyle(Qt.PenStyle.SolidLine if window_mode else Qt.PenStyle.DashLine)
            painter.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(40)
            painter.setBrush(QBrush(fill))
            painter.drawRect(drag_rect)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_osnap_marker(self, painter: QPainter) -> None:
        pt, kind = self._osnap_marker
        scale = max(self.transform().m11(), 1e-6)
        size = _OSNAP_MARKER_SIZE_PX / scale
        half = size / 2
        center = cad_to_scene(pt)

        pen = QPen(QColor(OSNAP_MARKER_COLOR))
        pen.setWidth(0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if kind == "endpoint":
            painter.drawRect(QRectF(center.x() - half, center.y() - half, size, size))
        elif kind == "midpoint":
            path = QPainterPath(QPointF(center.x(), center.y() - half))
            path.lineTo(center.x() - half, center.y() + half)
            path.lineTo(center.x() + half, center.y() + half)
            path.closeSubpath()
            painter.drawPath(path)
        elif kind == "center":
            painter.drawEllipse(center, half, half)
        elif kind == "intersection":
            painter.drawLine(QPointF(center.x() - half, center.y() - half), QPointF(center.x() + half, center.y() + half))
            painter.drawLine(QPointF(center.x() - half, center.y() + half), QPointF(center.x() + half, center.y() - half))
        elif kind == "node":
            painter.drawEllipse(center, half, half)
            painter.drawLine(QPointF(center.x() - half, center.y()), QPointF(center.x() + half, center.y()))
            painter.drawLine(QPointF(center.x(), center.y() - half), QPointF(center.x(), center.y() + half))
        elif kind == "insert":
            path = QPainterPath(QPointF(center.x(), center.y() - half))
            path.lineTo(center.x() + half, center.y())
            path.lineTo(center.x(), center.y() + half)
            path.lineTo(center.x() - half, center.y())
            path.closeSubpath()
            painter.drawPath(path)

    def set_grid_visible(self, visible: bool) -> None:
        self.grid_visible = visible
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled

    def set_ortho_enabled(self, enabled: bool) -> None:
        self.ortho_enabled = enabled

    def set_osnap_enabled(self, enabled: bool) -> None:
        self.osnap_enabled = enabled
        if not enabled:
            self._osnap_marker = None
            self.viewport().update()

    def set_polar_enabled(self, enabled: bool) -> None:
        self.polar_enabled = enabled

    def clear_transient_overlays(self) -> None:
        """Limpa preview/dynamic-input residuais quando um comando termina,
        sem esperar o próximo movimento do mouse."""
        self._preview_path = None
        self._dyn_text.hide()
        self._osnap_marker = None
        self.viewport().update()

    def set_dynamic_input_enabled(self, enabled: bool) -> None:
        self.dynamic_input_enabled = enabled
        if not enabled:
            self._dyn_text.hide()

    # ------------------------------------------------------------------ #
    # zoom (usado pelo menu View)
    # ------------------------------------------------------------------ #
    def zoom_in(self) -> None:
        self.scale(1.25, 1.25)

    def zoom_out(self) -> None:
        self.scale(1 / 1.25, 1 / 1.25)

    def compute_extents_rect(self, margin_ratio: float = 0.1) -> QRectF | None:
        """Bounding box (coordenadas de cena) de todas as entidades do
        documento, com margem — usado por zoom_extents() e por export_pdf()."""
        if not self.document.entities:
            return None
        rect: QRectF | None = None
        for entity in self.document.entities.values():
            if not self.document.is_layer_visible(entity):
                continue
            bbox = self._entity_bbox_scene(entity)
            rect = bbox if rect is None else rect.united(bbox)
        if rect is None or rect.isEmpty():
            return None
        margin = max(rect.width(), rect.height()) * margin_ratio or 1.0
        return rect.adjusted(-margin, -margin, margin, margin)

    def zoom_extents(self) -> None:
        rect = self.compute_extents_rect()
        if rect is None:
            return
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def export_pdf(self, path, page_size: str = "A4", orientation: str = "auto") -> bool:
        """PLOT/PUBLISH: renderiza todas as entidades do documento (não só o
        que está visível na tela) numa única página PDF via QPdfWriter.

        `page_size`: um dos nomes em `PDF_PAGE_SIZES` ("A4", "A3", "A2",
        "A1", "A0" — os tamanhos padrão usados em desenho técnico/
        arquitetônico). `orientation`: "auto" (retrato se a altura do
        desenho for maior que a largura, paisagem caso contrário —
        comportamento igual ao AutoCAD ao plotar "Fit"), "portrait" ou
        "landscape".

        Simplificação documentada no README: o NewSIcad não tem conceito de
        layouts/paper space nem de escala real de impressão (sempre "ajusta
        pra caber na folha", como um PLOT com Fit) — nem distinção real
        entre "imprimir a vista atual" (PLOT) e "publicar várias folhas"
        (PUBLISH), que aqui chamam este mesmo método (uma folha, o desenho
        inteiro)."""
        from PySide6.QtGui import QPageLayout, QPdfWriter

        rect = self.compute_extents_rect()
        if rect is None:
            return False

        if orientation == "auto":
            is_landscape = rect.width() >= rect.height()
        else:
            is_landscape = orientation == "landscape"

        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(PDF_PAGE_SIZES.get(page_size, QPageSize.PageSizeId.A4)))
        writer.setPageOrientation(
            QPageLayout.Orientation.Landscape if is_landscape else QPageLayout.Orientation.Portrait
        )
        writer.setResolution(300)
        painter = QPainter(writer)
        was_grid_visible = self.grid_visible
        self.grid_visible = False
        try:
            self._scene.render(painter, source=rect)
        finally:
            self.grid_visible = was_grid_visible
            painter.end()
        return True

    def zoom_window(self, p1: Point, p2: Point) -> None:
        """Zoom pra uma janela definida por dois pontos em coordenadas CAD
        (comando ZOOM digitado — "Specify corner of window")."""
        s1, s2 = cad_to_scene(p1), cad_to_scene(p2)
        rect = QRectF(
            min(s1.x(), s2.x()), min(s1.y(), s2.y()),
            abs(s2.x() - s1.x()), abs(s2.y() - s1.y()),
        )
        if rect.width() < 1e-9 or rect.height() < 1e-9:
            return
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------------ #
    # entrada do usuário
    # ------------------------------------------------------------------ #
    def _event_pos(self, event):
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

    def _apply_constraints(self, point: Point) -> Point:
        prompt = self.interpreter.current_prompt
        active_point_prompt = (
            self.interpreter.active and prompt is not None and prompt.kind == "point"
        )
        # ORTHO/POLAR só fazem sentido quando o ponto está definindo um segmento
        # que continua a partir do último ponto (ex.: próximo vértice de uma
        # LINE/PLINE). Em prompts que só *identificam* uma entidade já existente
        # (TRIM/EXTEND/OFFSET/FILLET/CHAMFER's "select object"), connect_to_last
        # é False e essas restrições relativas ao last_point não se aplicam.
        connect_prompt = active_point_prompt and prompt.connect_to_last

        # OSNAP tem prioridade sobre ORTHO/POLAR/SNAP — igual ao AutoCAD, o
        # cursor "gruda" no ponto de snap de objeto mesmo que isso quebre a
        # restrição ortogonal/polar. Mas só faz sentido quando o ponto está
        # DEFININDO geometria nova (connect_prompt) — em prompts que só
        # *identificam* uma entidade/lado já existente (TRIM/EXTEND/OFFSET/
        # FILLET/CHAMFER's "select object", connect_to_last=False), grudar no
        # snap mais próximo (tipicamente a interseção onde duas arestas se
        # cruzam) apaga a informação de "de que lado do corte o usuário
        # clicou" — bug real reportado: TRIM cortando o lado errado perto de
        # interseções, exatamente o caso mais comum de uso do comando.
        if self.osnap_enabled and connect_prompt:
            snap = self._find_osnap_point(point)
            if snap is not None:
                self._osnap_marker = snap
                return snap[0]
        self._osnap_marker = None

        result = point

        if (
            self.ortho_enabled
            and connect_prompt
            and self.interpreter.last_point is not None
        ):
            base = self.interpreter.last_point
            dx = result.x - base.x
            dy = result.y - base.y
            result = Point(result.x, base.y) if abs(dx) >= abs(dy) else Point(base.x, result.y)
        elif (
            self.polar_enabled
            and connect_prompt
            and self.interpreter.last_point is not None
        ):
            result = self._apply_polar(result)

        if self.snap_enabled:
            step = self.snap_spacing
            result = Point(round(result.x / step) * step, round(result.y / step) * step)

        return result

    def _apply_polar(self, point: Point) -> Point:
        """Gruda o cursor no múltiplo de 15° mais próximo do ângulo formado
        com `interpreter.last_point`, dentro de uma tolerância angular
        pequena — mesmo princípio do ORTHO acima, mas com 24 direções em vez
        de só 2."""
        base = self.interpreter.last_point
        if base is None:
            return point
        distance = base.distance_to(point)
        if distance < 1e-9:
            return point
        angle = base.angle_to(point)
        step = math.radians(_POLAR_STEP_DEG)
        snapped_angle = round(angle / step) * step
        tolerance = math.radians(_POLAR_TOLERANCE_DEG)
        diff = (angle - snapped_angle + math.pi) % (2 * math.pi) - math.pi
        if abs(diff) > tolerance:
            return point
        return Point(base.x + distance * math.cos(snapped_angle), base.y + distance * math.sin(snapped_angle))

    # ------------------------------------------------------------------ #
    # OSNAP — Endpoint / Midpoint / Center / Intersection
    # ------------------------------------------------------------------ #
    def _osnap_tolerance_world(self) -> float:
        scale = max(self.transform().m11(), 1e-6)
        return _OSNAP_TOLERANCE_PX / scale

    @staticmethod
    def _entity_snap_points(entity: Entity) -> list[tuple[Point, str]]:
        pts: list[tuple[Point, str]] = []
        if isinstance(entity, Line):
            pts.append((entity.start, "endpoint"))
            pts.append((entity.end, "endpoint"))
            pts.append((entity.midpoint(), "midpoint"))
        elif isinstance(entity, Arc):
            pts.append((entity.start_point(), "endpoint"))
            pts.append((entity.end_point(), "endpoint"))
            pts.append((entity.center, "center"))
        elif isinstance(entity, (Circle, Ellipse)):
            pts.append((entity.center, "center"))
        elif isinstance(entity, LWPolyline):
            for a, b in entity.segments():
                pts.append((a, "endpoint"))
                pts.append((b, "endpoint"))
                pts.append((Point((a.x + b.x) / 2, (a.y + b.y) / 2), "midpoint"))
        elif isinstance(entity, Spline):
            # Gruda nos fit points (não em pontos da curva suave em si —
            # simplificação: são os únicos pontos "nomeáveis" do modelo).
            for pt in entity.points:
                pts.append((pt, "endpoint"))
        elif isinstance(entity, PointEntity):
            pts.append((entity.location, "node"))
        elif isinstance(entity, BlockReference):
            pts.append((entity.insertion_point, "insert"))
        return pts

    def _nearby_entities(self, cursor_scene: QPointF, radius_world: float) -> list[Entity]:
        """Pré-filtro barato (reusa `_entity_bbox_scene`, já usado pela
        seleção por janela) pra não recalcular interseções entre todo par de
        entidades do documento a cada movimento do mouse."""
        result = []
        for entity in self.document.entities.values():
            if not self.document.is_layer_visible(entity):
                continue
            bbox = self._entity_bbox_scene(entity).adjusted(-radius_world, -radius_world, radius_world, radius_world)
            if bbox.contains(cursor_scene):
                result.append(entity)
        return result

    def _find_osnap_point(self, cursor: Point) -> tuple[Point, str] | None:
        tolerance = self._osnap_tolerance_world()
        cursor_scene = cad_to_scene(cursor)
        nearby = self._nearby_entities(cursor_scene, tolerance)
        if not nearby:
            return None

        candidates: list[tuple[float, Point, str]] = []
        for entity in nearby:
            for pt, kind in self._entity_snap_points(entity):
                d = cursor.distance_to(pt)
                if d <= tolerance:
                    candidates.append((d, pt, kind))

        for i in range(len(nearby)):
            pieces_a = as_intersectable_pieces(nearby[i])
            for j in range(i + 1, len(nearby)):
                pieces_b = as_intersectable_pieces(nearby[j])
                for pa in pieces_a:
                    for pb in pieces_b:
                        for pt in entity_intersections(pa, pb):
                            d = cursor.distance_to(pt)
                            if d <= tolerance:
                                candidates.append((d, pt, "intersection"))

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        _, pt, kind = candidates[0]
        return pt, kind

    def _resolve_point(self, event) -> Point:
        scene_pos = self.mapToScene(self._event_pos(event))
        return self._apply_constraints(scene_to_cad(scene_pos))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = self._event_pos(event)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            prompt = self.interpreter.current_prompt
            if self.interpreter.active and prompt is not None and prompt.kind == "selection":
                self._handle_selection_press(event)
                event.accept()
                return
            if not self.interpreter.active:
                # Fora de qualquer comando: clique seleciona/alterna a
                # entidade sob o cursor (ou inicia janela/crossing numa área
                # vazia) — antes disso só era possível selecionar clicando
                # DURANTE o prompt "Select objects:" de um comando como
                # ERASE/MOVE. Sem isso, Del e qualquer ação "selecione algo e
                # depois aja" (ex.: botão direito, ver abaixo) não tinham
                # como funcionar. Bug real reportado pela Rafaela.
                self._handle_selection_press(event)
                event.accept()
                return
            if self.on_point is not None:
                self.on_point(self._resolve_point(event))
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            if not self.interpreter.active:
                cad_point = scene_to_cad(self.mapToScene(self._event_pos(event)))
                hit_id = self._hit_test(cad_point)
                if hit_id is not None:
                    selection = self.interpreter.context.selection
                    if hit_id not in selection.ids:
                        selection.set({hit_id})
                        self.refresh_selection_highlight()
                        self.viewport().update()
                        if self.on_selection_changed is not None:
                            self.on_selection_changed()
                    if self.on_context_menu is not None:
                        self.on_context_menu()
                    event.accept()
                    return
            if self.on_enter is not None:
                self.on_enter()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = self._event_pos(event)

        if self._panning:
            delta = pos - self._pan_start
            self._pan_start = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        scene_pos = self.mapToScene(pos)
        self._mouse_scene_pos = scene_pos

        if self._selection_drag_start_scene is not None:
            self._selection_drag_current_scene = scene_pos
            self.viewport().update()
            event.accept()
            return

        cad_point = self._apply_constraints(scene_to_cad(scene_pos))
        self._update_dynamic_input(cad_point)
        previous_preview = self._preview_path
        self._update_preview(cad_point)
        self.mouse_moved.emit(cad_point)
        # Invalidação PARCIAL: o que o drawForeground desenha em função do
        # cursor são o crosshair (duas linhas finas atravessando a viewport
        # toda), o pickbox e o marcador de OSNAP (ambos a poucos px do
        # cursor). Redesenhar a viewport inteira a cada movimento — o
        # comportamento antigo — significa re-renderizar todos os itens
        # visíveis por movimento, o que num .dwg real (~35 mil itens) deixava
        # o simples mover do mouse arrastado (auditoria 2026-08-28). Aqui só
        # as faixas do crosshair (velho + novo) e uma caixa generosa ao redor
        # das duas posições do cursor (cobre pickbox/marcador de OSNAP; o
        # texto do dynamic input é um item de cena, se auto-invalida) são
        # marcadas pra repintura.
        prev = self._last_cursor_viewport_pos
        self._last_cursor_viewport_pos = pos
        if prev is None or self._preview_path is not None or previous_preview is not None:
            # Preview de comando (linha/retângulo/círculo em elástico até o
            # cursor) pode cruzar a viewport inteira em diagonal — aí não dá
            # pra recortar a área; repinta tudo. Fora de comando (o caso do
            # dia a dia, navegando pelo desenho) cai no ramo barato abaixo.
            self.viewport().update()
        else:
            self.viewport().update(self._cursor_region(prev, pos))
        super().mouseMoveEvent(event)

    def _cursor_region(self, prev: QPoint, pos: QPoint) -> QRegion:
        """Área a repintar quando SÓ o cursor se moveu: uma caixa em volta da
        posição anterior e da nova, do tamanho do crosshair (uma fração da
        viewport, ver CROSSHAIR_SIZE_PERCENT) mais uma folga para o pickbox,
        o marcador de OSNAP e o texto do dynamic input.

        Antes daqui saíam duas faixas de borda a borda da viewport (herança de
        quando o crosshair era de tela cheia), o que fazia cada movimento do
        mouse repintar todos os itens cruzados pela linha e pela coluna do
        cursor — a causa da lentidão relatada pelos testers em plantas reais
        (medição em newsicad/ui/canvas.py: 40 ms por movimento na planta Ana
        Beatriz)."""
        w, h = self.viewport().width(), self.viewport().height()
        half_w = w * CROSSHAIR_SIZE_PERCENT / 100 / 2
        half_h = h * CROSSHAIR_SIZE_PERCENT / 100 / 2
        margin = int(max(half_w, half_h, _PICKBOX_SIZE_PX, _OSNAP_MARKER_SIZE_PX)) + _CURSOR_REGION_PADDING_PX
        region = QRegion()
        for p in (prev, pos):
            region += QRect(p.x() - margin, p.y() - margin, margin * 2, margin * 2)
        return region

    def _apply_pending_zoom(self) -> None:
        """Aplica de uma vez o zoom acumulado desde o último repaint."""
        factor, self._pending_zoom_factor = self._pending_zoom_factor, 1.0
        if abs(factor - 1.0) > 1e-9:
            self.scale(factor, factor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.BlankCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._selection_drag_start_scene is not None:
            self._finish_selection_drag(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        """Zoom com a roda, acumulando a rajada num repaint só.

        Girar a roda rápido gera vários eventos seguidos, e cada `scale()`
        obriga um repaint da viewport inteira (~39 ms numa planta real). Com o
        acúmulo, três "cliques" de roda dados juntos viram um repaint com o
        fator total — o resultado final é idêntico (a escala é multiplicativa)
        e a sensação é de resposta imediata em vez de arrastada."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._pending_zoom_factor *= factor
        self._zoom_timer.start()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.on_cancel is not None:
                self.on_cancel()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            # Del/Backspace apaga a seleção atual direto (sem precisar digitar
            # ERASE) — bug real reportado: Del "não fazia nada". Só dispara
            # fora de um comando ativo (self.on_delete decide isso).
            if self.on_delete is not None:
                self.on_delete()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            # Depois de selecionar objetos clicando no canvas, o foco do
            # teclado fica no canvas (não na linha de comando) — Enter/Espaço
            # precisa confirmar mesmo assim, igual clique direito.
            if self.on_enter is not None:
                self.on_enter()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # preview e dynamic input
    # ------------------------------------------------------------------ #
    def _update_preview(self, cursor_point: Point) -> None:
        self._preview_path = None
        interp = self.interpreter
        if not interp.active or interp.last_point is None:
            return

        prompt = interp.current_prompt
        last = interp.last_point
        path = QPainterPath()

        if interp.last_command_name == "CIRCLE" and prompt is not None and prompt.kind == "distance":
            radius = last.distance_to(cursor_point)
            center_scene = cad_to_scene(last)
            path.addEllipse(center_scene, radius, radius)
            path.moveTo(center_scene)
            path.lineTo(cad_to_scene(cursor_point))
        elif interp.last_command_name == "RECTANG" and prompt is not None and prompt.kind == "point":
            # Sem isso, RECTANG caía no preview genérico de "linha reta até o
            # cursor" (igual LINE) — dava a impressão de estar desenhando uma
            # linha, não um retângulo, mesmo a entidade final sendo uma
            # LWPolyline fechada correta. Bug real reportado pelo grupo.
            path.addRect(QRectF(cad_to_scene(last), cad_to_scene(cursor_point)).normalized())
        elif prompt is not None and prompt.kind == "point" and prompt.connect_to_last:
            path.moveTo(cad_to_scene(last))
            path.lineTo(cad_to_scene(cursor_point))

        self._preview_path = path

    def _update_dynamic_input(self, cursor_point: Point) -> None:
        interp = self.interpreter
        if not self.dynamic_input_enabled or not interp.active or interp.last_point is None or self._mouse_scene_pos is None:
            self._dyn_text.hide()
            return

        prompt = interp.current_prompt
        if prompt is None or prompt.kind not in ("point", "distance"):
            self._dyn_text.hide()
            return
        if prompt.kind == "point" and not prompt.connect_to_last:
            self._dyn_text.hide()
            return

        last = interp.last_point
        distance = last.distance_to(cursor_point)
        angle_deg = math.degrees(last.angle_to(cursor_point)) % 360
        self._dyn_text.setText(f"{distance:.2f} < {angle_deg:.1f}°")

        scale = max(self.transform().m11(), 1e-6)
        offset = 14.0 / scale
        self._dyn_text.setPos(
            self._mouse_scene_pos.x() + offset, self._mouse_scene_pos.y() + offset
        )
        self._dyn_text.show()
