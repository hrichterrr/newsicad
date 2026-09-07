"""PDF legível no papel branco, e definições de bloco que não se fundem.

Auditoria de 2026-09-07: (a) o `export_pdf` renderiza a cena com as cores de
TELA, que é escura — tudo o que era branco (a cor padrão da camada "0") sumia
na folha, e o WIPEOUT, pintado com a cor de fundo do canvas, virava um
retângulo quase preto cobrindo o desenho; (b) o `new_anonymous_block` do ezdxf
só olha o que já existe no documento novo, então um nome gerado podia colidir
com um "*U1" legítimo do arquivo e as duas definições viravam uma.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import BlockReference, Circle, Hatch, Line, Point, Text  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui.canvas import CanvasView  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def _conta_pixels(caminho) -> tuple[int, int]:
    """(pixels escuros, pixels na cor de fundo do canvas). Conta pixel a
    pixel: amostrar de 3 em 3 pula linha fina de 1 pixel."""
    pix = pymupdf.open(caminho)[0].get_pixmap(dpi=100)
    dados, canais = pix.samples, pix.n
    escuros = fundo_canvas = 0
    for i in range(0, len(dados), canais):
        r, g, b = dados[i], dados[i + 1], dados[i + 2]
        if r < 150 and g < 150 and b < 150:
            escuros += 1
            if (r, g, b) == (0x1E, 0x1E, 0x1E):
                fundo_canvas += 1
    return escuros, fundo_canvas


def test_cor_clara_demais_vira_preta_no_papel():
    assert CanvasView._print_color("#FFFFFF") == "#000000"
    assert CanvasView._print_color("#e8e8e8") == "#000000"
    # cor de verdade do desenho é preservada
    assert CanvasView._print_color("#2776BB") == "#2776BB"
    assert CanvasView._print_color("#ff0000") == "#ff0000"


def test_desenho_branco_aparece_no_pdf_e_wipeout_nao_vira_tarja(window, tmp_path):
    doc = window.document
    for i in range(5):
        doc.add_entity(Line(start=Point(0, i), end=Point(20, i)))  # camada "0" = branco
    doc.add_entity(Text(insertion_point=Point(1, 7), content="TEXTO BRANCO", height=1.5))
    doc.add_entity(
        Hatch(
            boundary_points=[Point(5, -3), Point(15, -3), Point(15, -1), Point(5, -1)],
            solid_fill=True,
            wipeout=True,
        )
    )
    window.canvas.refresh_entities()
    pdf = tmp_path / "saida.pdf"
    assert window.canvas.export_pdf(pdf, page_size="A4")

    escuros, fundo_canvas = _conta_pixels(pdf)
    assert escuros > 500, "o desenho branco sumiu no papel"
    assert fundo_canvas == 0, "o wipeout virou tarja com a cor de fundo do canvas"


def test_cores_da_tela_voltam_depois_de_exportar(window, tmp_path):
    doc = window.document
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    window.canvas.refresh_entities()
    antes = window.canvas._entity_items[linha.id].pen().color().name()
    window.canvas.export_pdf(tmp_path / "x.pdf", page_size="A4")
    depois = window.canvas._entity_items[linha.id].pen().color().name()
    assert depois == antes


def test_nome_gerado_nao_colide_com_bloco_anonimo_do_arquivo():
    doc = Document()
    doc.define_block("*ML_ABC", [Line(start=Point(0, 0), end=Point(1, 0))])
    doc.define_block("*U1", [Circle(center=Point(0, 0), radius=1)])
    doc.add_entity(BlockReference(block_name="*ML_ABC", insertion_point=Point(0, 0)))
    doc.add_entity(BlockReference(block_name="*U1", insertion_point=Point(5, 5)))

    destino = pathlib.Path(tempfile.mkdtemp()) / "b.dxf"
    save_dxf(doc, destino)
    volta, _ = load_dxf(destino)

    assert len(volta.block_definitions) == 2, "duas definições viraram uma"
    assert all(len(ents) == 1 for ents in volta.block_definitions.values())
    refs = [e.block_name for e in volta.entities.values() if isinstance(e, BlockReference)]
    assert len(set(refs)) == 2, "os dois INSERT apontam para o mesmo bloco"
