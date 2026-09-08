"""Os seis achados baratos da rodada com as amostras oficiais da Autodesk
(07/09/2026): PDF ancorado no canto, cabeçalho do .dxf sobrescrito pelo
default do ezdxf, LENGTHEN que não dizia nada, MLEADER inexistente e um
rótulo de menu que descrevia o item errado."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.context import CommandContext  # noqa: E402
from newsicad.commands.interpreter import CommandInterpreter  # noqa: E402
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY  # noqa: E402
from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.core.selection import Selection  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui.canvas import CanvasView, _centralizado  # noqa: E402


# ------------------------------------------------------------------ PDF
class _PintorFalso:
    def __init__(self, largura, altura):
        self._r = QRectF(0, 0, largura, altura)

    def viewport(self):
        return self._r


@pytest.mark.parametrize(
    "folha, desenho",
    [
        ((595, 842), QRectF(0, 0, 100, 40)),   # A4 retrato, desenho deitado
        ((842, 595), QRectF(0, 0, 40, 100)),   # A4 paisagem, desenho em pé
        ((842, 1191), QRectF(0, 0, 30, 100)),  # A3 retrato, bem estreito
    ],
)
def test_pdf_centraliza_o_desenho_na_folha(folha, desenho):
    alvo = _centralizado(_PintorFalso(*folha), desenho)
    esquerda = alvo.left()
    direita = folha[0] - alvo.right()
    topo = alvo.top()
    base = folha[1] - alvo.bottom()
    assert esquerda == pytest.approx(direita, abs=0.5), "torto na horizontal"
    assert topo == pytest.approx(base, abs=0.5), "torto na vertical"
    assert alvo.width() <= folha[0] + 0.5 and alvo.height() <= folha[1] + 0.5
    assert alvo.width() / alvo.height() == pytest.approx(desenho.width() / desenho.height())


def test_pdf_sai_com_o_desenho_no_meio(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_entity(Line(start=Point(0, 0), end=Point(100, 10)))
    interp = CommandInterpreter(
        CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES
    )
    canvas = CanvasView(doc, interp)
    canvas.resize(800, 600)
    canvas.refresh_entities()
    pdf = tmp_path / "meio.pdf"
    assert canvas.export_pdf(pdf, page_size="A4", orientation="portrait")

    fitz = pytest.importorskip("fitz")
    documento = fitz.open(str(pdf))
    pagina = documento[0]
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for desenho in pagina.get_drawings():
        r = desenho["rect"]
        x0, y0 = min(x0, r.x0), min(y0, r.y0)
        x1, y1 = max(x1, r.x1), max(y1, r.y1)
    assert y0 == pytest.approx(pagina.rect.height - y1, abs=4), "desenho grudado no topo"
    documento.close()


# ------------------------------------------------------------- cabeçalho
@pytest.mark.parametrize(
    "chave, valor",
    [("$LUNITS", 4), ("$MEASUREMENT", 0), ("$AUPREC", 3)],
)
def test_cabecalho_imperial_sobrevive_a_ida_e_volta(tmp_path, chave, valor):
    origem = ezdxf.new("R2018")
    origem.header[chave] = valor
    origem.modelspace().add_line((0, 0), (1, 1))
    entrada = tmp_path / "imperial.dxf"
    origem.saveas(str(entrada))

    doc, _ = load_dxf(entrada)
    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    assert ezdxf.readfile(str(saida)).header[chave] == valor


def test_limites_do_desenho_sao_preservados(tmp_path):
    origem = ezdxf.new("R2018")
    # Os limites moram em dois lugares: o cabeçalho e o layout do modelspace.
    # Mexer só no cabeçalho não sobrevive nem à gravação do próprio ezdxf.
    origem.header["$LIMMIN"] = (-100.0, -50.0)
    origem.header["$LIMMAX"] = (900.0, 600.0)
    origem.modelspace().dxf.limmin = (-100.0, -50.0)
    origem.modelspace().dxf.limmax = (900.0, 600.0)
    origem.modelspace().add_line((0, 0), (1, 1))
    entrada = tmp_path / "limites.dxf"
    origem.saveas(str(entrada))
    assert tuple(ezdxf.readfile(str(entrada)).header["$LIMMAX"])[:2] == (900.0, 600.0)

    doc, _ = load_dxf(entrada)
    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravado = ezdxf.readfile(str(saida))
    assert tuple(gravado.header["$LIMMAX"])[:2] == (900.0, 600.0)


def test_desenho_novo_nao_inventa_cabecalho(tmp_path):
    doc = Document()
    doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    saida = tmp_path / "novo.dxf"
    save_dxf(doc, saida)
    assert ezdxf.readfile(str(saida)) is not None


# -------------------------------------------------------------- LENGTHEN
def test_lengthen_diz_o_comprimento_em_vez_de_nao_fazer_nada():
    doc = Document()
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(3, 4)))  # 5.0

    class _View:
        def _hit_test(self, _p):
            return linha.id

    ctx = CommandContext(document=doc, selection=Selection())
    ctx.view = _View()
    interp = CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES)
    interp.start("LENGTHEN")
    interp.submit_point(Point(1, 1))

    assert linha.length() == pytest.approx(5.0), "nada podia mudar"
    assert any("Comprimento atual: 5.0" in linha_log for linha_log in interp.log), interp.log


# --------------------------------------------------------------- MLEADER
@pytest.mark.parametrize("nome", ["MLEADER", "MLD", "QLEADER", "LEADER", "LE"])
def test_mleader_cai_no_leader(nome):
    doc = Document()
    interp = CommandInterpreter(
        CommandContext(document=doc, selection=Selection()), COMMAND_REGISTRY, ALIASES
    )
    assert interp.resolve_command(nome) == "LEADER"
    interp.start(nome)
    assert interp.current_prompt is not None
    assert "leader start point" in interp.current_prompt.message


# ---------------------------------------------------------------- rótulo
def test_rotulo_do_ctrl_shift_c_diz_o_que_ele_faz():
    from PySide6.QtGui import QAction

    QApplication.instance() or QApplication([])
    from newsicad.ui.main_window import MainWindow

    w = MainWindow()
    try:
        rotulos = [a.text() for a in w.findChildren(QAction)]
        assert "Duplicate in Drawing" in rotulos
        assert "Copy with Base Point" not in rotulos, (
            "esse é o nome do COPYBASE do AutoCAD; o item duplica dentro do desenho"
        )
    finally:
        for sessao in w.sessions:
            sessao.mark_saved()
        w.close()
