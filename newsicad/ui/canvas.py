"""Canvas 2D estilo AutoCAD: fundo escuro, grid adaptativo, crosshair cobrindo
a viewport, zoom no scroll, pan no botão do meio, preview ao vivo dos
comandos de desenho, dynamic input (distância/ângulo) perto do cursor, e
seleção de objetos (clique único + janela/crossing) para os comandos MODIFY."""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QTransform
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
from newsicad.core.entities import Arc, Circle, Ellipse, Entity, Line, LWPolyline, Point

BACKGROUND_COLOR = "#1e1e1e"
GRID_MINOR_COLOR = "#3a3a3a"
GRID_AXIS_COLOR = "#5a5a5a"
CROSSHAIR_COLOR = "#d0d0d0"
ENTITY_COLOR = "#e8e8e8"
PREVIEW_COLOR = "#4da3ff"
DYNAMIC_INPUT_COLOR = "#ffd479"
SELECTION_COLOR = "#ff9f1c"
WINDOW_SELECT_COLOR = "#4da3ff"
CROSSING_SELECT_COLOR = "#4caf50"

_GRID_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
_HIT_TOLERANCE_PX = 6.0


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

        self._selection_drag_start_scene: QPointF | None = None
        self._selection_drag_current_scene: QPointF | None = None

        self.grid_visible = True
        self.snap_enabled = False
        self.ortho_enabled = False
        self.dynamic_input_enabled = True
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
        self.on_selection_changed: Callable[[], None] | None = None

    # ------------------------------------------------------------------ #
    # sincronização com o Document
    # ------------------------------------------------------------------ #
    def refresh_entities(self) -> None:
        doc_ids = set(self.document.entities.keys())
        existing_ids = set(self._entity_items.keys())

        for stale_id in existing_ids - doc_ids:
            item = self._entity_items.pop(stale_id)
            self._scene.removeItem(item)

        # Recria o item gráfico de toda entidade presente no documento.
        # Necessário porque MOVE/ROTATE/SCALE mutam a entidade em memória
        # sem trocar de id — não dá pra saber por diff de ids se a
        # geometria mudou, então sempre reconstruímos a partir do estado
        # atual (custo desprezível para o volume de entidades do NewSIcad).
        for entity_id in doc_ids:
            old_item = self._entity_items.pop(entity_id, None)
            if old_item is not None:
                self._scene.removeItem(old_item)
            entity = self.document.entities[entity_id]
            item = self._create_item(entity)
            self._scene.addItem(item)
            self._entity_items[entity_id] = item

        self.refresh_selection_highlight()

    def refresh_selection_highlight(self) -> None:
        selected_ids = self.interpreter.context.selection.ids
        for entity_id, item in self._entity_items.items():
            item.setPen(_selected_pen() if entity_id in selected_ids else _entity_pen())

    def _create_item(self, entity: Entity) -> QGraphicsItem:
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

        if isinstance(entity, Ellipse):
            c = cad_to_scene(entity.center)
            path = QPainterPath()
            path.addEllipse(QPointF(0, 0), entity.radius_major, entity.radius_minor)
            transform = QTransform()
            transform.translate(c.x(), c.y())
            transform.rotate(-math.degrees(entity.rotation))
            item = QGraphicsPathItem(transform.map(path))
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
    # hit-testing / seleção
    # ------------------------------------------------------------------ #
    def _hit_tolerance_world(self) -> float:
        scale = max(self.transform().m11(), 1e-6)
        return _HIT_TOLERANCE_PX / scale

    def _hit_test(self, cad_point: Point) -> str | None:
        tolerance = self._hit_tolerance_world()
        best_id: str | None = None
        best_dist = tolerance
        for entity_id, entity in self.document.entities.items():
            dist = self._distance_to_entity(cad_point, entity)
            if dist is not None and dist <= best_dist:
                best_dist = dist
                best_id = entity_id
        return best_id

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
        return None

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
        return QRectF()

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
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        if self._preview_path is not None and not self._preview_path.isEmpty():
            pen = QPen(QColor(PREVIEW_COLOR))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(0)
            painter.setPen(pen)
            painter.drawPath(self._preview_path)

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

    def set_grid_visible(self, visible: bool) -> None:
        self.grid_visible = visible
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled

    def set_ortho_enabled(self, enabled: bool) -> None:
        self.ortho_enabled = enabled

    def clear_transient_overlays(self) -> None:
        """Limpa preview/dynamic-input residuais quando um comando termina,
        sem esperar o próximo movimento do mouse."""
        self._preview_path = None
        self._dyn_text.hide()
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

    def zoom_extents(self) -> None:
        if not self.document.entities:
            return
        rect: QRectF | None = None
        for entity in self.document.entities.values():
            bbox = self._entity_bbox_scene(entity)
            rect = bbox if rect is None else rect.united(bbox)
        if rect is None or rect.isEmpty():
            return
        margin = max(rect.width(), rect.height()) * 0.1 or 1.0
        rect = rect.adjusted(-margin, -margin, margin, margin)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

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
            prompt = self.interpreter.current_prompt
            if self.interpreter.active and prompt is not None and prompt.kind == "selection":
                self._handle_selection_press(event)
                event.accept()
                return
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

        if self._selection_drag_start_scene is not None:
            self._selection_drag_current_scene = scene_pos
            self.viewport().update()
            event.accept()
            return

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
        if event.button() == Qt.MouseButton.LeftButton and self._selection_drag_start_scene is not None:
            self._finish_selection_drag(event)
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
        elif prompt is not None and prompt.kind == "point":
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
