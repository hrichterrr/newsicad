"""Testes de newsicad/ui/canvas.py:CanvasView.export_pdf — tamanho de folha
(A4-A0) e orientação (auto/portrait/landscape). Verifica o `/MediaBox` do PDF
gerado (texto plano no arquivo, mesmo sem parser de PDF) em vez de só
checar que o arquivo não está vazio."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.canvas import PDF_PAGE_SIZES, CanvasView  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _canvas_with_line(start: Point = Point(0, 0), end: Point = Point(10, 5)) -> CanvasView:
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=start, end=end))
    window.canvas.refresh_entities()
    return window.canvas


def _media_box(path: Path) -> tuple[float, float]:
    data = path.read_bytes()
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    assert match, "MediaBox não encontrado no PDF gerado"
    return float(match.group(1)), float(match.group(2))


# Pontos (72/polegada) das folhas em retrato, pra conferir contra o MediaBox.
_PORTRAIT_POINTS = {
    "A4": (595.0, 842.0),
    "A3": (842.0, 1191.0),
    "A2": (1191.0, 1684.0),
    "A1": (1684.0, 2384.0),
    "A0": (2384.0, 3370.0),
}


@pytest.mark.parametrize("size", list(PDF_PAGE_SIZES.keys()))
def test_export_pdf_respects_page_size_in_portrait(size):
    canvas = _canvas_with_line()
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "out.pdf"
        assert canvas.export_pdf(path, page_size=size, orientation="portrait")
        width, height = _media_box(path)
        expected_w, expected_h = _PORTRAIT_POINTS[size]
        assert width == pytest.approx(expected_w, abs=1.0)
        assert height == pytest.approx(expected_h, abs=1.0)


def test_export_pdf_landscape_swaps_width_and_height():
    canvas = _canvas_with_line()
    with tempfile.TemporaryDirectory() as tmp_dir:
        portrait_path = Path(tmp_dir) / "portrait.pdf"
        landscape_path = Path(tmp_dir) / "landscape.pdf"
        canvas.export_pdf(portrait_path, page_size="A3", orientation="portrait")
        canvas.export_pdf(landscape_path, page_size="A3", orientation="landscape")

        pw, ph = _media_box(portrait_path)
        lw, lh = _media_box(landscape_path)
        assert (lw, lh) == pytest.approx((ph, pw), abs=1.0)


def test_export_pdf_auto_orientation_picks_landscape_for_wide_drawing():
    # A linha de teste vai de (0,0) a (10,5): mais larga que alta.
    canvas = _canvas_with_line()
    with tempfile.TemporaryDirectory() as tmp_dir:
        auto_path = Path(tmp_dir) / "auto.pdf"
        landscape_path = Path(tmp_dir) / "landscape.pdf"
        canvas.export_pdf(auto_path, page_size="A2", orientation="auto")
        canvas.export_pdf(landscape_path, page_size="A2", orientation="landscape")

        assert _media_box(auto_path) == pytest.approx(_media_box(landscape_path), abs=1.0)


def test_export_pdf_auto_orientation_picks_portrait_for_tall_drawing():
    canvas = _canvas_with_line(start=Point(0, 0), end=Point(5, 10))
    with tempfile.TemporaryDirectory() as tmp_dir:
        auto_path = Path(tmp_dir) / "auto.pdf"
        portrait_path = Path(tmp_dir) / "portrait.pdf"
        canvas.export_pdf(auto_path, page_size="A2", orientation="auto")
        canvas.export_pdf(portrait_path, page_size="A2", orientation="portrait")

        assert _media_box(auto_path) == pytest.approx(_media_box(portrait_path), abs=1.0)


def test_export_pdf_unknown_page_size_falls_back_to_a4():
    canvas = _canvas_with_line()
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "out.pdf"
        assert canvas.export_pdf(path, page_size="TABLOID", orientation="portrait")
        assert _media_box(path) == pytest.approx(_PORTRAIT_POINTS["A4"], abs=1.0)


def test_export_pdf_default_args_match_previous_behavior():
    """Regressão: chamadas antigas sem page_size/orientation (ex.: código já
    existente que chama `export_pdf(path)`) continuam funcionando como A4."""
    canvas = _canvas_with_line()
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "out.pdf"
        assert canvas.export_pdf(path)
        assert path.exists()
        assert path.stat().st_size > 0
