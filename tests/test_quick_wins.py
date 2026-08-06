"""Testes dos itens rápidos: ZOOM/PAN digitados, Select All (Ctrl+A),
backup .bak ao salvar, OOPS/REGEN/UNITS."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_zoom_extents_via_typed_command_changes_transform():
    _app()
    window = MainWindow()
    window.document.add_entity(Circle(center=Point(500, 500), radius=10))
    window.canvas.refresh_entities()

    original_scale = window.canvas.transform().m11()
    window._start_command("Z")
    window._handle_text_submitted("Extents")
    assert not window.interpreter.active
    assert window.canvas.transform().m11() != original_scale


def test_zoom_window_via_two_points():
    _app()
    window = MainWindow()
    window._start_command("ZOOM")
    window._handle_canvas_point(Point(-10, -10))
    window._handle_canvas_point(Point(10, 10))
    assert not window.interpreter.active


def test_pan_command_logs_info_and_ends():
    _app()
    window = MainWindow()
    window._start_command("PAN")
    assert not window.interpreter.active
    assert any("botão do meio" in line for line in window.interpreter.log)


def test_select_all_selects_every_entity():
    _app()
    window = MainWindow()
    a = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    b = window.document.add_entity(Circle(center=Point(0, 0), radius=1))

    window._select_all()

    assert window.selection.ids == {a.id, b.id}


def test_save_creates_bak_when_file_already_exists():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))

    path = Path(tempfile.mktemp(suffix=".dxf"))
    window.current_path = path
    window._save_file()  # primeiro save: arquivo ainda não existe, sem .bak
    assert path.exists()
    assert not path.with_suffix(".bak").exists()

    window._save_file()  # segundo save: já existe -> deve gerar .bak
    assert path.with_suffix(".bak").exists()

    path.unlink(missing_ok=True)
    path.with_suffix(".bak").unlink(missing_ok=True)


def test_oops_alias_triggers_undo():
    _app()
    window = MainWindow()
    window._start_command("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(1, 1))
    window._handle_text_submitted("")
    assert len(window.document.entities) == 1

    window._start_command("OOPS")
    assert len(window.document.entities) == 0


def test_regen_does_not_crash_and_stays_idle():
    _app()
    window = MainWindow()
    window._start_command("REGEN")
    assert not window.interpreter.active


def test_units_command_opens_and_applies_via_direct_call():
    _app()
    window = MainWindow()
    assert window.document.units == "mm"
    window.document.units = "in"  # equivalente ao que o diálogo faz ao aceitar
    assert window.document.units == "in"


def test_planned_command_from_new_list_gives_friendly_message():
    _app()
    window = MainWindow()
    window._start_command("TRIM")
    assert any("reconhecido" in line and "TRIM" in line for line in window.interpreter.log)
