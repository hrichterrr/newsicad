"""Painel de Propriedades (Ctrl+1): mostra a seleção atual organizada em
seções "Geral" (tipo/camada/cor) + "Geometria" (campos específicos do tipo,
ex.: centro/raio de um Circle) — mesmo padrão visual do Properties do
AutoCAD (faixas escuras de seção + linhas rótulo/valor), em vez do texto
corrido que o painel usava antes. Somente leitura nesta versão (edição
inline dos valores fica para um marco futuro — ver README)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QLabel, QScrollArea, QVBoxLayout, QWidget

from newsicad.core.entities import (
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
    PointEntity,
    Ray,
    Spline,
    Text,
    XLine,
)

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

PANEL_STYLE = """
    QScrollArea { background-color: #1e1e1e; border: none; }
    QWidget#propertiesBody { background-color: #1e1e1e; }
    QLabel#sectionHeader {
        background-color: #2a2a2a; color: #9a9a9a; font-size: 10px;
        padding: 3px 8px; letter-spacing: 1px;
    }
    QLabel#rowLabel { color: #8a8a8a; font-size: 11px; }
    QLabel#rowValue { color: #dedede; font-size: 11px; font-family: "Menlo"; }
    QLabel#emptyState { color: #6a6a6a; font-size: 11px; padding: 12px; }
"""


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _geometry_fields(entity: Entity) -> list[tuple[str, str]]:
    if isinstance(entity, Line):
        return [
            ("Início X", _fmt(entity.start.x)), ("Início Y", _fmt(entity.start.y)),
            ("Fim X", _fmt(entity.end.x)), ("Fim Y", _fmt(entity.end.y)),
            ("Comprimento", _fmt(entity.length())),
        ]
    if isinstance(entity, Circle):
        fields = [
            ("Centro X", _fmt(entity.center.x)), ("Centro Y", _fmt(entity.center.y)),
            ("Raio", _fmt(entity.radius)),
        ]
        if entity.inner_radius > 1e-9:
            fields.append(("Raio interno", _fmt(entity.inner_radius)))
        return fields
    if isinstance(entity, Arc):
        return [
            ("Centro X", _fmt(entity.center.x)), ("Centro Y", _fmt(entity.center.y)),
            ("Raio", _fmt(entity.radius)),
            ("Ângulo inicial", f"{math.degrees(entity.start_angle):.1f}°"),
            ("Ângulo final", f"{math.degrees(entity.end_angle):.1f}°"),
        ]
    if isinstance(entity, Ellipse):
        return [
            ("Centro X", _fmt(entity.center.x)), ("Centro Y", _fmt(entity.center.y)),
            ("Raio maior", _fmt(entity.radius_major)), ("Raio menor", _fmt(entity.radius_minor)),
        ]
    if isinstance(entity, (LWPolyline, Spline)):
        return [("Vértices", str(len(entity.points))), ("Fechada", "Sim" if entity.closed else "Não")]
    if isinstance(entity, Text):
        return [
            ("Conteúdo", entity.content if len(entity.content) <= 24 else entity.content[:24] + "…"),
            ("Altura", _fmt(entity.height)), ("Justificar", entity.justify),
            ("Inserção X", _fmt(entity.insertion_point.x)), ("Inserção Y", _fmt(entity.insertion_point.y)),
        ]
    if isinstance(entity, PointEntity):
        return [("X", _fmt(entity.location.x)), ("Y", _fmt(entity.location.y))]
    if isinstance(entity, (XLine, Ray)):
        return [
            ("Ponto X", _fmt(entity.point.x)), ("Ponto Y", _fmt(entity.point.y)),
            ("Ângulo", f"{math.degrees(entity.angle):.1f}°"),
        ]
    if isinstance(entity, Dimension):
        return [("Tipo de cota", entity.kind), ("Medida", entity.measurement_text())]
    if isinstance(entity, Hatch):
        return [("Vértices do contorno", str(len(entity.boundary_points)))]
    if isinstance(entity, BlockReference):
        sx, sy = entity.scale_xy()
        if entity.scale_y is None:
            scale_rows = [("Escala", _fmt(sx))]
        else:
            # Bloco dinâmico importado com escala por eixo (possivelmente
            # negativa = espelhado) — mostra os dois valores separados.
            scale_rows = [("Escala X", _fmt(sx)), ("Escala Y", _fmt(sy))]
        return [
            ("Bloco", entity.block_name), *scale_rows,
            ("Rotação", f"{math.degrees(entity.rotation):.1f}°"),
        ]
    if isinstance(entity, ImageReference):
        return [("Arquivo", entity.path.name), ("Largura", _fmt(entity.width)), ("Altura", _fmt(entity.height))]
    return []


class PropertiesPanel(QDockWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__("Properties", window)
        self.main_window = window
        self.setStyleSheet(PANEL_STYLE)

        self.body = QWidget()
        self.body.setObjectName("propertiesBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 4, 0, 4)
        self.body_layout.setSpacing(0)
        self.body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(self.body)
        scroll.setWidgetResizable(True)
        scroll.setMaximumWidth(240)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(scroll)

        self.refresh([])

    def _section(self, title: str) -> None:
        label = QLabel(title.upper())
        label.setObjectName("sectionHeader")
        self.body_layout.insertWidget(self.body_layout.count() - 1, label)

    def _row(self, label_text: str, value_text: str) -> None:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(0)
        inner = QWidget()
        from PySide6.QtWidgets import QHBoxLayout

        inner_layout = QHBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(label_text)
        label.setObjectName("rowLabel")
        value = QLabel(value_text)
        value.setObjectName("rowValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        inner_layout.addWidget(label)
        inner_layout.addStretch(1)
        inner_layout.addWidget(value)
        layout.addWidget(inner)
        self.body_layout.insertWidget(self.body_layout.count() - 1, row)

    def _clear(self) -> None:
        while self.body_layout.count() > 1:
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh(self, entities: list[Entity]) -> None:
        self._clear()

        if not entities:
            empty = QLabel("Nenhuma seleção")
            empty.setObjectName("emptyState")
            self.body_layout.insertWidget(0, empty)
            return

        if len(entities) > 1:
            self._section("Geral")
            self._row("Objetos selecionados", str(len(entities)))
            layers = {e.layer for e in entities}
            self._row("Camada", next(iter(layers)) if len(layers) == 1 else "*VARIA*")
            types = sorted({type(e).__name__ for e in entities})
            self._row("Tipos", ", ".join(types) if len(types) <= 3 else f"{len(types)} tipos")
            return

        entity = entities[0]
        self._section("Geral")
        self._row("Tipo", type(entity).__name__)
        self._row("Camada", entity.layer)
        self._row("Cor", entity.color or "ByLayer")

        fields = _geometry_fields(entity)
        if fields:
            self._section("Geometria")
            for label_text, value_text in fields:
                self._row(label_text, value_text)
