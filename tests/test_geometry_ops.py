import math

import pytest

from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point
from newsicad.core.geometry_ops import (
    clone_entity,
    mirror_entity,
    mirror_point,
    rotate_entity,
    rotate_point,
    scale_entity,
    scale_point,
    translate_entity,
    translate_point,
)


def test_translate_point():
    p = translate_point(Point(1, 2), 3, 4)
    assert (p.x, p.y) == (4, 6)


def test_rotate_point_90deg():
    p = rotate_point(Point(1, 0), Point(0, 0), math.pi / 2)
    assert p.x == pytest.approx(0, abs=1e-9)
    assert p.y == pytest.approx(1)


def test_scale_point():
    p = scale_point(Point(2, 2), Point(0, 0), 3)
    assert (p.x, p.y) == (6, 6)


def test_mirror_point_across_x_axis():
    p = mirror_point(Point(3, 5), Point(0, 0), Point(1, 0))
    assert p.x == pytest.approx(3)
    assert p.y == pytest.approx(-5)


def test_translate_entity_line():
    line = Line(start=Point(0, 0), end=Point(1, 1))
    translate_entity(line, 5, 5)
    assert line.start.as_tuple() == (5, 5)
    assert line.end.as_tuple() == (6, 6)


def test_translate_entity_polyline():
    poly = LWPolyline(points=[Point(0, 0), Point(1, 0), Point(1, 1)])
    translate_entity(poly, 2, 0)
    assert [p.as_tuple() for p in poly.points] == [(2, 0), (3, 0), (3, 1)]


def test_rotate_entity_circle_only_moves_center():
    circle = Circle(center=Point(1, 0), radius=5)
    rotate_entity(circle, Point(0, 0), math.pi / 2)
    assert circle.center.x == pytest.approx(0, abs=1e-9)
    assert circle.center.y == pytest.approx(1)
    assert circle.radius == 5


def test_scale_entity_circle_scales_radius():
    circle = Circle(center=Point(2, 0), radius=5)
    scale_entity(circle, Point(0, 0), 2)
    assert circle.center.x == pytest.approx(4)
    assert circle.radius == pytest.approx(10)


def test_clone_entity_has_new_id():
    line = Line(start=Point(0, 0), end=Point(1, 1))
    clone = clone_entity(line)
    assert clone.id != line.id
    assert clone.start.as_tuple() == line.start.as_tuple()
    # mutar o clone não deve afetar o original
    clone.start = Point(9, 9)
    assert line.start.as_tuple() == (0, 0)


def test_mirror_entity_line_across_y_axis():
    line = Line(start=Point(1, 0), end=Point(2, 3))
    mirrored = mirror_entity(line, Point(0, 0), Point(0, 1))
    assert mirrored.start.x == pytest.approx(-1)
    assert mirrored.end.x == pytest.approx(-2)
    # original não é alterado
    assert line.start.x == 1


def test_mirror_entity_arc_preserves_radius_and_bulge_side():
    arc = Arc(center=Point(0, 0), radius=10, start_angle=0, end_angle=math.pi / 2)
    mirrored = mirror_entity(arc, Point(0, 0), Point(0, 1))
    assert mirrored.radius == pytest.approx(10)
    assert mirrored.center.x == pytest.approx(0, abs=1e-6)
    assert mirrored.center.y == pytest.approx(0, abs=1e-6)
