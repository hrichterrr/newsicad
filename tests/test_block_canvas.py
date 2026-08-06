"""Testes de integração da UI para BlockReference/ImageReference no canvas
(newsicad/ui/canvas.py): renderização como QGraphicsItemGroup, hit-test e
bounding box levando em conta a transformação de inserção (ponto base,
escala, rotação), e que PLOT/PUBLISH (export_pdf) não quebra com blocos no
desenho."""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsItemGroup  # noqa: E402

from newsicad.core.entities import BlockReference, Circle, Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_block_reference_renders_as_item_group_and_is_hit_testable():
    app = _app()
    window = MainWindow()

    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(10, 0))])
    ref = window.document.add_entity(
        BlockReference(block_name="CHAIR", insertion_point=Point(20, 20))
    )
    window.canvas.refresh_entities()
    app.processEvents()

    item = window.canvas._entity_items[ref.id]
    assert isinstance(item, QGraphicsItemGroup)

    # A linha da definição vai de (0,0) a (10,0) local -> em (20,20)+local no
    # mundo, a linha vai de (20,20) a (30,20). (25,20) está sobre ela.
    hit = window.canvas._hit_test(Point(25, 20))
    assert hit == ref.id

    # Um ponto longe de qualquer geometria não deve acertar nada.
    assert window.canvas._hit_test(Point(1000, 1000)) is None


def test_block_reference_bbox_accounts_for_scale_and_rotation():
    app = _app()
    window = MainWindow()

    window.document.define_block("DOT", [Circle(center=Point(0, 0), radius=1)])
    ref = window.document.add_entity(
        BlockReference(block_name="DOT", insertion_point=Point(0, 0), scale=3.0)
    )
    window.canvas.refresh_entities()
    app.processEvents()

    bbox = window.canvas._entity_bbox_scene(ref)
    # círculo de raio 1 escalado 3x -> bbox 6x6 (em coordenadas de cena)
    assert bbox.width() == pytest.approx(6.0)
    assert bbox.height() == pytest.approx(6.0)


def test_selection_highlight_does_not_crash_on_block_reference():
    """refresh_selection_highlight chama setPen em cada item — para um
    QGraphicsItemGroup (bloco) isso precisa propagar pros filhos em vez de
    lançar AttributeError."""
    app = _app()
    window = MainWindow()

    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(10, 0))])
    ref = window.document.add_entity(
        BlockReference(block_name="CHAIR", insertion_point=Point(0, 0))
    )
    window.canvas.refresh_entities()
    window.selection.add(ref.id)
    window.canvas.refresh_selection_highlight()  # não deve levantar exceção
    app.processEvents()


def test_export_pdf_with_block_reference_produces_nonempty_file():
    app = _app()
    window = MainWindow()

    window.document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(10, 0))])
    window.document.add_entity(
        BlockReference(block_name="CHAIR", insertion_point=Point(0, 0), rotation=math.radians(15))
    )
    window.canvas.refresh_entities()
    app.processEvents()

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "out.pdf"
        ok = window.canvas.export_pdf(path)
        assert ok
        assert path.exists()
        assert path.stat().st_size > 0
