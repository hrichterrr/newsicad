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
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

ICON_SIZE = 28
PIXMAP_SIZE = 32
STROKE_COLOR = "#d8d8d8"
NOT_IMPLEMENTED_TIP = "Ainda não implementado — previsto para um próximo marco do NewSIcad."

RIBBON_STYLE = """
    QTabWidget::pane {
        border: none;
        background-color: #232323;
    }
    QTabWidget QWidget {
        background-color: #232323;
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
"""


def _make_icon(draw_fn: Callable[[QPainter, QRectF], None]) -> QIcon:
    pixmap = QPixmap(PIXMAP_SIZE, PIXMAP_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(STROKE_COLOR))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    margin = 5.0
    rect = QRectF(margin, margin, PIXMAP_SIZE - 2 * margin, PIXMAP_SIZE - 2 * margin)
    draw_fn(painter, rect)
    painter.end()
    return QIcon(pixmap)


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


def _icon_hatch(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    step = r.width() / 4
    x = r.left()
    while x < r.right():
        p.drawLine(QPointF(x, r.bottom()), QPointF(min(x + r.height(), r.right()), r.bottom() - min(x + r.height(), r.right()) + x))
        x += step


def _icon_block(p: QPainter, r: QRectF) -> None:
    p.drawRect(r)
    p.drawLine(r.topLeft(), r.center())
    p.drawLine(r.topRight(), r.center())
    p.drawLine(r.bottomLeft(), r.center())
    p.drawLine(r.bottomRight(), r.center())


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


def _icon_dimension(p: QPainter, r: QRectF) -> None:
    y = r.center().y()
    p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
    p.drawLine(QPointF(r.right(), r.top()), QPointF(r.right(), r.bottom()))
    p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))


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
# construção de botões / painéis
# ---------------------------------------------------------------------- #
def _button(
    label: str,
    draw_fn: Callable[[QPainter, QRectF], None],
    handler: Callable[[], None] | None = None,
    checkable: bool = False,
    tooltip: str | None = None,
) -> QToolButton:
    button = QToolButton()
    button.setIcon(_make_icon(draw_fn))
    button.setIconSize(_icon_qsize())
    button.setText(label)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setFixedSize(58, 54)
    button.setCheckable(checkable)
    if handler is not None:
        button.clicked.connect(handler)
    else:
        button.setEnabled(False)
        button.setToolTip(tooltip or NOT_IMPLEMENTED_TIP)
    return button


def _icon_qsize() -> QSize:
    return QSize(ICON_SIZE, ICON_SIZE)


def _panel(title: str, buttons: list[QToolButton]) -> QWidget:
    container = QWidget()
    outer = QVBoxLayout(container)
    outer.setContentsMargins(6, 4, 6, 2)
    outer.setSpacing(2)

    row = QHBoxLayout()
    row.setSpacing(2)
    for button in buttons:
        row.addWidget(button)
    outer.addLayout(row)

    label = QLabel(title)
    label.setObjectName("panelTitle")
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    outer.addWidget(label)

    return container


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: #3a3a3a;")
    return line


def _row(widgets: list[QWidget]) -> QWidget:
    page = QWidget()
    layout = QHBoxLayout(page)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(4)
    for i, w in enumerate(widgets):
        if i > 0:
            layout.addWidget(_separator())
        layout.addWidget(w)
    layout.addStretch(1)
    return page


# ---------------------------------------------------------------------- #
# abas
# ---------------------------------------------------------------------- #
def _build_home_tab(window: "MainWindow") -> QWidget:
    draw_panel = _panel(
        "Draw",
        [
            _button("Line", _icon_line, lambda: window._start_command("LINE")),
            _button("Polyline", _icon_polyline, lambda: window._start_command("PLINE")),
            _button("Circle", _icon_circle, lambda: window._start_command("CIRCLE")),
            _button("Arc", _icon_arc, lambda: window._start_command("ARC")),
            _button("Rectangle", _icon_rectangle, lambda: window._start_command("RECTANG")),
            _button("Ellipse", _icon_ellipse, lambda: window._start_command("ELLIPSE")),
        ],
    )

    modify_panel = _panel(
        "Modify",
        [
            _button("Move", _icon_move, lambda: window._start_command("MOVE")),
            _button("Copy", _icon_copy, lambda: window._start_command("COPY")),
            _button("Rotate", _icon_rotate, lambda: window._start_command("ROTATE")),
            _button("Mirror", _icon_mirror, lambda: window._start_command("MIRROR")),
            _button("Scale", _icon_scale, lambda: window._start_command("SCALE")),
            _button("Erase", _icon_erase, lambda: window._start_command("ERASE")),
        ],
    )

    edit_panel = _panel(
        "Edit Geometry",
        [
            _button("Trim", _icon_trim, lambda: window._start_command("TRIM")),
            _button("Extend", _icon_extend, lambda: window._start_command("EXTEND")),
            _button("Offset", _icon_offset, lambda: window._start_command("OFFSET")),
            _button("Fillet", _icon_fillet, lambda: window._start_command("FILLET")),
            _button("Chamfer", _icon_chamfer, lambda: window._start_command("CHAMFER")),
            _button("Explode", _icon_explode, lambda: window._start_command("EXPLODE")),
            _button("Join", _icon_join, lambda: window._start_command("JOIN")),
            _button("Stretch", _icon_stretch, lambda: window._start_command("STRETCH")),
        ],
    )

    points_panel = _panel(
        "Points",
        [
            _button("Divide", _icon_divide, lambda: window._start_command("DIVIDE")),
            _button("Measure", _icon_measure, lambda: window._start_command("MEASURE")),
        ],
    )

    utilities_panel = _panel(
        "Utilities",
        [
            _button("Undo", _icon_undo, window._do_undo),
            _button("Redo", _icon_redo, window._do_redo),
            _button("Match Prop", _icon_match_props),
        ],
    )

    return _row([draw_panel, modify_panel, edit_panel, points_panel, utilities_panel])


def _build_insert_tab(window: "MainWindow") -> QWidget:
    block_panel = _panel(
        "Block",
        [
            _button("Create", _icon_block, lambda: window._start_command("BLOCK")),
            _button("Insert", _icon_block, lambda: window._start_command("INSERT")),
            _button("Edit Block", _icon_block, lambda: window._start_command("BEDIT")),
            _button("Hatch", _icon_hatch, lambda: window._start_command("HATCH")),
        ],
    )
    reference_panel = _panel(
        "Reference",
        [
            _button("Attach Image", _icon_block, lambda: window._start_command("IMAGEATTACH")),
            _button("Attach XREF", _icon_block, lambda: window._start_command("XREF")),
            _button("Xref Panel", _icon_block, lambda: window._start_command("EXTERNALREFERENCES")),
        ],
    )
    return _row([block_panel, reference_panel])


def _build_annotate_tab(window: "MainWindow") -> QWidget:
    text_panel = _panel(
        "Text",
        [
            _button("Multiline Text", _icon_text, lambda: window._start_command("MTEXT")),
            _button("Leader", _icon_leader, lambda: window._start_command("LEADER")),
        ],
    )
    dim_panel = _panel(
        "Dimensions",
        [
            _button("Linear", _icon_dimension, lambda: window._start_command("DIMLINEAR")),
            _button("Aligned", _icon_dimension_aligned, lambda: window._start_command("DIMALIGNED")),
            _button("Angular", _icon_dimension_angular, lambda: window._start_command("DIMANGULAR")),
            _button("Radius", _icon_dimension_radius, lambda: window._start_command("DIMRADIUS")),
            _button("Diameter", _icon_dimension_diameter, lambda: window._start_command("DIMDIAMETER")),
            _button("Distance", _icon_dimension, lambda: window._start_command("DIST")),
        ],
    )
    return _row([text_panel, dim_panel])


def _build_view_tab(window: "MainWindow") -> QWidget:
    navigate_panel = _panel(
        "Navigate",
        [
            _button("Zoom In", _icon_zoom_in, window.canvas.zoom_in),
            _button("Zoom Out", _icon_zoom_out, window.canvas.zoom_out),
            _button("Extents", _icon_zoom_extents, window.canvas.zoom_extents),
        ],
    )

    grid_btn = _button("Grid", _icon_rectangle, checkable=True)
    grid_btn.setChecked(window.grid_button.isChecked())
    grid_btn.toggled.connect(window.grid_button.setChecked)
    window.grid_button.toggled.connect(grid_btn.setChecked)

    ortho_btn = _button("Ortho", _icon_rectangle, checkable=True)
    ortho_btn.setChecked(window.ortho_button.isChecked())
    ortho_btn.toggled.connect(window.ortho_button.setChecked)
    window.ortho_button.toggled.connect(ortho_btn.setChecked)

    snap_btn = _button("Snap", _icon_rectangle, checkable=True)
    snap_btn.setChecked(window.snap_button.isChecked())
    snap_btn.toggled.connect(window.snap_button.setChecked)
    window.snap_button.toggled.connect(snap_btn.setChecked)

    visibility_panel = _panel("Visibility", [grid_btn, ortho_btn, snap_btn])

    return _row([navigate_panel, visibility_panel])


def _build_file_tab(window: "MainWindow") -> QWidget:
    file_panel = _panel(
        "File",
        [
            _button("New", _icon_new, window._new_document),
            _button("Open", _icon_open, window._open_file),
            _button("Save", _icon_save, window._save_file),
            _button("Export PDF", _icon_save, window._export_pdf),
        ],
    )
    return _row([file_panel])


def build_ribbon(window: "MainWindow") -> QTabWidget:
    ribbon = QTabWidget()
    ribbon.setStyleSheet(RIBBON_STYLE)
    ribbon.setFixedHeight(92)
    ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    ribbon.setDocumentMode(True)

    ribbon.addTab(_build_file_tab(window), "File")
    ribbon.addTab(_build_home_tab(window), "Home")
    ribbon.addTab(_build_insert_tab(window), "Insert")
    ribbon.addTab(_build_annotate_tab(window), "Annotate")
    ribbon.addTab(_build_view_tab(window), "View")

    return ribbon
