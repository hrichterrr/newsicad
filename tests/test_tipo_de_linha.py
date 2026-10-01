"""Tipo de linha (LTYPE), espessura e escala de traço.

Achado da varredura da base, não de reclamação. O censo de 01/10/2026 abriu
um projeto de cada cliente e mediu: 6 dos 7 arquivos legíveis têm linha NÃO
contínua — 7 % das entidades em média, 25 % no pior caso — e 29 % das
entidades têm espessura própria, 75 % no pior caso. Num único projeto
(CASA SAPUCAIA) são 5.270 entidades na camada "LINHA TRACEJADA 2_1" e 2.728
na "- LINHA DE EIXO - TRAÇO E PONTO".

Nada disso era lido. Toda linha de eixo, projeção e circuito elétrico do
cliente voltava CONTÍNUA no arquivo entregue, e o desenho na tela deixava de
distinguir eixo de parede. É uma perda silenciosa: nenhuma entidade falta,
nenhuma cota se mexe, a contagem fecha — e o desenho está errado.

Os testes cobrem as duas pontas: o que a gente entrega (round-trip do DXF,
que é o compromisso com o cliente) e o que a gente mostra (a caneta do
canvas).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import ezdxf.audit  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document, LineType  # noqa: E402
from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402
from newsicad.ui.canvas import dash_pattern_do_padrao  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402

#: Padrões reais, como vêm na tabela LTYPE do AutoCAD (unidades do desenho).
DASHED = [1.27, -0.254]
CENTER = [3.175, -0.635, 0.635, -0.635]
DASHDOT = [2.54, -0.508, 0.0, -0.508]


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _arquivo_do_cliente(destino: Path) -> Path:
    """Um .dxf com tracejado nos três lugares onde ele aparece de verdade: na
    camada (ByLayer, o caso mais comum), na entidade, e num tipo de linha de
    nome próprio como os que a New SI usa."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$LTSCALE"] = 50.0  # planta em centímetros
    doc.linetypes.add("LINHA TRACEJADA 2_1", pattern=[3.0, 2.0, -1.0],
                      description="tracejada da New SI")
    eixo = doc.layers.add("EIXO")
    eixo.dxf.linetype = "CENTER"
    eixo.dxf.lineweight = 25
    doc.layers.add("PAREDE").dxf.lineweight = 50
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "EIXO"})
    msp.add_line((0, 1), (10, 1), dxfattribs={"layer": "PAREDE", "linetype": "DASHED"})
    msp.add_line((0, 2), (10, 2), dxfattribs={"layer": "0", "linetype": "LINHA TRACEJADA 2_1",
                                              "lineweight": 70, "ltscale": 2.5})
    msp.add_circle((5, 5), 2, dxfattribs={"layer": "EIXO", "lineweight": 13})
    caminho = destino / "cliente.dxf"
    doc.saveas(caminho)
    return caminho


# --------------------------------------------------------------------- #
# o que a gente ENTREGA
# --------------------------------------------------------------------- #


def test_le_tabela_de_tipos_de_linha_e_ltscale():
    with tempfile.TemporaryDirectory() as tmp:
        documento, _ = load_dxf(_arquivo_do_cliente(Path(tmp)))

    assert documento.linetype_scale == 50.0, "LTSCALE do arquivo, não 1.0 fixo"
    nomeado = documento.linetypes["LINHA TRACEJADA 2_1"]
    assert nomeado.pattern == [2.0, -1.0]
    assert nomeado.length == 3.0
    assert "CENTER" in documento.linetypes
    assert documento.linetypes["CONTINUOUS"].continuous


def test_le_tipo_de_linha_e_espessura_da_camada():
    with tempfile.TemporaryDirectory() as tmp:
        documento, _ = load_dxf(_arquivo_do_cliente(Path(tmp)))

    assert documento.layers["EIXO"].linetype == "CENTER"
    assert documento.layers["EIXO"].lineweight == 25
    assert documento.layers["PAREDE"].lineweight == 50
    # o nome vem com a caixa do arquivo ("Continuous" no ezdxf, "CONTINUOUS"
    # no AutoCAD): preservado como está e comparado sem caixa, que é como o
    # DXF trata nome de tabela.
    assert documento.layers["PAREDE"].linetype.upper() == "CONTINUOUS"


def test_resolve_bylayer_igual_a_cor():
    with tempfile.TemporaryDirectory() as tmp:
        documento, _ = load_dxf(_arquivo_do_cliente(Path(tmp)))

    por_camada = {}
    for entidade in documento.entities.values():
        por_camada.setdefault(entidade.layer, []).append(entidade)

    # a linha da camada EIXO não declara tipo nenhum: herda o da camada
    linha_eixo = next(e for e in por_camada["EIXO"] if isinstance(e, Line))
    assert linha_eixo.linetype == ""
    assert documento.linetype_of(linha_eixo).name == "CENTER"
    assert documento.lineweight_of(linha_eixo) == 25

    # o círculo tem espessura própria, mas tipo de linha da camada
    circulo = next(e for e in por_camada["EIXO"] if isinstance(e, Circle))
    assert documento.linetype_of(circulo).name == "CENTER"
    assert documento.lineweight_of(circulo) == 13, "espessura da entidade manda na da camada"

    # a linha com tipo próprio ignora a camada
    propria = next(e for e in por_camada["0"] if isinstance(e, Line))
    assert documento.linetype_of(propria).name == "LINHA TRACEJADA 2_1"
    assert propria.linetype_scale == 2.5


def test_round_trip_entrega_o_tracejado_de_volta():
    """O compromisso com o cliente: ele abre o arquivo que a gente entregou,
    no AutoCAD dele, e a linha de eixo continua linha de eixo."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        documento, _ = load_dxf(_arquivo_do_cliente(tmp))
        nosso = tmp / "entregue.dxf"
        save_dxf(documento, nosso)
        relido = ezdxf.readfile(nosso)

        assert relido.header.get("$LTSCALE") == 50.0
        tabela = relido.linetypes.get("LINHA TRACEJADA 2_1")
        comprimentos = [t.value for t in tabela.pattern_tags.tags if t.code == 49]
        assert comprimentos == [2.0, -1.0], "o padrão de traço tem que sair idêntico"

        camada = relido.layers.get("EIXO")
        assert camada.dxf.linetype == "CENTER"
        assert camada.dxf.lineweight == 25

        por_camada = {e.dxf.layer: e for e in relido.modelspace() if e.dxftype() == "LINE"}
        assert por_camada["PAREDE"].dxf.linetype == "DASHED"
        assert por_camada["0"].dxf.linetype == "LINHA TRACEJADA 2_1"
        assert por_camada["0"].dxf.lineweight == 70
        assert por_camada["0"].dxf.ltscale == 2.5
        # ByLayer não é gravado como nome: a chave ausente É o ByLayer do DXF
        assert por_camada["EIXO"].dxf.linetype.upper() == "BYLAYER"


def test_nao_cita_tipo_de_linha_que_nao_esta_na_tabela():
    """Nome órfão deixa o arquivo inválido pro AutoCAD. Perder o tracejado de
    um tipo desconhecido é menos grave do que entregar arquivo que não abre."""
    documento = Document()
    documento.add_entity(Line(start=Point(0, 0), end=Point(1, 1), linetype="NAO_EXISTE"))
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "orfao.dxf"
        save_dxf(documento, caminho)
        relido = ezdxf.readfile(caminho)
        linha = next(iter(relido.modelspace()))
        assert linha.dxf.linetype.upper() == "BYLAYER"
        auditor = ezdxf.audit.Auditor(relido)
        auditor.run()
        assert not auditor.errors, [str(e) for e in auditor.errors]


# --------------------------------------------------------------------- #
# o que a gente MOSTRA
# --------------------------------------------------------------------- #


def test_padrao_do_dxf_vira_dash_pattern_do_qt():
    assert dash_pattern_do_padrao([]) is None, "sem padrão = contínua"
    assert dash_pattern_do_padrao([1.0, 2.0]) is None, "só traço, sem lacuna = contínua"

    tracejada = dash_pattern_do_padrao(DASHED)
    assert len(tracejada) == 2 and tracejada[0] > tracejada[1], "traço longo, lacuna curta"

    eixo = dash_pattern_do_padrao(CENTER)
    assert len(eixo) == 4
    assert eixo[0] > eixo[2], "linha de eixo é traço longo + traço curto"

    traco_ponto = dash_pattern_do_padrao(DASHDOT)
    assert len(traco_ponto) == 4
    assert traco_ponto[2] < traco_ponto[0], "o ponto é bem menor que o traço"
    assert all(v > 0 for v in traco_ponto), "o Qt não aceita elemento zero ou negativo"


def test_lista_sempre_alterna_traco_e_lacuna():
    """Padrão que começa por lacuna ou tem dois traços seguidos existe em
    arquivo real; o Qt interpreta posição par como traço, então a lista tem
    que sair normalizada ou o tracejado aparece invertido."""
    assert len(dash_pattern_do_padrao([-1.0, 2.0])) % 2 == 0
    assert len(dash_pattern_do_padrao([2.0, -1.0, 1.0])) % 2 == 0
    assert all(v > 0 for v in dash_pattern_do_padrao([-1.0, 2.0]))


def _caneta(janela, entidade):
    return janela.canvas._entity_items[entidade.id].pen()


def test_canvas_desenha_tracejado_resolvendo_bylayer():
    app = _app()
    janela = MainWindow()
    documento = janela.document
    documento.linetypes["CENTER"] = LineType(name="CENTER", pattern=CENTER, length=5.08)
    documento.linetypes["DASHED"] = LineType(name="DASHED", pattern=DASHED, length=1.524)
    documento.add_layer("EIXO").linetype = "CENTER"

    continua = documento.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    por_camada = documento.add_entity(Line(layer="EIXO", start=Point(0, 1), end=Point(10, 1)))
    propria = documento.add_entity(Line(start=Point(0, 2), end=Point(10, 2), linetype="DASHED"))
    janela.canvas.refresh_entities()
    app.processEvents()

    assert _caneta(janela, continua).style() == Qt.PenStyle.SolidLine
    assert _caneta(janela, por_camada).style() == Qt.PenStyle.CustomDashLine
    assert _caneta(janela, propria).style() == Qt.PenStyle.CustomDashLine
    assert len(_caneta(janela, por_camada).dashPattern()) == 4, "CENTER tem 4 elementos"
    assert len(_caneta(janela, propria).dashPattern()) == 2, "DASHED tem 2"


def test_desselecionar_nao_apaga_o_tracejado():
    """A caneta de seleção substitui a do item; ao desselecionar, a de base é
    refeita a partir do que ficou guardado NO item. Sem guardar o tipo de
    linha ali, um clique na linha de eixo a deixava contínua até recarregar."""
    app = _app()
    janela = MainWindow()
    janela.document.linetypes["CENTER"] = LineType(name="CENTER", pattern=CENTER, length=5.08)
    janela.document.add_layer("EIXO").linetype = "CENTER"
    linha = janela.document.add_entity(Line(layer="EIXO", start=Point(0, 0), end=Point(10, 0)))
    janela.canvas.refresh_entities()
    app.processEvents()
    antes = list(_caneta(janela, linha).dashPattern())

    janela.interpreter.context.selection.ids = [linha.id]
    janela.canvas.refresh_selection_highlight()
    app.processEvents()
    janela.interpreter.context.selection.ids = []
    janela.canvas.refresh_selection_highlight()
    app.processEvents()

    depois = _caneta(janela, linha)
    assert depois.style() == Qt.PenStyle.CustomDashLine
    assert [round(v, 4) for v in depois.dashPattern()] == [round(v, 4) for v in antes]
