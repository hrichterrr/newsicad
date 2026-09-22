"""Painel de Propriedades (Ctrl+1): mostra a seleção atual organizada em
seções "Geral" (tipo/camada/cor) + "Geometria" (campos específicos do tipo,
ex.: centro/raio de um Circle) — mesmo padrão visual do Properties do
AutoCAD (faixas escuras de seção + linhas rótulo/valor).

A partir da 2.16 uma parte dos campos é EDITÁVEL ali mesmo: camada de
qualquer objeto, conteúdo/altura/rotação/justificação/estilo de um texto,
altura do texto, tamanho da seta e estilo de fonte de uma cota, raio de um
círculo e escala/rotação de um bloco. Cada edição entra no undo como um
passo (ver `_apply`). Antes o painel era só de leitura e mudar o tamanho do
texto de UMA cota exigia trocar o DIMSTYLE do desenho inteiro — pedido do
grupo do NewSicad em 22/09/2026. O resto dos campos (coordenadas, medida)
segue de leitura."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from newsicad.core.document import dim_arrow_size, dim_text_height
from newsicad.core.entities import (
    TEXT_JUSTIFY_OPTIONS,
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
    QLineEdit#rowField, QComboBox#rowField {
        background-color: #2a2a2a; color: #dedede; font-size: 11px;
        border: 1px solid #3a3a3a; border-radius: 2px; padding: 1px 4px;
    }
    QLineEdit#rowField:focus, QComboBox#rowField:focus { border-color: #5a8ac0; }
    QComboBox#rowField QAbstractItemView {
        background-color: #2a2a2a; color: #dedede; selection-background-color: #3a5a7a;
    }
"""


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _set_attribute(ref: BlockReference, attribute: Text, value: str) -> None:
    """Muda o valor de um atributo e avisa a instância que ela mudou.

    A etiqueta é filha do bloco, não uma entidade do desenho: sem o `touch`
    a instância não entra no registro de alterados e a tela continuaria
    mostrando o texto velho até algo mais forçar a repintura."""
    attribute.content = value
    ref.touch()


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
        # Conteúdo/altura/justificação estão na seção EDITÁVEL (ver
        # `_editable_section`) — aqui fica só o que é de leitura.
        return [
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
        #: Trava de reentrada da edição inline — ver `_apply`.
        self._applying = False
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

    def _field_row(self, label_text: str, widget: QWidget) -> None:
        """Linha rótulo/valor com um widget EDITÁVEL à direita, no mesmo
        desenho das linhas de leitura."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 2, 8, 2)
        label = QLabel(label_text)
        label.setObjectName("rowLabel")
        widget.setObjectName("rowField")
        widget.setMaximumWidth(110)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(widget)
        self.body_layout.insertWidget(self.body_layout.count() - 1, row)

    def _text_row(self, label_text: str, value: str, commit) -> None:
        field = QLineEdit(value)
        field.editingFinished.connect(
            lambda: self._commit_if_changed(field.text(), value, commit)
        )
        self._field_row(label_text, field)

    def _number_row(self, label_text: str, value: float, commit, positive: bool = False) -> None:
        field = QLineEdit(f"{value:g}")

        def done() -> None:
            try:
                novo = float(field.text().replace(",", "."))
            except ValueError:
                field.setText(f"{value:g}")  # valor inválido: volta o de antes
                return
            if positive and novo <= 0:
                field.setText(f"{value:g}")
                return
            if abs(novo - value) > 1e-12:
                self._apply(lambda: commit(novo))

        field.editingFinished.connect(done)
        self._field_row(label_text, field)

    def _combo_row(self, label_text: str, options: list[str], current: str, commit) -> None:
        combo = QComboBox()
        combo.addItems(options)
        if current not in options:
            combo.addItem(current)
        combo.setCurrentText(current)
        combo.activated.connect(
            lambda _i: self._commit_if_changed(combo.currentText(), current, commit)
        )
        self._field_row(label_text, combo)

    def _commit_if_changed(self, novo: str, antigo: str, commit) -> None:
        if novo != antigo:
            self._apply(lambda: commit(novo))

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
        self._combo_row(
            "Camada", sorted(self._document().layers), entity.layer,
            lambda nome: setattr(entity, "layer", nome),
        )
        self._row("Cor", entity.color or "ByLayer")

        fields = _geometry_fields(entity)
        if fields:
            self._section("Geometria")
            for label_text, value_text in fields:
                self._row(label_text, value_text)

        self._editable_section(entity)

    # ------------------------------------------------------------------ #
    # edição
    # ------------------------------------------------------------------ #
    def _document(self):
        return self.main_window.document

    def _apply(self, mutate) -> None:
        """Um passo de edição do painel: entra no undo, muda a entidade e
        redesenha. Mesmo caminho que qualquer comando usa (ver
        MainWindow._delete_selected).

        A remontagem do painel é ADIADA pro próximo ciclo de eventos: estamos
        dentro do sinal de um campo que a remontagem destrói, e destruir o
        widget que está emitindo trava a janela. O `_applying` protege contra
        reentrada — remontar dispara `editingFinished` em campo que perde o
        foco, e isso voltaria pra cá no meio da própria edição."""
        if self._applying:
            return
        self._applying = True
        window = self.main_window
        try:
            window.undo_stack.push()
            mutate()
            window.canvas.refresh_entities()
            window.layer_dock.refresh()
        finally:
            self._applying = False
        QTimer.singleShot(0, window._refresh_properties_panel)

    def _editable_section(self, entity: Entity) -> None:
        """Campos que o painel deixa MUDAR, por tipo de entidade.

        Até a 2.15.10 o painel era só de leitura, e a única forma de mexer no
        tamanho do texto de UMA cota era trocar o DIMSTYLE do desenho todo —
        "precisamos alterar propriedades, como tipo e tamanho da fonte, tipo
        de linha de marcação... por meio da opção Propriedades" (feedback do
        grupo, 22/09/2026)."""
        estilos = sorted(self._document().text_styles)

        if isinstance(entity, Text):
            self._section("Texto")
            self._text_row("Conteúdo", entity.content, lambda v: setattr(entity, "content", v))
            self._number_row("Altura", entity.height, lambda v: setattr(entity, "height", v), positive=True)
            self._number_row(
                "Rotação (°)", math.degrees(entity.rotation),
                lambda v: setattr(entity, "rotation", math.radians(v)),
            )
            self._combo_row("Justificar", list(TEXT_JUSTIFY_OPTIONS), entity.justify,
                            lambda v: setattr(entity, "justify", v))
            self._combo_row("Estilo", estilos, entity.style or "Standard",
                            lambda v: setattr(entity, "style", v))
            return

        if isinstance(entity, Dimension):
            self._section("Cota")
            style = self._document().dim_style
            self._number_row(
                "Altura do texto", dim_text_height(entity, style),
                lambda v: setattr(entity, "text_height", v), positive=True,
            )
            self._number_row(
                "Tamanho da seta", dim_arrow_size(entity, style),
                lambda v: setattr(entity, "arrow_size", v), positive=True,
            )
            self._combo_row("Estilo do texto", estilos, entity.text_style or "Standard",
                            lambda v: setattr(entity, "text_style", v))
            return

        if isinstance(entity, Circle):
            self._section("Editar")
            self._number_row("Raio", entity.radius, lambda v: setattr(entity, "radius", v), positive=True)
            return

        if isinstance(entity, BlockReference):
            self._section("Editar")
            sx, _sy = entity.scale_xy()
            self._number_row("Escala", sx, lambda v: setattr(entity, "scale", v), positive=True)
            self._number_row(
                "Rotação (°)", math.degrees(entity.rotation),
                lambda v: setattr(entity, "rotation", math.radians(v)),
            )
            self._attribute_rows(entity)

    def _attribute_rows(self, ref: BlockReference) -> None:
        """Atributos do bloco (ESCALA, PAVIMENTO, TÍTULO, CIRCUITO...) —
        os campos preenchíveis que vêm de um ATTRIB do .dwg e que moram
        dentro da própria instância (ver `BlockReference.attributes`). Antes
        não havia nada indicando que pertenciam ao bloco: selecionar o
        símbolo não mostrava nem deixava mudar nenhum deles ("os blocos do
        template estão sendo extraídos sem suas respectivas propriedades",
        feedback do grupo em 22/09/2026)."""
        attrs = [a for a in ref.attributes if a.attrib_tag]
        if not attrs:
            return
        self._section("Atributos")
        for attr in attrs:
            self._text_row(attr.attrib_tag, attr.content, lambda v, a=attr: _set_attribute(ref, a, v))
