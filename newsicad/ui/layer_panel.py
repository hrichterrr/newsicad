"""Painel de Camadas (comando LAYER/LA): lista todas as camadas do desenho
com toggle de visibilidade e trava, e qual é a camada atual (onde entidades
novas são desenhadas). Ao contrário do XrefPanel/BlockEditorDialog (QDialog
modal), este é um QDockWidget não-modal — o objetivo é deixar ligar/desligar
camadas olhando o efeito no canvas em tempo real, sem fechar nada.

Nota: `Layer.color` existe no modelo (`newsicad/core/document.py`) mas o
canvas nunca usou cor nenhuma pra renderizar entidades (sempre um branco
fixo, ver `_entity_pen()`) — por isso este painel não oferece editar cor:
seria um controle que muda o dado sem nenhum efeito visível, e isso é pior
que não ter o controle. Ver README para essa limitação."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QVBoxLayout,
    QWidget,
)

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

_COL_VISIBLE, _COL_LOCKED, _COL_NAME = range(3)


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

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Vis", "Trava", "Nome"])
        self.table.setStyleSheet(LAYER_TABLE_STYLE)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_VISIBLE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_LOCKED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
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

            visible_box = QCheckBox()
            visible_box.setChecked(layer.visible)
            visible_box.toggled.connect(lambda checked, n=name: self._set_visible(n, checked))
            self.table.setCellWidget(row, _COL_VISIBLE, self._centered(visible_box))

            locked_box = QCheckBox()
            locked_box.setChecked(layer.locked)
            locked_box.toggled.connect(lambda checked, n=name: self._set_locked(n, checked))
            self.table.setCellWidget(row, _COL_LOCKED, self._centered(locked_box))

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if name == document.current_layer:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setForeground(QColor("#4da3ff"))
            name_item.setToolTip("Duplo clique pra tornar esta a camada atual")
            self.table.setItem(row, _COL_NAME, name_item)

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
