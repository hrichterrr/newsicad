"""OLE2FRAME: a moldura do objeto OLE colado, que era descartada inteira.

Achado da varredura da base em 01/10/2026. O OLE2FRAME é o objeto
incorporado — planilha do Excel, imagem colada de outro programa — e era o
tipo não lido mais espalhado: 143 entidades em 32 arquivos (11 pastas de
projeto). Sumia da tela E do arquivo entregue ao cliente. Os casos medidos:

    4.0_ELÉTRICA_LEE CHUO CHIA (Joe Lee)       20 OLE2FRAME, um por prancha
    6644-FLE04-LO-DUG-H_M-R00 (Escritório H&M) 13 (6 em prancha, 7 em bloco —
                                               o carimbo, com 3 planilhas)
    6644-FLE05-LO-DUG-H_M-R00                  14

A SUTILEZA que custou uma volta de medição: os grupos 10/11 (os dois cantos
do retângulo) que o `dwg2dxf` grava são SEMPRE o mesmo par — (30,136; -18,989)
e (35,272; -22,393), 14 casas iguais em 9 arquivos de 8 projetos, com
objetos de 9 KB a 13 MB. Ler esses cantos punha toda moldura no mesmo lugar
errado. O retângulo de verdade mora nos 98 primeiros bytes do conteúdo
binário — conferido contra o ODA File Converter, que decodifica o .dwg por
conta própria: 51 de 51 OLE2FRAME coincidem até a última casa decimal. E o
ODA OBEDECE a esse preâmbulo, não aos grupos 10/11: uma moldura movida só nos
grupos 10/11 voltava ao lugar antigo ao passar pelo ODA.
"""

from __future__ import annotations

import os
import pickle
import struct
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import pytest  # noqa: E402
from ezdxf.lldxf.tags import Tags  # noqa: E402
from ezdxf.lldxf.types import DXFBinaryTag, DXFTag, DXFVertex  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import OleFrame, Point  # noqa: E402
from newsicad.io import dxf_io  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402

#: Os cantos que o `dwg2dxf` grava em TODO OLE2FRAME (valor padrão, não geometria).
FIXO_10 = (30.13602472538446, -18.98882829402869)
FIXO_11 = (35.27188116753285, -22.39344715050545)

#: O retângulo real da moldura do arquivo do Joe Lee (como o ODA o lê do .dwg).
X0, Y1 = 802.4224823303149, 18.00955470096021       # esquerda-cima
X1, Y0 = 824.4705700677296, -5.994038149653946      # direita-baixo


def _conteudo_ole(x0=X0, y1=Y1, x1=X1, y0=Y0, tamanho=4096, cabecalho=b"\x81\x55") -> bytes:
    """Conteúdo binário na forma medida nos 51 objetos reais: 2 bytes de
    cabeçalho, os 4 cantos (esquerda-cima, direita-cima, direita-baixo,
    esquerda-baixo) em double x,y,z=0, e o arquivo composto do Windows
    (D0CF11E0A1B11AE1) no byte 128."""
    cantos = struct.pack("<12d", x0, y1, 0.0, x1, y1, 0.0, x1, y0, 0.0, x0, y0, 0.0)
    miolo = bytes(128 - len(cabecalho) - len(cantos))
    assinatura = bytes.fromhex("d0cf11e0a1b11ae1")
    corpo = bytes((i * 7) % 251 for i in range(tamanho - 128 - len(assinatura)))
    return cabecalho + cantos + miolo + assinatura + corpo


def _poe_ole2frame(layout, dados: bytes, c10=FIXO_10, c11=FIXO_11, layer="0") -> None:
    """Grava um OLE2FRAME como o `dwg2dxf` grava: grupos 3 ("OLE"), 10/11,
    71, 72, 73, 90 e o conteúdo em linhas 310."""
    quadro = layout.new_entity("OLE2FRAME", dxfattribs={"layer": layer})
    marcas = [
        DXFTag(100, "AcDbOle2Frame"), DXFTag(70, 2), DXFTag(3, "OLE"),
        DXFVertex(10, (*c10, 0.0)), DXFVertex(11, (*c11, 0.0)),
        DXFTag(71, 2), DXFTag(72, 0), DXFTag(73, 2), DXFTag(90, len(dados)),
    ]
    marcas += [DXFBinaryTag(310, dados[i:i + 127]) for i in range(0, len(dados), 127)]
    marcas.append(DXFTag(1, "OLE"))
    quadro.acdb_ole2frame = Tags(marcas)


def _abre(dxf_doc):
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "ole.dxf"
        dxf_doc.saveas(caminho)
        return load_dxf(caminho)


def _quadros(documento) -> list[OleFrame]:
    achados = [e for e in documento.entities.values() if isinstance(e, OleFrame)]
    for prancha in documento.layouts.values():
        achados += [e for e in prancha.values() if isinstance(e, OleFrame)]
    for definicao in documento.block_definitions.values():
        achados += [e for e in definicao if isinstance(e, OleFrame)]
    return achados


def _entrega(documento):
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "entregue.dxf"
        save_dxf(documento, caminho)
        return ezdxf.readfile(caminho)


def _ole_do_arquivo(dxf_doc) -> list:
    return [e for e in dxf_doc.entitydb.values() if e.dxftype() == "OLE2FRAME"]


# --------------------------------------------------------------------------- #
# leitura
# --------------------------------------------------------------------------- #

def test_le_a_moldura_no_lugar_do_preambulo_e_nao_nos_cantos_fixos_do_dwg2dxf():
    """O caso do arquivo do Joe Lee: o .dxf do `dwg2dxf` traz os cantos
    FIXOS nos grupos 10/11, e a moldura de verdade está no conteúdo."""
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), _conteudo_ole(), layer="ELE-PLANILHA")

    documento, descartadas = _abre(doc)

    assert not dict(getattr(descartadas, "by_type", {})), "OLE2FRAME não pode mais contar como perdido"
    (quadro,) = _quadros(documento)
    assert quadro.layer == "ELE-PLANILHA"
    assert (quadro.insertion_point.x, quadro.insertion_point.y) == (X0, Y0)
    assert quadro.width == pytest.approx(X1 - X0)        # 22,048…
    assert quadro.height == pytest.approx(Y1 - Y0)       # 24,003…
    # e longe do lugar falso: a moldura NÃO pode cair no canto (30,1; -19,0)
    assert abs(quadro.insertion_point.x - FIXO_10[0]) > 700


def test_sem_preambulo_legivel_usa_os_cantos_do_dxf_do_autocad():
    """Num .dxf do AutoCAD ou do ODA os grupos 10/11 estão certos (o ODA
    escreve exatamente o que o preâmbulo diz). Se o conteúdo não tem a forma
    conhecida, valem eles."""
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), b"\x00" * 300, c10=(100.0, 50.0), c11=(160.0, 20.0))

    documento, _ = _abre(doc)

    (quadro,) = _quadros(documento)
    assert (quadro.insertion_point.x, quadro.insertion_point.y) == (100.0, 20.0)
    assert (quadro.width, quadro.height) == (60.0, 30.0)


def test_sem_preambulo_e_com_o_valor_fixo_nao_inventa_moldura_no_canto_errado():
    """Uma moldura no lugar errado é pior que nenhuma: sem preâmbulo legível e
    com o par fixo do `dwg2dxf`, o OLE2FRAME continua contando como perdido."""
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), b"\x00" * 300)   # cantos FIXOS

    documento, descartadas = _abre(doc)

    assert not _quadros(documento)
    assert dict(descartadas.by_type) == {"OLE2FRAME": 1}


@pytest.mark.parametrize("estraga", ["z", "assinatura", "curto", "nan"])
def test_preambulo_fora_da_forma_medida_nao_e_aceito(estraga):
    dados = bytearray(_conteudo_ole())
    if estraga == "z":
        struct.pack_into("<d", dados, 2 + 16, 5.0)         # z do primeiro canto != 0
    elif estraga == "assinatura":
        dados[128:136] = bytes(8)                          # sem o arquivo composto
    elif estraga == "curto":
        dados = dados[:60]
    elif estraga == "nan":
        struct.pack_into("<d", dados, 2, float("nan"))
    assert dxf_io._retangulo_do_preambulo_ole(bytes(dados)) is None


def test_vinte_quadros_iguais_dividem_uma_copia_do_objeto():
    """O arquivo do Joe Lee tem 20 OLE2FRAME — um por prancha, TODOS o mesmo
    objeto de 411.776 bytes. Cada entidade guarda só a chave."""
    doc = ezdxf.new("R2010")
    objeto = _conteudo_ole(tamanho=411_776)
    for n in range(20):
        _poe_ole2frame(doc.layouts.new(f"4.{n} PRANCHA"), objeto)

    documento, descartadas = _abre(doc)

    quadros = _quadros(documento)
    assert len(quadros) == 20
    assert int(descartadas) == 0
    assert len(documento.ole_dados) == 1, "20 objetos idênticos = 1 cópia"
    assert len({q.ole_key for q in quadros}) == 1
    assert all(q.bruto is None for q in quadros), "o conteúdo não pode ficar pendurado na entidade"
    assert len(documento.layouts) == 20


def test_le_o_ole_dentro_de_bloco_como_o_carimbo_do_h_e_m():
    """No Escritório H&M o OLE2FRAME está DENTRO do bloco do carimbo (7 dos 13
    do FLE04: o carimbo com três planilhas, mais cópias anônimas)."""
    doc = ezdxf.new("R2010")
    carimbo = doc.blocks.new("CARIMBONOVO-PADRAO")
    _poe_ole2frame(carimbo, _conteudo_ole(-40.75481435462797, 178.081314916932,
                                          -13.59843565182007, 151.0561451674228))
    doc.modelspace().add_blockref("CARIMBONOVO-PADRAO", (0, 0))

    documento, descartadas = _abre(doc)

    (quadro,) = _quadros(documento)
    assert quadro in documento.block_definitions["CARIMBONOVO-PADRAO"]
    assert (round(quadro.insertion_point.x, 6), round(quadro.insertion_point.y, 6)) == (-40.754814, 151.056145)
    assert (round(quadro.width, 6), round(quadro.height, 6)) == (27.156379, 27.02517)
    assert int(descartadas) == 0


# --------------------------------------------------------------------------- #
# gravação
# --------------------------------------------------------------------------- #

@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_devolve_o_objeto_no_arquivo_entregue_com_os_mesmos_bytes():
    """O compromisso com o cliente: ele reabre o que a gente entregou e o
    objeto continua lá, byte a byte — e o arquivo é válido."""
    objeto = _conteudo_ole(tamanho=20_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), objeto, layer="PLANILHA")
    documento, _ = _abre(doc)

    entregue = _entrega(documento)

    (ole,) = _ole_do_arquivo(entregue)
    assert ole.binary_data() == objeto
    assert ole.dxf.layer == "PLANILHA"
    tags = ole.acdb_ole2frame
    # 10/11 = esquerda-cima e direita-baixo, os valores REAIS (não os fixos)
    assert tuple(round(v, 9) for v in tags.get_first_value(10)[:2]) == (round(X0, 9), round(Y1, 9))
    assert tuple(round(v, 9) for v in tags.get_first_value(11)[:2]) == (round(X1, 9), round(Y0, 9))
    assert tags.get_first_value(90) == len(objeto)
    assert not list(entregue.audit().errors)


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_linhas_de_conteudo_cabem_no_limite_do_formato():
    """310 com o objeto inteiro numa linha só (13 MB num único valor) é DXF
    inválido; o AutoCAD grava 127 bytes por linha."""
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), _conteudo_ole(tamanho=50_000))
    documento, _ = _abre(doc)
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "entregue.dxf"
        save_dxf(documento, caminho)
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    comprimentos = [len(linhas[i + 1]) for i in range(0, len(linhas) - 1, 2) if linhas[i].strip() == "310"]
    assert comprimentos and max(comprimentos) <= 254


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_moldura_movida_leva_o_preambulo_junto():
    """O ODA obedece ao preâmbulo do conteúdo, não aos grupos 10/11: movida só
    em 10/11, a moldura voltava ao lugar antigo (medido passando o .dxf
    entregue por DXF -> DWG -> DXF no ODA). Aqui o preâmbulo acompanha — e o
    resto do objeto fica intacto."""
    objeto = _conteudo_ole(tamanho=20_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), objeto)
    documento, _ = _abre(doc)
    (quadro,) = _quadros(documento)

    quadro.insertion_point = Point(quadro.insertion_point.x + 100.0, quadro.insertion_point.y + 50.0)
    quadro.width *= 2

    entregue = _entrega(documento)

    (ole,) = _ole_do_arquivo(entregue)
    gravado = ole.binary_data()
    x0, y0 = X0 + 100.0, Y0 + 50.0
    esperado = (x0, y0, x0 + 2 * (X1 - X0), y0 + (Y1 - Y0))
    lido = dxf_io._retangulo_do_preambulo_ole(gravado)
    assert lido == pytest.approx(esperado)
    assert tuple(ole.acdb_ole2frame.get_first_value(10)[:2]) == pytest.approx((esperado[0], esperado[3]))
    assert tuple(ole.acdb_ole2frame.get_first_value(11)[:2]) == pytest.approx((esperado[2], esperado[1]))
    assert gravado[98:] == objeto[98:], "só o preâmbulo muda; o objeto do Windows fica como veio"
    assert len(gravado) == len(objeto)


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_quadro_sem_moldura_movida_regrava_os_bytes_intactos():
    """Sem mexer, nem um byte do preâmbulo muda (a conta dos cantos não pode
    introduzir ruído de ponto flutuante)."""
    objeto = _conteudo_ole(tamanho=5_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), objeto)
    documento, _ = _abre(doc)

    (ole,) = _ole_do_arquivo(_entrega(documento))

    assert ole.binary_data() == objeto


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_ole_em_prancha_e_em_bloco_volta_para_o_mesmo_lugar():
    objeto = _conteudo_ole(tamanho=8_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.layouts.new("4.0 ELETRICA"), objeto)
    _poe_ole2frame(doc.blocks.new("CARIMBO"), objeto)
    documento, _ = _abre(doc)

    entregue = _entrega(documento)

    onde = {}
    for lay in entregue.layouts:
        onde[lay.name] = [e.dxftype() for e in lay if e.dxftype() == "OLE2FRAME"]
    assert onde["4.0 ELETRICA"] == ["OLE2FRAME"]
    assert [e.dxftype() for e in entregue.blocks.get("CARIMBO") if e.dxftype() == "OLE2FRAME"] == ["OLE2FRAME"]
    assert len(_ole_do_arquivo(entregue)) == 2


def test_quadro_sem_o_objeto_nao_grava_moldura_vazia():
    """Um OleFrame colado de OUTRO desenho (onde `ole_dados` não veio junto)
    não pode virar um OLE2FRAME sem conteúdo — nem derrubar a gravação."""
    documento = Document()
    documento.add_entity(OleFrame(insertion_point=Point(0, 0), width=10, height=5, ole_key="que-nao-existe"))

    entregue = _entrega(documento)

    assert not _ole_do_arquivo(entregue)


# --------------------------------------------------------------------------- #
# o resto do programa
# --------------------------------------------------------------------------- #

def test_desfazer_nao_fotografa_o_objeto():
    """Cada comando fotografa as entidades. Com o objeto de 411 KB dentro da
    entidade, 20 quadros somariam 8 MB POR PASSO do desfazer."""
    doc = ezdxf.new("R2010")
    for n in range(20):
        _poe_ole2frame(doc.layouts.new(f"P{n}"), _conteudo_ole(tamanho=411_776))
    documento, _ = _abre(doc)
    for q in _quadros(documento):
        documento.entities[q.id] = q       # como se estivessem no desenho

    foto = pickle.dumps(documento.entities, protocol=pickle.HIGHEST_PROTOCOL)

    assert len(foto) < 20_000, f"a foto do desfazer tem {len(foto)} bytes — o objeto vazou para a entidade"


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_cache_de_abertura_preserva_o_objeto():
    """O cache guarda o Document em pickle; uma abertura vinda do cache tem de
    gravar o objeto igual à que veio do arquivo."""
    objeto = _conteudo_ole(tamanho=9_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.modelspace(), objeto)
    documento, _ = _abre(doc)

    do_cache = pickle.loads(pickle.dumps(documento, protocol=pickle.HIGHEST_PROTOCOL))

    (ole,) = _ole_do_arquivo(_entrega(do_cache))
    assert ole.binary_data() == objeto


def test_painel_de_propriedades_diz_que_e_objeto_ole():
    from newsicad.ui.properties_panel import _geometry_fields

    campos = dict(_geometry_fields(OleFrame(insertion_point=Point(0, 0), width=22.05, height=24.0)))

    assert "Arquivo" not in campos, "não há arquivo de imagem — o painel não pode mostrar um nome vazio"
    assert campos["Objeto"].startswith("OLE")


def test_canvas_desenha_a_moldura_e_ela_e_selecionavel():
    from PySide6.QtWidgets import QApplication, QGraphicsRectItem

    from newsicad.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    quadro = window.document.add_entity(
        OleFrame(insertion_point=Point(X0, Y0), width=X1 - X0, height=Y1 - Y0)
    )
    window.canvas.refresh_entities()
    app.processEvents()

    item = window.canvas._entity_items[quadro.id]
    assert isinstance(item, QGraphicsRectItem), "a moldura é o retângulo tracejado, sem tentar abrir imagem"
    assert item.rect().width() == pytest.approx(X1 - X0)
    assert item.rect().height() == pytest.approx(Y1 - Y0)
    # um clique em cima da borda esquerda acerta a moldura; longe dela, nada
    assert window.canvas._hit_test(Point(X0, (Y0 + Y1) / 2)) == quadro.id
    assert window.canvas._hit_test(Point(X0 - 500, Y0 - 500)) is None


@pytest.mark.skip(
    reason="gravação do binário OLE desligada por decisão de tamanho em "
           "04/10/2026 — o arquivo entregue ia de 1,0 MB para 78,3 MB. "
           "O teste fica aqui, dormente, para voltar junto se a decisão "
           "mudar; ver `_escreve_ole` em dxf_io.py."
)
def test_abrir_e_salvar_pela_janela_devolve_o_objeto():
    """O caminho de verdade do projetista: File > Open e File > Save As. A
    janela copia o Document lido para a aba — se `ole_dados` não for copiado
    junto, o quadro aparece na tela e SOME do arquivo entregue."""
    from unittest.mock import patch

    from PySide6.QtWidgets import QApplication

    from newsicad.ui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    objeto = _conteudo_ole(tamanho=12_000)
    doc = ezdxf.new("R2010")
    _poe_ole2frame(doc.layouts.new("4.0 ELETRICA"), objeto)
    _poe_ole2frame(doc.blocks.new("CARIMBO"), objeto)

    with tempfile.TemporaryDirectory() as tmp:
        origem, destino = Path(tmp) / "cliente.dxf", Path(tmp) / "entregue.dxf"
        doc.saveas(origem)
        window = MainWindow()
        with patch("newsicad.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(origem), "DXF (*.dxf)")):
            window._open_file()
        assert len(window.document.ole_dados) == 1
        with patch("newsicad.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(destino), "DXF (*.dxf)")):
            window._save_file_as()
        entregue = ezdxf.readfile(destino)

    assert [o.binary_data() for o in _ole_do_arquivo(entregue)] == [objeto, objeto]


def test_o_arquivo_entregue_nao_engorda_com_o_binario_do_ole():
    """A decisão de 04/10/2026, virada em teste.

    O objeto OLE vem como binário dentro do .dxf, que o formato guarda em
    hexadecimal — preservá-lo levava o arquivo entregue do Escritório H&M de
    1,0 MB para 78,3 MB (um Excel de 13 MB dentro do carimbo) e o do Joe Lee
    de 3,3 MB para 20,3 MB. A MOLDURA continua sendo lida e aparece na tela
    no lugar certo; o conteúdo não volta ao arquivo, exatamente como era
    antes deste trabalho.

    Se alguém religar a gravação sem rever a decisão, este teste cai.
    """
    import tempfile
    from pathlib import Path

    from newsicad.core.document import Document
    from newsicad.core.entities import OleFrame, Point
    from newsicad.io.dxf_io import save_dxf

    documento = Document()
    documento.add_entity(
        OleFrame(insertion_point=Point(0, 0), width=10, height=5, ole_key="k")
    )
    documento.ole_dados["k"] = type(
        "Fake", (), {"dados": b"X" * 2_000_000, "tipo": 2, "modo": 0}
    )()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        caminho = Path(tmp) / "entregue.dxf"
        save_dxf(documento, caminho)
        tamanho = caminho.stat().st_size
        texto = caminho.read_text(encoding="utf-8", errors="replace")

    assert "OLE2FRAME" not in texto, "o binário do OLE não pode voltar ao arquivo"
    assert tamanho < 200_000, (
        f"o arquivo entregue ficou com {tamanho} bytes — os 2 MB de binário vazaram"
    )
