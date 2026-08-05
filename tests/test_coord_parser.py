import math

import pytest

from newsicad.commands.coord_parser import CoordParseError, parse_coordinate
from newsicad.core.entities import Point


def test_absolute_cartesian():
    p = parse_coordinate("10,20")
    assert p.x == 10 and p.y == 20


def test_relative_cartesian():
    last = Point(5, 5)
    p = parse_coordinate("@10,20", last_point=last)
    assert p.x == 15 and p.y == 25


def test_relative_requires_last_point():
    with pytest.raises(CoordParseError):
        parse_coordinate("@10,20")


def test_absolute_polar_east():
    p = parse_coordinate("10<0")
    assert p.x == pytest.approx(10)
    assert p.y == pytest.approx(0, abs=1e-9)


def test_absolute_polar_north():
    p = parse_coordinate("10<90")
    assert p.x == pytest.approx(0, abs=1e-9)
    assert p.y == pytest.approx(10)


def test_relative_polar():
    last = Point(0, 0)
    p = parse_coordinate("@50<45", last_point=last)
    expected = 50 * math.cos(math.radians(45))
    assert p.x == pytest.approx(expected)
    assert p.y == pytest.approx(expected)


def test_direct_distance_along_cursor_direction():
    last = Point(0, 0)
    cursor = Point(10, 0)  # cursor apontando para leste
    p = parse_coordinate("25", last_point=last, cursor_point=cursor)
    assert p.x == pytest.approx(25)
    assert p.y == pytest.approx(0, abs=1e-9)


def test_direct_distance_requires_context():
    with pytest.raises(CoordParseError):
        parse_coordinate("25")


def test_invalid_cartesian():
    with pytest.raises(CoordParseError):
        parse_coordinate("10,abc")


def test_empty_input():
    with pytest.raises(CoordParseError):
        parse_coordinate("   ")
