"""Testes de round-trip para newsicad/io/dxf_io.py: grava um Document com
uma instância de cada tipo de entidade suportado, lê de volta, e compara a
geometria. Também cobre o caminho de erro (arquivo inexistente)."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import (
    Arc,
    BlockReference,
    Circle,
    Dimension,
    Ellipse,
    Hatch,
    Line,
    LWPolyline,
    Point,
    Text,
)
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


def test_round_trip_preserves_block_definition_and_reference():
    """Define um bloco (BLOCK), insere uma instância (INSERT), salva .dxf,
    reabre, e confirma que tanto a definição quanto a BlockReference
    (com escala/rotação/ponto de inserção) sobrevivem ao round-trip."""
    original = Document()
    original.define_block(
        "CHAIR",
        [
            Line(layer="0", start=Point(0, 0), end=Point(2, 0)),
            Circle(layer="0", center=Point(1, 1), radius=0.5),
        ],
    )
    original.add_entity(
        BlockReference(
            layer="0",
            block_name="CHAIR",
            insertion_point=Point(10, 20),
            scale=2.5,
            rotation=math.radians(37),
        )
    )
    # Uma segunda instância do mesmo bloco, pra garantir que a definição não
    # é duplicada e que múltiplas referências ao mesmo nome funcionam.
    original.add_entity(
        BlockReference(
            layer="0",
            block_name="CHAIR",
            insertion_point=Point(-5, -5),
            scale=1.0,
            rotation=0.0,
        )
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "blocks_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert "CHAIR" in loaded.block_definitions
    def_entities = loaded.block_definitions["CHAIR"]
    assert len(def_entities) == 2

    def_line = next(e for e in def_entities if isinstance(e, Line))
    assert def_line.start.x == pytest.approx(0)
    assert def_line.end.x == pytest.approx(2)

    def_circle = next(e for e in def_entities if isinstance(e, Circle))
    assert def_circle.center.x == pytest.approx(1)
    assert def_circle.radius == pytest.approx(0.5)

    refs = [e for e in loaded.all_entities() if isinstance(e, BlockReference)]
    assert len(refs) == 2

    ref_a = next(r for r in refs if r.insertion_point.x == pytest.approx(10))
    assert ref_a.block_name == "CHAIR"
    assert ref_a.insertion_point.y == pytest.approx(20)
    assert ref_a.scale == pytest.approx(2.5)
    assert ref_a.rotation == pytest.approx(math.radians(37))

    ref_b = next(r for r in refs if r.insertion_point.x == pytest.approx(-5))
    assert ref_b.scale == pytest.approx(1.0)
    assert ref_b.rotation == pytest.approx(0.0)


def test_load_dxf_skips_invisible_entities_dynamic_block_state():
    """Um BLOCO DINÂMICO com parâmetro de Visibilidade (ex.: um símbolo com
    opções de altura de montagem Baixo/Médio/Alto) fica gravado em DXF puro
    como vários INSERTs aninhados na mesma definição, todos na origem — só o
    INSERT do estado ativo quando o arquivo foi salvo tem invisible=0
    (ausente); os outros ganham group code 60 = 1. Sem filtrar isso, TODAS
    as variantes eram desenhadas empilhadas no mesmo ponto: o símbolo
    "explodido"/gigante reportado pelo Michael no grupo de feedback do
    NewSicad (planta PATRICIA E FABIO, 09/09/2026) — 202 dos 355 blocos do
    arquivo real tinham essa forma. O group code 60 é genérico do
    AcDbEntity (qualquer entidade pode estar invisível, não só INSERT de
    bloco dinâmico), então o teste cobre os dois casos: dentro de uma
    definição de bloco e solto no modelspace."""
    import ezdxf

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "dynamic_block_visibility.dxf"
        doc = ezdxf.new(setup=False)

        for suffix in ("A", "B", "C"):
            sub = doc.blocks.new(name=f"DYN_SYMBOL-{suffix}")
            sub.add_circle((0, 0), radius=1, dxfattribs={"layer": "0"})

        # Definição "container" do bloco dinâmico: 3 variantes empilhadas na
        # origem, só "-B" fica visível (as outras têm invisible=1) — imita
        # exatamente o que o dwg2dxf produz a partir de um .dwg real.
        parent = doc.blocks.new(name="DYN_SYMBOL")
        parent.add_blockref("DYN_SYMBOL-A", (0, 0), dxfattribs={"layer": "0", "invisible": 1})
        parent.add_blockref("DYN_SYMBOL-B", (0, 0), dxfattribs={"layer": "0"})
        parent.add_blockref("DYN_SYMBOL-C", (0, 0), dxfattribs={"layer": "0", "invisible": 1})

        msp = doc.modelspace()
        msp.add_blockref("DYN_SYMBOL", (5, 5), dxfattribs={"layer": "0"})
        # Entidade solta invisível no modelspace (fora de qualquer bloco) —
        # o mesmo group code 60 também deve ser respeitado aqui.
        msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "0", "invisible": 1})
        msp.add_line((2, 2), (3, 3), dxfattribs={"layer": "0"})
        doc.saveas(path)

        loaded, skipped = load_dxf(path)

    assert skipped == 0

    def_entities = loaded.block_definitions["DYN_SYMBOL"]
    assert len(def_entities) == 1
    only_ref = def_entities[0]
    assert isinstance(only_ref, BlockReference)
    assert only_ref.block_name == "DYN_SYMBOL-B"

    lines = [e for e in loaded.all_entities() if isinstance(e, Line)]
    assert len(lines) == 1
    assert (lines[0].start.x, lines[0].start.y) == (2, 2)


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


def test_load_dxf_reads_classic_polyline_as_lwpolyline():
    """Entidade POLYLINE "clássica" (pré-LWPOLYLINE, ainda comum em .dwg
    reais/mais antigos — não algo que o próprio save_dxf do NewSIcad emite,
    então precisa ser montada com ezdxf puro para existir no arquivo de
    teste). Bug real reportado pelos testers 2026-08-24: um .dwg de cliente
    convertido tinha dezenas dessas ignoradas como "não suportada"."""
    import ezdxf

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "classic_polyline.dxf"
        doc = ezdxf.new(setup=False)
        msp = doc.modelspace()
        msp.add_polyline2d([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "0"})
        doc.saveas(path)

        loaded, skipped = load_dxf(path)

    assert skipped == 0
    polylines = [e for e in loaded.all_entities() if isinstance(e, LWPolyline)]
    assert len(polylines) == 1
    assert polylines[0].closed is True
    assert [(p.x, p.y) for p in polylines[0].points] == [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_load_dxf_skipped_count_has_per_type_breakdown():
    """`skipped` continua se comportando como um int puro (comparações,
    interpolação em string) mas carrega `.by_type` com a contagem por
    dxftype — é isso que vira o "(Nx TIPO, ...)" na mensagem de aviso do
    File > Open em vez de só um número sem contexto nenhum."""
    import ezdxf

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "unsupported_entities.dxf"
        doc = ezdxf.new(setup=False)
        msp = doc.modelspace()
        # 3DFACE (face de malha 3D) continua sem suporte — SOLID, que este
        # teste usava antes, passou a ser lido como Hatch sólida em 2026-09.
        msp.add_3dface([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], dxfattribs={"layer": "0"})
        msp.add_3dface([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], dxfattribs={"layer": "0"})
        msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "0"})
        doc.saveas(path)

        loaded, skipped = load_dxf(path)

    assert skipped == 2
    assert skipped > 0
    assert f"{skipped} entidade(s)" == "2 entidade(s)"
    assert skipped.by_type == {"3DFACE": 2}
    assert len(loaded.all_entities()) == 1


# ---------------------------------------------------------------------- #
# paper space (layouts): achado do grupo de feedback do NewSicad,
# 09/09/2026 — arquivos onde o Model space vem quase vazio e o desenho de
# verdade está todo em pranchas de paper space (plantas FABIO E JULIANA e
# PATRICIA E FABIO). `document.layouts[nome]` guarda a geometria de cada
# prancha à parte do Model (`document.entities`), com round-trip completo.
# ---------------------------------------------------------------------- #
def test_load_dxf_reads_paper_space_layout_entities():
    import ezdxf

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "paper_space.dxf"
        doc = ezdxf.new(setup=False)
        doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "0"})

        layout = doc.layouts.new("01 - Planta")
        layout.add_line((10, 10), (20, 10), dxfattribs={"layer": "0"})
        layout.add_circle((15, 15), radius=2, dxfattribs={"layer": "0"})
        # VIEWPORT: a "janela" pro Model space — ainda não é conteúdo que o
        # NewSIcad desenha, então não deve aparecer nem ser contado como
        # entidade ignorada.
        layout.add_viewport(center=(0, 0), size=(10, 10), view_center_point=(0, 0), view_height=10)

        doc.saveas(path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert len(loaded.all_entities()) == 1  # só a LINE do Model
    assert "01 - Planta" in loaded.layouts
    layout_entities = list(loaded.layouts["01 - Planta"].values())
    assert len(layout_entities) == 2
    assert {type(e).__name__ for e in layout_entities} == {"Line", "Circle"}


def test_round_trip_preserves_paper_space_layout():
    """Save de um Document com `layouts` preenchido escreve as pranchas de
    volta no .dxf — sem isso, abrir um arquivo com conteúdo em paper space
    e dar Save apagava esse conteúdo silenciosamente (nunca era escrito,
    já que `save_dxf` sempre partia de um `ezdxf.new()` do zero)."""
    original = Document()
    original.add_entity(Line(layer="0", start=Point(0, 0), end=Point(1, 1)))
    original.layouts["01 - Planta"] = {
        "a": Circle(layer="0", center=Point(5, 5), radius=3),
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "paper_space_round_trip.dxf"
        save_dxf(original, path)
        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert len(loaded.all_entities()) == 1
    assert "01 - Planta" in loaded.layouts
    layout_entities = list(loaded.layouts["01 - Planta"].values())
    assert len(layout_entities) == 1
    circle = layout_entities[0]
    assert isinstance(circle, Circle)
    assert circle.center.x == pytest.approx(5)
    assert circle.radius == pytest.approx(3)


def test_load_dxf_ignores_model_named_layout_and_empty_layouts():
    """"Model" nunca vira uma entrada em `document.layouts` (é o Model
    space de verdade, já coberto por `document.entities`), e uma prancha
    sem nenhuma entidade de conteúdo (só título/config, sem geometria) não
    polui `document.layouts` com uma entrada vazia."""
    import ezdxf

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "empty_layout.dxf"
        doc = ezdxf.new(setup=False)
        doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "0"})
        doc.layouts.new("Layout vazio")  # sem nenhuma entidade
        doc.saveas(path)

        loaded, skipped = load_dxf(path)

    assert skipped == 0
    assert "Model" not in loaded.layouts
    assert loaded.layouts == {}
