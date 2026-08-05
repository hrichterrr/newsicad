"""Canvas 2D estilo AutoCAD: fundo escuro, grid adaptativo, crosshair cobrindo
a viewport, zoom no scroll, pan no botão do meio, preview ao vivo dos
comandos de desenho e dynamic input (distância/ângulo) perto do cursor."""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from newsicad.commands.interpreter import CommandInterpreter
from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point

BACKGROUND_COLOR = "#1e1e1e"
GRID_MINOR_COLOR = "#3a3a3a"
GRID_AXIS_COLOR = "#5a5a5a"
CROSSHAIR_COLOR = "#d0d0d0"
ENTITY_COLOR = "#e8e8e8"
PREVIEW_COLOR = "#4da3ff"
DYNAMIC_INPUT_COLOR = "#ffd479"

_GRID_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]


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


def _entity_pen() -> QPen:
    pen = QPen(QColor(ENTITY_COLOR))
    pen.setWidth(0)
    return pen


class CanvasView(QGraphicsView):
    mouse_moved = Signal(object)  # emite Point (coordenadas CAD)

    def __init__(self, document: Document, interpreter: CommandInterpreter, parent=None):
        super().__init__(parent)
        self.document = document
        self.interpreter = interpreter

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setSceneRect(-100000, -100000, 200000, 200000)
        self.scale(20, 20)

        self._entity_items: dict[str, QGraphicsItem] = {}
        self._mouse_scene_pos: QPointF | None = None
        self._preview_path: QPainterPath | None = None
        self._panning = False
        self._pan_start = QPointF()

        self.grid_visible = True
        self.snap_enabled = False
        self.ortho_enabled = False
        self.snap_spacing = 10.0

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

    # ------------------------------------------------------------------ #
    # sincronização com o Document
    # ------------------------------------------------------------------ #
    def refresh_entities(self) -> None:
        doc_ids = set(self.document.entities.keys())
        existing_ids = set(self._entity_items.keys())
        for stale_id in existing_ids - doc_ids:
            item = self._entity_items.pop(stale_id)
            self._scene.removeItem(item)
        for new_id in doc_ids - existing_ids:
            entity = self.document.entities[new_id]
            item = self._create_item(entity)
            self._scene.addItem(item)
            self._entity_items[new_id] = item

    def _create_item(self, entity) -> QGraphicsItem:
        if isinstance(entity, Line):
            p1 = cad_to_scene(entity.start)
            p2 = cad_to_scene(entity.end)
            item = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            item.setPen(_entity_pen())
            return item

        if isinstance(entity, Circle):
            c = cad_to_scene(entity.center)
            r = entity.radius
            item = QGraphicsEllipseItem(c.x() - r, c.y() - r, 2 * r, 2 * r)
            item.setPen(_entity_pen())
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
            item.setPen(_entity_pen())
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
            item.setPen(_entity_pen())
            return item

        raise TypeError(f"Tipo de entidade não suportado: {type(entity)!r}")

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
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        if self._preview_path is not None and not self._preview_path.isEmpty():
            pen = QPen(QColor(PREVIEW_COLOR))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(0)
            painter.setPen(pen)
            painter.drawPath(self._preview_path)

    def set_grid_visible(self, visible: bool) -> None:
        self.grid_visible = visible
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled

    def set_ortho_enabled(self, enabled: bool) -> None:
        self.ortho_enabled = enabled

    # ------------------------------------------------------------------ #
    # entrada do usuário
    # ------------------------------------------------------------------ #
    def _event_pos(self, event):
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

    def _apply_constraints(self, point: Point) -> Point:
        result = point
        prompt = self.interpreter.current_prompt
        if (
            self.ortho_enabled
            and self.interpreter.active
            and prompt is not None
            and prompt.kind == "point"
            and self.interpreter.last_point is not None
        ):
            base = self.interpreter.last_point
            dx = result.x - base.x
            dy = result.y - base.y
            result = Point(result.x, base.y) if abs(dx) >= abs(dy) else Point(base.x, result.y)

        if self.snap_enabled:
            step = self.snap_spacing
            result = Point(round(result.x / step) * step, round(result.y / step) * step)

        return result

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
            if self.on_point is not None:
                self.on_point(self._resolve_point(event))
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
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
        cad_point = self._apply_constraints(scene_to_cad(scene_pos))
        self._update_dynamic_input(cad_point)
        self._update_preview(cad_point)
        self.mouse_moved.emit(cad_point)
        self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.BlankCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.on_cancel is not None:
                self.on_cancel()
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
        elif prompt is not None and prompt.kind == "point":
            path.moveTo(cad_to_scene(last))
            path.lineTo(cad_to_scene(cursor_point))

        self._preview_path = path

    def _update_dynamic_input(self, cursor_point: Point) -> None:
        interp = self.interpreter
        if not interp.active or interp.last_point is None or self._mouse_scene_pos is None:
            self._dyn_text.hide()
            return

        prompt = interp.current_prompt
        if prompt is None or prompt.kind not in ("point", "distance"):
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
