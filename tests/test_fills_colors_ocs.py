"""Testes do pacote "preenchimentos, cores de bloco, ordem de desenho e
geometria OCS" (auditoria 2026-09-01 com .dwg reais da New SI — ícones de
legenda abrindo brancos/ocos, hachuras faltando, planta minúscula no zoom
extents): newsicad/io/dxf_fills.py, dxf_io.py e os ramos de Hatch/bloco/cor/
ordem de newsicad/ui/canvas.py.

Cada seção corresponde a um achado verificado por experimento:
1. hachura sólida NÃO é WIPEOUT (só `Hatch.wipeout` é);
2. HATCH com vários contornos e arestas curvas;
3. BYBLOCK / camada "0" herdam a cor do INSERT (inclusive aninhado);
4. SOLID/TRACE/WIPEOUT lidos;
5. ordem de desenho (arquivo e documento);
6. extrusão (0,0,-1) em ARC/CIRCLE/ELLIPSE/INSERT;
7. filtro de blocos "_" só pras setas do ezdxf, base_point, INSERT sem nome;
8. true color e espaçamento de padrão por unidade."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import ezdxf.colors  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsItemGroup  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import (  # noqa: E402
    BYBLOCK,
    Arc,
    BlockReference,
    Dimension,
    Ellipse,
    Hatch,
    Line,
    LWPolyline,
    Point,
)
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.io import dxf_fills  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui import canvas as canvas_mod  # noqa: E402
from newsicad.ui.canvas import BACKGROUND_COLOR, _hatch_fill_lines, cad_to_scene  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _new_dxf():
    doc = ezdxf.new("R2000", setup=False)
    return doc, doc.modelspace()


def _hatches(document: Document) -> list[Hatch]:
    return [e for e in document.all_entities() if isinstance(e, Hatch)]


def _render(window: MainWindow, rect_cad: tuple[float, float, float, float], size: int = 100) -> QImage:
    """Renderiza a cena numa QImage (fundo do canvas) cobrindo o retângulo
    CAD (x0, y0, x1, y1)."""
    window.canvas.refresh_entities()
    _app().processEvents()
    x0, y0, x1, y1 = rect_cad
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(BACKGROUND_COLOR))
    painter = QPainter(image)
    top_left = cad_to_scene(Point(x0, y1))
    bottom_right = cad_to_scene(Point(x1, y0))
    src = QRectF(top_left, bottom_right)
    window.canvas._scene.render(painter, QRectF(0, 0, size, size), src)
    painter.end()
    return image


# ---------------------------------------------------------------------- #
# 1. hachura sólida colorida x WIPEOUT
# ---------------------------------------------------------------------- #
def test_solid_hatch_from_other_program_is_colored_not_wipeout(tmp_path):
    doc, msp = _new_dxf()
    hatch = msp.add_hatch(color=1)
    hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
    hatch.set_solid_fill(color=1)
    path = tmp_path / "solid.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    (entity,) = _hatches(loaded)
    assert entity.solid_fill is True
    assert entity.wipeout is False
    assert entity.color == "#FF0000"

    _app()
    window = MainWindow()
    window.document.add_entity(entity)
    window.canvas.refresh_entities()
    item = window.canvas._entity_items[entity.id]
    assert item.brush().color().name() == "#ff0000"
    assert item.zValue() < 1.0  # não é mais o "z=100 por cima de tudo"


def test_wipeout_command_creates_wipeout_and_roundtrips_as_real_wipeout(tmp_path):
    document = Document()
    interp = CommandInterpreter(CommandContext(document=document, selection=Selection()), COMMAND_REGISTRY, ALIASES)
    interp.start("WIPEOUT")
    for pt in (Point(0, 0), Point(10, 0), Point(10, 10)):
        interp.submit_point(pt)
    interp.submit_text("")
    (hatch,) = _hatches(document)
    assert hatch.wipeout is True and hatch.solid_fill is True

    path = tmp_path / "wipeout.dxf"
    save_dxf(document, path)
    dxf_types = [e.dxftype() for e in ezdxf.readfile(path).modelspace()]
    assert dxf_types == ["WIPEOUT"]

    reloaded, skipped = load_dxf(path)
    assert skipped == 0
    (again,) = _hatches(reloaded)
    assert again.wipeout is True and again.solid_fill is True
    assert len(again.boundary_points) == 3

    _app()
    window = MainWindow()
    window.document.add_entity(again)
    window.canvas.refresh_entities()
    item = window.canvas._entity_items[again.id]
    assert item.brush().color().name() == QColor(BACKGROUND_COLOR).name()


def test_line_inside_block_with_solid_hatch_stays_visible():
    """O corpo sólido de um ícone não pode mais cobrir as linhas do próprio
    bloco: a hachura é desenhada na cor dela e ANTES da linha (ordem da
    definição), então a linha aparece por cima."""
    _app()
    window = MainWindow()
    window.document.define_block(
        "ICON",
        [
            Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], solid_fill=True, color="#FF0000"),
            Line(start=Point(0, 5), end=Point(10, 5), color="#00FF00"),
        ],
    )
    window.document.add_entity(BlockReference(block_name="ICON", insertion_point=Point(0, 0)))
    image = _render(window, (0, 0, 10, 10), size=100)

    colors = {image.pixelColor(x, y).name() for x in range(100) for y in range(100)}
    assert "#ff0000" in colors  # corpo do ícone pintado na cor da hachura
    assert "#00ff00" in colors  # a linha continua visível por cima
    assert QColor(BACKGROUND_COLOR).name() not in {image.pixelColor(50, 20).name(), image.pixelColor(50, 80).name()}


# ---------------------------------------------------------------------- #
# 2. contornos: arestas curvas e furos
# ---------------------------------------------------------------------- #
def test_hatch_edge_path_of_arcs_is_flattened(tmp_path):
    doc, msp = _new_dxf()
    hatch = msp.add_hatch(color=7)
    edge_path = hatch.paths.add_edge_path()
    edge_path.add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    edge_path.add_arc((0, 0), radius=5, start_angle=180, end_angle=360)
    hatch.set_solid_fill()
    path = tmp_path / "arcs.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    (entity,) = _hatches(loaded)
    assert len(entity.boundary_points) >= 8
    assert all(abs(math.hypot(p.x, p.y) - 5.0) < 0.2 for p in entity.boundary_points)


def test_hatch_spline_edge_with_bad_knots_falls_back_to_control_points(tmp_path):
    """Caso real (planta JOE LEE R00, 5 hachuras): SPLINE de contorno com
    vetor de nós inconsistente, que o ezdxf recusa ("N knot values required,
    got M") — em vez de descartar a hachura, usa os pontos de controle."""
    doc, msp = _new_dxf()
    hatch = msp.add_hatch(color=7)
    edge_path = hatch.paths.add_edge_path()
    control = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    edge_path.add_spline(control_points=control, knot_values=[0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9], degree=3)
    hatch.set_solid_fill()
    path = tmp_path / "bad_spline.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    (entity,) = _hatches(loaded)
    assert len(entity.boundary_points) == 4
    assert {(p.x, p.y) for p in entity.boundary_points} == {(0, 0), (10, 0), (10, 10), (0, 10)}


def test_hatch_with_hole_keeps_two_rings_and_hole_is_unfilled(tmp_path):
    doc, msp = _new_dxf()
    hatch = msp.add_hatch(color=7)
    hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True, flags=1)
    hatch.paths.add_polyline_path([(4, 4), (6, 4), (6, 6), (4, 6)], is_closed=True, flags=16)
    hatch.set_solid_fill()
    path = tmp_path / "hole.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    (entity,) = _hatches(loaded)
    assert len(entity.boundary_paths) == 2
    assert len(entity.boundary_points) == 4  # externo continua sendo o 1º anel

    _app()
    window = MainWindow()
    window.document.add_entity(entity)
    window.canvas.refresh_entities()
    item = window.canvas._entity_items[entity.id]
    assert item.path().contains(cad_to_scene(Point(2, 2))) is True
    assert item.path().contains(cad_to_scene(Point(5, 5))) is False  # centro do furo

    # round-trip: os dois anéis sobrevivem ao save
    out = tmp_path / "hole_again.dxf"
    save_dxf(loaded, out)
    again, _ = load_dxf(out)
    assert len(_hatches(again)[0].boundary_paths) == 2


def test_pattern_hatch_lines_are_clipped_by_hole():
    _app()
    window = MainWindow()
    outer = [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]
    inner = [Point(4, 4), Point(6, 4), Point(6, 6), Point(4, 6)]
    hatch = window.document.add_entity(Hatch(boundary_points=outer, boundary_paths=[outer, inner], spacing=0.5))
    window.canvas.refresh_entities()
    item = window.canvas._entity_items[hatch.id]
    assert isinstance(item, canvas_mod._HatchItem)
    assert item.path().contains(cad_to_scene(Point(5, 5))) is False
    assert item._hatch_lines


def test_transform_ops_move_all_rings_together():
    from newsicad.core.geometry_ops import mirror_entity, rotate_entity, scale_entity, translate_entity

    outer = [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]
    inner = [Point(4, 4), Point(6, 4), Point(6, 6), Point(4, 6)]
    hatch = Hatch(boundary_points=list(outer), boundary_paths=[list(outer), list(inner)])
    translate_entity(hatch, 1, 2)
    assert hatch.boundary_paths[1][0] == Point(5, 6)
    assert hatch.boundary_points[0] == Point(1, 2)
    scale_entity(hatch, Point(0, 0), 2)
    assert hatch.boundary_paths[1][0] == Point(10, 12)
    rotate_entity(hatch, Point(0, 0), math.pi)
    assert hatch.boundary_paths[1][0].x == pytest.approx(-10)
    mirrored = mirror_entity(hatch, Point(0, 0), Point(0, 1))
    assert mirrored.boundary_paths[1][0].x == pytest.approx(10)


# ---------------------------------------------------------------------- #
# 3. cor BYBLOCK / camada "0" herdada do INSERT
# ---------------------------------------------------------------------- #
def test_layer0_child_takes_color_of_insert_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("VERMELHA", color="#ff0000")
    window.document.define_block("B", [Line(start=Point(0, 0), end=Point(1, 0), layer="0")])
    ref = window.document.add_entity(BlockReference(block_name="B", layer="VERMELHA"))
    window.canvas.refresh_entities()
    (child,) = window.canvas._entity_items[ref.id].childItems()
    assert child.pen().color().name() == "#ff0000"


def test_byblock_child_takes_insert_own_color():
    _app()
    window = MainWindow()
    window.document.add_layer("VERMELHA", color="#ff0000")
    window.document.define_block(
        "B",
        [
            Line(start=Point(0, 0), end=Point(1, 0), layer="VERMELHA", color=BYBLOCK),
            Line(start=Point(0, 1), end=Point(1, 1), layer="VERMELHA"),  # ByLayer em outra camada: própria camada
        ],
    )
    ref = window.document.add_entity(BlockReference(block_name="B", color="#0000FF"))
    window.canvas.refresh_entities()
    byblock_item, bylayer_item = window.canvas._entity_items[ref.id].childItems()
    assert byblock_item.pen().color().name() == "#0000ff"
    assert bylayer_item.pen().color().name() == "#ff0000"


def test_nested_block_propagates_inherited_color_and_layer():
    _app()
    window = MainWindow()
    window.document.add_layer("VERDE", color="#00ff00")
    window.document.define_block("INNER", [Line(start=Point(0, 0), end=Point(1, 0), layer="0")])
    window.document.define_block("OUTER", [BlockReference(block_name="INNER", layer="0")])
    ref = window.document.add_entity(BlockReference(block_name="OUTER", layer="VERDE"))
    window.canvas.refresh_entities()
    (inner_group,) = window.canvas._entity_items[ref.id].childItems()
    assert isinstance(inner_group, QGraphicsItemGroup)
    (line_item,) = inner_group.childItems()
    assert line_item.pen().color().name() == "#00ff00"


def test_byblock_outside_block_falls_back_to_layer_color():
    _app()
    window = MainWindow()
    window.document.add_layer("AZUL", color="#0000ff")
    line = Line(start=Point(0, 0), end=Point(1, 0), layer="AZUL", color=BYBLOCK)
    assert window.canvas._effective_color(line) == "#0000ff"


def test_block_child_on_off_layer_is_not_drawn_and_layer0_follows_insert():
    _app()
    window = MainWindow()
    window.document.add_layer("OCULTA", color="#ff0000")
    window.document.layers["OCULTA"].visible = False
    window.document.define_block(
        "B",
        [Line(start=Point(0, 0), end=Point(1, 0), layer="OCULTA"), Line(start=Point(0, 1), end=Point(1, 1), layer="0")],
    )
    ref = window.document.add_entity(BlockReference(block_name="B"))
    window.canvas.refresh_entities()
    assert len(window.canvas._entity_items[ref.id].childItems()) == 1


def test_byblock_color_roundtrips_as_dxf_color_zero(tmp_path):
    document = Document()
    document.define_block("B", [Line(start=Point(0, 0), end=Point(1, 0), color=BYBLOCK)])
    document.add_entity(BlockReference(block_name="B"))
    path = tmp_path / "byblock.dxf"
    save_dxf(document, path)
    (line,) = list(ezdxf.readfile(path).blocks.get("B"))
    assert line.dxf.color == 0
    reloaded, _ = load_dxf(path)
    assert reloaded.block_definitions["B"][0].color == BYBLOCK


# ---------------------------------------------------------------------- #
# 4. SOLID / TRACE / WIPEOUT
# ---------------------------------------------------------------------- #
def test_solid_and_trace_become_colored_solid_hatches(tmp_path):
    doc, msp = _new_dxf()
    # vértices na ordem em que o AutoCAD GRAVA (vtx2/vtx3 trocados, "gravata
    # borboleta") — o ezdxf guarda o que recebe e `wcs_vertices()` desfaz a
    # troca ao ler
    msp.add_solid([(0, 0), (4, 0), (0, 4), (4, 4)], dxfattribs={"color": 3})
    msp.add_trace([(10, 0), (14, 0), (10, 4), (14, 4)], dxfattribs={"color": 3})
    path = tmp_path / "solid.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    entities = _hatches(loaded)
    assert len(entities) == 2
    for entity in entities:
        assert entity.solid_fill is True and entity.wipeout is False
        assert entity.color == "#00FF00"
        assert len(entity.boundary_points) == 4
    # vértices em ordem de polígono (o DXF grava o 3º e o 4º trocados)
    xs = [p.x for p in entities[0].boundary_points]
    ys = [p.y for p in entities[0].boundary_points]
    assert (xs, ys) == ([0, 4, 4, 0], [0, 0, 4, 4])


def test_wipeout_entity_from_dxf_is_read_as_wipeout_hatch(tmp_path):
    doc, msp = _new_dxf()
    msp.add_wipeout([(0, 0), (5, 0), (5, 5), (0, 5)])
    path = tmp_path / "wipeout_in.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    (entity,) = _hatches(loaded)
    assert entity.wipeout is True and entity.solid_fill is True
    assert len(entity.boundary_points) == 4


# ---------------------------------------------------------------------- #
# 5. ordem de desenho
# ---------------------------------------------------------------------- #
def test_scene_stacks_entities_in_document_order():
    _app()
    window = MainWindow()
    first = window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 10)))
    wipe = window.document.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], solid_fill=True, wipeout=True)
    )
    last = window.document.add_entity(Line(start=Point(0, 10), end=Point(10, 0)))
    window.canvas.refresh_entities()
    items = window.canvas._entity_items
    assert items[first.id].zValue() < items[wipe.id].zValue() < items[last.id].zValue()
    # scene.items() vem do topo pra base
    stacked = [it for it in window.canvas._scene.items() if it in (items[first.id], items[wipe.id], items[last.id])]
    assert stacked == [items[last.id], items[wipe.id], items[first.id]]

    # a linha anterior fica coberta pelo WIPEOUT; a posterior, visível
    image = _render(window, (0, 0, 10, 10), size=100)
    colors = {image.pixelColor(x, y).name() for x in range(100) for y in range(100)}
    assert len(colors) >= 2


def test_load_dxf_respects_sortents_redraw_order(tmp_path):
    doc, msp = _new_dxf()
    line_a = msp.add_line((0, 0), (1, 0))
    line_b = msp.add_line((0, 1), (1, 1))
    # tabela SORTENTS: B desenha antes de A
    msp.set_redraw_order({line_a.dxf.handle: line_b.dxf.handle, line_b.dxf.handle: line_a.dxf.handle})
    path = tmp_path / "order.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    ys = [e.start.y for e in loaded.all_entities() if isinstance(e, Line)]
    assert ys == [1.0, 0.0]


# ---------------------------------------------------------------------- #
# 6. OCS / extrusão (0,0,-1)
# ---------------------------------------------------------------------- #
def test_arc_and_circle_with_negative_extrusion_are_mirrored(tmp_path):
    doc, msp = _new_dxf()
    msp.add_arc((10, 5), 3, 0, 90, dxfattribs={"extrusion": (0, 0, -1)})
    msp.add_circle((10, 5), 3, dxfattribs={"extrusion": (0, 0, -1)})
    path = tmp_path / "ocs.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    (arc,) = [e for e in loaded.all_entities() if isinstance(e, Arc)]
    assert (arc.center.x, arc.center.y) == pytest.approx((-10, 5))
    assert math.degrees(arc.start_angle) == pytest.approx(90)
    assert math.degrees(arc.end_angle) == pytest.approx(180)
    circle = next(e for e in loaded.all_entities() if type(e).__name__ == "Circle")
    assert (circle.center.x, circle.center.y) == pytest.approx((-10, 5))


def test_insert_with_negative_extrusion_is_mirrored_like_ezdxf(tmp_path):
    doc, msp = _new_dxf()
    block = doc.blocks.new("B")
    block.add_line((0, 0), (1, 0.5))
    insert = msp.add_blockref("B", (2, 3), dxfattribs={"rotation": 30, "extrusion": (0, 0, -1)})
    expected = list(insert.virtual_entities())[0]
    path = tmp_path / "insert_ocs.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    (ref,) = [e for e in loaded.all_entities() if isinstance(e, BlockReference)]
    sx, sy = ref.scale_xy()
    assert sx < 0 and sy > 0
    assert (ref.insertion_point.x, ref.insertion_point.y) == pytest.approx((-2, 3))

    def transform(p: Point) -> tuple[float, float]:
        x, y = p.x * sx, p.y * sy
        c, s = math.cos(ref.rotation), math.sin(ref.rotation)
        return (ref.insertion_point.x + x * c - y * s, ref.insertion_point.y + x * s + y * c)

    (line,) = loaded.block_definitions["B"]
    assert transform(line.start) == pytest.approx((expected.dxf.start.x, expected.dxf.start.y))
    assert transform(line.end) == pytest.approx((expected.dxf.end.x, expected.dxf.end.y))


def test_ellipse_arc_becomes_polyline_and_full_ellipse_stays_ellipse(tmp_path):
    doc, msp = _new_dxf()
    msp.add_ellipse((0, 0), major_axis=(4, 0), ratio=0.5)
    msp.add_ellipse((20, 0), major_axis=(4, 0), ratio=0.5, start_param=0, end_param=math.pi)
    msp.add_ellipse((40, 0), major_axis=(4, 0), ratio=0.5, dxfattribs={"extrusion": (0, 0, -1)})
    path = tmp_path / "ellipse.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    ellipses = [e for e in loaded.all_entities() if isinstance(e, Ellipse)]
    polylines = [e for e in loaded.all_entities() if isinstance(e, LWPolyline)]
    assert len(ellipses) == 2 and len(polylines) == 1
    assert ellipses[0].center == Point(0, 0)
    assert (ellipses[1].center.x, ellipses[1].center.y) == pytest.approx((40, 0))
    arc = polylines[0]
    assert arc.closed is False and len(arc.points) >= 8
    assert all(abs(p.x - 20) <= 4.01 and -0.01 <= p.y <= 2.01 for p in arc.points)


# ---------------------------------------------------------------------- #
# 7. blocos "_", base_point, INSERT sem nome
# ---------------------------------------------------------------------- #
def test_underscore_user_blocks_are_loaded_but_ezdxf_arrow_blocks_are_not(tmp_path):
    doc, msp = _new_dxf()
    legend = doc.blocks.new("_PRANCHA_LEGENDA")
    legend.add_line((0, 0), (10, 0))
    msp.add_blockref("_PRANCHA_LEGENDA", (0, 0))
    path = tmp_path / "underscore.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped == 0
    assert "_PRANCHA_LEGENDA" in loaded.block_definitions
    assert len(loaded.block_definitions["_PRANCHA_LEGENDA"]) == 1

    # .dxf gravado pelo NewSIcad com cota: as setas do ezdxf ficam de fora
    # e o SOLID delas NÃO conta como "não suportado"
    document = Document()
    document.add_entity(Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 3)))
    out = tmp_path / "dim.dxf"
    save_dxf(document, out)
    reloaded, skipped = load_dxf(out)
    assert skipped == 0
    assert not (set(reloaded.block_definitions) & dxf_fills.EZDXF_ARROW_BLOCKS)
    assert "_CLOSEDFILLED" in dxf_fills.EZDXF_ARROW_BLOCKS


def test_block_base_point_is_subtracted_from_children_including_nested_inserts(tmp_path):
    doc, msp = _new_dxf()
    inner = doc.blocks.new("INNER", base_point=(5, 5))
    inner.add_line((5, 5), (15, 5))
    outer = doc.blocks.new("OUTER", base_point=(1, 1))
    outer.add_blockref("INNER", (6, 6))
    msp.add_blockref("OUTER", (100, 100))
    path = tmp_path / "base_point.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    (line,) = loaded.block_definitions["INNER"]
    assert (line.start.x, line.start.y) == (0, 0)
    assert (line.end.x, line.end.y) == (10, 0)
    (nested,) = loaded.block_definitions["OUTER"]
    assert (nested.insertion_point.x, nested.insertion_point.y) == (5, 5)


def test_insert_without_block_name_is_skipped(tmp_path):
    doc, msp = _new_dxf()
    msp.add_blockref("", (0, 0))
    msp.add_line((0, 0), (1, 1))
    path = tmp_path / "noname.dxf"
    doc.saveas(path)

    loaded, skipped = load_dxf(path)
    assert skipped.by_type == {"INSERT": 1}
    assert not [e for e in loaded.all_entities() if isinstance(e, BlockReference)]


# ---------------------------------------------------------------------- #
# 8. true color e padrão por unidade
# ---------------------------------------------------------------------- #
def test_true_color_has_priority_over_aci(tmp_path):
    doc = ezdxf.new("R2004", setup=False)  # grupo 420 (true color) só existe a partir do R2004
    msp = doc.modelspace()
    msp.add_line((0, 0), (1, 1), dxfattribs={"color": 1, "true_color": ezdxf.colors.rgb2int((10, 20, 30))})
    path = tmp_path / "truecolor.dxf"
    doc.saveas(path)
    loaded, _ = load_dxf(path)
    (line,) = loaded.all_entities()
    assert line.color == "#0A141E"


def test_pattern_hatch_spacing_from_file_definition_and_unit_fallback(tmp_path):
    assert dxf_fills.ansi31_spacing(1.0, "m") == pytest.approx(0.003175)
    assert dxf_fills.ansi31_spacing(1.0, "mm") == pytest.approx(3.175)
    assert dxf_fills.ansi31_spacing(1.0, "cm") == pytest.approx(0.3175)

    doc, msp = _new_dxf()
    doc.header["$INSUNITS"] = 6  # metros
    with_def = msp.add_hatch(color=7)
    with_def.paths.add_polyline_path([(0, 0), (1, 0), (1, 1)], is_closed=True)
    with_def.set_pattern_fill("AR-CONC", scale=2.0, angle=30)
    no_def = msp.add_hatch(color=7)
    no_def.paths.add_polyline_path([(2, 0), (3, 0), (3, 1)], is_closed=True)
    no_def.set_pattern_fill("ANSI31", scale=2.0, angle=45)
    no_def.pattern.lines.clear()  # HATCH sem a definição do padrão gravada
    path = tmp_path / "pattern.dxf"
    doc.saveas(path)

    loaded, _ = load_dxf(path)
    assert loaded.units == "m"
    first, second = _hatches(loaded)
    assert first.pattern_name == "AR-CONC" and first.solid_fill is False
    assert first.spacing > 0
    assert second.spacing == pytest.approx(2.0 * 0.003175)
    assert math.degrees(second.angle) == pytest.approx(45)


def test_pattern_name_and_exact_values_roundtrip(tmp_path):
    document = Document()
    document.add_entity(
        Hatch(boundary_points=[Point(0, 0), Point(10, 0), Point(10, 10)], pattern_name="AR-CONC", angle=0.3, spacing=0.7)
    )
    path = tmp_path / "pattern_rt.dxf"
    save_dxf(document, path)
    assert list(ezdxf.readfile(path).modelspace())[0].dxf.pattern_name == "AR-CONC"
    reloaded, _ = load_dxf(path)
    (hatch,) = _hatches(reloaded)
    assert hatch.pattern_name == "AR-CONC"
    assert (hatch.angle, hatch.spacing) == pytest.approx((0.3, 0.7))


def test_hatch_fill_lines_are_capped():
    boundary = [QPointF(0, 0), QPointF(100000, 0), QPointF(100000, 100000), QPointF(0, 100000)]
    lines = _hatch_fill_lines(boundary, math.pi / 4, 0.01)
    assert 0 < len(lines) <= canvas_mod._MAX_HATCH_LINES + 1
