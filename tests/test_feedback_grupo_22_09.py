"""Correções vindas do feedback do grupo do NewSicad de 22/09/2026 (Michael
Albert), testadas no arquivo de referência que ele mandou (NEWSI-TEMPLATE-
LEG_R00): abreviação de opção no prompt, seta/máscara das anotações
importadas, edição do texto dentro delas, FILLET, LEADER e o painel de
Propriedades editável."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter, match_option, option_keyword
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import (
    ANNOTATION_BLOCK_PREFIXES,
    Arc,
    BlockReference,
    Hatch,
    Line,
    Point,
    Text,
    is_annotation_block,
)
from newsicad.core.selection import Selection


def make_interpreter() -> tuple[CommandInterpreter, Document]:
    doc = Document()
    ctx = CommandContext(document=doc, selection=Selection())
    return CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES), doc


# ---------------------------------------------------------------- opções
@pytest.mark.parametrize(
    "option, keyword",
    [("Undo", "U"), ("Close", "C"), ("Radius", "R"), ("eXit", "X"), ("DElta", "DE"),
     ("Add vertex", "A"), ("First point", "F"), ("XY", "XY")],
)
def test_abreviacao_da_opcao_e_a_maiuscula(option, keyword):
    assert option_keyword(option) == keyword
    assert match_option(keyword, [option]) == option
    assert match_option(option.lower(), [option]) == option


def test_prefixo_so_vale_quando_e_unico():
    opcoes = ["Rectangular", "Polar"]
    assert match_option("REC", opcoes) == "Rectangular"
    assert match_option("P", opcoes) == "Polar"
    opcoes = ["eXit", "eDit"]
    assert match_option("X", opcoes) == "eXit"  # a maiúscula resolve
    assert match_option("E", opcoes) is None  # prefixo ambíguo não escolhe


def test_prompt_de_texto_nao_aceita_prefixo():
    # "e" numa célula de TABLE é a letra "e", não o começo de "eXit".
    assert match_option("e", ["eXit"], allow_prefix=False) is None
    assert match_option("X", ["eXit"], allow_prefix=False) == "eXit"


def test_undo_da_line_pela_letra_u():
    interp, doc = make_interpreter()
    interp.start("LINE")
    interp.submit_point(Point(0, 0))
    interp.submit_point(Point(10, 0))
    assert len(doc.entities) == 1
    interp.submit_text("U")  # antes caía no parser de coordenada
    assert len(doc.entities) == 0
    assert "inválid" not in interp.log[-1].lower()


# ---------------------------------------------------------------- FILLET
def _duas_linhas(doc: Document) -> tuple[Line, Line]:
    a = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    b = doc.add_entity(Line(start=Point(20, 10), end=Point(20, 30)))
    return a, b


def test_fillet_com_raio_zero_fecha_o_canto():
    """Raio 0 é o padrão do AutoCAD: estende/apara as duas linhas até o
    canto, sem criar arco nenhum."""
    interp, doc = make_interpreter()
    a, b = _duas_linhas(doc)
    interp.start("FILLET")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(20, 20))
    assert not interp.active
    assert not any(isinstance(e, Arc) for e in doc.entities.values())
    assert a.end.x == pytest.approx(20) and a.end.y == pytest.approx(0)
    assert b.start.x == pytest.approx(20) and b.start.y == pytest.approx(0)


def test_fillet_com_raio_pela_letra_r_cria_o_arco():
    interp, doc = make_interpreter()
    _duas_linhas(doc)
    interp.start("FILLET")
    interp.submit_text("R")  # abreviação de [Radius]
    interp.submit_text("2")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(20, 20))
    arcos = [e for e in doc.entities.values() if isinstance(e, Arc)]
    assert len(arcos) == 1
    assert arcos[0].radius == pytest.approx(2)


def test_fillet_lembra_o_raio_da_vez_anterior():
    interp, doc = make_interpreter()
    _duas_linhas(doc)
    interp.start("FILLET")
    interp.submit_text("R")
    interp.submit_text("3")
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(20, 20))
    assert doc.fillet_radius == pytest.approx(3)

    doc.entities.clear()
    _duas_linhas(doc)
    interp.start("FILLET")
    assert "3" in interp.current_prompt.message  # mostra o raio atual
    interp.submit_point(Point(5, 0))
    interp.submit_point(Point(20, 20))
    arcos = [e for e in doc.entities.values() if isinstance(e, Arc)]
    assert len(arcos) == 1 and arcos[0].radius == pytest.approx(3)


# --------------------------------------------------- anotação importada
def _anotacao(doc: Document, nome: str = "*ML_ABC") -> BlockReference:
    doc.define_block(nome, [
        Text(insertion_point=Point(0, 0), content="CX. 20x20x10", height=0.5),
        Text(insertion_point=Point(0, -1), content="SOBRE O FORRO", height=0.5),
        Line(start=Point(0, 0), end=Point(-2, -2)),
    ])
    return doc.add_entity(BlockReference(block_name=nome, insertion_point=Point(0, 0)))


def test_prefixos_de_anotacao_sao_reconhecidos():
    for prefixo in ANNOTATION_BLOCK_PREFIXES:
        assert is_annotation_block(f"{prefixo}1A2B")
    assert not is_annotation_block("Audio_Central")
    assert not is_annotation_block("*U143")  # bloco anônimo comum, não anotação


def test_ddedit_edita_o_texto_dentro_da_anotacao_importada():
    interp, doc = make_interpreter()
    ref = _anotacao(doc)
    interp.start("DDEDIT")
    interp.context.selection.add(ref.id)
    interp.submit_text("")  # encerra a seleção
    interp.submit_text("CX. 30x30x15")
    interp.submit_text("")  # Enter mantém a segunda linha
    assert not interp.active
    partes = doc.get_block_definition("*ML_ABC")
    assert [p.content for p in partes if isinstance(p, Text)] == ["CX. 30x30x15", "SOBRE O FORRO"]


def test_ddedit_em_bloco_comum_continua_recusando():
    interp, doc = make_interpreter()
    ref = _anotacao(doc, nome="Audio_Central")
    interp.start("DDEDIT")
    interp.context.selection.add(ref.id)
    interp.submit_text("")
    assert not interp.active
    assert "nenhum texto" in interp.log[-1].lower()


# ------------------------------------------------- painel de Propriedades
@pytest.fixture
def janela():
    from PySide6.QtWidgets import QApplication

    from newsicad.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    # Sem close(): o resto da suíte de UI segue a mesma convenção (ver
    # tests/test_layer_panel.py) — fechar a janela no teardown trava o Qt
    # offscreen quando há evento adiado pendente.
    return MainWindow()


def _linhas_editaveis(panel) -> dict:
    """{rótulo: widget} das linhas do painel que têm campo editável."""
    from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

    campos = {}
    for i in range(panel.body_layout.count()):
        widget = panel.body_layout.itemAt(i).widget()
        if widget is None:
            continue
        labels = widget.findChildren(QLabel)
        editaveis = widget.findChildren(QLineEdit) + widget.findChildren(QComboBox)
        if labels and editaveis:
            campos[labels[0].text()] = editaveis[0]
    return campos


def test_propriedades_edita_a_altura_do_texto_de_uma_cota(janela):
    from newsicad.core.entities import Dimension

    doc = janela.document
    dim = doc.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0), dim_line_point=Point(0, 2))
    )
    janela.selection.set({dim.id})
    janela._refresh_properties_panel()
    campos = _linhas_editaveis(janela.properties_dock)
    assert "Altura do texto" in campos  # antes o painel era só de leitura

    campo = campos["Altura do texto"]
    campo.setText("0.25")
    campo.editingFinished.emit()
    assert dim.text_height == pytest.approx(0.25)
    # ...e o desenho inteiro não foi junto
    assert doc.dim_style.text_height != pytest.approx(0.25)


def test_propriedades_edita_o_conteudo_de_um_texto(janela):
    doc = janela.document
    texto = doc.add_entity(Text(insertion_point=Point(0, 0), content="ANTES", height=1.0))
    janela.selection.set({texto.id})
    janela._refresh_properties_panel()
    campo = _linhas_editaveis(janela.properties_dock)["Conteúdo"]
    campo.setText("DEPOIS")
    campo.editingFinished.emit()
    assert texto.content == "DEPOIS"


def test_altura_propria_da_cota_sobrevive_ao_salvar_e_reabrir(tmp_path):
    from newsicad.core.entities import Dimension
    from newsicad.io.dxf_io import load_dxf, save_dxf

    doc = Document()
    doc.add_entity(
        Dimension(kind="linear", point1=Point(0, 0), point2=Point(10, 0),
                  dim_line_point=Point(0, 2), text_height=0.25, arrow_size=0.08)
    )
    caminho = tmp_path / "cota.dxf"
    save_dxf(doc, caminho)
    lido, _ = load_dxf(caminho)
    cota = next(e for e in lido.entities.values() if isinstance(e, Dimension))
    assert cota.text_height == pytest.approx(0.25)
    assert cota.arrow_size == pytest.approx(0.08)
