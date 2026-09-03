"""Testes da importação de PDF (newsicad/io/pdf_import.py). Gera PDFs de
teste na hora com o próprio PyMuPDF (fitz) em vez de depender de um arquivo
fixture — mantém o teste autocontido."""

from __future__ import annotations

import math

import fitz
import pytest

from newsicad.core.entities import Line, LWPolyline, Text
from newsicad.io.pdf_import import PdfImportError, import_pdf_page, pdf_page_count


def _make_pdf(path, page_sizes: list[tuple[float, float]] = [(200, 200)]) -> None:
    doc = fitz.open()
    for width, height in page_sizes:
        doc.new_page(width=width, height=height)
    doc.save(str(path))
    doc.close()


def test_pdf_page_count(tmp_path):
    path = tmp_path / "multi.pdf"
    _make_pdf(path, [(200, 200), (200, 200), (200, 200)])
    assert pdf_page_count(str(path)) == 3


def test_pdf_page_count_invalid_file_raises(tmp_path):
    path = tmp_path / "not_a_pdf.pdf"
    path.write_text("isso não é um pdf de verdade")
    with pytest.raises(PdfImportError):
        pdf_page_count(str(path))


def test_import_line_flips_y_axis_and_scales_to_mm(tmp_path):
    path = tmp_path / "line.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_line((10, 10), (100, 190))  # perto do topo (y baixo) até perto da base (y alto) em PDF
    doc.save(str(path))
    doc.close()

    entities = import_pdf_page(str(path), 0)
    lines = [e for e in entities if isinstance(e, Line)]
    assert len(lines) == 1

    scale = 25.4 / 72.0
    line = lines[0]
    # PDF (10,10) [perto do topo] -> CAD deve ficar perto do topo do desenho
    # (y grande, já que a altura da página é 200): y = (200-10)*scale
    assert line.start.x == pytest.approx(10 * scale)
    assert line.start.y == pytest.approx((200 - 10) * scale)
    assert line.end.x == pytest.approx(100 * scale)
    assert line.end.y == pytest.approx((200 - 190) * scale)


def test_import_rectangle_becomes_closed_lwpolyline(tmp_path):
    path = tmp_path / "rect.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(20, 20, 80, 80))
    doc.save(str(path))
    doc.close()

    entities = import_pdf_page(str(path), 0)
    polys = [e for e in entities if isinstance(e, LWPolyline)]
    assert len(polys) == 1
    assert polys[0].closed
    assert len(polys[0].points) == 4


def test_import_bezier_curve_tessellates_into_connected_lines(tmp_path):
    path = tmp_path / "curve.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_bezier((10, 190), (50, 150), (150, 150), (190, 190))
    doc.save(str(path))
    doc.close()

    entities = import_pdf_page(str(path), 0)
    lines = [e for e in entities if isinstance(e, Line)]
    assert len(lines) == 16  # _BEZIER_SEGMENTS

    # os segmentos formam uma cadeia contínua (fim de um = início do próximo)
    for a, b in zip(lines, lines[1:]):
        assert a.end.as_tuple() == pytest.approx(b.start.as_tuple())

    # não deve ser uma linha reta — o meio da curva deve se afastar da corda
    chord_mid_y = (lines[0].start.y + lines[-1].end.y) / 2
    mid_line = lines[len(lines) // 2]
    assert abs(mid_line.start.y - chord_mid_y) > 1.0


def test_import_text_extracts_content_position_and_height(tmp_path):
    path = tmp_path / "text.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((10, 50), "Hello NewSIcad", fontsize=12)
    doc.save(str(path))
    doc.close()

    entities = import_pdf_page(str(path), 0)
    texts = [e for e in entities if isinstance(e, Text)]
    assert len(texts) == 1
    assert texts[0].content == "Hello NewSIcad"
    assert texts[0].height == pytest.approx(12 * 25.4 / 72.0, rel=0.05)


def test_import_page_index_out_of_range_raises(tmp_path):
    path = tmp_path / "single.pdf"
    _make_pdf(path)
    with pytest.raises(PdfImportError):
        import_pdf_page(str(path), 5)


def test_import_uses_requested_layer(tmp_path):
    path = tmp_path / "line2.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.draw_line((0, 0), (10, 10))
    doc.save(str(path))
    doc.close()

    entities = import_pdf_page(str(path), 0, layer="PDF-IMPORT")
    assert all(e.layer == "PDF-IMPORT" for e in entities)
