"""Renderização de ícones desenhados via QPainter (sem depender de arquivos
de imagem externos) — compartilhado entre o ribbon (newsicad/ui/ribbon.py) e
o painel de camadas (newsicad/ui/layer_panel.py), pra não duplicar a lógica
de nitidez em telas HiDPI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

# Espaço de coordenadas lógico em que todo draw_fn desenha (independente da
# resolução final do bitmap — ver `_RENDER_SCALE` abaixo).
LOGICAL_CANVAS = 32
# Renderiza em resolução mais alta que o tamanho de exibição e marca
# `setDevicePixelRatio` de acordo — sem isso, o ícone fica borrado em
# qualquer tela com escala do Windows > 100% (notebook 4K/HiDPI comum).
RENDER_SCALE = 3
PIXMAP_SIZE = LOGICAL_CANVAS * RENDER_SCALE
STROKE_COLOR = "#d8d8d8"


def make_icon(draw_fn: Callable[[QPainter, QRectF], None], color: str = STROKE_COLOR) -> QIcon:
    pixmap = QPixmap(PIXMAP_SIZE, PIXMAP_SIZE)
    pixmap.setDevicePixelRatio(RENDER_SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # NÃO chamar painter.scale(RENDER_SCALE, ...) aqui: QPainter já aplica
    # esse fator sozinho porque o pixmap tem devicePixelRatio=RENDER_SCALE
    # (comportamento HiDPI padrão do Qt — coordenadas passadas ao painter
    # são "lógicas", a conversão pra pixel físico é automática). Uma versão
    # anterior desta função tinha as DUAS coisas ao mesmo tempo — um bug de
    # escala dupla (3x × 3x = 9x) que fazia praticamente todo ícone ser
    # desenhado fora dos limites físicos do pixmap e cortado silenciosamente
    # pelo próprio QPainter, sobrando só um fragmento perto da origem. Nunca
    # detectado porque não dava pra ver a janela rodando neste ambiente até
    # 2026-08-22 — reportado por Hamilton como "os ícones estão todos
    # cortados" assim que ele finalmente conseguiu ver a tela de verdade.
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    margin = 5.0
    rect = QRectF(margin, margin, LOGICAL_CANVAS - 2 * margin, LOGICAL_CANVAS - 2 * margin)
    draw_fn(painter, rect)
    painter.end()
    return QIcon(pixmap)


def _resources_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


# ---------------------------------------------------------------------- #
# ícones SVG (newsicad/resources/icons/*.svg) — conjunto desenhado em
# docs/design/ribbon-proposta-2026-09.html (aprovado pelo Hamilton em
# 03/09/2026). Cada arquivo é um SVG de 24x24 com o traço em `currentColor`
# (a cor da FAMÍLIA do painel: Draw laranja, Modify azul, Annotation roxo,
# neutro cinza) e as classes acc/fw (acento branco) e yl/yf (amarelo de
# lâmpada), resolvidas aqui por substituição de texto antes de renderizar —
# o QSvgRenderer do Qt não entende CSS de classe.
# ---------------------------------------------------------------------- #
FAMILY_DRAW = "#e8935a"
FAMILY_MODIFY = "#5b9bd5"
FAMILY_ANNOTATE = "#a586d9"
FAMILY_NEUTRAL = "#b8b8b8"
ACCENT_COLOR = "#ffffff"
DATA_YELLOW = "#f0c33e"
DISABLED_COLOR = "#5a5a5a"

_svg_cache: dict[tuple[str, str, str, int], QIcon] = {}
_svg_source_cache: dict[str, str] = {}


def _svg_source(name: str) -> str | None:
    if name in _svg_source_cache:
        return _svg_source_cache[name]
    path = _resources_dir() / "icons" / f"{name}.svg"
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        source = None
    _svg_source_cache[name] = source
    return source


def _svg_bytes(source: str, color: str, accent: str) -> bytes:
    text = source.replace("currentColor", color)
    text = text.replace('class="acc"', f'stroke="{accent}"')
    text = text.replace('class="fw"', f'fill="{accent}"')
    text = text.replace('class="yl"', f'stroke="{DATA_YELLOW}"')
    text = text.replace('class="yf"', f'fill="{DATA_YELLOW}"')
    return text.encode("utf-8")


def _render_svg(source: str, color: str, accent: str, size: int) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(_svg_bytes(source, color, accent))
    pixmap = QPixmap(size * RENDER_SCALE, size * RENDER_SCALE)
    pixmap.setDevicePixelRatio(RENDER_SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def svg_icon(name: str, color: str = FAMILY_NEUTRAL, size: int = 32, accent: str = ACCENT_COLOR) -> QIcon:
    """QIcon nítido em HiDPI (renderizado a RENDER_SCALE x) a partir de
    resources/icons/<name>.svg, com o traço em `color`. Traz também o estado
    desabilitado em cinza escuro (sem acento), pra botões `setEnabled(False)`
    não ficarem coloridos como se funcionassem. Cache por (nome, cor, acento,
    tamanho) — o mesmo ícone aparece no ribbon, no menu e no menu de
    contexto. Nome desconhecido devolve um QIcon vazio (não quebra a UI)."""
    key = (name, color, accent, size)
    cached = _svg_cache.get(key)
    if cached is not None:
        return cached
    source = _svg_source(name)
    icon = QIcon()
    if source is not None:
        icon.addPixmap(_render_svg(source, color, accent, size), QIcon.Mode.Normal)
        icon.addPixmap(_render_svg(source, DISABLED_COLOR, DISABLED_COLOR, size), QIcon.Mode.Disabled)
    _svg_cache[key] = icon
    return icon


def svg_toggle_icon(name: str, size: int = 16) -> QIcon:
    """Ícone de toggle da barra de status: cinza quando desligado, branco
    (com acento) quando ligado — o fundo azul do botão marcado faz o resto."""
    key = (name, "toggle", "", size)
    cached = _svg_cache.get(key)
    if cached is not None:
        return cached
    source = _svg_source(name)
    icon = QIcon()
    if source is not None:
        icon.addPixmap(_render_svg(source, "#a0a0a0", "#c8c8c8", size), QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(_render_svg(source, "#ffffff", "#ffffff", size), QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(_render_svg(source, DISABLED_COLOR, DISABLED_COLOR, size), QIcon.Mode.Disabled, QIcon.State.Off)
    _svg_cache[key] = icon
    return icon


# Ícone (nome do SVG + família de cor) de cada comando da linha de comando —
# usado pelo menu clássico (menu_bar.py), pelo menu de contexto do canvas e
# pelos flyouts do ribbon, pra o mesmo comando ter o mesmo ícone em todo lugar.
COMMAND_ICONS: dict[str, tuple[str, str]] = {
    "LINE": ("line", FAMILY_DRAW), "PLINE": ("pline", FAMILY_DRAW), "CIRCLE": ("circle", FAMILY_DRAW),
    "ARC": ("arc", FAMILY_DRAW), "RECTANG": ("rect", FAMILY_DRAW), "POLYGON": ("polygon", FAMILY_DRAW),
    "ELLIPSE": ("ellipse", FAMILY_DRAW), "SPLINE": ("spline", FAMILY_DRAW), "XLINE": ("xline", FAMILY_DRAW),
    "RAY": ("ray", FAMILY_DRAW), "POINT": ("point", FAMILY_DRAW), "DONUT": ("donut", FAMILY_DRAW),
    "REVCLOUD": ("revcloud", FAMILY_DRAW), "WIPEOUT": ("wipeout", FAMILY_DRAW), "MLINE": ("mline", FAMILY_DRAW),
    "HATCH": ("hatch", FAMILY_DRAW), "BOUNDARY": ("boundary", FAMILY_DRAW),
    "MOVE": ("move", FAMILY_MODIFY), "ROTATE": ("rotate", FAMILY_MODIFY), "TRIM": ("trim", FAMILY_MODIFY),
    "EXTEND": ("extend", FAMILY_MODIFY), "COPY": ("copy", FAMILY_MODIFY), "MIRROR": ("mirror", FAMILY_MODIFY),
    "FILLET": ("fillet", FAMILY_MODIFY), "CHAMFER": ("chamfer", FAMILY_MODIFY), "STRETCH": ("stretch", FAMILY_MODIFY),
    "SCALE": ("scale", FAMILY_MODIFY), "ARRAY": ("array", FAMILY_MODIFY), "ERASE": ("erase", FAMILY_MODIFY),
    "EXPLODE": ("explode", FAMILY_MODIFY), "OFFSET": ("offset", FAMILY_MODIFY), "BREAK": ("break", FAMILY_MODIFY),
    "BREAKATPOINT": ("breakpt", FAMILY_MODIFY), "JOIN": ("join", FAMILY_MODIFY), "LENGTHEN": ("lengthen", FAMILY_MODIFY),
    "PEDIT": ("pedit", FAMILY_MODIFY), "HATCHEDIT": ("hatchedit", FAMILY_MODIFY), "ALIGN": ("align", FAMILY_MODIFY),
    "DIVIDE": ("divide", FAMILY_MODIFY), "MEASURE": ("measure", FAMILY_MODIFY),
    "MTEXT": ("mtext", FAMILY_ANNOTATE), "DDEDIT": ("ddedit", FAMILY_ANNOTATE), "FIND": ("find", FAMILY_ANNOTATE),
    "STYLE": ("textstyle", FAMILY_ANNOTATE), "DIMLINEAR": ("dim", FAMILY_ANNOTATE),
    "DIMALIGNED": ("dimaligned", FAMILY_ANNOTATE), "DIMANGULAR": ("dimangular", FAMILY_ANNOTATE),
    "DIMRADIUS": ("dimradius", FAMILY_ANNOTATE), "DIMDIAMETER": ("dimdiameter", FAMILY_ANNOTATE),
    "CENTERMARK": ("centermark", FAMILY_ANNOTATE), "DIMBREAK": ("dimbreak", FAMILY_ANNOTATE),
    "DIMSTYLE": ("dimstyle", FAMILY_ANNOTATE), "LEADER": ("leader", FAMILY_ANNOTATE),
    "MLEADERSTYLE": ("mleaderstyle", FAMILY_ANNOTATE), "TABLE": ("table", FAMILY_ANNOTATE),
    "TABLESTYLE": ("tablestyle", FAMILY_ANNOTATE),
    "INSERT": ("insert", FAMILY_ANNOTATE), "BLOCK": ("block", FAMILY_ANNOTATE), "BEDIT": ("bedit", FAMILY_ANNOTATE),
    "FIELD": ("field", FAMILY_ANNOTATE), "DATALINK": ("datalink", FAMILY_ANNOTATE),
    "IMAGEATTACH": ("image", FAMILY_NEUTRAL), "XREF": ("xref", FAMILY_NEUTRAL),
    "EXTERNALREFERENCES": ("xrefpanel", FAMILY_NEUTRAL), "CLIP": ("clip", FAMILY_NEUTRAL),
    "CLIPOFF": ("clipoff", FAMILY_NEUTRAL), "IMPORTPDF": ("importpdf", FAMILY_NEUTRAL),
    "LAYER": ("layers", FAMILY_NEUTRAL), "LAYISO": ("layiso", FAMILY_NEUTRAL), "LAYUNISO": ("layuniso", FAMILY_NEUTRAL),
    "LAYMCH": ("laymch", FAMILY_NEUTRAL), "RENAME": ("rename", FAMILY_NEUTRAL),
    "MATCHPROP": ("matchprop", FAMILY_NEUTRAL), "QSELECT": ("qselect", FAMILY_NEUTRAL),
    "SELECTSIMILAR": ("selsim", FAMILY_NEUTRAL), "DIST": ("dist", FAMILY_NEUTRAL), "AREA": ("area", FAMILY_NEUTRAL),
    "ID": ("id", FAMILY_NEUTRAL), "PURGE": ("purge", FAMILY_NEUTRAL), "UNITS": ("units", FAMILY_NEUTRAL),
    "CUTCLIP": ("cut", FAMILY_NEUTRAL), "COPYCLIP": ("copyclip", FAMILY_NEUTRAL), "PASTECLIP": ("paste", FAMILY_NEUTRAL),
    "VIEWPORTS": ("viewports", FAMILY_NEUTRAL),
}


def command_icon(command_name: str, size: int = 16) -> QIcon:
    """Ícone do comando (ver COMMAND_ICONS) ou QIcon vazio se não houver."""
    entry = COMMAND_ICONS.get(command_name.upper())
    if entry is None:
        return QIcon()
    return svg_icon(entry[0], entry[1], size)


def resolve_app_icon_path() -> Path:
    """Caminho do logo NewSI (`.ico`) tanto rodando a partir do código-fonte
    quanto empacotado com PyInstaller (dados extras do build_windows.spec
    ficam soltos na raiz do bundle, `sys._MEIPASS`) — mesmo padrão de
    `newsicad/main.py:_icon_path` e `dwg_bridge.py:_bundled_bin_dir`,
    reaproveitado aqui pra não duplicar a lógica uma terceira vez (usado
    tanto pelo ícone da janela/taskbar quanto pelo logo dentro do próprio
    Quick Access Toolbar — ver `newsicad/ui/ribbon.py`)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "resources" / "newsi_icon.ico"
