"""Ribbon estilo AutoCAD (abas Home/Insert/Annotate/View, painéis com botões
grandes de ícone) — fica abaixo do menu clássico, não o substitui. Os ícones
são desenhados programaticamente via QPainter (formas geométricas simples),
sem depender de arquivos de imagem externos.

Cada botão dispara exatamente o mesmo caminho que digitar o comando na linha
de comando (`window._start_command(nome)`) ou chama os mesmos métodos que o
menu clássico já usa (`newsicad/ui/menu_bar.py`) — o ribbon é só mais uma
forma de disparar as mesmas ações, não uma via paralela de lógica.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStyleFactory,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from newsicad.ui.icon_utils import make_icon as _make_icon
from newsicad.ui.icon_utils import resolve_app_icon_path

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

ICON_SIZE = 28
NOT_IMPLEMENTED_TIP = "Ainda não implementado — previsto para um próximo marco do NewSIcad."

BUTTON_MIN_WIDTH = 58
BUTTON_HEIGHT = 54

# Cor por FAMÍLIA de painel (não por comando individual) — mesma lógica que o
# AutoCAD clássico usava pra agrupar visualmente os toolbars: dá o ar
# "ilustrado" sem virar um arco-íris por botão. Neutro pra painéis que não são
# de desenho/modificação/anotação de verdade (Utilities, navegação, arquivo).
COLOR_DRAW = "#e8935a"
COLOR_MODIFY = "#5b9bd5"
COLOR_EDIT = "#5cb88a"
COLOR_ANNOTATE = "#a586d9"
COLOR_NEUTRAL = "#a8a8a8"

RIBBON_STYLE = """
    QTabWidget {
        background-color: #232323;
    }
    QTabWidget::pane {
        border: none;
        background-color: #232323;
    }
    QTabWidget QWidget {
        background-color: #232323;
    }
    QTabBar {
        background-color: #232323;
        border: none;
    }
    QTabBar::tab {
        background-color: #232323;
        color: #a0a0a0;
        padding: 4px 14px;
        border: none;
    }
    QTabBar::tab:selected {
        background-color: #2f2f2f;
        color: #ffffff;
        border-bottom: 2px solid #4da3ff;
    }
    QToolButton {
        background-color: transparent;
        color: #d0d0d0;
        border: none;
        padding: 3px;
        font-size: 10px;
    }
    QToolButton:hover {
        background-color: #3a3a3a;
        border-radius: 3px;
    }
    QToolButton:checked {
        background-color: #3a5a8c;
        border-radius: 3px;
    }
    QToolButton:disabled {
        color: #5a5a5a;
    }
    QLabel#panelTitle {
        color: #808080;
        font-size: 10px;
        padding-top: 2px;
    }
    QToolButton#panelLauncher {
        color: #7a7a7a;
        font-size: 9px;
        padding: 0px 3px;
        border: none;
    }
    QToolButton#panelLauncher:hover {
        color: #d0d0d0;
        background-color: #3a3a3a;
        border-radius: 2px;
    }
"""


# ---------------------------------------------------------------------- #
# desenho (Draw)
# ---------------------------------------------------------------------- #
def _icon_line(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))


def _icon_polyline(p: QPainter, r: QRectF) -> None:
    path = QPainterPath(QPointF(r.left(), r.bottom()))
    path.lineTo(r.left() + r.width() * 0.35, r.top())
    path.lineTo(r.left() + r.width() * 0.65, r.bottom())
    path.lineTo(r.right(), r.top())
    p.drawPath(path)


def _icon_circle(p: QPainter, r: QRectF) -> None:
    p.drawEllipse(r)


def _icon_arc(p: QPainter, r: QRectF) -> None:
    path = QPainterPath()
    path.arcMoveTo(r, 30)
    path.arcTo(r, 30, 180)
    p.drawPath(path)


def _icon_rectangle(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)


def _icon_ellipse(p: QPainter, r: QRectF) -> None:
    center = r.center()
    p.save()
    p.translate(center)
    p.scale(1.0, 0.6)
    p.drawEllipse(QRectF(-r.width() / 2, -r.width() / 2, r.width(), r.width()))
    p.restore()


def _icon_polygon(p: QPainter, r: QRectF) -> None:
    sides = 6
    cx, cy = r.center().x(), r.center().y()
    rx, ry = r.width() / 2, r.height() / 2
    path = QPainterPath()
    for i in range(sides):
        angle = math.radians(90 + i * 360 / sides)
        pt = QPointF(cx + rx * math.cos(angle), cy - ry * math.sin(angle))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _icon_spline(p: QPainter, r: QRectF) -> None:
    path = QPainterPath(QPointF(r.left(), r.bottom()))
    path.cubicTo(
        QPointF(r.left() + r.width() * 0.15, r.top()),
        QPointF(r.left() + r.width() * 0.55, r.top()),
        QPointF(r.center().x(), r.center().y()),
    )
    path.cubicTo(
        QPointF(r.left() + r.width() * 0.75, r.bottom()),
        QPointF(r.right() - r.width() * 0.1, r.bottom()),
        QPointF(r.right(), r.top()),
    )
    p.drawPath(path)


def _icon_hatch(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    step = r.width() / 4
    x = r.left()
    while x < r.right():
        p.drawLine(QPointF(x, r.bottom()), QPointF(min(x + r.height(), r.right()), r.bottom() - min(x + r.height(), r.right()) + x))
        x += step


def _icon_revcloud(p: QPainter, r: QRectF) -> None:
    n = 8
    cx, cy = r.center().x(), r.center().y()
    rx, ry = r.width() / 2, r.height() / 2
    path = QPainterPath()
    for i in range(n + 1):
        angle = 2 * math.pi * i / n
        bulge = 1.0 + (0.12 if i % 2 == 0 else -0.06)
        pt = QPointF(cx + rx * bulge * math.cos(angle), cy + ry * bulge * math.sin(angle))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    p.drawPath(path)


def _icon_wipeout(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    p.drawLine(r.topLeft(), r.bottomRight())
    p.drawLine(r.topRight(), r.bottomLeft())


def _icon_centermark(p: QPainter, r: QRectF) -> None:
    p.drawEllipse(r)
    c = r.center()
    d = r.width() * 0.22
    p.drawLine(QPointF(c.x() - d, c.y()), QPointF(c.x() + d, c.y()))
    p.drawLine(QPointF(c.x(), c.y() - d), QPointF(c.x(), c.y() + d))


def _icon_qselect(p: QPainter, r: QRectF) -> None:
    p.drawRect(r.adjusted(0, 0, -r.width() * 0.3, -r.height() * 0.3))
    path = QPainterPath()
    path.moveTo(r.left() + r.width() * 0.25, r.top() + r.height() * 0.55)
    path.lineTo(r.left() + r.width() * 0.45, r.top() + r.height() * 0.75)
    path.lineTo(r.left() + r.width() * 0.8, r.top() + r.height() * 0.3)
    p.drawPath(path)


def _icon_layers(p: QPainter, r: QRectF) -> None:
    step = r.height() * 0.28
    height = r.height() * 0.5
    for i in range(3):
        y = r.top() + i * step
        p.drawRect(QRectF(r.left(), y, r.width(), height))


def _icon_create_block(p: QPainter, r: QRectF) -> None:
    """BLOCK (Create): contorno tracejado (seleção) virando um bloco sólido
    menor, com um "+" de criação no canto — distingue de Insert/Edit, que
    antes reaproveitavam `_icon_block` (ver artifact de mockup validado por
    Hamilton, 2026-08-22)."""
    solid = QPen(p.pen())
    dashed = QPen(solid)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawRect(QRectF(r.left() + 1, r.top() + 3, r.width() * 0.82, r.height() * 0.68))
    p.setPen(solid)
    p.drawRect(QRectF(r.left() + 5, r.top() + 7, r.width() * 0.45, r.height() * 0.32))
    plus_x = r.right() - 4
    plus_y = r.bottom() - 6
    p.drawLine(QPointF(plus_x - 1.5, plus_y), QPointF(plus_x + 1.5, plus_y))
    p.drawLine(QPointF(plus_x, plus_y - 1.5), QPointF(plus_x, plus_y + 1.5))


def _icon_insert_block(p: QPainter, r: QRectF) -> None:
    """INSERT: seta descendo até o ponto de inserção de um bloco já
    definido — a metáfora real do comando (posicionar algo pronto), em vez
    do losango genérico de `_icon_block`."""
    p.drawRect(QRectF(r.left() + 2, r.center().y(), r.width() - 4, r.bottom() - r.center().y()))
    top = r.top() - 1
    arrow_y = r.center().y() - 2
    p.drawLine(QPointF(r.center().x(), top), QPointF(r.center().x(), arrow_y))
    path = QPainterPath()
    path.moveTo(r.center().x() - 4, arrow_y - 4.5)
    path.lineTo(r.center().x(), arrow_y)
    path.lineTo(r.center().x() + 4, arrow_y - 4.5)
    p.drawPath(path)


def _icon_edit_block(p: QPainter, r: QRectF) -> None:
    """BEDIT: bloco + lápis no canto — mesma linguagem visual de "editar"
    já usada noutros ícones do app (DDEDIT/HATCHEDIT), aplicada aqui."""
    p.drawRect(QRectF(r.left(), r.top() + 1, r.width() * 0.62, r.height() * 0.62))
    pencil_start = QPointF(r.left() + r.width() * 0.42, r.bottom() - 2)
    pencil_tip = QPointF(r.right(), r.top() + r.height() * 0.28)
    p.drawLine(pencil_start, pencil_tip)
    path = QPainterPath()
    path.moveTo(pencil_tip.x() - 3.5, pencil_tip.y() + 3.5)
    path.lineTo(pencil_tip)
    path.lineTo(pencil_tip.x() - 3.5, pencil_tip.y() - 3.5)
    p.drawPath(path)


def _icon_attach_image(p: QPainter, r: QRectF) -> None:
    """IMAGEATTACH: moldura + sol/montanhas — ícone universal de "imagem",
    em vez do losango genérico de `_icon_block`."""
    p.drawRect(r)
    sun_c = QPointF(r.left() + r.width() * 0.27, r.top() + r.height() * 0.28)
    p.drawEllipse(sun_c, r.width() * 0.09, r.width() * 0.09)
    path = QPainterPath()
    path.moveTo(r.left(), r.bottom() - 3)
    path.lineTo(r.left() + r.width() * 0.3, r.top() + r.height() * 0.45)
    path.lineTo(r.left() + r.width() * 0.5, r.center().y())
    path.lineTo(r.left() + r.width() * 0.7, r.top() + r.height() * 0.22)
    path.lineTo(r.right(), r.top() + r.height() * 0.5)
    p.drawPath(path)


def _icon_attach_xref(p: QPainter, r: QRectF) -> None:
    """XREF: documento com canto dobrado + seta tracejada apontando pra
    fora — "geometria vem de outro arquivo", distinto de Attach Image/
    Xref Panel (antes os três eram o mesmo losango genérico)."""
    doc_w = r.width() * 0.55
    doc_right = r.left() + doc_w
    fold = 3.5
    path = QPainterPath()
    path.moveTo(r.left(), r.top())
    path.lineTo(r.left(), r.bottom() - 2)
    path.lineTo(doc_right, r.bottom() - 2)
    path.lineTo(doc_right, r.top() + fold)
    path.lineTo(doc_right - fold, r.top())
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(doc_right - fold, r.top()), QPointF(doc_right - fold, r.top() + fold))
    p.drawLine(QPointF(doc_right - fold, r.top() + fold), QPointF(doc_right, r.top() + fold))

    solid = QPen(p.pen())
    dashed = QPen(solid)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    arrow_start = QPointF(doc_right + 2, r.center().y() + 2)
    arrow_end = QPointF(r.right() - 1, r.bottom() - 1)
    p.drawLine(arrow_start, arrow_end)
    p.setPen(solid)
    path2 = QPainterPath()
    path2.moveTo(arrow_end.x() - 4.5, arrow_end.y())
    path2.lineTo(arrow_end)
    path2.lineTo(arrow_end.x(), arrow_end.y() - 4.5)
    p.drawPath(path2)


def _icon_xref_panel(p: QPainter, r: QRectF) -> None:
    """EXTERNALREFERENCES: painel com cabeçalho + linhas de lista — mesma
    ideia do painel de Layers de verdade (lista de itens), em vez do
    losango genérico de `_icon_block`."""
    p.drawRect(r)
    header_y = r.top() + r.height() * 0.26
    p.drawLine(QPointF(r.left(), header_y), QPointF(r.right(), header_y))
    row_step = (r.bottom() - header_y) / 3
    for i in range(1, 3):
        y = header_y + row_step * i
        p.drawLine(QPointF(r.left() + 2.5, y), QPointF(r.right() - 2.5, y))


# ---------------------------------------------------------------------- #
# modificação (Modify)
# ---------------------------------------------------------------------- #
def _icon_move(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
    p.drawLine(QPointF(r.right(), r.center().y()), QPointF(r.right() - 6, r.center().y() - 5))
    p.drawLine(QPointF(r.right(), r.center().y()), QPointF(r.right() - 6, r.center().y() + 5))


def _icon_copy(p: QPainter, r: QRectF) -> None:
    back = QRectF(r.left(), r.top(), r.width() * 0.7, r.height() * 0.7)
    front = QRectF(r.right() - r.width() * 0.7, r.bottom() - r.height() * 0.7, r.width() * 0.7, r.height() * 0.7)
    p.drawRect(back)
    p.drawRect(front)


def _icon_cut(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom()))
    p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))
    ring_size = r.width() * 0.22
    p.drawEllipse(QPointF(r.left() + ring_size * 0.6, r.top() + ring_size * 0.6), ring_size / 2, ring_size / 2)
    p.drawEllipse(QPointF(r.left() + ring_size * 0.6, r.bottom() - ring_size * 0.6), ring_size / 2, ring_size / 2)


def _icon_paste(p: QPainter, r: QRectF) -> None:
    board = r.adjusted(r.width() * 0.12, r.height() * 0.05, -r.width() * 0.12, 0)
    p.drawRect(board)
    clip = QRectF(board.center().x() - board.width() * 0.22, board.top() - r.height() * 0.05, board.width() * 0.44, r.height() * 0.12)
    p.drawRect(clip)
    for i in range(3):
        y = board.top() + board.height() * (0.35 + i * 0.2)
        p.drawLine(QPointF(board.left() + 3, y), QPointF(board.right() - 3, y))


def _icon_copyclip(p: QPainter, r: QRectF) -> None:
    """COPYCLIP: mesma silhueta de prancheta de `_icon_paste` (pra ficar da
    mesma família visual), com duas páginas sobrepostas dentro em vez das
    linhas de texto — distingue de `_icon_copy` (usado pelo COPY do CAD,
    sem prancheta ao redor) e reaproveitava esse mesmo `_icon_copy` até
    aqui, deixando Cut/Copy/Paste com dois ícones iguais lado a lado (achado
    de auditoria, 2026-08-22)."""
    board = r.adjusted(r.width() * 0.12, r.height() * 0.05, -r.width() * 0.12, 0)
    p.drawRect(board)
    clip = QRectF(board.center().x() - board.width() * 0.22, board.top() - r.height() * 0.05, board.width() * 0.44, r.height() * 0.12)
    p.drawRect(clip)
    back = QRectF(board.left() + board.width() * 0.16, board.top() + board.height() * 0.3, board.width() * 0.45, board.height() * 0.45)
    front = QRectF(board.left() + board.width() * 0.4, board.top() + board.height() * 0.42, board.width() * 0.45, board.height() * 0.45)
    p.drawRect(back)
    p.drawRect(front)


def _icon_clip(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    corner = r.width() * 0.4
    p.drawLine(QPointF(r.right() - corner, r.top()), QPointF(r.right(), r.top() + corner))
    p.drawLine(QPointF(r.right() - corner, r.top()), QPointF(r.right() - corner, r.top() + corner))
    p.drawLine(QPointF(r.right() - corner, r.top() + corner), QPointF(r.right(), r.top() + corner))


def _icon_field(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    p.drawLine(QPointF(r.left() + r.width() * 0.25, r.top() + 3), QPointF(r.left() + r.width() * 0.25, r.bottom() - 3))
    p.drawLine(QPointF(r.left() + r.width() * 0.25, r.top() + 3), QPointF(r.right() - 3, r.top() + 3))
    p.drawLine(QPointF(r.left() + r.width() * 0.25, r.center().y()), QPointF(r.right() - r.width() * 0.25, r.center().y()))


def _icon_rotate(p: QPainter, r: QRectF) -> None:
    path = QPainterPath()
    path.arcMoveTo(r, 30)
    path.arcTo(r, 30, 300)
    p.drawPath(path)
    end_angle = math.radians(30 + 300)
    cx, cy = r.center().x(), r.center().y()
    rx, ry = r.width() / 2, r.height() / 2
    tip = QPointF(cx + rx * math.cos(end_angle), cy - ry * math.sin(end_angle))
    p.drawLine(tip, QPointF(tip.x() - 6, tip.y() - 2))
    p.drawLine(tip, QPointF(tip.x() - 2, tip.y() + 6))


def _icon_mirror(p: QPainter, r: QRectF) -> None:
    mid_x = r.center().x()
    pen = p.pen()
    dashed = QPen(pen)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawLine(QPointF(mid_x, r.top()), QPointF(mid_x, r.bottom()))
    p.setPen(pen)
    left = QPainterPath(QPointF(r.left(), r.bottom()))
    left.lineTo(mid_x - 3, r.bottom())
    left.lineTo(r.left(), r.top())
    left.closeSubpath()
    right = QPainterPath(QPointF(r.right(), r.bottom()))
    right.lineTo(mid_x + 3, r.bottom())
    right.lineTo(r.right(), r.top())
    right.closeSubpath()
    p.drawPath(left)
    p.drawPath(right)


def _icon_scale(p: QPainter, r: QRectF) -> None:
    small = QRectF(r.left(), r.center().y(), r.width() * 0.4, r.height() * 0.4)
    big = QRectF(r.left(), r.top(), r.width(), r.height())
    p.drawRect(small)
    p.drawRect(big)


def _icon_align(p: QPainter, r: QRectF) -> None:
    src = QRectF(r.left(), r.bottom() - r.height() * 0.4, r.width() * 0.4, r.height() * 0.4)
    dst = QRectF(r.right() - r.width() * 0.4, r.top(), r.width() * 0.4, r.height() * 0.4)
    p.drawRect(src)
    p.drawRect(dst)
    dashed = QPen(p.pen())
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawLine(src.center(), dst.center())
    p.setPen(QPen(p.pen().color(), p.pen().widthF()))


def _icon_array(p: QPainter, r: QRectF) -> None:
    cell_w, cell_h = r.width() * 0.35, r.height() * 0.35
    for row in range(2):
        for col in range(2):
            x = r.left() + col * (r.width() - cell_w)
            y = r.top() + row * (r.height() - cell_h)
            p.drawRect(QRectF(x, y, cell_w, cell_h))


def _icon_erase(p: QPainter, r: QRectF) -> None:
    p.drawLine(r.topLeft(), r.bottomRight())
    p.drawLine(r.topRight(), r.bottomLeft())


def _icon_match_props(p: QPainter, r: QRectF) -> None:
    small = QRectF(r.left(), r.top(), r.width() * 0.5, r.height() * 0.5)
    p.drawRect(small)
    p.drawLine(QPointF(r.right(), r.top()), QPointF(r.left() + small.width() * 0.7, r.top() + small.height() * 0.7))


# ---------------------------------------------------------------------- #
# edição geométrica (TRIM/EXTEND/OFFSET/FILLET/CHAMFER/EXPLODE/JOIN/STRETCH)
# ---------------------------------------------------------------------- #
def _icon_trim(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
    p.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
    cx = r.center().x() + (r.right() - r.center().x()) * 0.55
    cy = r.center().y()
    d = 3
    p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
    p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))


def _icon_extend(p: QPainter, r: QRectF) -> None:
    y = r.center().y()
    solid = QPen(p.pen())
    p.drawLine(QPointF(r.left(), y), QPointF(r.left() + r.width() * 0.5, y))
    dashed = QPen(solid)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawLine(QPointF(r.left() + r.width() * 0.5, y), QPointF(r.right(), y))
    p.setPen(solid)
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 6, y - 5))
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 6, y + 5))


def _icon_break(p: QPainter, r: QRectF) -> None:
    """BREAK: uma linha com um vão de verdade no meio (dois tracinhos
    perpendiculares marcando onde o corte entra/sai) — distinto de
    `_icon_trim` (que também era usado aqui, achado de auditoria,
    2026-08-22): Trim é sobre CORTAR contra uma borda, Break é sobre
    REMOVER um trecho entre dois pontos."""
    y = r.center().y()
    gap = r.width() * 0.22
    p.drawLine(QPointF(r.left(), y), QPointF(r.center().x() - gap / 2, y))
    p.drawLine(QPointF(r.center().x() + gap / 2, y), QPointF(r.right(), y))
    tick = 4.0
    p.drawLine(QPointF(r.center().x() - gap / 2, y - tick), QPointF(r.center().x() - gap / 2, y + tick))
    p.drawLine(QPointF(r.center().x() + gap / 2, y - tick), QPointF(r.center().x() + gap / 2, y + tick))


def _icon_lengthen(p: QPainter, r: QRectF) -> None:
    """LENGTHEN: uma linha curta com uma seta dupla ao lado indicando
    "esticar" — distinto de `_icon_extend` (que também era usado aqui,
    achado de auditoria, 2026-08-22): Extend é sobre alcançar uma borda
    específica, Lengthen é sobre alterar o comprimento por um valor."""
    y = r.center().y()
    p.drawLine(QPointF(r.left(), y), QPointF(r.left() + r.width() * 0.45, y))
    ax = r.right() - r.width() * 0.18
    p.drawLine(QPointF(ax, y), QPointF(r.right(), y))
    p.drawLine(QPointF(ax, y), QPointF(ax + 5, y - 4))
    p.drawLine(QPointF(ax, y), QPointF(ax + 5, y + 4))
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 5, y - 4))
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 5, y + 4))


def _icon_offset(p: QPainter, r: QRectF) -> None:
    solid = QPen(p.pen())
    p.drawRect(r)
    dashed = QPen(solid)
    dashed.setStyle(Qt.PenStyle.DashLine)
    p.setPen(dashed)
    p.drawRect(r.adjusted(5, 5, -5, -5))
    p.setPen(solid)


def _icon_fillet(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom() - 8))
    p.drawLine(QPointF(r.left() + 8, r.bottom()), QPointF(r.right(), r.bottom()))
    corner_rect = QRectF(r.left(), r.bottom() - 16, 16, 16)
    path = QPainterPath()
    path.arcMoveTo(corner_rect, 180)
    path.arcTo(corner_rect, 180, -90)
    p.drawPath(path)


def _icon_chamfer(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom() - 8))
    p.drawLine(QPointF(r.left() + 8, r.bottom()), QPointF(r.right(), r.bottom()))
    p.drawLine(QPointF(r.left(), r.bottom() - 8), QPointF(r.left() + 8, r.bottom()))


def _icon_explode(p: QPainter, r: QRectF) -> None:
    c = r.center()
    for angle_deg in (20, 90, 160, 230, 300, 340):
        angle = math.radians(angle_deg)
        inner = QPointF(c.x() + 3 * math.cos(angle), c.y() - 3 * math.sin(angle))
        outer = QPointF(c.x() + (r.width() / 2) * math.cos(angle), c.y() - (r.width() / 2) * math.sin(angle))
        p.drawLine(inner, outer)


def _icon_join(p: QPainter, r: QRectF) -> None:
    y = r.center().y()
    p.drawLine(QPointF(r.left(), y), QPointF(r.left() + r.width() * 0.4, y))
    p.drawLine(QPointF(r.left() + r.width() * 0.6, y), QPointF(r.right(), y))
    p.drawEllipse(QPointF(r.center().x(), y), 2.5, 2.5)


def _icon_stretch(p: QPainter, r: QRectF) -> None:
    p.drawRect(QRectF(r.left(), r.top(), r.width() * 0.55, r.height()))
    y = r.center().y()
    p.drawLine(QPointF(r.left() + r.width() * 0.55, y), QPointF(r.right(), y))
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 6, y - 5))
    p.drawLine(QPointF(r.right(), y), QPointF(r.right() - 6, y + 5))


def _icon_point(p: QPainter, r: QRectF) -> None:
    """POINT: uma cruz central pequena, igual ao marcador que `PointEntity`
    de verdade desenha no canvas (`CanvasView`, tamanho constante em tela) —
    antes reaproveitava `_icon_divide` (o traço de "dividir em N partes"),
    que não tem nada a ver com criar um ponto único (achado de auditoria,
    2026-08-22)."""
    c = r.center()
    d = r.width() * 0.22
    p.drawLine(QPointF(c.x() - d, c.y()), QPointF(c.x() + d, c.y()))
    p.drawLine(QPointF(c.x(), c.y() - d), QPointF(c.x(), c.y() + d))
    p.drawEllipse(c, 1.6, 1.6)


def _icon_divide(p: QPainter, r: QRectF) -> None:
    y = r.center().y()
    p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
    step = r.width() / 4
    x = r.left()
    while x <= r.right() + 0.01:
        p.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        x += step


def _icon_measure(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    step = r.width() / 4
    x = r.left() + step
    while x < r.right():
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.top() + r.height() * 0.3))
        x += step


# ---------------------------------------------------------------------- #
# arquivo / utilidades / navegação
# ---------------------------------------------------------------------- #
def _icon_new(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    p.drawLine(QPointF(r.center().x(), r.top() + 4), QPointF(r.center().x(), r.bottom() - 4))
    p.drawLine(QPointF(r.left() + 4, r.center().y()), QPointF(r.right() - 4, r.center().y()))


def _icon_open(p: QPainter, r: QRectF) -> None:
    path = QPainterPath(QPointF(r.left(), r.top() + 4))
    path.lineTo(r.left() + r.width() * 0.35, r.top() + 4)
    path.lineTo(r.left() + r.width() * 0.45, r.top())
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.closeSubpath()
    p.drawPath(path)


def _icon_save(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    inner = QRectF(r.left() + r.width() * 0.2, r.top(), r.width() * 0.6, r.height() * 0.45)
    p.drawRect(inner)


def _icon_export_pdf(p: QPainter, r: QRectF) -> None:
    """Export PDF: página com canto dobrado + seta pra fora saindo por
    baixo — "exportar/gerar arquivo", distinto do disquete de `_icon_save`
    (que também era usado aqui, achado de auditoria, 2026-08-22): Save
    grava o próprio `.dxf`, Export PDF gera um arquivo derivado."""
    fold = r.width() * 0.25
    path = QPainterPath()
    path.moveTo(r.left(), r.top())
    path.lineTo(r.right() - fold, r.top())
    path.lineTo(r.right(), r.top() + fold)
    path.lineTo(r.right(), r.top() + r.height() * 0.62)
    path.lineTo(r.left(), r.top() + r.height() * 0.62)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(r.right() - fold, r.top()), QPointF(r.right() - fold, r.top() + fold))
    p.drawLine(QPointF(r.right() - fold, r.top() + fold), QPointF(r.right(), r.top() + fold))
    cx = r.center().x()
    arrow_top = r.top() + r.height() * 0.7
    p.drawLine(QPointF(cx, arrow_top), QPointF(cx, r.bottom()))
    p.drawLine(QPointF(cx, r.bottom()), QPointF(cx - 4, r.bottom() - 5))
    p.drawLine(QPointF(cx, r.bottom()), QPointF(cx + 4, r.bottom() - 5))


def _icon_undo(p: QPainter, r: QRectF) -> None:
    path = QPainterPath()
    path.arcMoveTo(r, 200)
    path.arcTo(r, 200, 220)
    p.drawPath(path)
    p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.left() + 7, r.center().y() - 6))
    p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.left() + 3, r.center().y() + 7))


def _icon_redo(p: QPainter, r: QRectF) -> None:
    path = QPainterPath()
    path.arcMoveTo(r, -20)
    path.arcTo(r, -20, -220)
    p.drawPath(path)
    p.drawLine(QPointF(r.right(), r.center().y()), QPointF(r.right() - 7, r.center().y() - 6))
    p.drawLine(QPointF(r.right(), r.center().y()), QPointF(r.right() - 3, r.center().y() + 7))


def _icon_zoom_in(p: QPainter, r: QRectF) -> None:
    circle = QRectF(r.left(), r.top(), r.width() * 0.7, r.height() * 0.7)
    p.drawEllipse(circle)
    c = circle.center()
    p.drawLine(QPointF(c.x() - 4, c.y()), QPointF(c.x() + 4, c.y()))
    p.drawLine(QPointF(c.x(), c.y() - 4), QPointF(c.x(), c.y() + 4))
    p.drawLine(circle.center() + QPointF(circle.width() / 2 * 0.7, circle.height() / 2 * 0.7), r.bottomRight())


def _icon_zoom_out(p: QPainter, r: QRectF) -> None:
    circle = QRectF(r.left(), r.top(), r.width() * 0.7, r.height() * 0.7)
    p.drawEllipse(circle)
    c = circle.center()
    p.drawLine(QPointF(c.x() - 4, c.y()), QPointF(c.x() + 4, c.y()))
    p.drawLine(circle.center() + QPointF(circle.width() / 2 * 0.7, circle.height() / 2 * 0.7), r.bottomRight())


def _icon_zoom_extents(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    d = 5
    for corner in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
        p.drawEllipse(corner, 1.5, 1.5)
    p.drawLine(r.topLeft(), r.topLeft() + QPointF(d, 0))
    p.drawLine(r.topLeft(), r.topLeft() + QPointF(0, d))


def _icon_text(p: QPainter, r: QRectF) -> None:
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.right(), r.top()))
    p.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
    p.drawLine(QPointF(r.left() + 3, r.bottom()), QPointF(r.right() - 3, r.bottom()))


def _icon_table(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    step_x = r.width() / 3
    step_y = r.height() / 3
    for i in (1, 2):
        p.drawLine(QPointF(r.left() + step_x * i, r.top()), QPointF(r.left() + step_x * i, r.bottom()))
        p.drawLine(QPointF(r.left(), r.top() + step_y * i), QPointF(r.right(), r.top() + step_y * i))


def _icon_dimension(p: QPainter, r: QRectF) -> None:
    y = r.center().y()
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
    p.drawLine(QPointF(r.right(), r.top()), QPointF(r.right(), r.bottom()))
    p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))


def _icon_distance(p: QPainter, r: QRectF) -> None:
    """DIST: uma linha diagonal só com seta nas duas pontas, sem as linhas
    de extensão de `_icon_dimension` (que também era usado aqui, achado de
    auditoria, 2026-08-22) — DIST é uma consulta pontual (não cria uma
    entidade de cota persistente), então o ícone não devia prometer a
    mesma geometria de cota de verdade."""
    p1 = QPointF(r.left(), r.bottom())
    p2 = QPointF(r.right(), r.top())
    p.drawLine(p1, p2)
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    perp_x, perp_y = -uy, ux
    for base, direction in ((p1, 1), (p2, -1)):
        tip = QPointF(base.x() + ux * 6 * direction, base.y() + uy * 6 * direction)
        p.drawLine(base, QPointF(tip.x() + perp_x * 3, tip.y() + perp_y * 3))
        p.drawLine(base, QPointF(tip.x() - perp_x * 3, tip.y() - perp_y * 3))


def _icon_dimension_aligned(p: QPainter, r: QRectF) -> None:
    p.save()
    p.translate(r.center())
    p.rotate(-25)
    half_w, half_h = r.width() / 2, 4.0
    p.drawLine(QPointF(-half_w, -half_h), QPointF(-half_w, half_h))
    p.drawLine(QPointF(half_w, -half_h), QPointF(half_w, half_h))
    p.drawLine(QPointF(-half_w, 0), QPointF(half_w, 0))
    p.restore()


def _icon_dimension_angular(p: QPainter, r: QRectF) -> None:
    p.drawLine(r.bottomLeft(), r.bottomRight())
    p.drawLine(r.bottomLeft(), r.topLeft())
    path = QPainterPath()
    path.arcMoveTo(QRectF(r.left() - r.width() * 0.4, r.bottom() - r.height() * 0.4, r.width() * 0.8, r.height() * 0.8), 0)
    path.arcTo(QRectF(r.left() - r.width() * 0.4, r.bottom() - r.height() * 0.4, r.width() * 0.8, r.height() * 0.8), 0, 90)
    p.drawPath(path)


def _icon_dimension_radius(p: QPainter, r: QRectF) -> None:
    p.drawEllipse(r)
    c = r.center()
    p.drawLine(c, QPointF(r.right(), r.top()))


def _icon_dimension_diameter(p: QPainter, r: QRectF) -> None:
    p.drawEllipse(r)
    p.drawLine(r.topLeft(), r.bottomRight())


def _icon_leader(p: QPainter, r: QRectF) -> None:
    tip = QPointF(r.left(), r.bottom())
    bend = QPointF(r.left() + r.width() * 0.4, r.top() + r.height() * 0.3)
    end = QPointF(r.right(), r.top() + r.height() * 0.3)
    p.drawLine(tip, bend)
    p.drawLine(bend, end)
    p.drawLine(tip, QPointF(tip.x() + 6, tip.y() - 2))
    p.drawLine(tip, QPointF(tip.x() + 2, tip.y() - 7))


# ---------------------------------------------------------------------- #
# View tab (Grid/Ortho/Snap) e comandos novos (VIEWPORTS/STYLE/TABLESTYLE/
# MLEADERSTYLE/FIND/DATALINK) — pedido explícito do Hamilton pra caprichar
# nos ícones em vez de reaproveitar o genérico `_icon_rectangle` (2026-08-22)
# ---------------------------------------------------------------------- #
def _icon_grid(p: QPainter, r: QRectF) -> None:
    step_x = r.width() / 3
    step_y = r.height() / 3
    for row in range(4):
        for col in range(4):
            pt = QPointF(r.left() + col * step_x, r.top() + row * step_y)
            p.drawPoint(pt)
            p.drawEllipse(pt, 0.6, 0.6)


def _icon_ortho(p: QPainter, r: QRectF) -> None:
    corner = QPointF(r.left(), r.bottom())
    p.drawLine(corner, QPointF(r.left(), r.top()))
    p.drawLine(corner, QPointF(r.right(), r.bottom()))
    d = 3.5
    p.drawRect(QRectF(corner.x(), corner.y() - d, d, d))


def _icon_snap(p: QPainter, r: QRectF) -> None:
    c = r.center()
    p.drawLine(QPointF(r.left(), c.y()), QPointF(r.right(), c.y()))
    p.drawLine(QPointF(c.x(), r.top()), QPointF(c.x(), r.bottom()))
    p.drawEllipse(c, 2.6, 2.6)


def _icon_viewports(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    p.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
    p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))


def _icon_text_style(p: QPainter, r: QRectF) -> None:
    """STYLE: um "A" estilizado — linguagem visual comum de seletor de
    fonte/estilo de texto, distinto do ícone de MTEXT (`_icon_text`, um
    parágrafo com linhas)."""
    apex = QPointF(r.center().x(), r.top())
    base_l = QPointF(r.left() + 1, r.bottom())
    base_r = QPointF(r.right() - 1, r.bottom())
    p.drawLine(apex, base_l)
    p.drawLine(apex, base_r)
    mid_y = r.top() + r.height() * 0.62
    frac = (mid_y - r.top()) / (r.bottom() - r.top())
    p.drawLine(
        QPointF(apex.x() - (apex.x() - base_l.x()) * frac, mid_y),
        QPointF(apex.x() + (base_r.x() - apex.x()) * frac, mid_y),
    )


def _icon_table_style(p: QPainter, r: QRectF) -> None:
    """TABLESTYLE: a mesma grade de `_icon_table`, com um lápis no canto —
    mesma linguagem de "editar/configurar" já usada em `_icon_edit_block`,
    distinguindo do comando TABLE em si."""
    grid = QRectF(r.left(), r.top() + 1, r.width() * 0.62, r.height() * 0.62)
    p.drawRect(grid)
    step_x, step_y = grid.width() / 2, grid.height() / 2
    p.drawLine(QPointF(grid.left() + step_x, grid.top()), QPointF(grid.left() + step_x, grid.bottom()))
    p.drawLine(QPointF(grid.left(), grid.top() + step_y), QPointF(grid.right(), grid.top() + step_y))
    pencil_start = QPointF(grid.left() + grid.width() * 0.5, grid.bottom() - 1)
    pencil_tip = QPointF(r.right(), r.top() + r.height() * 0.28)
    p.drawLine(pencil_start, pencil_tip)
    path = QPainterPath()
    path.moveTo(pencil_tip.x() - 3.5, pencil_tip.y() + 3.5)
    path.lineTo(pencil_tip)
    path.lineTo(pencil_tip.x() - 3.5, pencil_tip.y() - 3.5)
    p.drawPath(path)


def _icon_mleader_style(p: QPainter, r: QRectF) -> None:
    """MLEADERSTYLE: a mesma seta de `_icon_leader`, com um lápis no canto —
    mesmo par visual de TABLE/TABLESTYLE, aplicado a LEADER."""
    tip = QPointF(r.left(), r.bottom())
    bend = QPointF(r.left() + r.width() * 0.35, r.top() + r.height() * 0.55)
    end = QPointF(r.left() + r.width() * 0.62, r.top() + r.height() * 0.55)
    p.drawLine(tip, bend)
    p.drawLine(bend, end)
    p.drawLine(tip, QPointF(tip.x() + 5, tip.y() - 1.5))
    p.drawLine(tip, QPointF(tip.x() + 1.5, tip.y() - 6))
    pencil_tip = QPointF(r.right(), r.top())
    p.drawLine(end, pencil_tip)
    path = QPainterPath()
    path.moveTo(pencil_tip.x() - 3.5, pencil_tip.y() + 3.5)
    path.lineTo(pencil_tip)
    path.lineTo(pencil_tip.x() - 3.5, pencil_tip.y() - 3.5)
    p.drawPath(path)


def _icon_find(p: QPainter, r: QRectF) -> None:
    glass = QRectF(r.left(), r.top(), r.width() * 0.68, r.height() * 0.68)
    p.drawEllipse(glass)
    p.drawLine(
        QPointF(glass.right() - 2, glass.bottom() - 2),
        QPointF(r.right(), r.bottom()),
    )


def _icon_datalink(p: QPainter, r: QRectF) -> None:
    """DATALINK: grade pequena de tabela + um link/corrente no canto —
    distingue de TABLE (dados vêm de fora, não digitados célula a célula)."""
    grid = QRectF(r.left(), r.top() + r.height() * 0.28, r.width() * 0.62, r.height() * 0.62)
    p.drawRect(grid)
    p.drawLine(
        QPointF(grid.left() + grid.width() / 2, grid.top()),
        QPointF(grid.left() + grid.width() / 2, grid.bottom()),
    )
    p.drawLine(
        QPointF(grid.left(), grid.top() + grid.height() / 2),
        QPointF(grid.right(), grid.top() + grid.height() / 2),
    )
    link1 = QPointF(r.right() - 5, r.top() + 3)
    link2 = QPointF(r.right() - 1, r.top() + 7)
    p.drawEllipse(link1, 2.6, 2.6)
    p.drawEllipse(link2, 2.6, 2.6)


# ---------------------------------------------------------------------- #
# construção de botões / painéis
# ---------------------------------------------------------------------- #
def _button(
    label: str,
    draw_fn: Callable[[QPainter, QRectF], None],
    handler: Callable[[], None] | None = None,
    checkable: bool = False,
    tooltip: str | None = None,
    color: str = COLOR_NEUTRAL,
) -> QToolButton:
    button = QToolButton()
    button.setIcon(_make_icon(draw_fn, color))
    button.setIconSize(_icon_qsize())
    button.setText(label)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setFixedSize(_button_width_for(label), BUTTON_HEIGHT)
    button.setCheckable(checkable)
    if handler is not None:
        button.clicked.connect(handler)
    else:
        button.setEnabled(False)
        button.setToolTip(tooltip or NOT_IMPLEMENTED_TIP)
    return button


def _icon_qsize() -> QSize:
    return QSize(ICON_SIZE, ICON_SIZE)


def _button_width_for(label: str) -> int:
    """Largura do botão: BUTTON_MIN_WIDTH pros rótulos curtos (a maioria),
    ou o suficiente pro texto de rótulos compostos de 2 palavras (ex.:
    "Multiline Text", "Attach Image") não truncar com "...". Calculado sob
    demanda (não em import time) porque QFontMetrics precisa de uma
    QApplication já criada."""
    font = QFont()
    font.setPointSize(10)  # mesmo tamanho do "font-size: 10px" do QToolButton em RIBBON_STYLE
    text_width = QFontMetrics(font).horizontalAdvance(label)
    return max(BUTTON_MIN_WIDTH, text_width + 12)


def _panel(title: str, buttons: list[QToolButton], launcher: Callable[[], None] | None = None) -> QWidget:
    """`launcher`: se dado, mostra uma setinha ↘ no rodapé do painel (mesma
    posição do "dialog box launcher" do AutoCAD) que dispara um comando
    relacionado — só usado onde existe mesmo uma ação real por trás (ex.:
    o painel de Dimensions abre DIMSTYLE), nunca como decoração."""
    container = QWidget()
    outer = QVBoxLayout(container)
    outer.setContentsMargins(6, 4, 6, 2)
    outer.setSpacing(2)

    row = QHBoxLayout()
    row.setSpacing(2)
    for button in buttons:
        row.addWidget(button)
    outer.addLayout(row)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(2)
    title_row.addStretch(1)
    label = QLabel(title)
    label.setObjectName("panelTitle")
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    title_row.addWidget(label)
    title_row.addStretch(1)
    if launcher is not None:
        launcher_btn = QToolButton()
        launcher_btn.setText("↘")
        launcher_btn.setObjectName("panelLauncher")
        launcher_btn.setToolTip("Mais opções")
        launcher_btn.clicked.connect(launcher)
        title_row.addWidget(launcher_btn)
    outer.addLayout(title_row)

    return container


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: #3a3a3a;")
    return line


def _row(widgets: list[QWidget]) -> QWidget:
    """Monta o conteúdo de uma aba (painéis lado a lado) dentro de um
    QScrollArea horizontal — sem isso, numa janela mais estreita que a soma
    dos painéis (ex.: aba Home, com bastante coisa), os botões mais à
    direita ficavam simplesmente cortados fora da tela, sem nenhum jeito de
    alcançá-los."""
    page = QWidget()
    layout = QHBoxLayout(page)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(4)
    for i, w in enumerate(widgets):
        if i > 0:
            layout.addWidget(_separator())
        layout.addWidget(w)
    layout.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidget(page)
    scroll.setWidgetResizable(False)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea { background-color: #232323; border: none; }")
    return scroll


# ---------------------------------------------------------------------- #
# abas
# ---------------------------------------------------------------------- #
def _build_home_tab(window: "MainWindow") -> QWidget:
    draw_panel = _panel(
        "Draw",
        [
            _button("Line", _icon_line, lambda: window._start_command("LINE"), color=COLOR_DRAW),
            _button("Polyline", _icon_polyline, lambda: window._start_command("PLINE"), color=COLOR_DRAW),
            _button("Circle", _icon_circle, lambda: window._start_command("CIRCLE"), color=COLOR_DRAW),
            _button("Arc", _icon_arc, lambda: window._start_command("ARC"), color=COLOR_DRAW),
            _button("Rectangle", _icon_rectangle, lambda: window._start_command("RECTANG"), color=COLOR_DRAW),
            _button("Ellipse", _icon_ellipse, lambda: window._start_command("ELLIPSE"), color=COLOR_DRAW),
            _button("Polygon", _icon_polygon, lambda: window._start_command("POLYGON"), color=COLOR_DRAW),
            _button("Spline", _icon_spline, lambda: window._start_command("SPLINE"), color=COLOR_DRAW),
            _button("Revision Cloud", _icon_revcloud, lambda: window._start_command("REVCLOUD"), color=COLOR_DRAW),
            _button("Wipeout", _icon_wipeout, lambda: window._start_command("WIPEOUT"), color=COLOR_DRAW),
        ],
    )

    clipboard_panel = _panel(
        "Clipboard",
        [
            _button("Cut", _icon_cut, lambda: window._start_command("CUTCLIP"), color=COLOR_NEUTRAL),
            _button("Copy", _icon_copyclip, lambda: window._start_command("COPYCLIP"), color=COLOR_NEUTRAL),
            _button("Paste", _icon_paste, lambda: window._start_command("PASTECLIP"), color=COLOR_NEUTRAL),
        ],
    )

    modify_panel = _panel(
        "Modify",
        [
            _button("Move", _icon_move, lambda: window._start_command("MOVE"), color=COLOR_MODIFY),
            _button("Copy", _icon_copy, lambda: window._start_command("COPY"), color=COLOR_MODIFY),
            _button("Rotate", _icon_rotate, lambda: window._start_command("ROTATE"), color=COLOR_MODIFY),
            _button("Mirror", _icon_mirror, lambda: window._start_command("MIRROR"), color=COLOR_MODIFY),
            _button("Scale", _icon_scale, lambda: window._start_command("SCALE"), color=COLOR_MODIFY),
            _button("Align", _icon_align, lambda: window._start_command("ALIGN"), color=COLOR_MODIFY),
            _button("Array", _icon_array, lambda: window._start_command("ARRAY"), color=COLOR_MODIFY),
            _button("Erase", _icon_erase, lambda: window._start_command("ERASE"), color=COLOR_MODIFY),
        ],
    )

    edit_panel = _panel(
        "Edit Geometry",
        [
            _button("Trim", _icon_trim, lambda: window._start_command("TRIM"), color=COLOR_EDIT),
            _button("Extend", _icon_extend, lambda: window._start_command("EXTEND"), color=COLOR_EDIT),
            _button("Offset", _icon_offset, lambda: window._start_command("OFFSET"), color=COLOR_EDIT),
            _button("Fillet", _icon_fillet, lambda: window._start_command("FILLET"), color=COLOR_EDIT),
            _button("Chamfer", _icon_chamfer, lambda: window._start_command("CHAMFER"), color=COLOR_EDIT),
            _button("Break", _icon_break, lambda: window._start_command("BREAK"), color=COLOR_EDIT),
            _button("Lengthen", _icon_lengthen, lambda: window._start_command("LENGTHEN"), color=COLOR_EDIT),
            _button("Explode", _icon_explode, lambda: window._start_command("EXPLODE"), color=COLOR_EDIT),
            _button("Join", _icon_join, lambda: window._start_command("JOIN"), color=COLOR_EDIT),
            _button("Stretch", _icon_stretch, lambda: window._start_command("STRETCH"), color=COLOR_EDIT),
        ],
    )

    points_panel = _panel(
        "Points",
        [
            _button("Point", _icon_point, lambda: window._start_command("POINT"), color=COLOR_NEUTRAL),
            _button("Divide", _icon_divide, lambda: window._start_command("DIVIDE"), color=COLOR_NEUTRAL),
            _button("Measure", _icon_measure, lambda: window._start_command("MEASURE"), color=COLOR_NEUTRAL),
        ],
    )

    utilities_panel = _panel(
        "Utilities",
        [
            _button("Undo", _icon_undo, window._do_undo, color=COLOR_NEUTRAL),
            _button("Redo", _icon_redo, window._do_redo, color=COLOR_NEUTRAL),
            _button("Match Prop", _icon_match_props, lambda: window._start_command("MATCHPROP"), color=COLOR_NEUTRAL),
            _button("Quick Select", _icon_qselect, lambda: window._start_command("QSELECT"), color=COLOR_NEUTRAL),
        ],
    )

    return _row([draw_panel, clipboard_panel, modify_panel, edit_panel, points_panel, utilities_panel])


def _build_insert_tab(window: "MainWindow") -> QWidget:
    block_panel = _panel(
        "Block",
        [
            _button("Create", _icon_create_block, lambda: window._start_command("BLOCK"), color=COLOR_ANNOTATE),
            _button("Insert", _icon_insert_block, lambda: window._start_command("INSERT"), color=COLOR_ANNOTATE),
            _button("Edit Block", _icon_edit_block, lambda: window._start_command("BEDIT"), color=COLOR_ANNOTATE),
            _button("Hatch", _icon_hatch, lambda: window._start_command("HATCH"), color=COLOR_ANNOTATE),
        ],
    )
    reference_panel = _panel(
        "Reference",
        [
            _button("Attach Image", _icon_attach_image, lambda: window._start_command("IMAGEATTACH"), color=COLOR_NEUTRAL),
            _button("Attach XREF", _icon_attach_xref, lambda: window._start_command("XREF"), color=COLOR_NEUTRAL),
            _button("XREF Panel", _icon_xref_panel, lambda: window._start_command("EXTERNALREFERENCES"), color=COLOR_NEUTRAL),
            _button("Clip", _icon_clip, lambda: window._start_command("CLIP"), color=COLOR_NEUTRAL),
        ],
    )
    data_panel = _panel(
        "Data",
        [
            _button("Field", _icon_field, lambda: window._start_command("FIELD"), color=COLOR_ANNOTATE),
            _button("Data Link", _icon_datalink, lambda: window._start_command("DATALINK"), color=COLOR_ANNOTATE),
        ],
    )
    return _row([block_panel, reference_panel, data_panel])


def _build_annotate_tab(window: "MainWindow") -> QWidget:
    text_panel = _panel(
        "Text",
        [
            _button("Multiline Text", _icon_text, lambda: window._start_command("MTEXT"), color=COLOR_ANNOTATE),
            _button("Find Text", _icon_find, lambda: window._start_command("FIND"), color=COLOR_ANNOTATE),
        ],
        launcher=lambda: window._start_command("STYLE"),
    )
    leader_panel = _panel(
        "Leaders",
        [
            _button("Leader", _icon_leader, lambda: window._start_command("LEADER"), color=COLOR_ANNOTATE),
        ],
        launcher=lambda: window._start_command("MLEADERSTYLE"),
    )
    table_panel = _panel(
        "Tables",
        [
            _button("Table", _icon_table, lambda: window._start_command("TABLE"), color=COLOR_ANNOTATE),
        ],
        launcher=lambda: window._start_command("TABLESTYLE"),
    )
    dim_panel = _panel(
        "Dimensions",
        [
            _button("Linear", _icon_dimension, lambda: window._start_command("DIMLINEAR"), color=COLOR_ANNOTATE),
            _button("Aligned", _icon_dimension_aligned, lambda: window._start_command("DIMALIGNED"), color=COLOR_ANNOTATE),
            _button("Angular", _icon_dimension_angular, lambda: window._start_command("DIMANGULAR"), color=COLOR_ANNOTATE),
            _button("Radius", _icon_dimension_radius, lambda: window._start_command("DIMRADIUS"), color=COLOR_ANNOTATE),
            _button("Diameter", _icon_dimension_diameter, lambda: window._start_command("DIMDIAMETER"), color=COLOR_ANNOTATE),
            _button("Distance", _icon_distance, lambda: window._start_command("DIST"), color=COLOR_ANNOTATE),
            _button("Center Mark", _icon_centermark, lambda: window._start_command("CENTERMARK"), color=COLOR_ANNOTATE),
        ],
        launcher=lambda: window._start_command("DIMSTYLE"),
    )
    return _row([text_panel, leader_panel, table_panel, dim_panel])


def _build_view_tab(window: "MainWindow") -> QWidget:
    navigate_panel = _panel(
        "Navigate",
        [
            _button("Zoom In", _icon_zoom_in, lambda: window.canvas.zoom_in(), color=COLOR_NEUTRAL),
            _button("Zoom Out", _icon_zoom_out, lambda: window.canvas.zoom_out(), color=COLOR_NEUTRAL),
            _button("Extents", _icon_zoom_extents, lambda: window.canvas.zoom_extents(), color=COLOR_NEUTRAL),
        ],
    )

    grid_btn = _button("Grid", _icon_grid, checkable=True, color=COLOR_NEUTRAL)
    grid_btn.setChecked(window.grid_button.isChecked())
    grid_btn.toggled.connect(window.grid_button.setChecked)
    window.grid_button.toggled.connect(grid_btn.setChecked)

    ortho_btn = _button("Ortho", _icon_ortho, checkable=True, color=COLOR_NEUTRAL)
    ortho_btn.setChecked(window.ortho_button.isChecked())
    ortho_btn.toggled.connect(window.ortho_button.setChecked)
    window.ortho_button.toggled.connect(ortho_btn.setChecked)

    snap_btn = _button("Snap", _icon_snap, checkable=True, color=COLOR_NEUTRAL)
    snap_btn.setChecked(window.snap_button.isChecked())
    snap_btn.toggled.connect(window.snap_button.setChecked)
    window.snap_button.toggled.connect(snap_btn.setChecked)

    visibility_panel = _panel("Visibility", [grid_btn, ortho_btn, snap_btn])

    viewports_panel = _panel(
        "Viewports",
        [
            _button("Configuration", _icon_viewports, lambda: window._start_command("VIEWPORTS"), color=COLOR_NEUTRAL),
        ],
    )

    panels_panel = _panel(
        "Panels",
        [
            _button("Layers", _icon_layers, lambda: window._start_command("LAYER"), color=COLOR_NEUTRAL),
        ],
        launcher=lambda: window._start_command("LAYER"),
    )

    return _row([navigate_panel, visibility_panel, viewports_panel, panels_panel])


def _build_file_tab(window: "MainWindow") -> QWidget:
    file_panel = _panel(
        "File",
        [
            _button("New", _icon_new, window._new_document, color=COLOR_NEUTRAL),
            _button("Open", _icon_open, window._open_file, color=COLOR_NEUTRAL),
            _button("Save", _icon_save, window._save_file, color=COLOR_NEUTRAL),
            _button("Export PDF", _icon_export_pdf, window._export_pdf, color=COLOR_NEUTRAL),
        ],
    )
    return _row([file_panel])


QAT_STYLE = """
    QWidget#qat { background-color: #262626; border-bottom: 1px solid #333333; }
    QToolButton { background-color: transparent; border: none; padding: 3px; }
    QToolButton:hover { background-color: #3a3a3a; border-radius: 3px; }
"""
_QAT_ICON_SIZE = 16


def build_quick_access_toolbar(window: "MainWindow") -> QWidget:
    """Barra fina acima do ribbon com os comandos mais usados — New/Open/Save/
    Undo/Redo — sempre visíveis não importa qual aba do ribbon está aberta
    (mesma ideia da Quick Access Toolbar do AutoCAD, ao lado do ícone "A"
    vermelho). Pedido explícito do Hamilton a partir do print do AutoCAD 2019
    que ele mandou: "principais comandos sempre no menu aparente"."""
    bar = QWidget()
    bar.setObjectName("qat")
    bar.setStyleSheet(QAT_STYLE)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(8, 3, 8, 3)
    layout.setSpacing(2)

    def qat_button(draw_fn, handler, tooltip) -> QToolButton:
        button = QToolButton()
        button.setIcon(_make_icon(draw_fn, COLOR_NEUTRAL))
        button.setIconSize(QSize(_QAT_ICON_SIZE, _QAT_ICON_SIZE))
        button.setToolTip(tooltip)
        button.clicked.connect(handler)
        return button

    logo_label = QLabel()
    logo_pixmap = QIcon(str(resolve_app_icon_path())).pixmap(_QAT_ICON_SIZE + 4, _QAT_ICON_SIZE + 4)
    if not logo_pixmap.isNull():
        logo_label.setPixmap(logo_pixmap)
        logo_label.setToolTip("NewSIcad")
        layout.addWidget(logo_label)
        layout.addWidget(_separator())

    layout.addWidget(qat_button(_icon_new, window._new_document, "New (Ctrl+N)"))
    layout.addWidget(qat_button(_icon_open, window._open_file, "Open... (Ctrl+O)"))
    layout.addWidget(qat_button(_icon_save, window._save_file, "Save (Ctrl+S)"))
    layout.addWidget(_separator())
    layout.addWidget(qat_button(_icon_undo, window._do_undo, "Undo (Ctrl+Z)"))
    layout.addWidget(qat_button(_icon_redo, window._do_redo, "Redo (Ctrl+Y)"))
    layout.addStretch(1)
    return bar


def build_ribbon(window: "MainWindow") -> QTabWidget:
    ribbon = QTabWidget()
    ribbon.setStyleSheet(RIBBON_STYLE)
    ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    ribbon.setDocumentMode(True)
    # No macOS, documentMode=True desenha a tira "vazia" da barra de abas
    # (depois da última aba) com o fundo nativo claro do Cocoa, ignorando o
    # stylesheet — só o estilo Fusion (não-nativo) respeita background-color
    # aí. Aplicado só neste widget (não no app inteiro), pra não perder a
    # aparência nativa do resto da janela.
    ribbon.setStyle(QStyleFactory.create("Fusion"))

    ribbon.addTab(_build_file_tab(window), "File")
    ribbon.addTab(_build_home_tab(window), "Home")
    ribbon.addTab(_build_insert_tab(window), "Insert")
    ribbon.addTab(_build_annotate_tab(window), "Annotate")
    ribbon.addTab(_build_view_tab(window), "View")

    # Altura calculada a partir do sizeHint() real (tab bar + maior página de
    # botões), em vez de um número fixo chutado — um valor fixo menor que o
    # necessário (era 92, mas o conteúdo pede >=109) cortava a parte de baixo
    # de todo rótulo de botão e do título de cada painel ("Draw", "Modify"
    # etc.) em todas as abas. +4px de folga pra fontes um pouco mais altas
    # que a testada no macOS (ex.: renderização de fonte no Windows).
    ribbon.setFixedHeight(ribbon.sizeHint().height() + 4)

    return ribbon
