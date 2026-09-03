"""Painel de Camadas (comando LAYER/LA): lista todas as camadas do desenho
com toggle de visibilidade e trava (ícones estilo lâmpada/cadeado, igual ao
Layer Properties Manager do AutoCAD) e a cor de cada camada, e qual é a
camada atual (onde entidades novas são desenhadas). Ao contrário do
XrefPanel/BlockEditorDialog (QDialog modal), este é um QDockWidget não-modal
— o objetivo é deixar ligar/desligar camadas olhando o efeito no canvas em
tempo real, sem fechar nada.

A cor de camada agora afeta o desenho de verdade (`CanvasView._effective_color`,
usada por `_create_item`) — antes disso, o canvas sempre desenhava tudo na
mesma cor fixa e este painel deliberadamente não oferecia editar cor por não
ter efeito visível nenhum (ver git history). Isso mudou."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from newsicad.ui.icon_utils import make_icon

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

LAYER_TABLE_STYLE = """
    QTableWidget {
        background-color: #1e1e1e;
        color: #d8d8d8;
        gridline-color: #333333;
        border: 1px solid #333333;
        font-size: 11px;
    }
    QHeaderView::section {
        background-color: #2a2a2a;
        color: #a0a0a0;
        border: none;
        border-bottom: 1px solid #333333;
        padding: 3px;
    }
    QTableWidget::item:selected {
        background-color: #3a5a8c;
    }
"""

_TOGGLE_STYLE = """
    QToolButton { border: none; background: transparent; padding: 1px; }
    QToolButton:hover { background-color: #333333; border-radius: 3px; }
"""

_COL_NAME, _COL_VISIBLE, _COL_LOCKED, _COL_COLOR = range(4)


# ---------------------------------------------------------------------- #
# ícones (lâmpada ligada/desligada, cadeado travado/destravado) — mesmo
# padrão de renderização nítida em HiDPI de newsicad/ui/icon_utils.py
# ---------------------------------------------------------------------- #
def _draw_bulb(on: bool):
    color = QColor("#f0c33e") if on else QColor("#5a5a5a")

    def draw(p: QPainter, r: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        cx = r.center().x()
        cy = r.top() + r.height() * 0.42
        radius = r.width() * 0.34
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        base = QRectF(cx - radius * 0.55, cy + radius * 0.65, radius * 1.1, radius * 0.6)
        p.drawRoundedRect(base, 1.0, 1.0)

    return draw


def _draw_lock(locked: bool):
    color = QColor("#e0a63e") if locked else QColor("#5a5a5a")

    def draw(p: QPainter, r: QRectF) -> None:
        pen = p.pen()
        pen.setColor(color)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx = r.center().x()
        body_top = r.top() + r.height() * 0.42
        shackle_rect = QRectF(cx - r.width() * 0.22, r.top(), r.width() * 0.44, r.height() * 0.5)
        if locked:
            p.drawArc(shackle_rect, 0, 180 * 16)
        else:
            p.drawArc(shackle_rect.adjusted(-r.width() * 0.05, 0, -r.width() * 0.05, 0), 20 * 16, 160 * 16)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        body = QRectF(cx - r.width() * 0.28, body_top, r.width() * 0.56, r.height() * 0.4)
        p.drawRoundedRect(body, 1.5, 1.5)

    return draw


def _draw_swatch(color_hex: str):
    def draw(p: QPainter, r: QRectF) -> None:
        p.setPen(QColor("#1a1a1a"))
        p.setBrush(QColor(color_hex))
        inset = r.adjusted(r.width() * 0.12, r.height() * 0.12, -r.width() * 0.12, -r.height() * 0.12)
        p.drawRoundedRect(inset, 2.0, 2.0)

    return draw


class LayerPanel(QDockWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__("Layers", window)
        self.main_window = window

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        note = QLabel(
            "Duplo clique no nome define a camada atual (onde novas\n"
            "entidades são desenhadas) — em negrito na lista. Clique com o\n"
            "botão direito pra renomear."
        )
        note.setStyleSheet("color: #808080; font-size: 10px;")
        layout.addWidget(note)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nome", "Ativa", "Trava", "Cor"])
        self.table.setStyleSheet(LAYER_TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_VISIBLE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_LOCKED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_COLOR, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._handle_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table, stretch=1)

        button_row = QHBoxLayout()
        new_layer_button = QPushButton("Nova camada...")
        new_layer_button.clicked.connect(self._create_layer)
        button_row.addWidget(new_layer_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.setWidget(container)
        self.refresh()

    # ------------------------------------------------------------------ #
    # construção da tabela
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        document = self.main_window.document
        names = sorted(document.layers.keys())
        self.table.setRowCount(len(names))

        for row, name in enumerate(names):
            layer = document.layers[name]

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if name == document.current_layer:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setForeground(QColor("#4da3ff"))
            name_item.setToolTip("Duplo clique pra tornar esta a camada atual")
            self.table.setItem(row, _COL_NAME, name_item)

            visible_btn = self._toggle_button(
                layer.visible, _draw_bulb,
                "Camada ligada — clique pra desligar (some do desenho e do plot)",
                "Camada desligada — clique pra ligar",
                lambda checked, n=name: self._set_visible(n, checked),
            )
            self.table.setCellWidget(row, _COL_VISIBLE, self._centered(visible_btn))

            locked_btn = self._toggle_button(
                layer.locked, _draw_lock,
                "Camada travada — visível, mas não pode ser selecionada/editada",
                "Camada destravada — clique pra travar",
                lambda checked, n=name: self._set_locked(n, checked),
            )
            self.table.setCellWidget(row, _COL_LOCKED, self._centered(locked_btn))

            color_btn = QToolButton()
            color_btn.setStyleSheet(_TOGGLE_STYLE)
            color_btn.setIcon(make_icon(_draw_swatch(layer.color)))
            color_btn.setToolTip(f"Cor da camada ({layer.color}) — clique pra mudar")
            color_btn.clicked.connect(lambda checked=False, n=name: self._pick_color(n))
            self.table.setCellWidget(row, _COL_COLOR, self._centered(color_btn))

    def _toggle_button(self, checked_state, draw_fn_factory, tip_on, tip_off, handler) -> QToolButton:
        button = QToolButton()
        button.setCheckable(True)
        button.setChecked(checked_state)
        button.setStyleSheet(_TOGGLE_STYLE)
        button.setIcon(make_icon(draw_fn_factory(checked_state)))
        button.setToolTip(tip_on if checked_state else tip_off)

        def on_toggled(checked: bool) -> None:
            button.setIcon(make_icon(draw_fn_factory(checked)))
            button.setToolTip(tip_on if checked else tip_off)
            handler(checked)

        button.toggled.connect(on_toggled)
        return button

    @staticmethod
    def _centered(widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(widget)
        return wrapper

    # ------------------------------------------------------------------ #
    # ações
    # ------------------------------------------------------------------ #
    def _set_visible(self, name: str, visible: bool) -> None:
        document = self.main_window.document
        layer = document.layers.get(name)
        if layer is None:
            return
        layer.visible = visible
        self.main_window.canvas.refresh_entities()
        self.main_window.canvas.viewport().update()

    def _set_locked(self, name: str, locked: bool) -> None:
        document = self.main_window.document
        layer = document.layers.get(name)
        if layer is None:
            return
        layer.locked = locked
        # Trancar uma camada não muda o desenho na tela, só o que dá pra
        # selecionar — mas uma seleção já feita antes de travar pode conter
        # entidades da camada, então limpamos pra manter consistente com
        # "trancado = intocável".
        self.main_window.selection.clear()
        self.main_window.canvas.refresh_selection_highlight()
        self.main_window.canvas.viewport().update()

    def _pick_color(self, name: str) -> None:
        document = self.main_window.document
        layer = document.layers.get(name)
        if layer is None:
            return
        chosen = QColorDialog.getColor(QColor(layer.color), self, f"Cor da camada '{name}'")
        if not chosen.isValid():
            return
        self._set_color_with_hex(name, chosen.name())

    def _set_color_with_hex(self, name: str, color_hex: str) -> None:
        """Lógica de aplicar a cor em si, separada de `_pick_color` (que
        abre o QColorDialog) pra poder ser testada sem simular um diálogo."""
        document = self.main_window.document
        layer = document.layers.get(name)
        if layer is None:
            return
        layer.color = color_hex
        self.main_window.canvas.refresh_entities()
        self.refresh()

    def _handle_double_click(self, row: int, column: int) -> None:
        name_item = self.table.item(row, _COL_NAME)
        if name_item is None:
            return
        self.main_window.document.set_current_layer(name_item.text())
        self.refresh()

    def _show_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        name_item = self.table.item(row, _COL_NAME)
        if name_item is None:
            return
        name = name_item.text()

        menu = QMenu(self)
        rename_action = menu.addAction("Renomear...")
        rename_action.setEnabled(name != "0")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is rename_action:
            self._rename_layer(name)

    def prompt_rename_current_layer(self) -> None:
        """Chamado pelo comando RENAME (REN) digitado — sem uma linha da
        tabela clicada pra saber qual camada, usa a camada atual como
        default (mesmo padrão de "onde o usuário está trabalhando agora")."""
        self._rename_layer(self.main_window.document.current_layer)

    def _rename_layer(self, old_name: str) -> None:
        if old_name == "0":
            QMessageBox.information(self, "Renomear camada", 'A camada "0" não pode ser renomeada.')
            return
        new_name, ok = QInputDialog.getText(self, "Renomear camada", "Novo nome:", text=old_name)
        if not ok:
            return
        self._rename_layer_with_names(old_name, new_name)

    def _rename_layer_with_names(self, old_name: str, new_name: str) -> None:
        """Lógica de renomear em si, separada de `_rename_layer` (que lida
        com o QInputDialog) pra poder ser testada sem simular um diálogo."""
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        try:
            self.main_window.document.rename_layer(old_name, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Renomear camada", str(exc))
            return
        self.refresh()
        self.main_window._refresh_properties_panel()

    def _create_layer(self) -> None:
        name, ok = QInputDialog.getText(self, "Nova camada", "Nome da camada:")
        if not ok:
            return
        self._create_layer_with_name(name)

    def _create_layer_with_name(self, name: str) -> None:
        """Lógica de criação em si, separada de `_create_layer` (que só lida
        com o QInputDialog) pra poder ser testada sem precisar simular um
        diálogo modal."""
        name = name.strip()
        if not name:
            return
        if name in self.main_window.document.layers:
            QMessageBox.information(self, "Nova camada", f"A camada '{name}' já existe.")
            return
        self.main_window.document.add_layer(name)
        self.refresh()
