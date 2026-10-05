"""ACAD_TABLE que o `dwg2dxf` descarta: a posição vem do .dwg, não do .dxf.

Achado da varredura da base. O LibreDWG não traduz a entidade ACAD_TABLE:
avisa "Unhandled Class entity ... ACAD_TABLE" e não a escreve. O DESENHO da
tabela ele escreve (o bloco anônimo `*T…`, com linhas, fundos e textos
prontos), só que sem a entidade que o insere — a tabela sumia da tela e do
arquivo devolvido ao cliente.

Medido nos 218 projetos da base: 85 tabelas em 25 arquivos. O bloco `*T…` é
LOCAL (começa em 0,0 no canto superior esquerdo e desce em Y negativo; caixa
de (0; -187,3) a (146,4; 0) no Carla e Raymond), então sem a posição não há
como inseri-lo — e a posição não está no .dxf (nem no BLOCK, base 0,0,0, nem
no aviso). Está no .dwg, e só o log de rastreio do `dwg2dxf` (`-v3`) a deixa
sair: os bits crus da entidade começam com ponto de inserção, escala,
rotação e extrusão. As 9 tabelas dos 6 arquivos até 10 MB foram conferidas
contra uma segunda fonte do mesmo registro (a matriz do proxy graphics) e
batem exatamente:

    Carla e Raymond R06      1 tabela  prancha "03"   (396,24; 350,65)
    Alejandro e Andrea R07   2 tabelas pranchas "03" e outra
    Rafael e Marina R02      2 tabelas
    Joao e Brenda R00        1 tabela  modelspace     (5867,47; -3501,04)

Três armadilhas medidas que estes testes seguram:

* Alejandro e Andrea tem 4 blocos `*T` e só 2 tabelas vivas — os outros 2 são
  restos de tabelas apagadas. O elo certo é o `{BLKREFS` do BLOCK_RECORD, não
  "todo `*T` que ninguém insere".
* A tabela da JOÃO E BRENDA não tem `ownerhandle` no log (`entmode: 2` =
  modelspace). A primeira versão do leitor a perdia justamente por isso.
* A extrusão (0, 0, 1) que fecha o prefixo é a trava de sanidade: se a leitura
  sai do alinhamento, o número sai lixo e a posição é recusada em vez de
  inventada.
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import ezdxf
import pytest

from newsicad.core.entities import BlockReference
from newsicad.io import dwg_bridge
from newsicad.io.dwg_tabelas import (
    ExtratorDeTabelas,
    TabelaPerdida,
    blocos_das_tabelas,
    decodifica_insercao,
    le_registro_de_tabela,
)
from newsicad.io.dxf_io import load_dxf, save_dxf

# --------------------------------------------------------------------------- #
# Registros REAIS do log de rastreio (`dwg2dxf -v3`), com o binário do preview
# omitido e o hexa dos bits cortado nos primeiros 64 bytes (o resto não é lido).
# --------------------------------------------------------------------------- #
#: Carla e Raymond R06, a tabela da prancha "03".
BITS_CARLA = (
    "04155A0EFAB0DE100D4636DA755EA7540BA9005209481D06DA0D2073AEC6E81481D15C4D3C2B1A089A81481D18B24BE59F20A8281481D17CB1E5164BBE7C8091"
)
REGISTRO_CARLA = (
    "Unhandled Class entity 572 ACAD_TABLE (0x401) 74030/0\n"
    "Add entity UNKNOWN_ENT [74030] Decode entity UNKNOWN_ENT\n\n"
    " has_strings: 1\nhandle: 0.3.1420F8 [H 5]\n\nnum_eed: 0\n"
    "preview_exists: 1 [B 0]\npreview_size: 37000 [BLL 160]\n"
    'preview: "<binario omitido>" [TF 37000 310]\n'
    "entmode: 0 [BB 0]\nnum_reactors: 0 [BL 0]\ninvisible: 0 [BS 60]\n"
    "ownerhandle: (4.1.D6) abs:D6 [H 330]\n"
    "xdicobjhandle: (3.3.145950) abs:145950 [H 360]\n"
    "layer: (5.2.3AF) abs:3AF [H 8]\n"
    f"unknown_bits [332211 (296091,326574,56848) 41527 TF]: {BITS_CARLA}\n"
)
#: Joao e Brenda R00: sem `ownerhandle` — `entmode: 2` é o modelspace.
REGISTRO_JOAO = (
    "Unhandled Class entity 579 ACAD_TABLE (0x401) 47803/0\n"
    "Add entity UNKNOWN_ENT [47803] Decode entity UNKNOWN_ENT\n\n"
    " has_strings: 1\nhandle: 0.3.42311 [H 5]\n\nnum_eed: 0\n"
    "entmode: 2 [BB 0]\nnum_reactors: 0 [BL 0]\ninvisible: 0 [BS 60]\n"
    "xdicobjhandle: (3.3.8476F) abs:8476F [H 360]\n"
    "layer: (5.1.10) abs:10 [H 8]\n"
    "unknown_bits [69147 (87483,67800,21928) 8644 TF]: "
    "0AB48CE21E3AED900E83F38EE155AABC0BA9005205481D000A1EAB80E68A881481D00000000001809E8088205480A048100000000001016C81480A02832088D2080218"
)
#: Outra classe que o dwg2dxf também não traduz: não é tabela e não conta.
REGISTRO_OUTRA_CLASSE = (
    "Unhandled Class entity 600 AEC_DISP_PROPS_EDITINPLACEPROFILE_MODEL (0x401) 5/0\n"
    "handle: 0.3.99 [H 5]\nunknown_bits [8 (0,0,0) 1 TF]: FF\n"
)


def _log(*registros: str) -> bytes:
    """Monta um log de rastreio com lixo no meio, como o real."""
    partes = ["Warning: Unknown object, skipping eed/reactors/xdic\n", "crc: 1234 [RSx]\n"]
    for registro in registros:
        partes.append(registro)
        partes.append("\ncrc: E984 [RSx]\n check_CRC 78545: E984 == E984\n\n")
        partes.append("< Next object: 74031 =============\n")
    return "".join(partes).encode("latin-1")


# --------------------------------------------------------------------------- #
# Decodificação dos bits
# --------------------------------------------------------------------------- #
class _Escritor:
    """Escreve bits no formato do DWG, para montar casos que nenhum arquivo da
    base exercita (escala diferente de 1)."""

    def __init__(self) -> None:
        self.bits = ""

    def bd(self, valor: float) -> "_Escritor":
        if valor == 1.0:
            self.bits += "01"
        elif valor == 0.0:
            self.bits += "10"
        else:
            self.bits += "00" + "".join(f"{b:08b}" for b in struct.pack("<d", valor))
        return self

    def rd(self, valor: float) -> "_Escritor":
        self.bits += "".join(f"{b:08b}" for b in struct.pack("<d", valor))
        return self

    def cru(self, bits: str) -> "_Escritor":
        self.bits += bits
        return self

    def hexa(self) -> str:
        bits = self.bits + "0" * (-len(self.bits) % 8)
        return "".join(f"{int(bits[i : i + 8], 2):02X}" for i in range(0, len(bits), 8)) + "00" * 8


def test_decodifica_o_prefixo_real_da_tabela_do_carla_e_raymond():
    assert decodifica_insercao(BITS_CARLA) == (
        396.2446855617027,
        350.6459116242452,
        0.0,
        0.0,
        (1.0, 1.0, 1.0),
    )


def test_decodifica_o_prefixo_real_da_tabela_do_joao_e_brenda():
    x, y, z, rotacao, escala = decodifica_insercao(REGISTRO_JOAO.rsplit(": ", 1)[1].strip())
    assert (x, y, z) == (5867.470828284082, -3501.042833097268, 0.0)
    assert rotacao == 0.0 and escala == (1.0, 1.0, 1.0)


def test_escala_e_rotacao_sao_lidas_pela_especificacao():
    """Nenhuma tabela da base tem escala ≠ 1 nem rotação, então estes casos só
    existem aqui, montados bit a bit. Servem para a leitura não ficar travada
    no caso comum — `plana` é quem impede inserir o que não foi medido."""
    escritor = _Escritor().bd(10.5).bd(20.25).bd(0.0).cru("10").rd(2.0).bd(0.5).bd(0.0).bd(0.0).bd(1.0)
    x, y, z, rotacao, escala = decodifica_insercao(escritor.hexa())
    assert (x, y, z) == (10.5, 20.25, 0.0)
    assert escala == (2.0, 2.0, 2.0)
    assert rotacao == 0.5


def test_extrusao_fora_do_lugar_recusa_a_posicao():
    """Se a leitura sai do alinhamento a extrusão vira lixo. Recusar é melhor
    que posicionar a tabela num lugar inventado."""
    escritor = _Escritor().bd(10.5).bd(20.25).bd(0.0).cru("11").bd(0.0).bd(0.0).bd(0.0).bd(0.0)
    assert decodifica_insercao(escritor.hexa()) is None
    assert decodifica_insercao("") is None
    assert decodifica_insercao("FF" * 3) is None


def test_so_a_tabela_sem_escala_nem_rotacao_e_plana():
    base = dict(handle="A", dono="B", camada="C", x=0.0, y=0.0)
    assert TabelaPerdida(**base).plana
    assert not TabelaPerdida(**base, rotacao=0.5).plana
    assert not TabelaPerdida(**base, escala=(2.0, 2.0, 2.0)).plana


# --------------------------------------------------------------------------- #
# Leitura do log
# --------------------------------------------------------------------------- #
def test_le_o_registro_real_da_prancha():
    tabela = le_registro_de_tabela(REGISTRO_CARLA.encode("latin-1"))

    assert tabela is not None
    assert (tabela.handle, tabela.dono, tabela.camada) == ("1420F8", "D6", "3AF")
    assert (tabela.x, tabela.y) == (396.2446855617027, 350.6459116242452)
    assert tabela.plana and not tabela.invisivel


def test_tabela_sem_ownerhandle_esta_no_modelspace():
    """O caso que a primeira versão perdia: `entmode: 2`, nenhum ownerhandle."""
    tabela = le_registro_de_tabela(REGISTRO_JOAO.encode("latin-1"))

    assert tabela is not None
    assert tabela.dono == "MODELO"
    assert (tabela.handle, tabela.camada) == ("42311", "10")
    assert (tabela.x, tabela.y) == (5867.470828284082, -3501.042833097268)


def test_registro_incompleto_nao_vira_tabela():
    sem_bits = REGISTRO_CARLA.split("unknown_bits")[0]
    assert le_registro_de_tabela(sem_bits.encode("latin-1")) is None
    assert le_registro_de_tabela(REGISTRO_OUTRA_CLASSE.encode("latin-1")) is None


@pytest.mark.parametrize("tamanho_do_pedaco", [1, 7, 64, 1 << 20])
def test_extrator_acha_as_tabelas_em_pedacos_de_qualquer_tamanho(tamanho_do_pedaco):
    """A marca e o `crc:` podem cair no meio de dois pedaços de 1 MB lidos do
    pipe; o resultado não pode depender de onde o corte caiu."""
    log = _log(REGISTRO_OUTRA_CLASSE, REGISTRO_CARLA, REGISTRO_OUTRA_CLASSE, REGISTRO_JOAO)
    extrator = ExtratorDeTabelas()
    for i in range(0, len(log), tamanho_do_pedaco):
        extrator.alimenta(log[i : i + tamanho_do_pedaco])

    assert [t.handle for t in extrator.tabelas] == ["1420F8", "42311"]
    assert [t.dono for t in extrator.tabelas] == ["D6", "MODELO"]
    assert extrator.ilegiveis == 0


def test_extrator_conta_a_tabela_que_nao_deu_para_ler():
    quebrada = REGISTRO_CARLA.replace(BITS_CARLA, "FF" * 8)
    extrator = ExtratorDeTabelas()
    extrator.alimenta(_log(quebrada, REGISTRO_JOAO))

    assert [t.handle for t in extrator.tabelas] == ["42311"]
    assert extrator.ilegiveis == 1


# --------------------------------------------------------------------------- #
# Qual bloco `*T…` é de qual tabela
# --------------------------------------------------------------------------- #
def _bloco_record(handle: str, nome: str, referencias: tuple[str, ...] = ()) -> str:
    texto = f"  0\nBLOCK_RECORD\n  5\n{handle}\n330\n1\n100\nAcDbSymbolTableRecord\n100\nAcDbBlockTableRecord\n  2\n{nome}\n"
    if referencias:
        texto += "102\n{BLKREFS\n" + "".join(f"331\n{r}\n" for r in referencias) + "102\n}\n"
    return texto + " 70\n     0\n280\n     1\n"


def test_blocos_das_tabelas_liga_pelo_blkrefs_e_ignora_o_resto_de_tabela_apagada():
    """Alejandro e Andrea R07: *T244 e *T697 têm BLKREFS (tabelas vivas); *T680
    e *T683 não (restos de tabelas apagadas) — inserir esses ressuscitaria
    tabelas que o projetista apagou."""
    dxf = (
        "  0\nTABLE\n  2\nBLOCK_RECORD\n  5\n1\n330\n0\n100\nAcDbSymbolTable\n 70\n     7\n"
        + _bloco_record("D1A69", "*T244", ("D1A68",))
        + _bloco_record("E1946", "*T680")
        + _bloco_record("E21B9", "*T683")
        + _bloco_record("E2C8E", "*T697", ("E2BE5",))
        # Bloco comum: também tem BLKREFS, mas não é tabela.
        + _bloco_record("39C8", "PORTA", ("39C85", "CFF9"))
        + "  0\nENDTAB\n  0\nENDSEC\n"
    ).replace("\n", "\r\n")

    assert blocos_das_tabelas(dxf.encode("latin-1")) == {"D1A68": "*T244", "E2BE5": "*T697"}


def test_blocos_das_tabelas_nao_confunde_valor_com_codigo():
    """Um valor pode ser igual a um código de grupo ("2", "331"): a leitura é
    em pares, não por busca solta."""
    registro = (
        "  0\nBLOCK_RECORD\n  5\n2\n330\n1\n  2\n*T1\n102\n{BLKREFS\n331\n331\n102\n}\n"
    )
    dxf = "  0\nTABLE\n  2\nBLOCK_RECORD\n" + registro + "  0\nENDTAB\n"

    assert blocos_das_tabelas(dxf.encode("latin-1")) == {"331": "*T1"}


def test_blocos_das_tabelas_sem_tabela_de_blocos_devolve_vazio():
    assert blocos_das_tabelas(b"  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n") == {}


# --------------------------------------------------------------------------- #
# Inserção no desenho
# --------------------------------------------------------------------------- #
def _dxf_com_blocos_de_tabela(destino: Path) -> tuple[Path, str, str]:
    """DXF como o `dwg2dxf` entrega: bloco `*T7` (a tabela viva) e `*T9` (resto
    de tabela apagada), as duas com geometria local de (0,0) para baixo, e uma
    prancha "03". Devolve (caminho, layout_key da prancha, handle da camada)."""
    doc = ezdxf.new("R2010")
    doc.layers.add("_NEWSI_TEXTO")
    for nome in ("*T7", "*T9"):
        bloco = doc.blocks.new(nome)
        bloco.add_line((0, 0), (146.4, 0))
        bloco.add_line((0, -187.3), (146.4, -187.3))
        bloco.add_mtext("LEGENDA", dxfattribs={"insert": (2, -5), "char_height": 3})
    doc.modelspace().add_line((0, 0), (1000, 1000))
    prancha = doc.layouts.new("03")
    prancha.add_line((0, 0), (594, 0))
    caminho = destino / "tabela.dxf"
    doc.saveas(caminho)
    return caminho, prancha.layout_key, doc.layers.get("_NEWSI_TEXTO").dxf.handle


def test_a_tabela_volta_na_prancha_certa_com_a_camada_certa():
    with tempfile.TemporaryDirectory() as tmp:
        caminho, chave, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        tabela = TabelaPerdida(
            handle="1420F8", dono=chave, camada=camada, x=396.2446855617027, y=350.6459116242452,
            bloco="*T7",
        )
        documento, _ = load_dxf(caminho, [tabela])

    insercoes = [e for e in documento.layouts["03"].values() if isinstance(e, BlockReference)]
    assert len(insercoes) == 1
    tabela_no_desenho = insercoes[0]
    assert tabela_no_desenho.block_name == "*T7"
    assert (tabela_no_desenho.insertion_point.x, tabela_no_desenho.insertion_point.y) == (
        396.2446855617027, 350.6459116242452,
    )
    assert tabela_no_desenho.layer == "_NEWSI_TEXTO"
    assert tabela.inserida
    assert not [e for e in documento.entities.values() if isinstance(e, BlockReference)]


def test_o_resto_de_tabela_apagada_nao_ganha_insercao():
    with tempfile.TemporaryDirectory() as tmp:
        caminho, chave, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        tabela = TabelaPerdida(handle="A", dono=chave, camada=camada, x=1.0, y=2.0, bloco="*T7")
        documento, _ = load_dxf(caminho, [tabela])

    usados = {
        e.block_name
        for conjunto in [documento.entities, *documento.layouts.values()]
        for e in conjunto.values()
        if isinstance(e, BlockReference)
    }
    assert usados == {"*T7"}, "o *T9 é resto de tabela apagada e não pode voltar"


def test_tabela_do_modelspace_entra_no_desenho_e_nao_numa_prancha():
    with tempfile.TemporaryDirectory() as tmp:
        caminho, _, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        tabela = TabelaPerdida(
            handle="42311", dono="MODELO", camada=camada, x=5867.47, y=-3501.04, bloco="*T7"
        )
        documento, _ = load_dxf(caminho, [tabela])

    insercoes = [e for e in documento.entities.values() if isinstance(e, BlockReference)]
    assert [(e.block_name, round(e.insertion_point.x, 2)) for e in insercoes] == [("*T7", 5867.47)]
    assert tabela.inserida


def test_tabela_sem_dono_na_prancha_padrao_entra_no_layout_do_paper_space():
    """`entmode: 1` no .dwg = a prancha padrão (o BLOCK_RECORD `*Paper_Space`
    sem número), que não vem com handle de dono."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho, _, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        tabela = TabelaPerdida(
            handle="A", dono="PRANCHA", camada=camada, x=10.0, y=20.0, bloco="*T7"
        )
        documento, _ = load_dxf(caminho, [tabela])

    assert tabela.inserida
    assert [e.block_name for e in documento.layouts["Layout1"].values()] == ["*T7"]


@pytest.mark.parametrize(
    "mudanca",
    [
        {"bloco": ""},                      # BLKREFS não ligou a nenhum bloco
        {"bloco": "*T404"},                 # bloco que não veio no arquivo
        {"dono": "FFFF"},                   # espaço que não existe
        {"invisivel": True},                # a tabela estava oculta no AutoCAD
        {"rotacao": 1.57},                  # fora do único caso medido
        {"escala": (2.0, 2.0, 2.0)},        # idem
    ],
)
def test_so_entra_o_que_esta_provado(mudanca):
    """Na dúvida a tabela continua perdida (e contada como perdida): uma tabela
    de 146 x 187 num lugar chutado fica por cima da planta, pior que sumir."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho, chave, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        campos = dict(handle="A", dono=chave, camada=camada, x=1.0, y=2.0, bloco="*T7")
        campos.update(mudanca)
        tabela = TabelaPerdida(**campos)
        documento, _ = load_dxf(caminho, [tabela])

    assert not tabela.inserida
    assert not [
        e
        for conjunto in [documento.entities, *documento.layouts.values()]
        for e in conjunto.values()
        if isinstance(e, BlockReference)
    ]


def test_a_tabela_recuperada_sobrevive_a_gravar_e_reabrir():
    """O ponto de a tabela voltar ao desenho é voltar também ao arquivo que o
    cliente recebe, na mesma posição."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho, chave, camada = _dxf_com_blocos_de_tabela(Path(tmp))
        tabela = TabelaPerdida(
            handle="A", dono=chave, camada=camada, x=396.25, y=350.65, bloco="*T7"
        )
        documento, _ = load_dxf(caminho, [tabela])
        saida = Path(tmp) / "saida.dxf"
        save_dxf(documento, saida)
        reaberto = ezdxf.readfile(saida)
        insercoes = [e for e in reaberto.layouts.get("03") if e.dxftype() == "INSERT"]
        assert len(insercoes) == 1
        assert tuple(round(v, 2) for v in insercoes[0].dxf.insert)[:2] == (396.25, 350.65)
        bloco = reaberto.blocks.get(insercoes[0].dxf.name)
        assert len([e for e in bloco if e.dxftype() in ("LINE", "MTEXT")]) == 3


# --------------------------------------------------------------------------- #
# Costura com o dwg_bridge (sem depender de um .dwg real)
# --------------------------------------------------------------------------- #
def _bridge_falso(monkeypatch, tmp: Path, stderr: str, achadas: list[tuple[str, float, float]]) -> Path:
    """Faz `dwg_to_document` converter um .dwg de mentira: `_run` grava o DXF
    pronto e devolve o stderr; a segunda volta devolve `achadas` (handle, x, y)
    como tabelas da prancha "03"; e o BLKREFS liga o handle 1420F8 ao *T7."""
    caminho, chave, camada = _dxf_com_blocos_de_tabela(tmp)
    dxf_bytes = caminho.read_bytes()
    monkeypatch.setattr(dwg_bridge, "_tool_path", lambda nome: "dwg2dxf-falso")

    def _run_falso(args):
        Path(args[2]).write_bytes(dxf_bytes)
        return stderr

    monkeypatch.setattr(dwg_bridge, "_run", _run_falso)
    monkeypatch.setattr(
        dwg_bridge,
        "acha_tabelas_no_dwg",
        lambda *a, **k: [
            TabelaPerdida(handle=h, dono=chave, camada=camada, x=x, y=y) for h, x, y in achadas
        ],
    )
    monkeypatch.setattr(dwg_bridge, "blocos_das_tabelas", lambda dxf: {"1420F8": "*T7"})
    entrada = tmp / "projeto.dwg"
    entrada.write_bytes(b"AC1032")
    return entrada


AVISO_DE_TABELA = "Warning: Unhandled Class entity 572 ACAD_TABLE (0x401) 74030/0\n"


def test_tabela_recuperada_sai_da_conta_de_perdidas(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _bridge_falso(
            monkeypatch, Path(tmp), AVISO_DE_TABELA,
            [("1420F8", 396.25, 350.65)],
        )
        documento, descartadas = dwg_bridge.dwg_to_document(entrada)

    assert dict(descartadas.by_type) == {}
    assert int(descartadas) == 0
    assert any("recuperadas" in nota for nota in descartadas.notes)
    assert [e.block_name for e in documento.layouts["03"].values() if isinstance(e, BlockReference)] == ["*T7"]


def test_tabela_que_nao_deu_para_ler_continua_contada_como_perdida(monkeypatch):
    """A segunda volta não achou nada (arquivo grande, falha, tempo): o
    comportamento é exatamente o de antes — descartada e avisada."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _bridge_falso(monkeypatch, Path(tmp), AVISO_DE_TABELA, [])
        documento, descartadas = dwg_bridge.dwg_to_document(entrada)

    assert dict(descartadas.by_type) == {"ACAD_TABLE (descartada pelo dwg2dxf)": 1}
    assert int(descartadas) == 1
    assert not any("recuperadas" in nota for nota in descartadas.notes)
    assert "03" not in documento.layouts or not any(
        isinstance(e, BlockReference) for e in documento.layouts["03"].values()
    )


def test_so_uma_das_duas_tabelas_recuperada_deixa_a_outra_na_conta(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _bridge_falso(
            monkeypatch, Path(tmp), AVISO_DE_TABELA * 2,
            [("1420F8", 1.0, 2.0)],
        )
        _, descartadas = dwg_bridge.dwg_to_document(entrada)

    assert dict(descartadas.by_type) == {"ACAD_TABLE (descartada pelo dwg2dxf)": 1}
    assert int(descartadas) == 1


def test_arquivo_grande_nao_paga_a_segunda_volta(monkeypatch):
    """O .dwg de 71 MB da Loja Casual levou 416 s no rastreio (48 s na
    conversão normal); acima do limite a tabela segue descartada, como sempre."""
    chamadas = []
    monkeypatch.setattr(dwg_bridge, "acha_tabelas_no_dwg", lambda *a, **k: chamadas.append(a) or [])
    monkeypatch.setattr(dwg_bridge, "_TABELAS_MAX_BYTES", 10)
    with tempfile.TemporaryDirectory() as tmp:
        grande = Path(tmp) / "grande.dwg"
        grande.write_bytes(b"x" * 11)
        resultado = dwg_bridge.recupera_tabelas("ferramenta", grande, Path(tmp) / "x.dxf", Path(tmp), 4)

    assert resultado == []
    assert not chamadas, "nem deveria ter chamado o dwg2dxf de novo"


def test_sem_aviso_de_tabela_a_segunda_volta_nem_roda(monkeypatch):
    chamadas = []
    monkeypatch.setattr(dwg_bridge, "acha_tabelas_no_dwg", lambda *a, **k: chamadas.append(a) or [])
    with tempfile.TemporaryDirectory() as tmp:
        pequeno = Path(tmp) / "p.dwg"
        pequeno.write_bytes(b"x")
        resultado = dwg_bridge.recupera_tabelas("ferramenta", pequeno, Path(tmp) / "x.dxf", Path(tmp), 0)

    assert resultado == [] and not chamadas
