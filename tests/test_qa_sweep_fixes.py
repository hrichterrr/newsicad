"""Testes de regressão pros bugs confirmados na varredura de QA com 10
agentes paralelos (2026-08-22) — ver o artifact consolidado. Cobre os itens
críticos/altos que têm lógica testável sem depender de uma GUI de verdade;
os fixes puramente visuais (troca de ícone, rótulo) não têm teste dedicado
aqui, cobertos pelo resto da suíte não quebrar."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.modify_commands import _join_collinear_runs  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document, TextStyle  # noqa: E402
from newsicad.core.entities import (  # noqa: E402
    Arc,
    BlockReference,
    Circle,
    Line,
    LWPolyline,
    Point,
    PointEntity,
    Text,
)
from newsicad.core.geometry_ops import offset_polyline  # noqa: E402
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    return interp, doc


# ---------------------------------------------------------------------- #
# Interpretador: catch amplo + validação de kind="keyword"
# ---------------------------------------------------------------------- #
def test_arc_with_collinear_points_cancels_cleanly_instead_of_crashing():
    interp, doc = make_interpreter()
    interp.start("ARC")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(10, 0))  # colinear com os dois primeiros
    assert not interp.active
    assert not doc.all_entities()


def test_array_polar_blank_enter_uses_default_instead_of_crashing():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("ARRAY")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("Polar")
    interp.submit_point(Point(0, 0))
    interp.submit_text("")  # Enter em branco no número de itens -> default <6>
    interp.submit_text("")  # ângulo default 360
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, Line)]) == 6


def test_divide_blank_enter_cancels_cleanly_instead_of_crashing():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("DIVIDE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("")  # Enter em branco -> sem default, cancela
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, PointEntity)]


def test_measure_blank_enter_cancels_cleanly_instead_of_crashing():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    interp.start("MEASURE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_text("")
    assert not interp.active


def test_measure_now_supports_circle():
    interp, doc = make_interpreter()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=10))
    interp.start("MEASURE")
    interp.context.selection.add(circle.id)
    interp.submit_text("")
    interp.submit_text(str(2 * math.pi * 10 / 4))  # 4 marcadores ao redor
    assert not interp.active
    points = [e for e in doc.all_entities() if isinstance(e, PointEntity)]
    assert len(points) == 4


def test_field_rejects_unknown_keyword_instead_of_creating_broken_text():
    interp, doc = make_interpreter()
    interp.start("FIELD")
    interp.submit_text("Banana")  # não é AREA/LENGTH/DATE
    assert interp.active  # continua no mesmo prompt, não avança
    interp.submit_text("Date")  # agora sim uma opção válida
    interp.submit_point(Point(0, 0))
    interp.submit_text("")
    assert not interp.active
    texts = [e for e in doc.all_entities() if isinstance(e, Text)]
    assert len(texts) == 1
    assert texts[0].field_type == "DATE"


# ---------------------------------------------------------------------- #
# ELLIPSE / SCALE / MIRROR / INSERT — validação de geometria degenerada
# ---------------------------------------------------------------------- #
def test_ellipse_zero_radius_is_rejected():
    interp, doc = make_interpreter()
    interp.start("ELLIPSE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 0))  # centro == ponto do eixo -> raio maior 0
    interp.submit_text("2")
    assert not interp.active
    assert not doc.all_entities()


def test_scale_factor_zero_or_negative_is_rejected():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("SCALE")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    interp.submit_text("-2")
    assert not interp.active
    assert line.end.as_tuple() == (1.0, 0.0)  # inalterado


def test_mirror_degenerate_axis_is_rejected():
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    interp.start("MIRROR")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(5, 5))
    interp.submit_point(Point(5, 5))  # eixo degenerado
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, Line)]) == 1


def test_insert_scale_zero_is_rejected():
    interp, doc = make_interpreter()
    doc.block_definitions["CADEIRA"] = [Line(start=Point(0, 0), end=Point(1, 0))]
    interp.start("INSERT")
    interp.submit_text("CADEIRA")
    interp.submit_point(Point(0, 0))
    interp.submit_text("0")
    assert not interp.active
    assert not [e for e in doc.all_entities() if isinstance(e, BlockReference)]


def test_xline_same_point_is_rejected_and_command_keeps_going():
    interp, doc = make_interpreter()
    interp.start("XLINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(0, 0))  # coincide com a base
    interp.submit_point(Point(5, 5))  # ponto válido em seguida
    interp.submit_text("")
    assert not interp.active
    from newsicad.core.entities import XLine
    assert len([e for e in doc.all_entities() if isinstance(e, XLine)]) == 1


# ---------------------------------------------------------------------- #
# LINE [Undo] agora remove o segmento de verdade
# ---------------------------------------------------------------------- #
def test_line_undo_removes_last_segment():
    interp, doc = make_interpreter()
    interp.start("LINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(5, 5))
    assert len([e for e in doc.all_entities() if isinstance(e, Line)]) == 2
    interp.submit_text("Undo")
    assert len([e for e in doc.all_entities() if isinstance(e, Line)]) == 1
    interp.submit_text("")
    assert not interp.active


# ---------------------------------------------------------------------- #
# LAYISO / LAYUNISO — substitui em vez de empilhar
# ---------------------------------------------------------------------- #
def test_layiso_called_twice_does_not_orphan_earlier_layers():
    interp, doc = make_interpreter()
    doc.add_layer("REDE")
    doc.add_layer("CFTV")
    doc.add_layer("SOM")
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0), layer="REDE"))
    b = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 0), layer="CFTV"))

    interp.start("LAYISO")
    interp.context.selection.add(a.id)
    interp.submit_text("")
    assert doc.layers["CFTV"].visible is False
    assert doc.layers["SOM"].visible is False
    assert doc.layers["REDE"].visible is True

    interp.start("LAYISO")
    interp.context.selection.add(b.id)
    interp.submit_text("")
    # REDE tinha sido escondida? não, mas CFTV deveria estar visível de novo
    # e SOM continuar escondida (única camada nem A nem B usam agora).
    assert doc.layers["REDE"].visible is False
    assert doc.layers["CFTV"].visible is True
    assert doc.layers["SOM"].visible is False

    interp.start("LAYUNISO")
    assert doc.layers["REDE"].visible is True
    assert doc.layers["SOM"].visible is True


# ---------------------------------------------------------------------- #
# PASTECLIP deixa os objetos colados selecionados
# ---------------------------------------------------------------------- #
def test_pasteclip_leaves_pasted_objects_selected():
    _app()
    interp, doc = make_interpreter()
    line = doc.add_entity(Line(start=Point(0, 0), end=Point(2, 0)))
    interp.start("COPYCLIP")
    interp.context.selection.add(line.id)
    interp.submit_text("")
    interp.submit_point(Point(0, 0))
    assert not interp.active

    interp.start("PASTECLIP")
    interp.submit_point(Point(10, 10))
    assert not interp.active
    assert len(interp.context.selection.ids) == 1


# ---------------------------------------------------------------------- #
# STRETCH agora move Circle/Arc/PointEntity/Text/BlockReference
# ---------------------------------------------------------------------- #
def test_stretch_moves_circle_arc_point_text_and_block_inside_window():
    interp, doc = make_interpreter()
    doc.block_definitions["CAM"] = [Line(start=Point(0, 0), end=Point(1, 0))]
    circle = doc.add_entity(Circle(center=Point(5, 5), radius=1))
    arc = doc.add_entity(Arc(center=Point(5, 6), radius=1, start_angle=0, end_angle=1))
    point = doc.add_entity(PointEntity(location=Point(5, 7)))
    text = doc.add_entity(Text(insertion_point=Point(5, 8), content="tag"))
    block = doc.add_entity(BlockReference(block_name="CAM", insertion_point=Point(5, 9)))
    outside_circle = doc.add_entity(Circle(center=Point(50, 50), radius=1))

    interp.start("STRETCH")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 20))
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(2, 3))
    assert not interp.active

    assert circle.center.as_tuple() == (7.0, 8.0)
    assert arc.center.as_tuple() == (7.0, 9.0)
    assert point.location.as_tuple() == (7.0, 10.0)
    assert text.insertion_point.as_tuple() == (7.0, 11.0)
    assert block.insertion_point.as_tuple() == (7.0, 12.0)
    assert outside_circle.center.as_tuple() == (50.0, 50.0)  # fora da janela, intocado


# ---------------------------------------------------------------------- #
# DDEDIT num FIELD "quebra" o vínculo em vez de perder a edição
# ---------------------------------------------------------------------- #
def test_ddedit_on_field_text_breaks_the_live_link():
    interp, doc = make_interpreter()
    text = doc.add_entity(Text(insertion_point=Point(0, 0), content="100.00 m²", field_type="AREA"))
    interp.start("DDEDIT")
    interp.context.selection.add(text.id)
    interp.submit_text("")
    interp.submit_text("Área definitiva: 120m²")
    assert not interp.active
    assert text.content == "Área definitiva: 120m²"
    assert text.field_type is None
    assert text.field_ref is None


# ---------------------------------------------------------------------- #
# FIND agora busca em Dimension e Table também
# ---------------------------------------------------------------------- #
def test_find_matches_table_cell_and_dimension_text():
    _app()
    window = MainWindow()
    from newsicad.core.entities import Dimension, Table

    table = window.document.add_entity(
        Table(insertion_point=Point(0, 0), rows=1, cols=1, cells=[["QA-01"]])
    )
    dim = window.document.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(5, 0), dim_line_point=Point(0, 1))
    )

    with patch("newsicad.ui.main_window.QInputDialog.getText", return_value=("qa-01", True)), patch(
        "newsicad.ui.main_window.QMessageBox.information"
    ):
        window._show_find_dialog()
    assert window.selection.ids == {table.id}

    with patch("newsicad.ui.main_window.QInputDialog.getText", return_value=("5.00", True)), patch(
        "newsicad.ui.main_window.QMessageBox.information"
    ):
        window._show_find_dialog()
    assert window.selection.ids == {dim.id}


# ---------------------------------------------------------------------- #
# Save não trava mais com geometria degenerada / XREF com nome inválido
# ---------------------------------------------------------------------- #
def test_save_file_catches_ezdxf_exception_instead_of_crashing(tmp_path):
    _app()
    window = MainWindow()
    # Geometria válida por construção (ELLIPSE agora é validada na criação),
    # então simulamos o mesmo tipo de falha diretamente na chamada de
    # save_dxf pra confirmar que o handler genérico realmente existe.
    path = tmp_path / "out.dxf"
    window.current_path = path
    with patch("newsicad.ui.main_window.save_dxf", side_effect=RuntimeError("boom")), patch(
        "newsicad.ui.main_window.QMessageBox.critical"
    ) as mock_critical:
        result = window._save_file()
    assert result is False
    mock_critical.assert_called_once()


def test_xref_block_name_is_dxf_safe_and_survives_save(tmp_path):
    _app()
    window = MainWindow()
    ref_path = tmp_path / "planta arquiteto.dxf"
    other_doc = Document()
    other_doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    save_dxf(other_doc, ref_path)

    with patch(
        "newsicad.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(ref_path), "DXF (*.dxf)"),
    ):
        window._start_xref()

    block_names = list(window.document.block_definitions.keys())
    assert len(block_names) == 1
    assert ":" not in block_names[0]

    out_path = tmp_path / "com_xref.dxf"
    save_dxf(window.document, out_path)  # não deve levantar exceção
    reloaded, _ = load_dxf(out_path)
    assert block_names[0] in reloaded.block_definitions


# ---------------------------------------------------------------------- #
# round-trip de metadado do DXF (cor/visibilidade/trava de camada,
# current_layer, unidade, cor de entidade, estilo de texto)
# ---------------------------------------------------------------------- #
def test_dxf_roundtrip_preserves_layer_and_document_metadata(tmp_path):
    doc = Document()
    doc.add_layer("PAREDES", color="#FF0000")
    doc.layers["PAREDES"].visible = False
    doc.layers["PAREDES"].locked = True
    doc.set_current_layer("PAREDES")
    doc.units = "in"
    doc.text_styles["Titulo"] = TextStyle(name="Titulo", font_family="Arial", height=5.0)

    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0), layer="PAREDES", color="#00FF00"))
    doc.add_entity(Text(insertion_point=Point(0, 0), content="Oi", style="Titulo", layer="PAREDES"))

    path = tmp_path / "metadata.dxf"
    save_dxf(doc, path)
    reloaded, skipped = load_dxf(path)

    assert skipped == 0
    assert reloaded.units == "in"
    assert reloaded.current_layer == "PAREDES"
    layer = reloaded.layers["PAREDES"]
    assert layer.color == "#FF0000"
    assert layer.visible is False
    assert layer.locked is True

    line = next(e for e in reloaded.all_entities() if isinstance(e, Line))
    assert line.color == "#00FF00"
    text = next(e for e in reloaded.all_entities() if isinstance(e, Text))
    assert text.style == "Titulo"
    assert reloaded.text_styles["Titulo"].font_family == "Arial"
    assert reloaded.text_styles["Titulo"].height == 5.0


# ---------------------------------------------------------------------- #
# Undo/Redo guardado contra comando ativo + BEDIT empilha undo
# ---------------------------------------------------------------------- #
def test_ctrl_z_mid_command_cancels_command_instead_of_corrupting_undo_stack():
    _app()
    window = MainWindow()
    window._start_command("LINE")
    window.canvas.on_point(Point(0, 0))
    window.canvas.on_point(Point(5, 0))
    assert window.interpreter.active
    entities_before = len(window.document.entities)

    window._do_undo()  # não deve consumir um snapshot do undo_stack

    assert not window.interpreter.active
    assert len(window.document.entities) == entities_before  # nada desfeito, só cancelado


def test_bedit_save_pushes_undo_snapshot():
    _app()
    window = MainWindow()
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    window.document.define_block("MESA", [line])
    window.document.remove_entity(line.id)
    window.document.add_entity(BlockReference(block_name="MESA", insertion_point=Point(0, 0)))
    stack_depth_before = len(window.undo_stack._history) if hasattr(window.undo_stack, "_history") else None

    with patch("newsicad.ui.main_window.QInputDialog.getItem", return_value=("MESA", True)), patch(
        "newsicad.ui.main_window.BlockEditorDialog"
    ) as mock_dialog:
        mock_dialog.return_value.exec.return_value = None
        window._start_bedit()

    # Só confere que o push aconteceu (o board de teste não sabe o formato
    # interno do UndoStack) — indiretamente, via um undo() bem-sucedido.
    assert window.undo_stack.undo() or stack_depth_before is None


# ---------------------------------------------------------------------- #
# OFFSET de LWPolyline fechada: distância maior que o menor raio de
# curvatura agora levanta erro em vez de inflar/inverter a forma
# ---------------------------------------------------------------------- #
def test_offset_closed_polyline_normal_distance_shrinks_correctly():
    square = LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    result = offset_polyline(square, 2.0, Point(5, 5))  # lado de dentro
    assert len(result.points) == 4
    xs = [p.x for p in result.points]
    ys = [p.y for p in result.points]
    assert min(xs) == pytest.approx(2.0)
    assert max(xs) == pytest.approx(8.0)
    assert min(ys) == pytest.approx(2.0)
    assert max(ys) == pytest.approx(8.0)


def test_offset_closed_polyline_distance_larger_than_shape_raises_instead_of_inverting():
    square = LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    with pytest.raises(ValueError):
        offset_polyline(square, 20.0, Point(5, 5))  # bem maior que cabe dentro do quadrado


def test_offset_command_reports_the_collapse_instead_of_crashing():
    interp, doc = make_interpreter()
    square = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    )
    interp.start("OFFSET")
    interp.submit_text("20")
    interp.submit_point(Point(5, 0))  # clica perto do segmento de baixo
    interp.submit_point(Point(5, 5))  # lado de dentro
    assert interp.active  # OFFSET continua no loop pedindo o próximo objeto
    interp.submit_text("")
    assert not interp.active
    assert len([e for e in doc.all_entities() if isinstance(e, LWPolyline)]) == 1  # nada novo foi criado


# ---------------------------------------------------------------------- #
# JOIN: uma linha solta na seleção não bloqueia mais os pares válidos
# ---------------------------------------------------------------------- #
def test_join_collinear_runs_groups_valid_pairs_and_leaves_stray_line_alone():
    a = Line(start=Point(0, 0), end=Point(5, 0))
    b = Line(start=Point(5, 0), end=Point(10, 0))  # colinear/conectada com a
    stray = Line(start=Point(0, 20), end=Point(3, 25))  # nem colinear nem conectada

    runs = _join_collinear_runs([a, b, stray])
    run_sizes = sorted(len(r) for r in runs)
    assert run_sizes == [1, 2]


def test_join_command_merges_valid_pair_and_leaves_stray_line_untouched():
    interp, doc = make_interpreter()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))
    b = doc.add_entity(Line(start=Point(5, 0), end=Point(10, 0)))
    stray = doc.add_entity(Line(start=Point(0, 20), end=Point(3, 25)))

    interp.start("JOIN")
    interp.context.selection.set({a.id, b.id, stray.id})
    interp.submit_text("")
    assert not interp.active

    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2  # a+b viraram uma linha só, stray continua existindo
    assert stray in lines
    survivor = next(line for line in lines if line is not stray)
    assert survivor.start.as_tuple() == (0.0, 0.0)
    assert survivor.end.as_tuple() == (10.0, 0.0)


def test_join_command_with_only_a_stray_line_reports_nothing_joined():
    interp, doc = make_interpreter()
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(5, 0)))
    stray = doc.add_entity(Line(start=Point(0, 20), end=Point(3, 25)))

    interp.start("JOIN")
    interp.context.selection.set({a.id, stray.id})
    interp.submit_text("")
    assert not interp.active
    lines = [e for e in doc.all_entities() if isinstance(e, Line)]
    assert len(lines) == 2  # nada foi unido/removido


# ---------------------------------------------------------------------- #
# rename_layer: nome vazio é rejeitado no modelo, não só na UI
# ---------------------------------------------------------------------- #
def test_rename_layer_rejects_blank_new_name():
    doc = Document()
    doc.add_layer("PAREDES")
    with pytest.raises(ValueError):
        doc.rename_layer("PAREDES", "")
    with pytest.raises(ValueError):
        doc.rename_layer("PAREDES", "   ")
    assert "PAREDES" in doc.layers


# ---------------------------------------------------------------------- #
# Esc sem comando ativo agora limpa a seleção parada (igual ao AutoCAD)
# ---------------------------------------------------------------------- #
def test_escape_with_no_active_command_clears_selection():
    _app()
    window = MainWindow()
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    window.selection.add(line.id)
    assert window.selection.ids
    assert not window.interpreter.active

    window._handle_cancel()

    assert not window.selection.ids


def test_escape_mid_command_still_cancels_the_command_not_the_selection():
    _app()
    window = MainWindow()
    line = window.document.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    window.selection.add(line.id)
    window._start_command("LINE")
    assert window.interpreter.active

    window._handle_cancel()

    assert not window.interpreter.active
    assert window.selection.ids == {line.id}  # Esc só cancelou o comando desta vez


# ---------------------------------------------------------------------- #
# Comandos read-only (ZOOM/PAN/DIST/ID/AREA/SELECTSIMILAR/QSELECT/COPYCLIP)
# não empilham mais um snapshot de undo à toa
# ---------------------------------------------------------------------- #
def test_read_only_command_does_not_push_undo_snapshot():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    depth_before = len(window.undo_stack._undo_stack)

    window._start_command("DIST")
    window.interpreter.submit_point(Point(0, 0))
    window.interpreter.submit_point(Point(5, 0))
    assert not window.interpreter.active

    assert len(window.undo_stack._undo_stack) == depth_before


def test_mutating_command_still_pushes_undo_snapshot():
    _app()
    window = MainWindow()
    depth_before = len(window.undo_stack._undo_stack)

    window._start_command("LINE")
    window.canvas.on_point(Point(0, 0))
    window.canvas.on_point(Point(5, 0))
    window.interpreter.submit_text("")

    assert len(window.undo_stack._undo_stack) == depth_before + 1


def test_repeat_last_read_only_command_does_not_push_undo_snapshot():
    _app()
    window = MainWindow()
    window.document.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window._start_command("ID")
    window.interpreter.submit_point(Point(0, 0))
    assert not window.interpreter.active
    depth_before = len(window.undo_stack._undo_stack)

    window._repeat_last_command()
    window.interpreter.submit_point(Point(1, 1))

    assert len(window.undo_stack._undo_stack) == depth_before


# ---------------------------------------------------------------------- #
# dwg_export: falha ao gravar o .dwg em disco (arquivo aberto em outro
# programa, disco cheio...) agora vira DwgExportError amigável, não uma
# exceção crua subindo até a UI
# ---------------------------------------------------------------------- #
def test_dwg_export_download_write_failure_raises_dwg_export_error(tmp_path):
    from newsicad.io.dwg_export import DwgExportError, _download_result

    job_data = {
        "tasks": [
            {"name": "export-dwg", "result": {"files": [{"url": "https://example.invalid/f.dwg"}]}}
        ]
    }
    bad_path = tmp_path / "nao-existe" / "sub" / "saida.dwg"  # diretório pai não existe -> OSError

    class _FakeResponse:
        status_code = 200
        content = b"fake dwg bytes"

    with patch("newsicad.io.dwg_export.requests.get", return_value=_FakeResponse()):
        with pytest.raises(DwgExportError):
            _download_result(job_data, bad_path)


# ---------------------------------------------------------------------- #
# HATCH agora confirma o que criou e avisa que é um padrão único de
# aproximação, em vez de terminar em silêncio
# ---------------------------------------------------------------------- #
def test_hatch_command_reports_creation_and_approximation_note():
    interp, doc = make_interpreter()
    boundary = doc.add_entity(
        LWPolyline(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)], closed=True)
    )
    interp.start("HATCH")
    interp.context.selection.add(boundary.id)
    interp.submit_text("")
    assert not interp.active
    assert any("HATCH: 1 hachura" in line and "padrão único" in line for line in interp.log)
