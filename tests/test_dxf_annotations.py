"""Leitura de textos e anotações de .dxf de outros programas (WP-B 2026-09,
newsicad/io/dxf_annotations.py): alinhamento/baseline de TEXT e ATTRIB,
rotação/largura de MTEXT, MULTILEADER/LEADER/DIMENSION/ACAD_TABLE como bloco
anônimo + BlockReference, ATTRIB aninhado, STYLE com fonte SHX e width,
DimStyle proporcional ao arquivo, e o aviso do dwg2dxf pra ACAD_TABLE."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf.entities.acad_table import AcadTableBlockContent
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2
from ezdxf.render.mleader import ConnectionSide

from newsicad.core.document import DimStyle, Document, TextStyle
from newsicad.core.entities import BlockReference, Dimension, Hatch, Line, LWPolyline, Point, Text
from newsicad.io.dwg_bridge import count_unhandled_entities
from newsicad.io.dxf_annotations import read_dim_style
from newsicad.io.dxf_io import load_dxf, save_dxf


def _texts(entities) -> list[Text]:
    return [e for e in entities if isinstance(e, Text)]


def _annotation_refs(document: Document, prefix: str) -> list[BlockReference]:
    return [
        e
        for e in document.all_entities()
        if isinstance(e, BlockReference) and e.block_name.startswith(prefix)
    ]


def _save_ezdxf(doc, tmp_path: Path, name: str = "sample.dxf") -> Path:
    path = tmp_path / name
    doc.saveas(str(path))
    return path


# ---------------------------------------------------------------------- #
# TEXT / ATTRIB: alinhamento e baseline
# ---------------------------------------------------------------------- #
def test_text_with_align_point_uses_align_point_and_mapped_justify(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    centered = msp.add_text("MEIO", dxfattribs={"height": 1.0, "insert": (0, 0)})
    centered.set_placement((1, 2), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text("ESQ", dxfattribs={"height": 1.0, "insert": (5, 6)})
    right = msp.add_text("DIR", dxfattribs={"height": 1.0})
    right.set_placement((9, 9), align=TextEntityAlignment.RIGHT)

    document, skipped = load_dxf(_save_ezdxf(doc, tmp_path))
    by_content = {t.content: t for t in _texts(document.all_entities())}

    assert skipped == 0
    assert by_content["MEIO"].justify == "MC"
    assert (by_content["MEIO"].insertion_point.x, by_content["MEIO"].insertion_point.y) == (1.0, 2.0)
    # ponto 10 = esquerda-BASELINE -> "BL" (não mais "TL" no ponto de inserção)
    assert by_content["ESQ"].justify == "BL"
    assert (by_content["ESQ"].insertion_point.x, by_content["ESQ"].insertion_point.y) == (5.0, 6.0)
    assert by_content["DIR"].justify == "BR"
    assert (by_content["DIR"].insertion_point.x, by_content["DIR"].insertion_point.y) == (9.0, 9.0)


def test_text_reads_style_rotation_and_width_factor(tmp_path):
    doc = ezdxf.new("R2010")
    doc.styles.add("Romans", font="romans.shx", dxfattribs={"width": 0.8})
    msp = doc.modelspace()
    msp.add_text("GIRADO", dxfattribs={"height": 0.5, "rotation": 45.0, "style": "Romans", "width": 1.2})

    document, _ = load_dxf(_save_ezdxf(doc, tmp_path))
    text = _texts(document.all_entities())[0]

    assert text.style == "Romans"
    assert math.isclose(text.rotation, math.radians(45.0))
    assert math.isclose(text.width_factor, 1.2)
    style = document.text_styles["Romans"]
    assert style.font_file == "romans.shx"
    assert style.font_family == "romans"
    assert math.isclose(style.width, 0.8)


def test_text_with_zero_height_is_discarded(tmp_path):
    doc = ezdxf.new("R2010")
    # (o ezdxf troca height=0 pelo padrão 2.5 no add_text; setar depois)
    doc.modelspace().add_text("INVISIVEL").dxf.height = 5e-7
    doc.modelspace().add_text("OK", dxfattribs={"height": 0.2})

    document, _ = load_dxf(_save_ezdxf(doc, tmp_path))

    assert [t.content for t in _texts(document.all_entities())] == ["OK"]


def test_style_font_file_and_width_survive_save_and_reload(tmp_path):
    document = Document()
    document.text_styles["Romans"] = TextStyle(name="Romans", font_family="romans", height=1.8, width=0.8, font_file="romans.shx")
    document.text_styles["Standard"].width = 1.0
    path = tmp_path / "styles.dxf"
    save_dxf(document, path)

    reloaded, _ = load_dxf(path)

    assert reloaded.text_styles["Romans"].font_file == "romans.shx"
    assert math.isclose(reloaded.text_styles["Romans"].width, 0.8)
    assert math.isclose(reloaded.text_styles["Romans"].height, 1.8)
    # estilo criado no NewSIcad continua saindo como <família>.ttf
    dxf_doc = ezdxf.readfile(str(path))
    assert dxf_doc.styles.get("Standard").dxf.font == "Menlo.ttf"


# ---------------------------------------------------------------------- #
# MTEXT: rotação por text_direction, largura, espaçamento
# ---------------------------------------------------------------------- #
def test_mtext_rotation_comes_from_text_direction(tmp_path):
    doc = ezdxf.new("R2010")
    mtext = doc.modelspace().add_mtext("VERTICAL", dxfattribs={"char_height": 0.2, "width": 3.0})
    mtext.dxf.text_direction = (0, 1, 0)  # o dwg2dxf só grava o vetor 11, nunca o 50

    document, _ = load_dxf(_save_ezdxf(doc, tmp_path))
    text = _texts(document.all_entities())[0]

    assert math.isclose(text.rotation, math.pi / 2, abs_tol=1e-9)
    assert math.isclose(text.width, 3.0)
    assert math.isclose(text.line_spacing_factor, 1.0)


def test_mtext_width_line_spacing_and_justify_round_trip_through_save(tmp_path):
    document = Document()
    document.add_entity(
        Text(insertion_point=Point(1, 1), content="AAAA BBBB", height=0.5, width=1.5, line_spacing_factor=1.5, justify="BC")
    )
    path = tmp_path / "mtext.dxf"
    save_dxf(document, path)

    dxf_doc = ezdxf.readfile(str(path))
    mtext = dxf_doc.modelspace().query("MTEXT")[0]
    assert math.isclose(mtext.dxf.width, 1.5)
    assert math.isclose(mtext.dxf.line_spacing_factor, 1.5)

    reloaded, _ = load_dxf(path)
    text = _texts(reloaded.all_entities())[0]
    assert math.isclose(text.width, 1.5)
    assert math.isclose(text.line_spacing_factor, 1.5)
    assert text.justify == "BC"


# ---------------------------------------------------------------------- #
# MULTILEADER / LEADER
# ---------------------------------------------------------------------- #
def test_multileader_is_imported_as_anonymous_block(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    ml = msp.add_multileader_mtext("Standard", dxfattribs={"layer": "LEADERS"})
    ml.set_content("TOMADA\n110V", style="Standard")
    ml.add_leader_line(ConnectionSide.left, [Vec2(-5, -5)])
    ml.build(insert=Vec2(10, 10))

    document, skipped = load_dxf(_save_ezdxf(doc, tmp_path))

    assert "MULTILEADER" not in skipped.by_type
    refs = _annotation_refs(document, "*ML_")
    assert len(refs) == 1
    ref = refs[0]
    assert ref.layer == "LEADERS"
    assert (ref.insertion_point.x, ref.insertion_point.y) == (0.0, 0.0)
    parts = document.block_definitions[ref.block_name]
    texts = _texts(parts)
    assert len(texts) >= 1
    assert "TOMADA" in texts[0].content
    assert texts[0].layer == "LEADERS"  # sub-entidade na camada "0" herda a do leader
    assert any(isinstance(p, (Line, LWPolyline)) for p in parts)


def test_leader_is_imported_as_anonymous_block_with_lines(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_leader([(0, 0), (2, 2), (4, 2)], dxfattribs={"layer": "L"})

    document, skipped = load_dxf(_save_ezdxf(doc, tmp_path))

    assert "LEADER" not in skipped.by_type
    refs = _annotation_refs(document, "*LD_")
    assert len(refs) == 1
    parts = document.block_definitions[refs[0].block_name]
    assert sum(1 for p in parts if isinstance(p, Line)) >= 2
    # seta (SOLID) vira hachura sólida na camada do leader
    arrows = [p for p in parts if isinstance(p, Hatch)]
    assert all(a.solid_fill and a.layer == "L" for a in arrows)


# ---------------------------------------------------------------------- #
# DIMENSION externa (estática) x nativa (XDATA)
# ---------------------------------------------------------------------- #
def test_external_dimension_is_imported_as_static_block(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$DIMTXT"] = 0.25
    doc.header["$DIMASZ"] = 0.125
    msp = doc.modelspace()
    msp.add_linear_dim(base=(0, 2), p1=(0, 0), p2=(10, 0), dxfattribs={"layer": "COTAS"}).render()

    document, skipped = load_dxf(_save_ezdxf(doc, tmp_path))

    assert "DIMENSION" not in skipped.by_type
    assert not any(isinstance(e, Dimension) for e in document.all_entities())
    refs = _annotation_refs(document, "*D_")
    assert len(refs) == 1
    assert refs[0].layer == "COTAS"
    parts = document.block_definitions[refs[0].block_name]
    texts = _texts(parts)
    assert len(texts) >= 1
    assert texts[0].content.strip() == "10"
    assert sum(1 for p in parts if isinstance(p, Line)) >= 3
    # DimStyle segue a altura real do texto da cota importada (mediana) e a
    # razão seta/texto do cabeçalho
    assert math.isclose(document.dim_style.text_height, texts[0].height)
    assert math.isclose(document.dim_style.arrow_size, texts[0].height * 0.5)


def test_newsicad_dimension_round_trips_as_native_dimension(tmp_path):
    document = Document()
    document.dim_style = DimStyle(text_height=0.2, arrow_size=0.1)
    document.add_entity(Dimension(kind="linear", point1=Point(0, 0), point2=Point(5, 0), dim_line_point=Point(0, 1)))
    path = tmp_path / "native_dim.dxf"
    save_dxf(document, path)

    reloaded, skipped = load_dxf(path)

    dims = [e for e in reloaded.all_entities() if isinstance(e, Dimension)]
    assert len(dims) == 1 and dims[0].kind == "linear"
    assert not _annotation_refs(reloaded, "*D_")
    assert skipped == 0
    assert math.isclose(reloaded.dim_style.text_height, 0.2)
    assert math.isclose(reloaded.dim_style.arrow_size, 0.1)
    # e o DXF em si sai com o DIMSTYLE do documento pra outros programas
    dxf_doc = ezdxf.readfile(str(path))
    assert math.isclose(dxf_doc.header["$DIMTXT"], 0.2)


def test_read_dim_style_falls_back_to_header_then_defaults():
    header = {"$DIMTXT": 0.18, "$DIMASZ": 0.09, "$DIMSCALE": 2.0}
    assert read_dim_style(header, []) == (0.36, 0.18)
    assert read_dim_style({}, []) == (DimStyle().text_height, DimStyle().arrow_size)
    text_height, arrow = read_dim_style(header, [0.1, 0.3, 0.2])
    assert math.isclose(text_height, 0.2) and math.isclose(arrow, 0.1)


def test_imported_annotation_block_survives_save_as_anonymous_block(tmp_path):
    document = Document()
    document.define_block("*D_1A", [Line(start=Point(0, 0), end=Point(1, 0)), Text(insertion_point=Point(0, 0), content="1", height=0.1)])
    document.add_entity(BlockReference(block_name="*D_1A", insertion_point=Point(0, 0), layer="COTAS"))
    path = tmp_path / "anon.dxf"
    save_dxf(document, path)

    dxf_doc = ezdxf.readfile(str(path))
    assert "*D_1A" not in dxf_doc.blocks
    reloaded, _ = load_dxf(path)
    refs = [e for e in reloaded.all_entities() if isinstance(e, BlockReference)]
    assert len(refs) == 1 and refs[0].block_name.upper().startswith("*U")
    parts = reloaded.block_definitions[refs[0].block_name]
    assert any(isinstance(p, Line) for p in parts) and any(isinstance(p, Text) for p in parts)


# ---------------------------------------------------------------------- #
# ACAD_TABLE
# ---------------------------------------------------------------------- #
def _acad_table_dxf(tmp_path: Path) -> Path:
    doc = ezdxf.new("R2010")
    block = doc.blocks.new_anonymous_block(type_char="T")
    block.add_line((0, 0), (10, 0))
    block.add_line((0, 0), (0, -4))
    block.add_text("CELULA", dxfattribs={"height": 0.5}).set_placement((1, -1))
    table = AcadTableBlockContent.from_text(
        "  0\nACAD_TABLE\n100\nAcDbEntity\n  8\nTAB\n100\nAcDbBlockReference\n  2\n"
        f"{block.name}\n 10\n5.0\n 20\n7.0\n 30\n0.0\n100\nAcDbTable\n280\n0\n 91\n2\n 92\n2\n",
        doc,
    )
    doc.modelspace().add_entity(table)
    return _save_ezdxf(doc, tmp_path, "table.dxf")


def test_acad_table_is_imported_as_block_reference(tmp_path):
    document, skipped = load_dxf(_acad_table_dxf(tmp_path))

    assert "ACAD_TABLE" not in skipped.by_type
    refs = _annotation_refs(document, "*T_")
    assert len(refs) == 1
    assert refs[0].layer == "TAB"
    parts = document.block_definitions[refs[0].block_name]
    lines = [p for p in parts if isinstance(p, Line)]
    texts = _texts(parts)
    assert len(lines) == 2 and len(texts) == 1
    # conteúdo do bloco *T transladado pro ponto de inserção da tabela (5,7)
    assert (lines[0].start.x, lines[0].start.y) == (5.0, 7.0)
    assert texts[0].content == "CELULA"
    assert (texts[0].insertion_point.x, texts[0].insertion_point.y) == (6.0, 6.0)


def test_dwg_bridge_counts_acad_table_dropped_by_dwg2dxf():
    stderr = (
        "Warning: Unhandled Class object 527 ACDB_MLEADEROBJECTCONTEXTDATA_CLASS (0x481) 24826/0\n"
        "Warning: Unhandled Class entity 579 ACAD_TABLE (0x401) 47946/0\n"
        "Warning: Unhandled Class entity 579 ACAD_TABLE (0x401) 47947/0\n"
    )
    assert count_unhandled_entities(stderr) == {"ACAD_TABLE (descartada pelo dwg2dxf)": 2}
    assert count_unhandled_entities("") == {}


# ---------------------------------------------------------------------- #
# ATTRIB aninhado (INSERT dentro de definição de bloco)
# ---------------------------------------------------------------------- #
def test_attrib_of_nested_insert_is_promoted_inside_parent_block(tmp_path):
    doc = ezdxf.new("R2010")
    inner = doc.blocks.new("B")
    inner.add_circle((0, 0), 0.5)
    inner.add_attdef("X", (0, 0), dxfattribs={"height": 0.25})
    outer = doc.blocks.new("A")
    insert = outer.add_blockref("B", (1, 1))
    insert.add_auto_attribs({"X": "T-01"})
    doc.modelspace().add_blockref("A", (10, 10))

    document, _ = load_dxf(_save_ezdxf(doc, tmp_path))

    texts = _texts(document.block_definitions["A"])
    assert [t.content for t in texts] == ["T-01"]
    assert texts[0].justify == "BL"
    assert (texts[0].insertion_point.x, texts[0].insertion_point.y) == (1.0, 1.0)
    assert math.isclose(texts[0].height, 0.25)
    # o ATTRIB do INSERT de modelspace continua sendo promovido a Text solto
    top = doc.modelspace().add_blockref("B", (3, 3))
    top.add_auto_attribs({"X": "T-02"})
    document, _ = load_dxf(_save_ezdxf(doc, tmp_path, "msp.dxf"))
    assert "T-02" in [t.content for t in _texts(document.all_entities())]
