"""Correções vindas do feedback do grupo do NewSicad de 22/09/2026 (Michael
Albert), testadas no arquivo de referência que ele mandou (NEWSI-TEMPLATE-
LEG_R00): abreviação de opção no prompt, seta/máscara das anotações
importadas, edição do texto dentro delas, FILLET, LEADER e o painel de
Propriedades editável."""

from __future__ import annotations

import math
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


def test_preview_do_arc_mostra_o_arco_e_nao_uma_reta():
    """Com os dois primeiros pontos dados, o arco que passa por eles e pelo
    cursor já está determinado — o preview mostra ele, não a corda. Antes o
    arco só aparecia no terceiro clique ("a marcação do ARC demora muito
    para aparecer", 22/09/2026)."""
    from PySide6.QtWidgets import QApplication

    from newsicad.ui.canvas import CanvasView, cad_to_scene

    QApplication.instance() or QApplication([])
    interp, doc = make_interpreter()
    canvas = CanvasView(doc, interp)
    interp.start("ARC")
    for ponto in (Point(0, 0), Point(5, 5)):
        interp.submit_point(ponto)
    canvas._update_preview(Point(10, 0))

    caminho = canvas._preview_path
    assert caminho is not None and not caminho.isEmpty()
    # Um arco de raio 5 centrado em (5,0) passa por (5,5); uma reta de (0,0)
    # a (10,0) não passaria nem perto.
    topo = cad_to_scene(Point(5, 5))
    assert any(
        abs(caminho.elementAt(i).x - topo.x()) < 0.2 and abs(caminho.elementAt(i).y - topo.y()) < 0.2
        for i in range(caminho.elementCount())
    )


def test_propriedades_mostra_e_edita_os_atributos_do_bloco(janela):
    """Selecionar o bloco tem que mostrar os campos preenchíveis que vieram
    do ATTRIB do .dwg (TÍTULO, ESCALA, CIRCUITO...) — feedback de
    22/09/2026, "blocos extraídos sem suas respectivas propriedades"."""
    doc = janela.document
    doc.define_block("TABELA DE ICONS", [Line(start=Point(0, 0), end=Point(1, 0))])
    etiqueta = Text(insertion_point=Point(0, 0), content="ÁUDIO", height=0.25, attrib_tag="TÍTULO")
    ref = doc.add_entity(
        BlockReference(block_name="TABELA DE ICONS", insertion_point=Point(0, 0), attributes=[etiqueta])
    )
    janela.selection.set({ref.id})
    janela._refresh_properties_panel()
    campos = _linhas_editaveis(janela.properties_dock)
    assert "TÍTULO" in campos

    campo = campos["TÍTULO"]
    campo.setText("VÍDEO")
    campo.editingFinished.emit()
    assert etiqueta.content == "VÍDEO"


def test_atributo_do_dwg_chega_com_a_tag_e_o_dono():
    """Na importação, cada ATTRIB vira um Text carimbado com o nome do campo
    e o id do bloco que o trouxe."""
    import ezdxf

    from newsicad.io.dxf_io import load_dxf

    doc = ezdxf.new(setup=True)
    bloco = doc.blocks.new("TAG-CIRCUITO")
    bloco.add_attdef("CIRCUITO", (0, 0), height=1.8)
    msp = doc.modelspace()
    insert = msp.add_blockref("TAG-CIRCUITO", (0, 0))
    insert.add_auto_attribs({"CIRCUITO": "C-12"})
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        caminho = f"{tmp}/attr.dxf"
        doc.saveas(caminho)
        lido, _ = load_dxf(caminho)

    ref = next(e for e in lido.entities.values() if isinstance(e, BlockReference))
    assert not [e for e in lido.entities.values() if isinstance(e, Text)]  # não solta no desenho
    etiqueta = ref.attributes[0]
    assert etiqueta.content == "C-12"
    assert etiqueta.attrib_tag == "CIRCUITO"


# --------------------------------------------- atributo de volta no .dxf
def _dwg_com_atributo(caminho):
    """Um .dxf mínimo com um bloco que tem um campo preenchível, como o
    selo e a legenda do template da New SI."""
    import ezdxf

    doc = ezdxf.new(setup=True)
    bloco = doc.blocks.new("TABELA DE ICONS")
    bloco.add_line((0, 0), (10, 0))
    bloco.add_attdef("TÍTULO", (1, 1), height=0.25, dxfattribs={"prompt": "Nome da seção"})
    insert = doc.modelspace().add_blockref("TABELA DE ICONS", (0, 0))
    insert.add_auto_attribs({"TÍTULO": "ÁUDIO"})
    doc.saveas(caminho)


def test_atributo_editado_volta_como_attrib_de_verdade(tmp_path):
    """Antes da 2.16.1 todo atributo saía como texto comum: o campo
    funcionava dentro do NewSIcad, mas ao reabrir no AutoCAD deixava de ser
    preenchível e virava um texto solto por cima do símbolo."""
    import ezdxf

    from newsicad.io.dxf_io import load_dxf, save_dxf

    origem = tmp_path / "origem.dxf"
    _dwg_com_atributo(str(origem))
    doc, _ = load_dxf(origem)

    ref = next(e for e in doc.entities.values() if isinstance(e, BlockReference))
    etiqueta = ref.attributes[0]
    assert etiqueta.content == "ÁUDIO"
    etiqueta.content = "VÍDEO"  # a edição que o painel/duplo clique faz

    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravado = ezdxf.readfile(saida)

    inserts = [e for e in gravado.modelspace() if e.dxftype() == "INSERT"]
    assert len(inserts) == 1
    attribs = [(a.dxf.tag, a.dxf.text) for a in inserts[0].attribs]
    assert attribs == [("TÍTULO", "VÍDEO")]
    # e o valor NÃO saiu também como texto solto ao lado
    assert not [e for e in gravado.modelspace() if e.dxftype() in ("TEXT", "MTEXT")]


def test_molde_do_atributo_volta_para_dentro_do_bloco(tmp_path):
    """Sem o ATTDEF de volta na definição, os ATTRIBs ficam órfãos: o
    AutoCAD perde os campos no primeiro ATTSYNC e inserir uma cópia nova do
    bloco deixa de perguntar os valores."""
    import ezdxf

    from newsicad.io.dxf_io import load_dxf, save_dxf

    origem = tmp_path / "origem.dxf"
    _dwg_com_atributo(str(origem))
    doc, _ = load_dxf(origem)
    assert [a.tag for a in doc.block_attdefs["TABELA DE ICONS"]] == ["TÍTULO"]

    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravado = ezdxf.readfile(saida)
    bloco = gravado.blocks.get("TABELA DE ICONS")
    attdefs = [e for e in bloco if e.dxftype() == "ATTDEF"]
    assert [(a.dxf.tag, a.dxf.prompt) for a in attdefs] == [("TÍTULO", "Nome da seção")]


def test_apagar_o_bloco_leva_a_etiqueta_junto(tmp_path):
    """A etiqueta é filha da instância: apagar o bloco apaga o campo com
    ele, em vez de deixar um texto órfão flutuando na planta."""
    import ezdxf

    from newsicad.io.dxf_io import load_dxf, save_dxf

    origem = tmp_path / "origem.dxf"
    _dwg_com_atributo(str(origem))
    doc, _ = load_dxf(origem)
    ref = next(e for e in doc.entities.values() if isinstance(e, BlockReference))
    doc.remove_entity(ref.id)

    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravado = ezdxf.readfile(saida)
    # Sem o bloco, a etiqueta vai junto — ela é parte dele, não um texto solto.
    assert not [e for e in gravado.modelspace() if e.dxftype() in ("TEXT", "MTEXT")]
    assert not [e for e in gravado.modelspace() if e.dxftype() == "INSERT"]


# ------------------------------------- etiqueta amarrada de verdade no bloco
def _doc_com_bloco_atributado() -> tuple[Document, BlockReference, Text]:
    doc = Document()
    doc.define_block("TAG", [Line(start=Point(0, 0), end=Point(2, 0))])
    etiqueta = Text(insertion_point=Point(1, 1), content="C-12", height=0.5, attrib_tag="CIRCUITO")
    ref = doc.add_entity(BlockReference(block_name="TAG", insertion_point=Point(10, 20), attributes=[etiqueta]))
    return doc, ref, etiqueta


def test_mover_o_bloco_leva_a_etiqueta():
    """O pedido do Hamilton em 22/09/2026: amarrar a etiqueta no bloco. A
    etiqueta vive em coordenadas DO BLOCO, então mover a instância já a
    carrega — nenhum comando precisa saber que ela existe."""
    from newsicad.core.geometry_ops import attribute_to_world, translate_entity

    doc, ref, etiqueta = _doc_com_bloco_atributado()
    antes = attribute_to_world(etiqueta, ref)
    assert antes.insertion_point.as_tuple() == (11, 21)

    translate_entity(ref, 5, -3)
    depois = attribute_to_world(etiqueta, ref)
    assert depois.insertion_point.as_tuple() == (16, 18)
    # e a etiqueta não é uma entidade solta no desenho
    assert not [e for e in doc.entities.values() if isinstance(e, Text)]


def test_girar_e_escalar_o_bloco_levam_a_etiqueta():
    from newsicad.core.geometry_ops import attribute_to_world, rotate_entity, scale_entity

    doc, ref, etiqueta = _doc_com_bloco_atributado()
    rotate_entity(ref, Point(10, 20), math.pi / 2)
    mundo = attribute_to_world(etiqueta, ref)
    # (1,1) local girado 90° em torno do ponto de inserção -> (-1, 1)
    assert mundo.insertion_point.x == pytest.approx(9)
    assert mundo.insertion_point.y == pytest.approx(21)
    assert mundo.rotation == pytest.approx(math.pi / 2)

    doc2, ref2, etiqueta2 = _doc_com_bloco_atributado()
    scale_entity(ref2, Point(10, 20), 2.0)
    mundo2 = attribute_to_world(etiqueta2, ref2)
    assert mundo2.insertion_point.as_tuple() == (12, 22)
    assert mundo2.height == pytest.approx(1.0)  # 0,5 x 2


def test_copiar_o_bloco_duplica_a_etiqueta_com_id_proprio():
    from newsicad.core.geometry_ops import clone_entity, translate_entity

    _doc, ref, etiqueta = _doc_com_bloco_atributado()
    copia = clone_entity(ref)
    translate_entity(copia, 100, 0)
    assert copia.attributes[0].content == "C-12"
    assert copia.attributes[0].id != etiqueta.id
    copia.attributes[0].content = "C-99"
    assert etiqueta.content == "C-12"  # editar a cópia não mexe no original


def test_etiqueta_sobrevive_a_mover_salvar_e_reabrir(tmp_path):
    """O caso completo: abre, move o bloco, salva e reabre — a etiqueta tem
    que estar na posição nova, ainda como ATTRIB."""
    import ezdxf

    from newsicad.core.geometry_ops import translate_entity
    from newsicad.io.dxf_io import load_dxf, save_dxf

    origem = tmp_path / "origem.dxf"
    _dwg_com_atributo(str(origem))
    doc, _ = load_dxf(origem)
    ref = next(e for e in doc.entities.values() if isinstance(e, BlockReference))
    translate_entity(ref, 50, 30)

    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)

    gravado = ezdxf.readfile(saida)
    insert = next(e for e in gravado.modelspace() if e.dxftype() == "INSERT")
    attrib = insert.attribs[0]
    assert attrib.dxf.tag == "TÍTULO"
    # ATTDEF estava em (1,1) e o bloco foi de (0,0) para (50,30)
    assert attrib.dxf.insert.x == pytest.approx(51)
    assert attrib.dxf.insert.y == pytest.approx(31)

    de_novo, _ = load_dxf(saida)
    ref2 = next(e for e in de_novo.entities.values() if isinstance(e, BlockReference))
    assert ref2.insertion_point.as_tuple() == (50, 30)
    assert ref2.attributes[0].insertion_point.x == pytest.approx(1)
    assert ref2.attributes[0].insertion_point.y == pytest.approx(1)
