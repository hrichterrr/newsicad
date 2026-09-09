"""Arco dentro de polilinha (bulge) e espessura constante.

O NewSIcad lia só x e y da LWPOLYLINE: todo arco virava a reta entre os
vértices e a espessura sumia. O ícone do keypad da Casa Pau Brasil (Wi-Fi de
três arcos + onda de cinco, traço de 0,14 a 0,43) aparecia como um "X"
rabiscado — relato do Hamilton em 09/09/2026; são 285 polilinhas com arco só
dentro dos símbolos dessa planta e 118 na Ana Beatriz.
"""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import pytest  # noqa: E402
from ezdxf.math import bulge_to_arc as ezdxf_bulge_to_arc  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.bulge import arc_midpoint, bulge_to_arc, polyline_pieces  # noqa: E402
from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Arc, Line, LWPolyline, Point  # noqa: E402
from newsicad.core.geometry_ops import (  # noqa: E402
    as_intersectable_pieces,
    entity_intersections,
    mirror_entity,
    point_entity_distance,
)
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui.canvas import CanvasView  # noqa: E402


# ------------------------------------------------------------- matemática
@pytest.mark.parametrize(
    "a, b, bulge",
    [
        (Point(0, 0), Point(10, 0), 1.0),      # semicírculo anti-horário
        (Point(0, 0), Point(10, 0), -1.0),     # semicírculo horário
        (Point(3, 4), Point(-2, 7), 0.732),    # ~ os bulges do keypad
        (Point(3, 4), Point(-2, 7), -0.56),
        (Point(1, 1), Point(1.5, 1.2), 0.107), # arco raso do Wi-Fi
    ],
)
def test_bulge_bate_com_o_ezdxf(a, b, bulge):
    nosso = bulge_to_arc(a, b, bulge)
    centro, inicio, fim, raio = ezdxf_bulge_to_arc((a.x, a.y), (b.x, b.y), bulge)
    assert nosso.center.x == pytest.approx(centro.x, abs=1e-9)
    assert nosso.center.y == pytest.approx(centro.y, abs=1e-9)
    assert nosso.radius == pytest.approx(raio, abs=1e-9)
    assert nosso.start_angle == pytest.approx(inicio % (2 * math.pi), abs=1e-9)
    assert nosso.end_angle == pytest.approx(fim % (2 * math.pi), abs=1e-9)


def test_semicirculo_passa_pelo_arco_e_nao_pela_corda():
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0])
    (arco,) = polyline_pieces(poly)
    assert isinstance(arco, Arc)
    meio = arc_midpoint(arco)
    assert meio.x == pytest.approx(5) and meio.y == pytest.approx(-5)
    assert point_entity_distance(Point(5, -5), poly) == pytest.approx(0, abs=1e-9)
    assert point_entity_distance(Point(5, 0), poly) == pytest.approx(5, abs=1e-9), "a corda não faz parte do desenho"


def test_bulge_negativo_vai_para_o_outro_lado():
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[-1.0])
    (arco,) = polyline_pieces(poly)
    assert arc_midpoint(arco).y == pytest.approx(5)


def test_sem_bulge_continua_tudo_reta():
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)])
    pecas = polyline_pieces(poly)
    assert all(isinstance(p, Line) for p in pecas) and len(pecas) == 2


# ------------------------------------------------------------ transformações
def test_espelhar_inverte_o_arco():
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0])
    espelhada = mirror_entity(poly, Point(0, 0), Point(1, 0))  # eixo X
    assert list(espelhada.bulges) == [-1.0]
    assert arc_midpoint(polyline_pieces(espelhada)[0]).y == pytest.approx(5)


def test_trim_enxerga_o_arco():
    """Uma linha vertical em x=5 cruza o semicírculo no topo (5,5) — pela
    corda ela cruzaria em (5,0), que não existe no desenho."""
    poly = LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0])
    reta = Line(start=Point(5, -8), end=Point(5, 8))
    cruzamentos = [pt for peca in as_intersectable_pieces(poly) for pt in entity_intersections(reta, peca)]
    assert len(cruzamentos) == 1
    assert cruzamentos[0].x == pytest.approx(5) and cruzamentos[0].y == pytest.approx(-5)


def test_explode_solta_um_arc_de_verdade():
    doc = Document()
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10)], bulges=[1.0, 0.0]))
    interp = CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES)
    interp.context.selection.set({poly.id})
    interp.start("EXPLODE")
    tipos = sorted(type(e).__name__ for e in doc.all_entities())
    assert tipos == ["Arc", "Line"]


# ------------------------------------------------------------ ida e volta
def test_bulge_e_espessura_sobrevivem_a_leitura_e_gravacao(tmp_path):
    origem = ezdxf.new("R2018")
    msp = origem.modelspace()
    msp.add_lwpolyline([(0, 0, 0.732), (4, 3, 0.56), (8, 0, -0.56), (12, 3, 0)], format="xyb",
                       dxfattribs={"const_width": 0.2304})
    entrada = tmp_path / "onda.dxf"
    origem.saveas(str(entrada))

    doc, _ = load_dxf(entrada)
    (poly,) = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    assert poly.bulges == pytest.approx([0.732, 0.56, -0.56, 0.0])
    assert poly.width == pytest.approx(0.2304)

    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravada = ezdxf.readfile(str(saida)).modelspace().query("LWPOLYLINE").first
    assert [round(p[2], 6) for p in gravada.get_points("xyb")] == [0.732, 0.56, -0.56, 0.0]
    assert gravada.dxf.const_width == pytest.approx(0.2304)


def test_polilinha_espelhada_por_ocs_inverte_o_bulge(tmp_path):
    """Extrusão (0,0,-1) = a entidade está num sistema espelhado; o sentido
    do arco tem de virar junto com os pontos."""
    origem = ezdxf.new("R2018")
    origem.modelspace().add_lwpolyline([(0, 0, 1.0), (10, 0, 0)], format="xyb",
                                       dxfattribs={"extrusion": (0, 0, -1)})
    entrada = tmp_path / "ocs.dxf"
    origem.saveas(str(entrada))
    doc, _ = load_dxf(entrada)
    (poly,) = [e for e in doc.all_entities() if isinstance(e, LWPolyline)]
    meio = arc_midpoint(polyline_pieces(poly)[0])
    # Em WCS o desenho fica refletido em X: o arco que descia até (5,-5)
    # passa a descer até (-5,-5). Sem inverter o bulge ele subiria — o
    # espelho mudaria o lado do arco, e o AutoCAD não faz isso.
    assert poly.points[1].x == pytest.approx(-10)
    assert meio.x == pytest.approx(-5, abs=1e-6)
    assert meio.y == pytest.approx(-5, abs=1e-6)


# --------------------------------------------------------------- tela
@pytest.fixture
def tela():
    QApplication.instance() or QApplication([])
    doc = Document()
    interp = CommandInterpreter(CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES)
    canvas = CanvasView(doc, interp)
    canvas.resize(600, 600)
    return doc, canvas


def _pinta(canvas, ponto_cad) -> bool:
    """O pixel da viewport onde `ponto_cad` cai está pintado?"""
    canvas.show()
    QApplication.processEvents()
    img = canvas.viewport().grab().toImage()
    px = canvas.mapFromScene(ponto_cad.x, -ponto_cad.y)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if img.pixelColor(px.x() + dx, px.y() + dy).lightness() > 90:
                return True
    return False


def test_a_tela_desenha_o_arco_e_nao_a_corda(tela):
    doc, canvas = tela
    doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0]))
    canvas.refresh_entities()
    canvas.zoom_extents()
    assert _pinta(canvas, Point(5, -5)), "o meio do arco tem de estar pintado"
    assert not _pinta(canvas, Point(5, 0)), "a corda não pode aparecer"


def test_clique_acha_a_polilinha_pelo_arco(tela):
    doc, canvas = tela
    poly = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0]))
    canvas.refresh_entities()
    canvas.zoom_extents()
    assert canvas._hit_test(Point(5, -5)) == poly.id


def test_espessura_vai_para_a_caneta(tela):
    doc, canvas = tela
    grossa = doc.add_entity(LWPolyline(points=[Point(0, 0), Point(10, 0)], width=0.4))
    fina = doc.add_entity(LWPolyline(points=[Point(0, 5), Point(10, 5)]))
    canvas.refresh_entities()
    assert canvas._entity_items[grossa.id].pen().widthF() == pytest.approx(0.4)
    assert canvas._entity_items[grossa.id].pen().isCosmetic() is False
    assert canvas._entity_items[fina.id].pen().isCosmetic() or canvas._entity_items[fina.id].pen().width() == 0

    # desselecionar tem de devolver a espessura, não a caneta fina
    canvas.interpreter.context.selection.set({grossa.id})
    canvas.refresh_selection_highlight()
    canvas.interpreter.context.selection.clear()
    canvas.refresh_selection_highlight()
    assert canvas._entity_items[grossa.id].pen().widthF() == pytest.approx(0.4)


def test_arco_dentro_de_bloco_tambem_e_desenhado(tela):
    from newsicad.core.entities import BlockReference

    doc, canvas = tela
    doc.define_block("WIFI", [LWPolyline(points=[Point(0, 0), Point(10, 0)], bulges=[1.0])])
    doc.add_entity(BlockReference(block_name="WIFI", insertion_point=Point(0, 0)))
    canvas.refresh_entities()
    canvas.zoom_extents()
    assert _pinta(canvas, Point(5, -5))
    assert not _pinta(canvas, Point(5, 0))


def test_bulge_negativo_no_meio_da_polilinha_nao_vira_circulo(tela):
    """A onda do keypad: bulges 0.732, 0.56, -0.56, -0.732. O arco negativo é
    percorrido ao contrário; começar do lado errado fazia o Qt varrer o
    complemento e desenhar um círculo quase inteiro."""
    from newsicad.core.bulge import arc_midpoint, polyline_pieces

    doc, canvas = tela
    poly = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(20, 0)], bulges=[1.0, -1.0, 0.0])
    )
    canvas.refresh_entities()
    canvas.zoom_extents()
    primeiro, segundo = polyline_pieces(poly)
    assert _pinta(canvas, arc_midpoint(primeiro))   # (5, -5)
    assert _pinta(canvas, arc_midpoint(segundo))    # (15, 5)
    # o complemento do segundo arco passaria por (15, -5): não pode existir
    assert not _pinta(canvas, Point(15, -5))
    assert not _pinta(canvas, Point(5, 5))
