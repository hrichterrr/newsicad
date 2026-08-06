"""Testes de round-trip para newsicad/io/dxf_io.py: grava um Document com
uma instância de cada tipo de entidade suportado, lê de volta, e compara a
geometria. Também cobre o caminho de erro (arquivo inexistente)."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Dimension, Ellipse, Hatch, Line, LWPolyline, Point, Text
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


# ---------------------------------------------------------------------- #
# round-trip: Text, Dimension (todos os `kind`), Hatch
# ---------------------------------------------------------------------- #
def test_round_trip_text_preserves_content_height_rotation():
    original = Document()
    original.add_entity(
        Text(
            layer="0",
            insertion_point=Point(1.5, -2.0),
            content="Linha 1\nLinha 2 com espaço",
            height=3.25,
            rotation=math.radians(37),
        )
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "text_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    texts = [e for e in loaded.all_entities() if isinstance(e, Text)]
    assert len(texts) == 1
    text = texts[0]
    assert text.insertion_point.x == pytest.approx(1.5)
    assert text.insertion_point.y == pytest.approx(-2.0)
    assert text.content == "Linha 1\nLinha 2 com espaço"
    assert text.height == pytest.approx(3.25)
    assert text.rotation == pytest.approx(math.radians(37))


def _make_dimension_document() -> Document:
    document = Document()
    document.add_entity(
        Dimension(layer="0", kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 5))
    )
    document.add_entity(
        Dimension(
            layer="0", kind="aligned", point1=Point(0, 0), point2=Point(10, 10), dim_line_point=Point(2, 8)
        )
    )
    document.add_entity(
        Dimension(layer="0", kind="radius", center=Point(0, 0), radius=5.0, leader_point=Point(4, 4))
    )
    document.add_entity(
        Dimension(layer="0", kind="diameter", center=Point(20, 20), radius=3.0, leader_point=Point(22, 22))
    )
    document.add_entity(
        Dimension(
            layer="0",
            kind="angular",
            center=Point(0, 0),
            point1=Point(10, 0),
            point2=Point(0, 10),
            dim_line_point=Point(5, 5),
        )
    )
    return document


def test_round_trip_dimension_all_kinds_preserve_exact_geometry():
    original = _make_dimension_document()

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "dimension_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    orig_dims = [e for e in original.all_entities() if isinstance(e, Dimension)]
    loaded_dims = {e.kind: e for e in loaded.all_entities() if isinstance(e, Dimension)}
    assert len(loaded_dims) == len(orig_dims) == 5

    for orig in orig_dims:
        loaded_dim = loaded_dims[orig.kind]
        assert loaded_dim.point1.as_tuple() == pytest.approx(orig.point1.as_tuple())
        assert loaded_dim.point2.as_tuple() == pytest.approx(orig.point2.as_tuple())
        assert loaded_dim.dim_line_point.as_tuple() == pytest.approx(orig.dim_line_point.as_tuple())
        assert loaded_dim.center.as_tuple() == pytest.approx(orig.center.as_tuple())
        assert loaded_dim.radius == pytest.approx(orig.radius)
        assert loaded_dim.leader_point.as_tuple() == pytest.approx(orig.leader_point.as_tuple())
        assert loaded_dim.measurement() == pytest.approx(orig.measurement())


def test_round_trip_hatch_preserves_boundary_angle_spacing():
    original = Document()
    original.add_entity(
        Hatch(
            layer="0",
            boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
            angle=math.radians(30),
            spacing=2.5,
        )
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "hatch_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    hatches = [e for e in loaded.all_entities() if isinstance(e, Hatch)]
    assert len(hatches) == 1
    hatch = hatches[0]
    assert len(hatch.boundary_points) == 4
    for loaded_pt, orig_pt in zip(hatch.boundary_points, [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]):
        assert loaded_pt.x == pytest.approx(orig_pt.x)
        assert loaded_pt.y == pytest.approx(orig_pt.y)
    assert hatch.angle == pytest.approx(math.radians(30))
    assert hatch.spacing == pytest.approx(2.5)


def test_dimension_and_hatch_coexist_with_other_entity_types():
    """Um único documento com TODOS os 8 tipos suportados (5 antigos + Text,
    Dimension, Hatch) grava e recarrega sem perder nem uma entidade."""
    original = _make_document()
    original.add_entity(Text(insertion_point=Point(0, 0), content="ok", height=2.0))
    original.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(5, 0), dim_line_point=Point(0, 2))
    )
    original.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4)])
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "mixed_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert len(loaded.all_entities()) == len(original.all_entities()) == 8
