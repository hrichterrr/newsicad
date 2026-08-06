"""Janela principal: menu superior estilo AutoCAD, canvas, linha de comando
(dock inferior), painel de propriedades (Ctrl+1) e barra de status
(coordenadas + toggles GRID/SNAP/ORTHO/POLAR/OSNAP/OSNAP TRACKING/DYNAMIC INPUT)."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import Point
from newsicad.core.selection import Selection
from newsicad.core.undo import UndoStack
from newsicad.io.dwg_bridge import DwgBridgeError, dwg_to_document
from newsicad.io.dxf_io import DxfIoError, load_dxf, save_dxf
from newsicad.ui.canvas import CanvasView
from newsicad.ui.command_line import CommandLineWidget
from newsicad.ui.menu_bar import build_menu_bar
from newsicad.ui.ribbon import build_ribbon

APP_TITLE = "NewSIcad — Developed by HRichter"

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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        self._last_cursor_point: Point | None = None
        self.current_path: Path | None = None

        self.document = Document()
        self.selection = Selection()
        self.context = CommandContext(document=self.document, selection=self.selection)
        self.interpreter = CommandInterpreter(self.context, COMMAND_REGISTRY, ALIASES)
        self.undo_stack = UndoStack(self.document)

        self.canvas = CanvasView(self.document, self.interpreter)
        self.canvas.on_point = self._handle_canvas_point
        self.canvas.on_enter = self._handle_enter
        self.canvas.on_cancel = self._handle_cancel
        self.canvas.on_selection_changed = self._refresh_properties_panel
        self.canvas.mouse_moved.connect(self._handle_mouse_moved)
        self.context.view = self.canvas

        self._build_command_dock()
        self._build_status_bar()
        self._build_properties_dock()
        self._build_central_widget()
        self.setMenuBar(build_menu_bar(self))

        self._refresh_prompt()
        self._refresh_properties_panel()
        self.command_line.focus_input()

    # ------------------------------------------------------------------ #
    # construção da UI
    # ------------------------------------------------------------------ #
    def _build_central_widget(self) -> None:
        """Ribbon estilo AutoCAD (acima) + canvas (abaixo). O ribbon convive
        com o menu clássico (File/Edit/View/...), não o substitui."""
        self.ribbon = build_ribbon(self)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(self.canvas, stretch=1)
        self.setCentralWidget(central)

    def _build_command_dock(self) -> None:
        self.command_line = CommandLineWidget()
        self.command_line.text_submitted.connect(self._handle_text_submitted)
        self.command_line.cancel_requested.connect(self._handle_cancel)

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

        self.grid_button = self._make_toggle("GRID", "F7", self._toggle_grid, checked=True)
        self.snap_button = self._make_toggle("SNAP", "F9", self._toggle_snap)
        self.ortho_button = self._make_toggle("ORTHO", "F8", self._toggle_ortho)
        self.polar_button = self._make_toggle(
            "POLAR", "F10", self._toggle_polar,
            tooltip="Rastreamento polar — gruda em múltiplos de 15° a partir do último ponto",
        )
        self.osnap_button = self._make_toggle(
            "OSNAP", "F3", self._toggle_osnap,
            tooltip="Snap a objetos (Endpoint/Midpoint/Center/Intersection)",
        )
        self.osnap_tracking_button = self._make_toggle(
            "OTRACK", "F11", self._toggle_osnap_tracking,
            tooltip="Rastreamento de OSNAP (em desenvolvimento)",
        )
        self.dynamic_input_button = self._make_toggle(
            "DYN", "F12", self._toggle_dynamic_input, checked=True,
            tooltip="Entrada dinâmica (distância/ângulo perto do cursor)",
        )

        for button in (
            self.grid_button, self.snap_button, self.ortho_button, self.polar_button,
            self.osnap_button, self.osnap_tracking_button, self.dynamic_input_button,
        ):
            status.addPermanentWidget(button)

        brand = QLabel("NewSIcad · Developed by HRichter")
        brand.setStyleSheet("color: #6a8fc9; font-family: Menlo; font-size: 11px; padding: 0 10px;")
        status.addPermanentWidget(brand)

    def _build_properties_dock(self) -> None:
        self.properties_view = QTextEdit()
        self.properties_view.setReadOnly(True)
        self.properties_view.setStyleSheet(DARK_TEXT_STYLE)
        self.properties_view.setMaximumWidth(240)

        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setWidget(self.properties_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

    def _make_toggle(self, label, shortcut, handler, checked=False, tooltip=None) -> QPushButton:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setStyleSheet(STATUS_TOGGLE_STYLE)
        button.setToolTip(tooltip or f"{label} ({shortcut})")
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
        self.undo_stack.push()
        self.interpreter.start(text)
        self._after_interpreter_step()

    def _select_all(self) -> None:
        self.selection.set(set(self.document.entities.keys()))
        self.canvas.refresh_selection_highlight()
        self.canvas.viewport().update()
        self._refresh_properties_panel()

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

    def _repeat_last_command(self) -> None:
        if self.interpreter.active or self.interpreter.last_command_name is None:
            return
        self.undo_stack.push()
        self.interpreter.repeat_last()
        self._after_interpreter_step()

    def _do_undo(self) -> None:
        if self.undo_stack.undo():
            self.selection.clear()
            self.canvas.refresh_entities()

    def _do_redo(self) -> None:
        if self.undo_stack.redo():
            self.selection.clear()
            self.canvas.refresh_entities()

    def _new_document(self) -> None:
        if self.interpreter.active:
            self.interpreter.cancel()
        self.document.clear()
        self.selection.clear()
        self.interpreter.log.clear()
        self.canvas.refresh_entities()
        self._refresh_prompt()
        self._refresh_properties_panel()

    def _update_window_title(self) -> None:
        if self.current_path is None:
            self.setWindowTitle(APP_TITLE)
        else:
            self.setWindowTitle(f"NewSIcad — {self.current_path.name} — Developed by HRichter")

    def _load_document(self, loaded: Document, path: Path, skipped: int) -> None:
        """Substitui o documento atual pelo `loaded` (vindo de load_dxf/dwg_to_document)."""
        if self.interpreter.active:
            self.interpreter.cancel()
        self.document.clear()
        for layer in loaded.layers.values():
            self.document.add_layer(layer.name, layer.color)
        for entity in loaded.all_entities():
            self.document.add_entity(entity)
        self.selection.clear()
        self.undo_stack = UndoStack(self.document)
        self.current_path = path
        self._update_window_title()
        self.canvas.refresh_entities()
        self.canvas.zoom_extents()
        self._refresh_prompt()
        self._refresh_properties_panel()
        self.command_line.focus_input()

        if skipped > 0:
            self.interpreter.log.append(
                f"Aviso: {skipped} entidade(s) do arquivo não são suportadas e foram ignoradas."
            )
            self._refresh_prompt()

    def _open_file(self) -> None:
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
            if path.suffix.lower() == ".dwg":
                loaded, skipped = dwg_to_document(path)
            else:
                loaded, skipped = load_dxf(path)
        except (DxfIoError, DwgBridgeError) as exc:
            QMessageBox.critical(self, "Erro ao abrir arquivo", str(exc))
            return

        self._load_document(loaded, path, skipped)

    def _save_file(self) -> None:
        if self.current_path is None:
            self._save_file_as()
            return

        if self.current_path.suffix.lower() == ".dwg":
            QMessageBox.warning(
                self,
                "Gravação de .dwg indisponível",
                "NewSIcad ainda não grava arquivos .dwg (o gravador do LibreDWG não é "
                "confiável). Escolha um local para salvar como .dxf.",
            )
            self._save_file_as()
            return

        self._backup_before_overwrite(self.current_path)
        try:
            save_dxf(self.document, self.current_path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao salvar arquivo", str(exc))

    def _save_file_as(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Salvar desenho como", "", "DXF (*.dxf)"
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".dxf":
            path = path.with_suffix(".dxf")

        self._backup_before_overwrite(path)
        try:
            save_dxf(self.document, path)
        except DxfIoError as exc:
            QMessageBox.critical(self, "Erro ao salvar arquivo", str(exc))
            return

        self.current_path = path
        self._update_window_title()

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
        self.command_line.focus_input()

    def _refresh_prompt(self) -> None:
        self.command_line.set_log(self.interpreter.log)
        if self.interpreter.active and self.interpreter.current_prompt is not None:
            self.command_line.set_prompt(self.interpreter.current_prompt.message)
        else:
            self.command_line.set_prompt("Command:")

    def _refresh_properties_panel(self) -> None:
        entities = self.selection.entities(self.document)
        if not entities:
            self.properties_view.setPlainText("Nenhuma seleção")
            return
        lines = [f"{type(e).__name__}  •  camada: {e.layer}" for e in entities]
        self.properties_view.setPlainText("\n".join(lines))
