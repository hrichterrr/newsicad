"""Testes do OSNAP (Endpoint/Midpoint/Center/Intersection) e do POLAR
(múltiplos de 15°) — ver `newsicad/ui/canvas.py` (`_find_osnap_point`,
`_apply_polar`, `_apply_constraints`). Igual a `test_canvas_selection.py`,
usa um QApplication real (offscreen) pra exercitar o CanvasView de verdade,
mas sem precisar simular eventos de mouse pra essa parte da lógica — os
métodos testados são puros o bastante pra chamar direto."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------- #
# OSNAP
# ---------------------------------------------------------------------- #
def test_osnap_finds_endpoint_within_tolerance():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(10.05, 0.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "endpoint"
    assert pt.as_tuple() == (10, 0)


def test_osnap_finds_midpoint_within_tolerance():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(5.1, 0.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "midpoint"
    assert pt.as_tuple() == (5, 0)


def test_osnap_finds_circle_center():
    _app()
    window = MainWindow()
    window.document.add_entity(Circle(center=Point(3, 4), radius=5))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(3.1, 4.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "center"
    assert pt.as_tuple() == (3, 4)


def test_osnap_finds_intersection_between_two_lines():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    # cortador assimétrico: seu próprio midpoint (3,-1) fica fora da
    # tolerância, só a interseção real em (3,0) deve ser candidata
    window.document.add_entity(Line(start=Point(3, -5), end=Point(3, 3)))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(3.05, 0.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "intersection"
    assert pt.x == pytest.approx(3)
    assert pt.y == pytest.approx(0)


def test_osnap_finds_point_entity_node():
    _app()
    window = MainWindow()
    from newsicad.core.entities import PointEntity

    window.document.add_entity(PointEntity(location=Point(7, 2)))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(7.05, 2.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "node"
    assert pt.as_tuple() == (7, 2)


def test_osnap_finds_block_reference_insertion_point():
    _app()
    window = MainWindow()
    from newsicad.core.entities import BlockReference, Line as _Line

    window.document.block_definitions["CADEIRA"] = [_Line(start=Point(0, 0), end=Point(1, 0))]
    window.document.add_entity(BlockReference(block_name="CADEIRA", insertion_point=Point(-4, 6)))
    window.canvas.set_osnap_enabled(True)

    snap = window.canvas._find_osnap_point(Point(-3.95, 6.05))
    assert snap is not None
    pt, kind = snap
    assert kind == "insert"
    assert pt.as_tuple() == (-4, 6)


def test_osnap_returns_none_outside_tolerance():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.set_osnap_enabled(True)

    assert window.canvas._find_osnap_point(Point(5, 5)) is None


def test_osnap_overrides_click_point_during_line_command():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.set_osnap_enabled(True)

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(-5, -5))  # primeiro ponto, longe de qualquer snap
    # clique perto do endpoint (10,0) mas não exatamente nele
    resolved = window.canvas._apply_constraints(Point(10.1, -0.1))
    assert resolved.as_tuple() == (10, 0)


def test_osnap_disabled_does_not_snap():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.set_osnap_enabled(False)

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(-5, -5))
    resolved = window.canvas._apply_constraints(Point(10.1, -0.1))
    assert resolved.as_tuple() == (10.1, -0.1)


def test_osnap_does_not_override_pick_point_during_trim():
    """Bug real reportado: TRIM cortando o lado errado perto de interseções.
    Causa raiz: o clique de "Select object to trim" (connect_to_last=False,
    só identifica uma entidade/lado já existente, não define geometria nova)
    grudava no OSNAP igual um clique normal — perto de uma interseção (o caso
    mais comum de TRIM), isso apaga a informação de qual lado do corte o
    usuário quis apagar. OSNAP não deve se aplicar aqui."""
    _app()
    window = MainWindow()
    line1 = window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    line2 = window.document.add_entity(Line(start=Point(5, -5), end=Point(5, 5)))
    window.canvas.set_osnap_enabled(True)

    window._handle_text_submitted("TR")
    window.selection.add(line1.id)
    window.selection.add(line2.id)
    window._handle_text_submitted("")  # termina a seleção de cutting edges

    # ponto perto da interseção (5,0), mas não exatamente nela
    resolved = window.canvas._apply_constraints(Point(5.05, 2.0))
    assert resolved.as_tuple() == (5.05, 2.0)


# ---------------------------------------------------------------------- #
# POLAR
# ---------------------------------------------------------------------- #
def test_polar_snaps_to_15_degree_multiple_within_tolerance():
    _app()
    window = MainWindow()
    window.canvas.set_polar_enabled(True)
    window.interpreter.last_point = Point(0, 0)

    snapped = window.canvas._apply_polar(Point(10, 10.4))  # ângulo real ~46.09°
    angle = math.degrees(math.atan2(snapped.y, snapped.x)) % 360
    assert angle == pytest.approx(45.0, abs=1e-6)
    # a distância original é preservada, só o ângulo é ajustado
    assert math.hypot(snapped.x, snapped.y) == pytest.approx(math.hypot(10, 10.4))


def test_polar_does_not_snap_outside_tolerance():
    _app()
    window = MainWindow()
    window.canvas.set_polar_enabled(True)
    window.interpreter.last_point = Point(0, 0)

    original = Point(10, 5)  # ângulo ~26.57°, > 3° do múltiplo de 15° mais próximo (30°)
    result = window.canvas._apply_polar(original)
    assert result.as_tuple() == (10, 5)


def test_polar_applies_during_line_command_when_enabled_and_ortho_off():
    _app()
    window = MainWindow()
    window.canvas.set_polar_enabled(True)

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    resolved = window.canvas._apply_constraints(Point(10, 10.4))
    angle = math.degrees(math.atan2(resolved.y - 0, resolved.x - 0)) % 360
    assert angle == pytest.approx(45.0, abs=1e-6)


def test_ortho_takes_precedence_over_polar_when_both_enabled():
    _app()
    window = MainWindow()
    window.canvas.set_ortho_enabled(True)
    window.canvas.set_polar_enabled(True)

    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    resolved = window.canvas._apply_constraints(Point(10, 10.4))
    # ORTHO só permite 0°/90° (aqui dy>dx -> trava vertical em x=0) — não 45°
    assert resolved.as_tuple() == (0, 10.4)
