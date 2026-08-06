"""Painel EXTERNALREFERENCES (ER): lista as xrefs inseridas no desenho atual
(BlockReference com is_xref=True) e permite "Reload" — relê o .dxf original
e substitui a definição do bloco correspondente.

Limitação documentada (ver README): não há watch automático do arquivo.
"Atualizar" uma xref, hoje, significa clicar em Reload manualmente; se o
arquivo original mudou, os desenhos que o referenciam só percebem quando o
usuário pedir."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from newsicad.core.entities import BlockReference
from newsicad.io.dxf_io import DxfIoError, load_dxf

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow


class XrefPanel(QDialog):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.main_window = window
        self.setWindowTitle("External References")
        self.resize(560, 320)

        layout = QVBoxLayout(self)

        note = QLabel(
            "Referências externas (.dxf) inseridas neste desenho. \"Reload\" relê o\n"
            "arquivo do disco — não há atualização automática (sem watch de arquivo)."
        )
        note.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(note)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Bloco", "Arquivo"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, stretch=1)

        button_row = QHBoxLayout()
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload_selected)
        button_row.addWidget(reload_button)
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._refresh_table()

    def _xref_references(self) -> list[BlockReference]:
        return [
            e
            for e in self.main_window.document.all_entities()
            if isinstance(e, BlockReference) and e.is_xref
        ]

    def _refresh_table(self) -> None:
        refs = self._xref_references()
        self.table.setRowCount(len(refs))
        for row, ref in enumerate(refs):
            self.table.setItem(row, 0, QTableWidgetItem(ref.block_name))
            path_text = str(ref.xref_path) if ref.xref_path else "(caminho desconhecido)"
            self.table.setItem(row, 1, QTableWidgetItem(path_text))

    def _reload_selected(self) -> None:
        row = self.table.currentRow()
        refs = self._xref_references()
        if row < 0 or row >= len(refs):
            QMessageBox.information(self, "Reload", "Selecione uma referência externa na lista.")
            return

        ref = refs[row]
        if ref.xref_path is None:
            QMessageBox.warning(self, "Reload", "Esta referência não guarda o caminho do arquivo original.")
            return

        try:
            loaded, _skipped = load_dxf(ref.xref_path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao recarregar xref", str(exc))
            return

        self.main_window.document.define_block(ref.block_name, loaded.all_entities())
        self.main_window.canvas.refresh_entities()
        self.main_window.canvas.viewport().update()
        QMessageBox.information(self, "Reload", f'Referência "{ref.block_name}" recarregada.')
