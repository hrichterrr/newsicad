"""Testes de integração do menu File > Open/Save/Save As, ligados aos
métodos novos em MainWindow (newsicad/ui/main_window.py). Confirma que:
  - as QAction de Open/Save/Save As não estão mais desabilitadas;
  - os métodos _open_file/_save_file/_save_file_as existem e são chamáveis;
  - o fluxo real (sem diálogo de verdade, via mock de QFileDialog) abre e
    salva um .dxf, atualizando document/current_path/título da janela.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Point  # noqa: E402
from newsicad.io.dxf_io import load_dxf  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_file_menu_open_save_actions_are_enabled():
    # Todas as QAction do menu File são criadas com `window` como parent
    # (ver newsicad/ui/menu_bar.py), então window.findChildren(QAction) as
    # alcança sem precisar navegar via QMenuBar.actions()[i].menu() — esse
    # caminho recria o wrapper Python do QMenu sob demanda e, em alguns
    # ambientes PySide6, o C++ subjacente já foi liberado nesse ponto
    # (RuntimeError: Internal C++ object already deleted), então evitamos.
    _app()
    window = MainWindow()

    labels = {a.text(): a for a in window.findChildren(QAction) if a.text()}

    for label in ("Open...", "Save", "Save As..."):
        assert label in labels, f"ação '{label}' não está no menu File"
        assert labels[label].isEnabled(), f"ação '{label}' ainda está desabilitada"


def test_main_window_exposes_callable_file_methods():
    _app()
    window = MainWindow()

    for name in ("_open_file", "_save_file", "_save_file_as"):
        assert hasattr(window, name)
        assert callable(getattr(window, name))


def test_open_file_loads_dxf_and_updates_state():
    _app()
    window = MainWindow()

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(1, 1))
    window._handle_text_submitted("")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "sample.dxf"
        from newsicad.io.dxf_io import save_dxf

        save_dxf(window.document, dxf_path)

        fresh_window = MainWindow()
        assert len(fresh_window.document.entities) == 0

        with patch(
            "newsicad.ui.main_window.QFileDialog.getOpenFileName",
            return_value=(str(dxf_path), "DXF (*.dxf)"),
        ):
            fresh_window._open_file()

        assert len(fresh_window.document.entities) == 1
        assert fresh_window.current_path == dxf_path
        assert dxf_path.name in fresh_window.windowTitle()


def test_open_file_cancelled_dialog_does_nothing():
    _app()
    window = MainWindow()

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        window._open_file()

    assert window.current_path is None
    assert len(window.document.entities) == 0


def test_save_file_as_writes_dxf_and_sets_current_path():
    _app()
    window = MainWindow()
    window._handle_text_submitted("CIRCLE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_text_submitted("5")

    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "saved.dxf"
        with patch(
            "newsicad.ui.main_window.QFileDialog.getSaveFileName",
            return_value=(str(target), "DXF (*.dxf)"),
        ):
            window._save_file_as()

        assert target.exists()
        assert window.current_path == target

        loaded, skipped = load_dxf(target)
        assert skipped == 0
        assert len(loaded.all_entities()) == 1


def test_save_file_without_current_path_delegates_to_save_as():
    _app()
    window = MainWindow()
    assert window.current_path is None

    with patch.object(window, "_save_file_as") as mock_save_as:
        window._save_file()
        mock_save_as.assert_called_once()


def test_save_file_with_existing_dxf_path_saves_directly():
    _app()
    window = MainWindow()
    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(3, 3))
    window._handle_text_submitted("")

    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "direct.dxf"
        window.current_path = target
        window._save_file()

        assert target.exists()
        loaded, skipped = load_dxf(target)
        assert skipped == 0
        assert len(loaded.all_entities()) == 1


def test_save_file_with_dwg_path_warns_and_falls_back_to_save_as():
    _app()
    window = MainWindow()
    window.current_path = Path("/tmp/some_open_drawing.dwg")

    with patch("newsicad.ui.main_window.QMessageBox.warning") as mock_warning, patch.object(
        window, "_save_file_as"
    ) as mock_save_as:
        window._save_file()
        mock_warning.assert_called_once()
        mock_save_as.assert_called_once()
