"""Janela principal: menu superior estilo AutoCAD, Quick Access Toolbar,
ribbon, abas de documento (vários desenhos abertos ao mesmo tempo — cada aba
é uma `DocumentSession` independente, ver newsicad/ui/document_session.py),
linha de comando (dock inferior), painel de propriedades (Ctrl+1) e barra de
status (coordenadas + toggles GRID/SNAP/ORTHO/POLAR/OSNAP/OSNAP
TRACKING/DYNAMIC INPUT)."""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from newsicad.commands.block_commands import place_image_command, place_reference_command
from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import READ_ONLY_COMMANDS
from newsicad.core.document import Document, MLeaderStyle, TableStyle, TextStyle
from newsicad.core.entities import Dimension, Point, Table, Text
from newsicad.core.selection import Selection
from newsicad.core.undo import UndoStack
from newsicad.io.dwg_bridge import DwgBridgeError, dwg_to_document
from newsicad.io.dwg_export import DwgExportError, document_to_dwg
from newsicad.io.dxf_io import DxfIoError, load_dxf, save_dxf
from newsicad.io.open_cache import load_cached, store_cached
from newsicad.io.pdf_import import PdfImportError, import_pdf_page, pdf_page_count
from newsicad.ui.block_editor_dialog import BlockEditorDialog
from newsicad.ui.canvas import PDF_PAGE_SIZES, CanvasView
from newsicad.ui.command_line import CommandLineWidget
from newsicad.ui.document_session import DocumentSession
from newsicad.ui.icon_utils import FAMILY_NEUTRAL, command_icon, svg_icon, svg_toggle_icon
from newsicad.ui.layer_panel import LayerPanel
from newsicad.ui.menu_bar import MENU_BAR_STYLE, build_menu_bar
from newsicad.ui.properties_panel import PropertiesPanel
from newsicad.ui.ribbon import build_quick_access_toolbar, build_ribbon
from newsicad.ui.xref_panel import XrefPanel

APP_VERSION = "2.15.1"
APP_TITLE = f"NewSIcad {APP_VERSION} — Developed by HRichter"

STATUS_TOGGLE_STYLE = """
    QPushButton {
        background-color: #2b2b2b;
        color: #a0a0a0;
        border: 1px solid #3a3a3a;
        padding: 2px 8px;
        font-size: 11px;
    }
    QPushButton:checked {
        background-color: #3a5a8c;
        color: #ffffff;
    }
    QPushButton[iconOnly="true"] {
        background-color: transparent;
        border: none;
        border-radius: 2px;
        padding: 0px;
        color: transparent;
        font-size: 1px;
    }
    QPushButton[iconOnly="true"]:hover { background-color: #3a3a3a; }
    QPushButton[iconOnly="true"]:checked { background-color: #3a5a8c; }
"""

DARK_TEXT_STYLE = """
    QTextEdit {
        background-color: #141414;
        color: #d8d8d8;
        border: 1px solid #333333;
        font-family: "Menlo";
        font-size: 12px;
    }
"""

# Abas de documento — cada página da QTabWidget É o CanvasView da sessão
# correspondente (ver DocumentSession). Estilo escuro consistente com o
# ribbon/canvas, com o "x" de fechar sempre visível (setTabsClosable).
DOC_TABS_STYLE = """
    QTabWidget::pane { border: none; }
    QTabBar {
        background-color: #1c1c1c;
        border-bottom: 1px solid #333333;
    }
    QTabBar::tab {
        background-color: #1c1c1c;
        color: #9a9a9a;
        padding: 6px 12px;
        border-top: 2px solid transparent;
    }
    QTabBar::tab:selected {
        background-color: #2d2d2d;
        color: #ffffff;
        border-top: 2px solid #4da3ff;
    }
    QTabBar::tab:hover:!selected {
        background-color: #262626;
    }
    QTabBar::close-button {
        subcontrol-position: right;
    }
"""


def _skipped_warning(skipped, subject: str) -> str:
    """Monta a mensagem de aviso de entidades ignoradas na leitura de um
    arquivo. `skipped` pode ser um `SkippedCount` (int com `.by_type`
    opcional, ver dxf_io.py) — quando tem breakdown, mostra os tipos de
    entidade mais frequentes primeiro, em vez de só o total; sem isso, um
    tester reportando "vários itens sumiram" não tinha como saber SE o
    problema era um tipo de entidade específico não suportado ainda ou outra
    coisa (caso real reportado pelos testers em 2026-08-24)."""
    msg = f"Aviso: {skipped} entidade(s) {subject} não são suportadas e foram ignoradas."
    by_type = getattr(skipped, "by_type", None)
    if by_type:
        breakdown = ", ".join(f"{n}x {t}" for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]))
        msg += f" ({breakdown})"
    return msg


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        self._untitled_counter = 0
        self.sessions: list[DocumentSession] = []
        # _on_active_tab_changed toca em widgets (status bar, docks) que só
        # existem depois de _build_* rodar — a primeira aba já é criada bem
        # antes disso (ver comentário abaixo), então essa flag evita que o
        # sinal currentChanged dispare esse sync cedo demais; ligada no fim
        # do __init__, que então chama o sync manualmente uma vez.
        self._ui_ready = False

        self.doc_tabs = QTabWidget()
        self.doc_tabs.setStyleSheet(DOC_TABS_STYLE)
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.tabCloseRequested.connect(self._close_tab)
        self.doc_tabs.currentChanged.connect(self._on_active_tab_changed)

        # "+" no canto da barra de abas pra abrir um desenho novo — mesma
        # convenção de qualquer app com abas (navegador, VS Code...). File >
        # New / Ctrl+N / o botão "New" do ribbon e da QAT já faziam a mesma
        # coisa, mas sem um "+" na própria barra de abas não tinha nenhum
        # jeito óbvio de abrir uma aba olhando só pra lá.
        new_tab_button = QToolButton()
        new_tab_button.setText("+")
        new_tab_button.setToolTip("Novo desenho (Ctrl+N)")
        new_tab_button.setAutoRaise(True)
        new_tab_button.setStyleSheet(
            "QToolButton { color: #a0a0a0; font-size: 15px; font-weight: bold; "
            "background: #1c1c1c; border: none; padding: 2px 10px; } "
            "QToolButton:hover { color: #ffffff; background: #3a3a3a; }"
        )
        new_tab_button.clicked.connect(self._new_document)
        self.doc_tabs.setCornerWidget(new_tab_button, Qt.Corner.TopRightCorner)

        # A primeira sessão precisa existir ANTES de qualquer dock que leia
        # window.document/window.canvas na própria construção (LayerPanel
        # chama self.refresh() já no __init__) — self.doc_tabs.addTab() não
        # depende de doc_tabs já estar dentro do layout da janela, só de já
        # existir como objeto (ver _build_central_widget mais abaixo).
        self._add_session_tab(self._make_untitled_session())

        self._build_command_dock()
        self._build_status_bar()
        self._build_properties_dock()
        self._build_layer_dock()
        self._build_central_widget()
        self.setMenuBar(build_menu_bar(self))

        self._ui_ready = True
        self._on_active_tab_changed(self.doc_tabs.currentIndex())
        self.command_line.focus_input()

    # ------------------------------------------------------------------ #
    # sessões de documento (abas) — ver newsicad/ui/document_session.py
    # ------------------------------------------------------------------ #
    def _make_untitled_session(self) -> DocumentSession:
        self._untitled_counter += 1
        return DocumentSession(f"Drawing{self._untitled_counter}")

    def _active_session(self) -> DocumentSession:
        return self.sessions[self.doc_tabs.currentIndex()]

    def _wire_session_canvas(self, session: DocumentSession) -> None:
        canvas = session.canvas
        canvas.on_point = self._handle_canvas_point
        canvas.on_enter = self._handle_enter
        canvas.on_cancel = self._handle_cancel
        canvas.on_delete = self._delete_selected
        canvas.on_selection_changed = self._refresh_properties_panel
        canvas.on_context_menu = self._show_selection_context_menu
        canvas.mouse_moved.connect(self._handle_mouse_moved)

    def _on_viewport_pane_selection_changed(self, session: DocumentSession) -> None:
        """Contraparte de `on_selection_changed` pras panes SECUNDÁRIAS de
        Viewport Configuration — a seleção é compartilhada (mesmo
        `ctx.selection`), então clicar numa pane secundária muda a seleção
        de verdade, mas cada CanvasView guarda seu PRÓPRIO realce visual;
        sem propagar pra todo mundo, só quem clicou saberia (e nem isso, já
        que essa pane nem tem o próprio realce ligado a um refresh
        explícito aqui)."""
        self._refresh_properties_panel()
        session.canvas.refresh_selection_highlight()
        for pane in session.viewport_panes:
            pane.refresh_selection_highlight()

    def _add_session_tab(self, session: DocumentSession) -> None:
        self._wire_session_canvas(session)
        self.sessions.append(session)
        session.tab_widget = session.canvas
        index = self.doc_tabs.addTab(session.canvas, session.tab_label())
        self.doc_tabs.setCurrentIndex(index)

    def _close_tab(self, index: int) -> None:
        session = self.sessions[index]
        if session.is_dirty():
            self.doc_tabs.setCurrentIndex(index)
            if not self._confirm_discard_changes():
                return
        self.sessions.pop(index)
        widget = self.doc_tabs.widget(index)
        self.doc_tabs.removeTab(index)
        widget.deleteLater()
        if not self.sessions:
            self._add_session_tab(self._make_untitled_session())

    def _close_current_tab(self) -> None:
        if self.sessions:
            self._close_tab(self.doc_tabs.currentIndex())

    def _on_active_tab_changed(self, index: int) -> None:
        if not self._ui_ready or index < 0 or index >= len(self.sessions):
            return
        session = self.sessions[index]
        self._sync_status_toggles(session)
        self._update_window_title()
        self._refresh_prompt()
        self._refresh_properties_panel()
        self.layer_dock.refresh()
        self.command_line.focus_input()

    def _sync_status_toggles(self, session: DocumentSession) -> None:
        """Cada aba tem seu próprio CanvasView, então GRID/SNAP/ORTHO/OSNAP/
        POLAR/DYN são por aba (mesmo espírito de systemvars por desenho do
        AutoCAD) — ao trocar de aba, os toggles da barra de status (e os
        espelhados no ribbon) passam a refletir o estado da aba nova, sem
        disparar `_toggle_*` de novo (blockSignals evita um round-trip
        redundante escrevendo o mesmo valor de volta no canvas já correto)."""
        canvas = session.canvas
        pairs = [
            (self.grid_button, canvas.grid_visible),
            (self.snap_button, canvas.snap_enabled),
            (self.ortho_button, canvas.ortho_enabled),
            (self.polar_button, canvas.polar_enabled),
            (self.osnap_button, canvas.osnap_enabled),
            (self.dynamic_input_button, canvas.dynamic_input_enabled),
        ]
        for button, value in pairs:
            button.blockSignals(True)
            button.setChecked(value)
            button.blockSignals(False)

        # Annotation Scale também é por documento (Document.annotation_scale)
        scale_index = self.annotation_scale_combo.findData(session.document.annotation_scale)
        if scale_index < 0:
            scale_index = self.annotation_scale_combo.findText("1:1")
        self.annotation_scale_combo.blockSignals(True)
        self.annotation_scale_combo.setCurrentIndex(scale_index)
        self.annotation_scale_combo.blockSignals(False)

    def _on_annotation_scale_changed(self, index: int) -> None:
        value = self.annotation_scale_combo.itemData(index)
        if value is not None:
            self.document.annotation_scale = value

    def _refresh_tab_labels(self) -> None:
        for index, session in enumerate(self.sessions):
            self.doc_tabs.setTabText(index, session.tab_label())

    # ------------------------------------------------------------------ #
    # indireção pra aba ativa: o resto do app (menu, ribbon, docks, testes)
    # continua lendo/escrevendo window.document/window.canvas/etc como se
    # fosse um documento só — essas propriedades é que resolvem pra sessão
    # ativa no momento, sem precisar mudar mais nada no resto do código.
    # ------------------------------------------------------------------ #
    @property
    def document(self) -> Document:
        return self._active_session().document

    @property
    def selection(self) -> Selection:
        return self._active_session().selection

    @property
    def context(self) -> CommandContext:
        return self._active_session().context

    @property
    def interpreter(self) -> CommandInterpreter:
        return self._active_session().interpreter

    @property
    def undo_stack(self) -> UndoStack:
        return self._active_session().undo_stack

    @property
    def canvas(self) -> CanvasView:
        return self._active_session().canvas

    @property
    def current_path(self) -> Path | None:
        return self._active_session().current_path

    @current_path.setter
    def current_path(self, value: Path | None) -> None:
        self._active_session().current_path = value

    @property
    def _last_cursor_point(self) -> Point | None:
        return self._active_session().last_cursor_point

    @_last_cursor_point.setter
    def _last_cursor_point(self, value: Point | None) -> None:
        self._active_session().last_cursor_point = value

    # ------------------------------------------------------------------ #
    # construção da UI
    # ------------------------------------------------------------------ #
    def _build_central_widget(self) -> None:
        """Quick Access Toolbar (comandos principais sempre visíveis, não
        somem trocando de aba do ribbon) + Ribbon estilo AutoCAD + abas de
        documento. Ribbon/QAT convivem com o menu clássico (File/Edit/
        View/...), não o substituem."""
        self.qat = build_quick_access_toolbar(self)
        self.ribbon = build_ribbon(self)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.qat)
        layout.addWidget(self.ribbon)
        layout.addWidget(self.doc_tabs, stretch=1)
        self.setCentralWidget(central)

    def _build_command_dock(self) -> None:
        self.command_line = CommandLineWidget()
        self.command_line.text_submitted.connect(self._handle_text_submitted)
        self.command_line.cancel_requested.connect(self._handle_cancel)
        self.command_line.undo_requested.connect(self._do_undo)
        self.command_line.redo_requested.connect(self._do_redo)

        self.command_dock = QDockWidget("", self)
        self.command_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.command_dock.setTitleBarWidget(QWidget())
        self.command_dock.setWidget(self.command_line)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.command_dock)

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)

        self.coord_label = QLabel("0.00, 0.00")
        self.coord_label.setStyleSheet("color: #d8d8d8; font-family: Menlo; padding: 0 8px;")
        status.addWidget(self.coord_label)

        # Toggles só de ícone, como a barra de status do AutoCAD 2020 (azul
        # quando ligado); o nome e o atalho ficam no tooltip. Os ícones são
        # os mesmos do ribbon (newsicad/resources/icons).
        self.grid_button = self._make_toggle("GRID", "F7", self._toggle_grid, checked=True, icon="grid")
        self.snap_button = self._make_toggle("SNAP", "F9", self._toggle_snap, icon="snap")
        self.ortho_button = self._make_toggle("ORTHO", "F8", self._toggle_ortho, icon="ortho")
        self.polar_button = self._make_toggle(
            "POLAR", "F10", self._toggle_polar, icon="polar",
            tooltip="POLAR (F10) — rastreamento polar, gruda em múltiplos de 15° a partir do último ponto",
        )
        self.osnap_button = self._make_toggle(
            "OSNAP", "F3", self._toggle_osnap, icon="osnap",
            tooltip="OSNAP (F3) — snap a objetos (Endpoint/Midpoint/Center/Intersection/Node/Insert)",
        )
        self.osnap_tracking_button = self._make_toggle(
            "OTRACK", "F11", self._toggle_osnap_tracking, icon="otrack",
            tooltip="OTRACK (F11) — rastreamento de OSNAP, ainda não implementado (previsto para um próximo marco)",
        )
        # Diferente de todo outro controle "ainda não implementado" no app
        # (que vem desabilitado), este ficava clicável/marcável mas sem
        # nenhum efeito — parecia ligado sem fazer nada (bug real de
        # auditoria, 2026-08-22).
        self.osnap_tracking_button.setEnabled(False)
        self.dynamic_input_button = self._make_toggle(
            "DYN", "F12", self._toggle_dynamic_input, checked=True, icon="dyn",
            tooltip="DYN (F12) — entrada dinâmica (distância/ângulo perto do cursor)",
        )

        for button in (
            self.grid_button, self.snap_button, self.ortho_button, self.polar_button,
            self.osnap_button, self.osnap_tracking_button, self.dynamic_input_button,
        ):
            status.addPermanentWidget(button)

        # Annotation Scale: multiplicador global simplificado (sem
        # representações múltiplas por objeto/viewport como o de verdade do
        # AutoCAD, que não se aplica sem paper space — ver
        # Document.annotation_scale) aplicado na altura de texto/cota/
        # tabela/leader NA HORA DE CRIAR (não retroativo aos já desenhados).
        scale_label = QLabel("Scale:")
        scale_label.setStyleSheet("color: #8a8a90; font-size: 11px; padding-left: 6px;")
        status.addPermanentWidget(scale_label)
        self.annotation_scale_combo = QComboBox()
        self.annotation_scale_combo.setStyleSheet(
            "QComboBox { background-color: #2b2b2b; color: #d0d0d0; border: 1px solid #3a3a3a; "
            "padding: 1px 4px; font-size: 11px; }"
        )
        for label, value in (
            ("1:100", 0.01), ("1:50", 0.02), ("1:20", 0.05), ("1:10", 0.1),
            ("1:2", 0.5), ("1:1", 1.0), ("2:1", 2.0), ("10:1", 10.0),
        ):
            self.annotation_scale_combo.addItem(label, value)
        self.annotation_scale_combo.setCurrentIndex(5)  # "1:1"
        self.annotation_scale_combo.currentIndexChanged.connect(self._on_annotation_scale_changed)
        status.addPermanentWidget(self.annotation_scale_combo)

        brand = QLabel(f"NewSIcad {APP_VERSION} · Developed by HRichter")
        brand.setStyleSheet("color: #6a8fc9; font-family: Menlo; font-size: 11px; padding: 0 10px;")
        status.addPermanentWidget(brand)

    def _build_properties_dock(self) -> None:
        self.properties_dock = PropertiesPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

    def _build_layer_dock(self) -> None:
        self.layer_dock = LayerPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.layer_dock)
        self.tabifyDockWidget(self.properties_dock, self.layer_dock)
        self.properties_dock.raise_()

    def _make_toggle(self, label, shortcut, handler, checked=False, tooltip=None, icon=None) -> QPushButton:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setStyleSheet(STATUS_TOGGLE_STYLE)
        button.setToolTip(tooltip or f"{label} ({shortcut})")
        if icon is not None:
            # Só o ícone (o rótulo continua em text() pra busca/testes, mas
            # não é desenhado — ver STATUS_TOGGLE_STYLE, que zera a fonte).
            button.setIcon(svg_toggle_icon(icon, 16))
            button.setIconSize(QSize(16, 16))
            button.setProperty("iconOnly", True)
            button.setFixedSize(26, 22)
        button.toggled.connect(handler)

        action = QAction(self)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(button.toggle)
        self.addAction(action)

        return button

    # ------------------------------------------------------------------ #
    # toggles da barra de status
    # ------------------------------------------------------------------ #
    def _toggle_grid(self, checked: bool) -> None:
        self.canvas.set_grid_visible(checked)

    def _toggle_snap(self, checked: bool) -> None:
        self.canvas.set_snap_enabled(checked)

    def _toggle_ortho(self, checked: bool) -> None:
        self.canvas.set_ortho_enabled(checked)

    def _toggle_polar(self, checked: bool) -> None:
        self.canvas.set_polar_enabled(checked)

    def _toggle_osnap(self, checked: bool) -> None:
        self.canvas.set_osnap_enabled(checked)

    def _toggle_osnap_tracking(self, checked: bool) -> None:
        pass  # reservado: par do OSNAP, mesmo marco futuro

    def _toggle_dynamic_input(self, checked: bool) -> None:
        self.canvas.set_dynamic_input_enabled(checked)

    # ------------------------------------------------------------------ #
    # comandos: início, repetição, undo/redo
    # ------------------------------------------------------------------ #
    def _start_command(self, text: str) -> None:
        """Inicia um comando a partir de texto digitado OU de um clique de menu
        (ex.: menu Draw > Line chama `_start_command("LINE")`)."""
        if self.interpreter.active:
            return
        name = self.interpreter.resolve_command(text)
        if name in ("UNDO", "OOPS"):
            # OOPS no AutoCAD restaura só o último apagado, mesmo que outros
            # comandos tenham rodado depois — simplificação aqui: como nosso
            # undo é por snapshot do desenho inteiro, um Undo comum cobre o
            # caso de uso típico (desfazer o ERASE mais recente).
            self._do_undo()
            self._after_interpreter_step()
            return
        if name == "REDO":
            self._do_redo()
            self._after_interpreter_step()
            return
        if name == "REGEN":
            self.interpreter.log.append("Regenerating model.")
            self.canvas.refresh_entities()
            self._after_interpreter_step()
            return
        if name == "UNITS":
            self._show_units_dialog()
            self._after_interpreter_step()
            return
        if name in ("BEDIT", "REFEDIT"):
            self._start_bedit()
            self._after_interpreter_step()
            return
        if name == "XREF":
            self._start_xref()
            self._after_interpreter_step()
            return
        if name == "EXTERNALREFERENCES":
            XrefPanel(self).exec()
            self._after_interpreter_step()
            return
        if name in ("LAYER", "RENAME"):
            self.layer_dock.refresh()
            self.layer_dock.setVisible(True)
            self.layer_dock.raise_()
            if name == "RENAME":
                self.layer_dock.prompt_rename_current_layer()
            self._after_interpreter_step()
            return
        if name == "IMAGEATTACH":
            self._start_imageattach()
            self._after_interpreter_step()
            return
        if name == "IMPORTPDF":
            self._start_import_pdf()
            self._after_interpreter_step()
            return
        if name in ("PLOT", "PUBLISH"):
            self._export_pdf()
            self._after_interpreter_step()
            return
        if name == "STYLE":
            self._show_text_style_dialog()
            self._after_interpreter_step()
            return
        if name == "TABLESTYLE":
            self._show_table_style_dialog()
            self._after_interpreter_step()
            return
        if name == "MLEADERSTYLE":
            self._show_mleader_style_dialog()
            self._after_interpreter_step()
            return
        if name == "FIND":
            self._show_find_dialog()
            self._after_interpreter_step()
            return
        if name == "DATALINK":
            self._show_datalink_dialog()
            self._after_interpreter_step()
            return
        if name == "VIEWPORTS":
            self._show_vports_dialog()
            self._after_interpreter_step()
            return
        if name not in READ_ONLY_COMMANDS:
            self.undo_stack.push()
        self.interpreter.start(text)
        self._after_interpreter_step()

    def _select_all(self) -> None:
        self.selection.set(set(self.document.entities.keys()))
        self.canvas.refresh_selection_highlight()
        self.canvas.viewport().update()
        self._refresh_properties_panel()

    def _show_selection_context_menu(self) -> None:
        """Menu de contexto no botão direito, sobre uma entidade já
        selecionada (canvas.py garante isso antes de chamar aqui — clicar
        com o direito num objeto ainda não selecionado o seleciona antes de
        abrir o menu). Pedido real da Rafaela: ela tentava usar o botão
        direito pra selecionar linhas/o desenho, e não tinha efeito nenhum —
        na real, não existia NENHUMA forma de selecionar clicando fora de um
        comando tipo ERASE/MOVE (só durante o prompt "Select objects:"
        deles, ver canvas.py:mousePressEvent)."""
        if not self.selection.ids:
            return
        menu = self._build_selection_context_menu()
        menu.exec(QCursor.pos())

    def _build_selection_context_menu(self) -> QMenu:
        """Menu do botão direito com seleção, na ordem do menu de contexto do
        AutoCAD (Repeat, Clipboard, Isolate, Erase/Move/Copy/Scale/Rotate,
        Select Similar/Deselect All, Quick Select/Find/Properties), com os
        mesmos ícones do ribbon e do menu clássico (icon_utils.command_icon).
        Itens que o AutoCAD tem e o NewSIcad não ficam desabilitados."""
        menu = QMenu(self)
        menu.setStyleSheet(MENU_BAR_STYLE)  # mesmo tema escuro do menu clássico
        cmd = lambda name: (lambda: self._start_command(name))  # noqa: E731

        last = self.interpreter.last_command_name
        repeat = menu.addAction(svg_icon("repeat", FAMILY_NEUTRAL, 16), f"Repeat {last}" if last else "Repeat")
        if last:
            repeat.triggered.connect(cmd(last))
        else:
            repeat.setEnabled(False)
        recent = menu.addAction(svg_icon("history", FAMILY_NEUTRAL, 16), "Recent Input")
        recent.setEnabled(False)
        menu.addSeparator()

        clipboard = menu.addMenu(svg_icon("paste", FAMILY_NEUTRAL, 16), "Clipboard")
        clipboard.addAction(command_icon("CUTCLIP"), "Cut\tCtrl+X", cmd("CUTCLIP"))
        clipboard.addAction(command_icon("COPYCLIP"), "Copy\tCtrl+C", cmd("COPYCLIP"))
        clipboard.addAction(svg_icon("copybase", FAMILY_NEUTRAL, 16), "Copy with Base Point\tCtrl+Shift+C", cmd("COPY"))
        clipboard.addAction(command_icon("PASTECLIP"), "Paste\tCtrl+V", cmd("PASTECLIP"))
        isolate = menu.addMenu(command_icon("LAYISO"), "Isolate")
        isolate.addAction(command_icon("LAYISO"), "Isolate Layer(s)", cmd("LAYISO"))
        isolate.addAction(command_icon("LAYUNISO"), "Unisolate Layer(s)", cmd("LAYUNISO"))
        menu.addSeparator()

        menu.addAction(command_icon("ERASE"), "Erase", self._delete_selected)
        menu.addAction(command_icon("MOVE"), "Move", cmd("MOVE"))
        menu.addAction(command_icon("COPY"), "Copy Selection", cmd("COPY"))
        menu.addAction(command_icon("SCALE"), "Scale", cmd("SCALE"))
        menu.addAction(command_icon("ROTATE"), "Rotate", cmd("ROTATE"))
        draw_order = menu.addAction(svg_icon("draworder", FAMILY_NEUTRAL, 16), "Draw Order")
        draw_order.setEnabled(False)
        group = menu.addAction(svg_icon("group", FAMILY_NEUTRAL, 16), "Group")
        group.setEnabled(False)
        menu.addSeparator()

        menu.addAction(command_icon("SELECTSIMILAR"), "Select Similar", cmd("SELECTSIMILAR"))
        menu.addAction(svg_icon("deselect", FAMILY_NEUTRAL, 16), "Deselect All", self._deselect_all)
        menu.addSeparator()

        menu.addAction(command_icon("QSELECT"), "Quick Select...", cmd("QSELECT"))
        menu.addAction(command_icon("FIND"), "Find...\tCtrl+F", cmd("FIND"))
        menu.addAction(svg_icon("props", FAMILY_NEUTRAL, 16), "Properties\tCtrl+1", self._show_properties_dock)
        return menu

    def _deselect_all(self) -> None:
        self.selection.clear()
        self.canvas.refresh_selection_highlight()
        self.canvas.viewport().update()

    def refresh_layer_combo(self) -> None:
        """Atualiza o combo de camada atual do ribbon (painel Layers da aba
        Home) — chamado por LayerPanel.refresh, que já é o ponto único por
        onde toda mudança de camada passa."""
        combo = getattr(self, "layer_combo", None)
        if combo is not None:
            combo.refresh()

    def _show_properties_dock(self) -> None:
        self.properties_dock.setVisible(True)
        self.properties_dock.raise_()

    def _delete_selected(self) -> None:
        """Del/Backspace no canvas: apaga a seleção atual direto, sem
        precisar digitar ERASE (que limpa a seleção e pede uma nova). Só
        age fora de um comando ativo, pra não interferir com Del/Backspace
        que algum comando futuro venha a usar com outro sentido."""
        if self.interpreter.active or not self.selection.ids:
            return
        self.undo_stack.push()
        for entity_id in list(self.selection.ids):
            self.document.remove_entity(entity_id)
        self.selection.clear()
        self.canvas.refresh_entities()
        self._refresh_properties_panel()
        self.layer_dock.refresh()

    def _show_units_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Units")
        layout = QFormLayout(dialog)

        combo = QComboBox()
        options = ["mm", "cm", "m", "in", "ft"]
        combo.addItems(options)
        if self.document.units in options:
            combo.setCurrentText(self.document.units)
        layout.addRow("Unidade de desenho:", combo)

        note = QLabel(
            "Só define a unidade nominal do desenho (metadado salvo no\n"
            "arquivo) — não reescala entidades já desenhadas."
        )
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.document.units = combo.currentText()

    # ------------------------------------------------------------------ #
    # STYLE / TABLESTYLE / MLEADERSTYLE / FIND / DATALINK / VIEWPORTS
    # ------------------------------------------------------------------ #
    def _show_text_style_dialog(self) -> None:
        """STYLE (ST): estilos de texto nomeados — versão simplificada do
        Text Style de verdade do AutoCAD (sem largura/oblíquo/efeitos). OK
        cria o estilo se o nome digitado não existir ainda, e o torna o
        estilo atual (usado pelo próximo MTEXT/LEADER/FIELD)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Text Style")
        layout = QFormLayout(dialog)

        name_combo = QComboBox()
        name_combo.setEditable(True)
        name_combo.addItems(sorted(self.document.text_styles.keys()))
        name_combo.setCurrentText(self.document.current_text_style)
        layout.addRow("Style name:", name_combo)

        font_combo = QFontComboBox()
        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.01, 10000.0)
        height_spin.setDecimals(2)

        def load_style(name: str) -> None:
            style = self.document.text_styles.get(name)
            font_combo.setCurrentFont(QFont(style.font_family if style else "Menlo"))
            height_spin.setValue(style.height if style else 2.5)

        load_style(self.document.current_text_style)
        name_combo.currentTextChanged.connect(load_style)

        layout.addRow("Font:", font_combo)
        layout.addRow("Height:", height_spin)

        note = QLabel(
            "Cria o estilo se o nome digitado ainda não existir. OK também o\n"
            "torna o estilo atual — usado no próximo texto/leader/field criado."
        )
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_combo.currentText().strip() or "Standard"
            self.document.text_styles[name] = TextStyle(
                name=name, font_family=font_combo.currentFont().family(), height=height_spin.value()
            )
            self.document.current_text_style = name
            self.canvas.refresh_entities()

    def _show_table_style_dialog(self) -> None:
        """TABLESTYLE (TS): valores usados pelo próximo comando TABLE — um
        único estilo global (não nomeado/múltiplo como no AutoCAD de
        verdade), mesma simplificação de DIMSTYLE. Não altera tabelas já
        criadas."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Table Style")
        layout = QFormLayout(dialog)

        borders_check = QCheckBox("Show grid borders")
        borders_check.setChecked(self.document.table_style.show_borders)
        layout.addRow(borders_check)

        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.01, 10000.0)
        height_spin.setDecimals(2)
        height_spin.setValue(self.document.table_style.text_height)
        layout.addRow("Cell text height:", height_spin)

        note = QLabel("Usado pelo próximo TABLE criado — não altera tabelas já no desenho.")
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.document.table_style = TableStyle(
                show_borders=borders_check.isChecked(), text_height=height_spin.value()
            )

    def _show_mleader_style_dialog(self) -> None:
        """MLEADERSTYLE (MLS): valor de altura de texto usado pelo próximo
        LEADER — mesma simplificação de TABLESTYLE (LEADER nesta versão é
        uma LWPolyline + Text, não uma entidade MULTILEADER de verdade)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Multileader Style")
        layout = QFormLayout(dialog)

        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.01, 10000.0)
        height_spin.setDecimals(2)
        height_spin.setValue(self.document.mleader_style.text_height)
        layout.addRow("Text height:", height_spin)

        note = QLabel("Usado pelo próximo LEADER criado — não altera leaders já no desenho.")
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.document.mleader_style = MLeaderStyle(text_height=height_spin.value())

    def _show_find_dialog(self) -> None:
        """FIND: busca um trecho em todo `Text` (MTEXT/LEADER/FIELD), no
        texto de medida de toda `Dimension` e em toda célula de `Table` do
        desenho, e seleciona os que combinam — sem o Find/Replace com
        navegação Next/Previous do FIND de verdade do AutoCAD, mas cobre o
        caso de uso principal (achar rápido onde um texto está). Antes só
        `Text` era buscado — justo onde ficam as tags de circuito da New SI
        (dentro de células de TABLE) e o valor de uma cota não apareciam
        (bug real de auditoria, 2026-08-22)."""
        query, ok = QInputDialog.getText(self, "Find Text", "Find what:")
        query = query.strip()
        if not ok or not query:
            return
        needle = query.lower()
        matches = []
        for e in self.document.all_entities():
            if isinstance(e, Text) and needle in e.content.lower():
                matches.append(e)
            elif isinstance(e, Dimension) and needle in e.measurement_text().lower():
                matches.append(e)
            elif isinstance(e, Table) and any(
                needle in cell.lower() for row in e.cells for cell in row
            ):
                matches.append(e)
        if not matches:
            QMessageBox.information(self, "Find Text", f'Nenhum texto contendo "{query}" encontrado.')
            return
        self.selection.set({e.id for e in matches})
        self.canvas.refresh_selection_highlight()
        self._refresh_properties_panel()
        QMessageBox.information(
            self, "Find Text", f'{len(matches)} objeto(s) contendo "{query}" encontrado(s) e selecionado(s).'
        )

    def _show_datalink_dialog(self) -> None:
        """DATALINK: importa um arquivo CSV como uma `Table` — versão
        simplificada e HONESTA do Data Link de verdade do AutoCAD (que
        mantém um vínculo vivo com a planilha externa, atualizável); aqui é
        uma importação única, sem vínculo — editar o CSV depois não
        atualiza a tabela. Insere sempre na origem (0,0); mova com MOVE
        depois se precisar de outro lugar (evita ter que enfiar um pick de
        ponto de canvas dentro de um fluxo baseado em QDialog)."""
        path, _ = QFileDialog.getOpenFileName(self, "Data Link — Select CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
        except OSError as exc:
            QMessageBox.warning(self, "Data Link", f"Não foi possível ler o arquivo:\n{exc}")
            return
        rows = [row for row in rows if row]
        if not rows:
            QMessageBox.warning(self, "Data Link", "Arquivo CSV vazio.")
            return

        max_cols = max(len(row) for row in rows)
        cells = [row + [""] * (max_cols - len(row)) for row in rows]

        self.undo_stack.push()
        table = Table(
            insertion_point=Point(0, 0),
            rows=len(cells),
            cols=max_cols,
            cells=cells,
            text_height=self.document.table_style.text_height * self.document.annotation_scale,
            show_borders=self.document.table_style.show_borders,
            layer=self.document.current_layer,
        )
        self.document.add_entity(table)
        self.canvas.refresh_entities()
        self.layer_dock.refresh()
        QMessageBox.information(
            self, "Data Link",
            f"Tabela {len(cells)}×{max_cols} importada de \"{Path(path).name}\" na origem (0,0) "
            "— mova com MOVE se precisar de outro lugar.\n\n"
            "Importação única: editar o CSV depois não atualiza esta tabela.",
        )

    def _show_vports_dialog(self) -> None:
        """VIEWPORTS/VM (Viewport Configuration): divide a aba atual em
        1/2/4 viewports lado a lado, cada uma com zoom/pan independentes —
        a "Viewport Configuration" clássica de espaço de modelo do AutoCAD
        (tiled viewports), não os viewports flutuantes de paper space (que
        o NewSIcad não tem, ver README). Só a PRIMEIRA viewport recebe
        clique/comando; as demais são só de referência visual, atualizadas
        automaticamente (ver CanvasView secundário em
        `_apply_viewport_layout` — refresh por timer, não em tempo real
        estrito, ver README)."""
        session = self._active_session()
        dialog = QDialog(self)
        dialog.setWindowTitle("Viewport Configuration")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Configuration:"))

        options = ["Single", "Two: Vertical", "Two: Horizontal", "Four: Equal"]
        combo = QComboBox()
        combo.addItems(options)
        if session.viewport_layout in options:
            combo.setCurrentText(session.viewport_layout)
        layout.addWidget(combo)

        note = QLabel(
            "Cada viewport mostra o mesmo desenho, com zoom/pan próprios.\n"
            "Só a primeira (esquerda/cima) recebe cliques de comando — as\n"
            "demais são só pra referência visual, atualizadas automaticamente."
        )
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_viewport_layout(session, combo.currentText())

    def _apply_viewport_layout(self, session: DocumentSession, layout_name: str) -> None:
        from PySide6.QtCore import QTimer

        for pane in session.viewport_panes:
            if hasattr(pane, "_vports_refresh_timer"):
                pane._vports_refresh_timer.stop()
            pane.setParent(None)
            pane.deleteLater()
        session.viewport_panes = []
        session.viewport_layout = layout_name

        old_widget = session.tab_widget
        idx = self.doc_tabs.indexOf(old_widget)
        label = session.tab_label()

        if layout_name == "Single":
            session.canvas.setParent(None)
            new_widget = session.canvas
        else:
            pane_count = {"Two: Vertical": 2, "Two: Horizontal": 2, "Four: Equal": 4}[layout_name]
            if layout_name == "Two: Horizontal":
                container = QSplitter(Qt.Orientation.Vertical)
            else:
                container = QSplitter(Qt.Orientation.Horizontal)
            container.addWidget(session.canvas)

            for _ in range(pane_count - 1):
                pane = CanvasView(session.document, session.interpreter)
                pane.grid_visible = session.canvas.grid_visible
                pane.snap_enabled = session.canvas.snap_enabled
                pane.ortho_enabled = session.canvas.ortho_enabled
                pane.osnap_enabled = session.canvas.osnap_enabled
                pane.polar_enabled = session.canvas.polar_enabled
                pane.dynamic_input_enabled = session.canvas.dynamic_input_enabled
                # `on_point`/`on_enter`/etc. ficam de propósito sem ligar —
                # só a viewport primária dirige um comando ativo. Mas sem
                # `on_selection_changed`, selecionar um objeto clicando numa
                # pane secundária (o clique MUDA `ctx.selection` de verdade,
                # já que é compartilhada) não acendia o realce em NENHUMA
                # viewport nem atualizava o painel Properties — parecia que
                # nada tinha acontecido (bug real de auditoria, 2026-08-22).
                pane.on_selection_changed = lambda s=session: self._on_viewport_pane_selection_changed(s)
                pane.refresh_entities()
                timer = QTimer(pane)
                timer.setInterval(400)
                timer.timeout.connect(pane.refresh_entities)
                timer.start()
                pane._vports_refresh_timer = timer
                container.addWidget(pane)
                session.viewport_panes.append(pane)

            if layout_name == "Four: Equal":
                # reorganiza as 4 panes numa grade 2x2 em vez da fila única
                # que o loop acima montou em `container` — mais simples
                # montar tudo numa fila primeiro e depois reagrupar do que
                # calcular a grade direto dentro do loop.
                panes = [session.canvas] + session.viewport_panes
                for pane in panes:
                    pane.setParent(None)
                sub_top = QSplitter(Qt.Orientation.Horizontal)
                sub_top.addWidget(panes[0])
                sub_top.addWidget(panes[1])
                sub_bottom = QSplitter(Qt.Orientation.Horizontal)
                sub_bottom.addWidget(panes[2])
                sub_bottom.addWidget(panes[3])
                container = QSplitter(Qt.Orientation.Vertical)
                container.addWidget(sub_top)
                container.addWidget(sub_bottom)

            new_widget = container

        self.doc_tabs.removeTab(idx)
        self.doc_tabs.insertTab(idx, new_widget, label)
        self.doc_tabs.setCurrentIndex(idx)
        session.tab_widget = new_widget
        if old_widget is not session.canvas and old_widget is not new_widget:
            old_widget.deleteLater()

    # ------------------------------------------------------------------ #
    # blocos: Block Editor (BEDIT/REFEDIT), referências externas (XREF/ER),
    # imagem raster (IMAGEATTACH), exportação PDF (PLOT/PUBLISH)
    # ------------------------------------------------------------------ #
    def _start_bedit(self) -> None:
        """BEDIT abre o editor para um bloco escolhido por nome numa lista.
        REFEDIT também cai aqui (ver newsicad/ui/block_editor_dialog.py para
        a limitação: não há seleção de referência por clique no canvas)."""
        if not self.document.block_definitions:
            QMessageBox.information(
                self, "Block Editor",
                "Nenhum bloco definido neste desenho ainda. Use BLOCK para criar um.",
            )
            return
        names = sorted(self.document.block_definitions.keys())
        name, ok = QInputDialog.getItem(self, "Edit Block Definition", "Block:", names, 0, False)
        if not ok or not name:
            return
        # Sem isso, "Save" no Block Editor (que redefine o bloco e atualiza
        # toda instância no desenho principal) nunca passava pela pilha de
        # undo — Ctrl+Z não tinha como desfazer a redefinição (bug real de
        # auditoria, 2026-08-22). Empilha antes de abrir o diálogo, mesmo
        # padrão de _start_command (push antes da ação, não depois).
        self.undo_stack.push()
        BlockEditorDialog(self, name).exec()

    def _start_xref(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select external DXF reference", "", "DXF (*.dxf)"
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            loaded, skipped = load_dxf(path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao referenciar arquivo externo", str(exc))
            return

        # ":" (e outros caracteres fora de [A-Za-z0-9_-]) são inválidos em
        # nome de bloco/tabela do DXF — usar ":" como separador aqui travava
        # o Save de QUALQUER desenho com uma xref anexada, sempre, com uma
        # exceção do ezdxf não capturada em lugar nenhum (bug real de
        # auditoria, 2026-08-22). `path.stem` também pode trazer espaços/
        # acentos de um nome de arquivo real, daí a sanitização completa.
        safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)
        block_name = f"XREF_{safe_stem}"
        self.document.define_block(block_name, loaded.all_entities())
        if skipped > 0:
            self.interpreter.log.append(_skipped_warning(skipped, "da xref"))

        self.undo_stack.push()
        self.interpreter.log.append(f"Command: XREF ({path.name})")
        generator = place_reference_command(self.context, block_name, is_xref=True, xref_path=path)
        self.interpreter.start_generator(generator)

    def _start_imageattach(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select image", "", "Imagens (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path_str:
            return
        path = Path(path_str)

        self.undo_stack.push()
        self.interpreter.log.append(f"Command: IMAGEATTACH ({path.name})")
        generator = place_image_command(self.context, path)
        self.interpreter.start_generator(generator)

    def _start_import_pdf(self) -> None:
        """IMPORTPDF: extrai a geometria vetorial + texto de uma página do
        PDF como entidades reais (Line/LWPolyline/Text), pra decalcar/editar
        por cima — diferente do IMAGEATTACH, que só cola uma imagem raster.
        Ver newsicad/io/pdf_import.py para a nota de licença (PyMuPDF/AGPL,
        aceitável aqui: uso interno da New SI)."""
        path_str, _ = QFileDialog.getOpenFileName(self, "Import PDF", "", "PDF (*.pdf)")
        if not path_str:
            return
        path = Path(path_str)

        try:
            page_count = pdf_page_count(str(path))
        except PdfImportError as exc:
            QMessageBox.critical(self, "Erro ao abrir PDF", str(exc))
            return

        page_index = 0
        if page_count > 1:
            page_number, ok = QInputDialog.getInt(
                self, "Import PDF", f"Página (1-{page_count}):", 1, 1, page_count
            )
            if not ok:
                return
            page_index = page_number - 1

        try:
            entities = import_pdf_page(str(path), page_index, layer=self.document.current_layer)
        except PdfImportError as exc:
            QMessageBox.critical(self, "Erro ao importar PDF", str(exc))
            return

        if not entities:
            QMessageBox.information(
                self, "Import PDF", "Nenhuma geometria ou texto encontrado nessa página."
            )
            return

        self.undo_stack.push()
        for entity in entities:
            self.document.add_entity(entity)
        self.selection.set({entity.id for entity in entities})
        self.canvas.refresh_entities()
        self.canvas.refresh_selection_highlight()
        self._refresh_properties_panel()
        self.layer_dock.refresh()
        self.interpreter.log.append(
            f"Command: IMPORTPDF ({path.name}, página {page_index + 1}) "
            f"— {len(entities)} entidade(s) importada(s)."
        )
        self._refresh_prompt()

    def _export_pdf(self) -> None:
        """PLOT/PUBLISH: exporta o desenho inteiro pra uma única página PDF
        (ver newsicad/ui/canvas.py:CanvasView.export_pdf — sem distinção real
        entre PLOT e PUBLISH, já que não há layouts/paper space no NewSIcad)."""
        settings = self._prompt_pdf_export_settings()
        if settings is None:
            return
        page_size, orientation = settings

        path_str, _ = QFileDialog.getSaveFileName(self, "Export PDF", "", "PDF (*.pdf)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        if not self.canvas.export_pdf(path, page_size=page_size, orientation=orientation):
            QMessageBox.information(self, "Export PDF", "Nada para exportar: o desenho está vazio.")

    def _prompt_pdf_export_settings(self) -> tuple[str, str] | None:
        """Pergunta tamanho de folha (A4-A0) e orientação antes de exportar.
        Retorna None se o usuário cancelar."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Export PDF")
        layout = QFormLayout(dialog)

        size_combo = QComboBox()
        size_combo.addItems(list(PDF_PAGE_SIZES.keys()))
        size_combo.setCurrentText("A3")
        layout.addRow("Tamanho da folha:", size_combo)

        orientation_combo = QComboBox()
        orientation_combo.addItem("Automático (recomendado)", "auto")
        orientation_combo.addItem("Retrato", "portrait")
        orientation_combo.addItem("Paisagem", "landscape")
        layout.addRow("Orientação:", orientation_combo)

        note = QLabel(
            "O desenho inteiro é ajustado pra caber na folha (sem escala\n"
            "real definida, ex.: 1:50) — ver limitações no README."
        )
        note.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return size_combo.currentText(), orientation_combo.currentData()

    def _export_dwg(self) -> None:
        """Export DWG...: converte o desenho atual pra .dwg via CloudConvert
        (dwg_export.py). Separado de Save/Save As de propósito — o formato
        nativo de gravação do NewSIcad continua sendo .dxf (ver README,
        seção "Arquivos .dwg"); isto é uma exportação sob demanda, precisa de
        internet, e envia o desenho pro CloudConvert."""
        path_str, _ = QFileDialog.getSaveFileName(self, "Export DWG", "", "DWG (*.dwg)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".dwg":
            path = path.with_suffix(".dwg")

        progress = QProgressDialog("Exportando pra .dwg (precisa de internet)...", None, 0, 0, self)
        progress.setWindowTitle("Export DWG")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        try:
            document_to_dwg(self.document, path)
        except DwgExportError as exc:
            QMessageBox.critical(self, "Erro ao exportar .dwg", str(exc))
            return
        finally:
            progress.close()

    def _repeat_last_command(self) -> None:
        if self.interpreter.active or self.interpreter.last_command_name is None:
            return
        if self.interpreter.last_command_name not in READ_ONLY_COMMANDS:
            self.undo_stack.push()
        self.interpreter.repeat_last()
        self._after_interpreter_step()

    def _do_undo(self) -> None:
        # Sem essa guarda, um Ctrl+Z digitado por hábito no meio de um
        # comando de vários pontos (LINE, ARRAY, TABLE...) consumia o
        # snapshot que pertencia àquele comando ainda em andamento — o
        # próximo Ctrl+Z "de verdade" então desfazia DUAS ações em vez de
        # uma, corrompendo a ordem do histórico (bug real de auditoria,
        # 2026-08-22). Cancela o comando ativo primeiro, sem desfazer nada
        # do desenho ainda — igual ao Esc — deixando o próximo Ctrl+Z agir
        # sobre o histórico de verdade.
        if self.interpreter.active:
            self.interpreter.cancel()
            self._after_interpreter_step()
            return
        if self.undo_stack.undo():
            self.selection.clear()
            self.canvas.refresh_entities()
            self._refresh_tab_labels()

    def _do_redo(self) -> None:
        if self.interpreter.active:
            self.interpreter.cancel()
            self._after_interpreter_step()
            return
        if self.undo_stack.redo():
            self.selection.clear()
            self.canvas.refresh_entities()
            self._refresh_tab_labels()

    # ------------------------------------------------------------------ #
    # proteção contra perda de trabalho não salvo: fechar uma aba e fechar a
    # janela inteira compartilham o mesmo risco (perder uma sessão suja), e
    # os dois passam por _confirm_discard_changes. File > New e File > Open
    # NÃO precisam mais disso — cada um abre uma aba nova em vez de substituir
    # a atual, então nada é descartado (ver _new_document/_open_file). A
    # detecção de "sujo" (DocumentSession.is_dirty) compara um snapshot
    # profundo (entidades, camadas, unidades, definições de bloco) contra o
    # estado no último save/load — cobre qualquer forma de alteração (MOVE/
    # ROTATE mutam entidades diretamente, sem passar por Document.add_entity).
    # ------------------------------------------------------------------ #
    def _snapshot_state(self) -> tuple:
        return self._active_session().snapshot_state()

    def _is_dirty(self) -> bool:
        return self._active_session().is_dirty()

    def _confirm_discard_changes(self) -> bool:
        """Retorna True se pode prosseguir com a ação que descartaria a aba
        ativa (fechar a aba, ou a janela): não há nada não salvo, o usuário
        escolheu descartar, ou o save foi concluído com sucesso. Retorna
        False se a ação deve ser cancelada (usuário escolheu Cancel, ou
        desistiu do diálogo Save As)."""
        if not self._is_dirty():
            return True

        name = self._active_session().display_name()
        box = QMessageBox(self)
        box.setWindowTitle("NewSIcad")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f'Salvar alterações em "{name}"?')
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()

        if choice == QMessageBox.StandardButton.Discard:
            return True
        if choice == QMessageBox.StandardButton.Save:
            if self.current_path is None:
                return self._save_file_as()
            return self._save_file()
        return False  # Cancel

    def closeEvent(self, event: QCloseEvent) -> None:
        for index in range(len(self.sessions)):
            if self.sessions[index].is_dirty():
                self.doc_tabs.setCurrentIndex(index)
                if not self._confirm_discard_changes():
                    event.ignore()
                    return
        event.accept()

    def _new_document(self) -> None:
        """File > New (Ctrl+N): abre uma aba nova em branco — a aba atual (e
        qualquer trabalho não salvo nela) fica intocada, então não há nada
        pra confirmar/descartar aqui (ver nota acima)."""
        self._add_session_tab(self._make_untitled_session())

    def _update_window_title(self) -> None:
        if self.current_path is None:
            self.setWindowTitle(APP_TITLE)
        else:
            self.setWindowTitle(f"NewSIcad {APP_VERSION} — {self.current_path.name} — Developed by HRichter")

    def _populate_session_from_loaded(self, session: DocumentSession, loaded: Document, path: Path, skipped: int) -> None:
        """Preenche uma DocumentSession recém-criada com o conteúdo de um
        Document já lido (load_dxf/dwg_to_document) — usado só por
        _open_file, que sempre abre numa aba nova (ver nota acima)."""
        document = session.document
        for layer in loaded.layers.values():
            document.add_layer(layer.name, layer.color)
        for name, entities in loaded.block_definitions.items():
            document.define_block(name, entities)
        for entity in loaded.all_entities():
            document.add_entity(entity)
        session.current_path = path
        session.canvas.refresh_entities()
        session.canvas.zoom_extents()

        if skipped > 0:
            session.interpreter.log.append(_skipped_warning(skipped, "do arquivo"))
        for note in getattr(skipped, "notes", []):
            session.interpreter.log.append(note)

        if not document.all_entities():
            # Sem isso, um arquivo que "abriu" mas ficou vazio (ex.: .dwg
            # complexo onde só a recuperação tolerante a erros funcionou, e
            # mesmo essa não conseguiu colocar nenhuma entidade no desenho —
            # às vezes sobram só definições de bloco órfãs, sem nenhuma
            # referência que as posicione) só mostraria uma tela em branco,
            # sem indicar que algo deu errado — o usuário pensaria que o
            # desenho original é mesmo vazio.
            session.interpreter.log.append(
                "Aviso: nenhuma entidade foi carregada deste arquivo — o desenho está vazio. "
                "Se o arquivo original tinha conteúdo, a conversão/leitura pode ter falhado "
                "em reconstruir a geometria (comum em .dwg complexos ou danificados)."
            )

        session.mark_saved()

    def _open_file(self) -> None:
        """File > Open (Ctrl+O): sempre abre numa aba nova — a aba atual não
        é tocada, então não há confirmação de descarte aqui (ver nota acima
        sobre _confirm_discard_changes)."""
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir desenho",
            "",
            "Desenhos (*.dxf *.dwg);;DXF (*.dxf);;DWG (*.dwg)",
        )
        if not path_str:
            return

        path = Path(path_str)
        try:
            loaded, skipped = self._load_document_file(path)
        except (DxfIoError, DwgBridgeError) as exc:
            QMessageBox.critical(self, "Erro ao abrir arquivo", str(exc))
            return

        session = self._make_untitled_session()
        self._populate_session_from_loaded(session, loaded, path, skipped)
        self._add_session_tab(session)
        self.command_line.focus_input()

    def _load_document_file(self, path: Path) -> tuple[Document, int]:
        """Lê um .dxf/.dwg com cursor de espera e cache do resultado (ver
        newsicad/io/open_cache.py): a segunda abertura do mesmo arquivo pula
        dwg2dxf + ezdxf e volta em poucos segundos mesmo numa planta grande."""
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            cached = load_cached(path, APP_VERSION)
            if cached is not None:
                return cached
            if path.suffix.lower() == ".dwg":
                loaded, skipped = dwg_to_document(path)
            else:
                loaded, skipped = load_dxf(path)
            store_cached(path, APP_VERSION, (loaded, skipped))
            return loaded, skipped
        finally:
            QApplication.restoreOverrideCursor()

    def _save_file(self) -> bool:
        if self.current_path is None:
            return self._save_file_as()

        if self.current_path.suffix.lower() == ".dwg":
            QMessageBox.warning(
                self,
                "Gravação de .dwg indisponível",
                "NewSIcad ainda não grava arquivos .dwg (o gravador do LibreDWG não é "
                "confiável). Escolha um local para salvar como .dxf.",
            )
            return self._save_file_as()

        self._backup_before_overwrite(self.current_path)
        try:
            save_dxf(self.document, self.current_path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao salvar arquivo", str(exc))
            return False
        except Exception as exc:
            # ezdxf pode levantar sua própria exceção (ex.: DXFValueError)
            # pra geometria degenerada que passou sem validação na hora de
            # desenhar (ex.: uma ELLIPSE de raio 0, um bloco com nome
            # inválido) — sem esse catch, Save trava o app inteiro em vez de
            # avisar (bug real encontrado em auditoria, 2026-08-22).
            QMessageBox.critical(
                self, "Erro ao salvar arquivo",
                f"Não foi possível gravar o arquivo — provavelmente uma entidade com "
                f"geometria inválida no desenho.\n\nDetalhe técnico: {exc}",
            )
            return False
        self._active_session().mark_saved()
        self._refresh_tab_labels()
        return True

    def _save_file_as(self) -> bool:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Salvar desenho como", "", "DXF (*.dxf)"
        )
        if not path_str:
            return False

        path = Path(path_str)
        if path.suffix.lower() != ".dxf":
            path = path.with_suffix(".dxf")

        self._backup_before_overwrite(path)
        try:
            save_dxf(self.document, path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao salvar arquivo", str(exc))
            return False
        except Exception as exc:
            QMessageBox.critical(
                self, "Erro ao salvar arquivo",
                f"Não foi possível gravar o arquivo — provavelmente uma entidade com "
                f"geometria inválida no desenho.\n\nDetalhe técnico: {exc}",
            )
            return False

        self.current_path = path
        self._update_window_title()
        self._active_session().mark_saved()
        self._refresh_tab_labels()
        return True

    def _backup_before_overwrite(self, path: Path) -> None:
        """Igual ao AutoCAD: se já existe um arquivo nesse caminho, guarda a
        versão anterior como .bak antes de sobrescrever."""
        if not path.exists():
            return
        try:
            shutil.copy2(path, path.with_suffix(".bak"))
        except OSError:
            pass  # falha ao criar backup não deve impedir o salvamento

    def _show_command_history(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Histórico de Comandos")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(DARK_TEXT_STYLE)
        text.setPlainText("\n".join(self.interpreter.log))
        layout.addWidget(text)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # ligação canvas <-> interpretador de comandos <-> linha de comando
    # ------------------------------------------------------------------ #
    def _handle_canvas_point(self, point: Point) -> None:
        if self.interpreter.active:
            self.interpreter.submit_point(point)
        self._after_interpreter_step()

    def _handle_enter(self) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text("")
            self._after_interpreter_step()
        else:
            self._repeat_last_command()

    def _handle_cancel(self) -> None:
        if self.interpreter.active:
            self.interpreter.cancel()
        elif self.selection.ids:
            # Esc sem comando ativo: igual ao AutoCAD, limpa a seleção
            # corrente em vez de não fazer nada (bug real de auditoria,
            # 2026-08-22 — só cancelava comandos, nunca a seleção parada).
            self.selection.clear()
            self._refresh_properties_panel()
            self.canvas.refresh_selection_highlight()
        self._after_interpreter_step()

    def _handle_text_submitted(self, text: str) -> None:
        if self.interpreter.active:
            self.interpreter.submit_text(text, cursor_point=self._last_cursor_point)
            self._after_interpreter_step()
        elif text.strip() == "":
            self._repeat_last_command()
        else:
            self._start_command(text)

    def _handle_mouse_moved(self, point: Point) -> None:
        self._last_cursor_point = point
        self.coord_label.setText(f"{point.x:.2f}, {point.y:.2f}")

    def _after_interpreter_step(self) -> None:
        self.canvas.refresh_entities()
        if not self.interpreter.active:
            self.canvas.clear_transient_overlays()
        self.canvas.viewport().update()
        self._refresh_prompt()
        self._refresh_properties_panel()
        # Cobre PURGE/BLOCK/qualquer comando que possa mudar o conjunto de
        # camadas do documento sem passar pelo LAYER/RENAME (que já dão
        # refresh explícito) — sem isso o painel de camadas ficava com dados
        # obsoletos (ex.: mostrando uma camada que o PURGE acabou de remover)
        # até o usuário mexer nele manualmente.
        self.layer_dock.refresh()
        self._refresh_tab_labels()
        self.command_line.focus_input()

    def _refresh_prompt(self) -> None:
        self.command_line.set_log(self.interpreter.log)
        if self.interpreter.active and self.interpreter.current_prompt is not None:
            self.command_line.set_prompt(self.interpreter.current_prompt.message)
        else:
            self.command_line.set_prompt("Command:")

    def _refresh_properties_panel(self) -> None:
        entities = self.selection.entities(self.document)
        self.properties_dock.refresh(entities)
