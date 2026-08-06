import math

import pytest

from newsicad.core.entities import Arc, Circle, Line, LWPolyline, Point
from newsicad.core.geometry_ops import (
    chamfer_lines,
    circle_circle_intersections,
    clone_entity,
    entity_intersections,
    extend_point_to_boundary,
    extend_point_to_circle,
    fillet_lines,
    line_arc_intersections,
    mirror_entity,
    mirror_point,
    nearest_entity,
    offset_arc,
    offset_circle,
    offset_line,
    offset_polyline,
    point_entity_distance,
    rotate_entity,
    rotate_point,
    scale_entity,
    scale_point,
    segment_circle_intersections,
    segment_intersection,
    segment_parameter,
    translate_entity,
    translate_point,
)
from newsicad.core.document import Document


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


# ---------------------------------------------------------------------- #
# interseções
# ---------------------------------------------------------------------- #
def test_segment_intersection_crossing_lines():
    p = segment_intersection(Point(0, 0), Point(10, 0), Point(5, -5), Point(5, 5))
    assert p.x == pytest.approx(5)
    assert p.y == pytest.approx(0)


def test_segment_intersection_none_when_parallel():
    assert segment_intersection(Point(0, 0), Point(10, 0), Point(0, 1), Point(10, 1)) is None


def test_segment_intersection_none_outside_bounds():
    # as retas suporte se cruzam, mas fora dos dois segmentos
    assert segment_intersection(Point(0, 0), Point(1, 0), Point(5, -5), Point(5, 5)) is None


def test_segment_intersection_unbounded_extends_beyond_segment():
    p = segment_intersection(Point(0, 0), Point(1, 0), Point(5, -5), Point(5, 5), bounded1=False)
    assert p.x == pytest.approx(5)


def test_segment_circle_intersections_two_points():
    pts = segment_circle_intersections(Point(-10, 0), Point(10, 0), Point(0, 0), 5)
    xs = sorted(p.x for p in pts)
    assert xs == [pytest.approx(-5), pytest.approx(5)]


def test_line_arc_intersections_respects_arc_range():
    # semicírculo superior (0 a pi); a reta y=0 só toca as pontas, que ficam
    # fora do alcance angular aberto (start incluso, end excluso na prática
    # numérica) — testamos com uma reta que cruza só a metade de cima
    arc = Arc(center=Point(0, 0), radius=5, start_angle=0, end_angle=math.pi)
    pts = line_arc_intersections(Point(-10, 3), Point(10, 3), arc)
    assert len(pts) == 2


def test_circle_circle_intersections():
    pts = circle_circle_intersections(Point(0, 0), 5, Point(6, 0), 5)
    assert len(pts) == 2
    for p in pts:
        assert p.x == pytest.approx(3)


def test_entity_intersections_line_circle():
    line = Line(start=Point(-10, 0), end=Point(10, 0))
    circle = Circle(center=Point(0, 0), radius=5)
    pts = entity_intersections(line, circle)
    assert len(pts) == 2


def test_extend_point_to_boundary_finds_point_ahead():
    p = extend_point_to_boundary(Point(0, 0), Point(5, 0), Point(10, -5), Point(10, 5))
    assert p.x == pytest.approx(10)
    assert p.y == pytest.approx(0)


def test_extend_point_to_boundary_none_when_behind():
    # anchor=(10,0) -> moving=(5,0): a extensão vai em direção a x menor;
    # um boundary em x=20 fica do lado oposto (atrás do anchor) -> None
    assert extend_point_to_boundary(Point(10, 0), Point(5, 0), Point(20, -5), Point(20, 5)) is None


def test_extend_point_to_circle():
    p = extend_point_to_circle(Point(0, 0), Point(3, 0), Point(10, 0), 2)
    assert p.x == pytest.approx(8)


def test_segment_parameter_projects_along_line():
    t = segment_parameter(Point(5, 3), Point(0, 0), Point(10, 0))
    assert t == pytest.approx(0.5)


def test_point_entity_distance_line():
    line = Line(start=Point(0, 0), end=Point(10, 0))
    assert point_entity_distance(Point(5, 3), line) == pytest.approx(3)


def test_nearest_entity_within_tolerance():
    doc = Document()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    found = nearest_entity(doc, Point(5, 0.1), tolerance=0.5)
    assert found is not None
    assert found.id == line.id
    assert nearest_entity(doc, Point(5, 5), tolerance=0.5) is None


# ---------------------------------------------------------------------- #
# OFFSET
# ---------------------------------------------------------------------- #
def test_offset_line_moves_parallel_toward_side_point():
    line = Line(start=Point(0, 0), end=Point(10, 0))
    offset = offset_line(line, 2, Point(5, 5))
    assert offset.start.y == pytest.approx(2)
    assert offset.end.y == pytest.approx(2)
    # original intocado
    assert line.start.y == 0


def test_offset_circle_outward_and_inward():
    circle = Circle(center=Point(0, 0), radius=10)
    outward = offset_circle(circle, 2, Point(20, 0))
    assert outward.radius == pytest.approx(12)
    inward = offset_circle(circle, 2, Point(0, 0))
    assert inward.radius == pytest.approx(8)


def test_offset_circle_collapse_raises():
    circle = Circle(center=Point(0, 0), radius=2)
    with pytest.raises(ValueError):
        offset_circle(circle, 5, Point(0, 0))


def test_offset_arc_preserves_angles():
    arc = Arc(center=Point(0, 0), radius=10, start_angle=0, end_angle=math.pi / 2)
    offset = offset_arc(arc, 2, Point(20, 0))
    assert offset.radius == pytest.approx(12)
    assert offset.start_angle == pytest.approx(0)
    assert offset.end_angle == pytest.approx(math.pi / 2)


def test_offset_polyline_l_shape():
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)])
    offset = offset_polyline(poly, 1, Point(5, 5))
    # deslocada 1 unidade "pra dentro" do L (lado do ponto 5,5)
    assert len(offset.points) == 3
    assert offset.points[0].y == pytest.approx(1)


# ---------------------------------------------------------------------- #
# FILLET / CHAMFER
# ---------------------------------------------------------------------- #
def test_fillet_lines_quarter_circle_corner():
    line1 = Line(start=Point(0, 0), end=Point(10, 0))
    line2 = Line(start=Point(10, 0), end=Point(10, 10))
    arc = fillet_lines(line1, line2, 2)
    assert arc.radius == pytest.approx(2)
    assert line1.end.x == pytest.approx(8)
    assert line1.end.y == pytest.approx(0)
    assert line2.start.x == pytest.approx(10)
    assert line2.start.y == pytest.approx(2)
    # extremidades distantes do canto ficam intocadas
    assert line1.start.as_tuple() == (0, 0)
    assert line2.end.as_tuple() == (10, 10)


def test_fillet_lines_parallel_raises():
    line1 = Line(start=Point(0, 0), end=Point(10, 0))
    line2 = Line(start=Point(0, 5), end=Point(10, 5))
    with pytest.raises(ValueError):
        fillet_lines(line1, line2, 1)


def test_chamfer_lines_cuts_corner_at_distances():
    line1 = Line(start=Point(0, 0), end=Point(10, 0))
    line2 = Line(start=Point(10, 0), end=Point(10, 10))
    chamfer = chamfer_lines(line1, line2, 2, 3)
    assert line1.end.x == pytest.approx(8)
    assert line2.start.y == pytest.approx(3)
    assert chamfer.start.as_tuple() == pytest.approx((8, 0))
    assert chamfer.end.as_tuple() == pytest.approx((10, 3))
