"""Testes de round-trip para newsicad/io/dxf_io.py: grava um Document com
uma instância de cada tipo de entidade suportado, lê de volta, e compara a
geometria. Também cobre o caminho de erro (arquivo inexistente)."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Ellipse, Line, LWPolyline, Point
from newsicad.io.dxf_io import DxfIoError, load_dxf, save_dxf


def _make_document() -> Document:
    document = Document()
    document.add_layer("PAREDES", color="#FF0000")

    document.add_entity(Line(layer="0", start=Point(0, 0), end=Point(10, 5)))
    document.add_entity(Circle(layer="0", center=Point(3, 4), radius=2.5))
    document.add_entity(
        Arc(
            layer="PAREDES",
            center=Point(-1, 2),
            radius=4.0,
            start_angle=math.radians(10),
            end_angle=math.radians(190),
        )
    )
    document.add_entity(
        Ellipse(
            layer="0",
            center=Point(5, 5),
            radius_major=6.0,
            radius_minor=3.0,
            rotation=math.radians(30),
        )
    )
    document.add_entity(
        LWPolyline(
            layer="PAREDES",
            points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
            closed=True,
        )
    )
    return document


def test_round_trip_preserves_geometry():
    original = _make_document()

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "round_trip.dxf"
        save_dxf(original, path)
        assert path.exists()

        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert len(loaded.all_entities()) == len(original.all_entities())

    def _by_type(document, cls):
        return [e for e in document.all_entities() if isinstance(e, cls)]

    orig_lines = _by_type(original, Line)
    loaded_lines = _by_type(loaded, Line)
    assert len(loaded_lines) == len(orig_lines) == 1
    assert loaded_lines[0].start.x == pytest.approx(orig_lines[0].start.x)
    assert loaded_lines[0].start.y == pytest.approx(orig_lines[0].start.y)
    assert loaded_lines[0].end.x == pytest.approx(orig_lines[0].end.x)
    assert loaded_lines[0].end.y == pytest.approx(orig_lines[0].end.y)

    orig_circles = _by_type(original, Circle)
    loaded_circles = _by_type(loaded, Circle)
    assert len(loaded_circles) == len(orig_circles) == 1
    assert loaded_circles[0].center.x == pytest.approx(orig_circles[0].center.x)
    assert loaded_circles[0].center.y == pytest.approx(orig_circles[0].center.y)
    assert loaded_circles[0].radius == pytest.approx(orig_circles[0].radius)

    orig_arcs = _by_type(original, Arc)
    loaded_arcs = _by_type(loaded, Arc)
    assert len(loaded_arcs) == len(orig_arcs) == 1
    assert loaded_arcs[0].center.x == pytest.approx(orig_arcs[0].center.x)
    assert loaded_arcs[0].center.y == pytest.approx(orig_arcs[0].center.y)
    assert loaded_arcs[0].radius == pytest.approx(orig_arcs[0].radius)
    assert loaded_arcs[0].start_angle == pytest.approx(orig_arcs[0].start_angle)
    assert loaded_arcs[0].end_angle == pytest.approx(orig_arcs[0].end_angle)
    assert loaded_arcs[0].layer == "PAREDES"

    orig_ellipses = _by_type(original, Ellipse)
    loaded_ellipses = _by_type(loaded, Ellipse)
    assert len(loaded_ellipses) == len(orig_ellipses) == 1
    assert loaded_ellipses[0].center.x == pytest.approx(orig_ellipses[0].center.x)
    assert loaded_ellipses[0].center.y == pytest.approx(orig_ellipses[0].center.y)
    assert loaded_ellipses[0].radius_major == pytest.approx(orig_ellipses[0].radius_major)
    assert loaded_ellipses[0].radius_minor == pytest.approx(orig_ellipses[0].radius_minor)
    assert loaded_ellipses[0].rotation == pytest.approx(orig_ellipses[0].rotation)

    orig_plines = _by_type(original, LWPolyline)
    loaded_plines = _by_type(loaded, LWPolyline)
    assert len(loaded_plines) == len(orig_plines) == 1
    assert loaded_plines[0].closed == orig_plines[0].closed
    assert len(loaded_plines[0].points) == len(orig_plines[0].points)
    for loaded_pt, orig_pt in zip(loaded_plines[0].points, orig_plines[0].points):
        assert loaded_pt.x == pytest.approx(orig_pt.x)
        assert loaded_pt.y == pytest.approx(orig_pt.y)


def test_load_dxf_missing_file_raises_dxf_io_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_path = Path(tmp_dir) / "does_not_exist.dxf"
        with pytest.raises(DxfIoError):
            load_dxf(missing_path)
