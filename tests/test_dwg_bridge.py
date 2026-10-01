"""Testes de newsicad/io/dwg_bridge.py.

`dwg2dxf` (LibreDWG) só está empacotado para macOS/Windows (ver
`resources/libredwg/`) e, fora isso, precisa estar no PATH. Em ambientes que
não têm nenhum dos dois (ex.: a maioria dos runners Linux de CI), os testes
que dependem dele são pulados via `pytest.skip`, cobrindo tanto "ferramenta
não encontrada" quanto "plataforma sem binário empacotado".

Não geramos aqui um .dwg de teste com o `dxf2dwg` do próprio LibreDWG: como
documentado em `dwg_bridge.py`, essa ferramenta (v0.13.3) é conhecida por
produzir arquivos com handles de entidade duplicados/inválidos mesmo para
conteúdo mínimo (uma única linha) — reproduzido manualmente durante o
desenvolvimento destes testes: o .dwg gerado pelo `dxf2dwg` falha ao ser
relido, com `ValueError: Invalid handle 0.` vazando de dentro do ezdxf. Por
isso o teste de "arquivo .dwg inválido" abaixo usa bytes arbitrários em vez
de depender do gravador não confiável.
"""

from __future__ import annotations

import tempfile
import unicodedata
from pathlib import Path

import pytest

from newsicad.io.dwg_bridge import (
    DwgBridgeError,
    _tool_path,
    dwg_to_document,
    entrada_que_a_ferramenta_abre,
    pasta_que_a_ferramenta_enxerga,
    repara_seqend,
    sanitize_dxf_text,
)


def _require_dwg2dxf() -> str:
    try:
        return _tool_path("dwg2dxf")
    except DwgBridgeError as exc:
        pytest.skip(str(exc))


def test_tool_path_resolves_or_skips():
    tool = _require_dwg2dxf()
    assert Path(tool).name.startswith("dwg2dxf")


def test_dwg_to_document_raises_clean_error_for_invalid_file():
    _require_dwg2dxf()

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_dwg = Path(tmp_dir) / "not_really_a_dwg.dwg"
        fake_dwg.write_bytes(b"this is not a valid dwg file")

        with pytest.raises(DwgBridgeError):
            dwg_to_document(fake_dwg)


def test_dwg_to_document_raises_for_missing_file():
    _require_dwg2dxf()

    with tempfile.TemporaryDirectory() as tmp_dir:
        missing = Path(tmp_dir) / "does_not_exist.dwg"
        with pytest.raises(DwgBridgeError):
            dwg_to_document(missing)


# ---------------------------------------------------------------------- #
# sanitize_dxf_text: função pura, roda em qualquer ambiente (não depende
# do binário dwg2dxf) — cobre a corrupção real encontrada em .dwg reais de
# clientes, onde o dwg2dxf quebra uma string de MTEXT longa (com códigos de
# formatação embutidos) no meio de uma palavra em vez de encadear várias
# linhas de código 3 como o formato DXF exige.
# ---------------------------------------------------------------------- #
def test_sanitize_dxf_text_rejoins_word_broken_by_stray_newline():
    # Reprodução mínima do padrão real: o valor do código 1 (texto do MTEXT)
    # tem uma quebra de linha crua bem no meio de "ISOCPEUR".
    broken = "  0\nMTEXT\n  1\n\\fISOC\nPEUR|b0;texto\n  7\nGENERATED_STYLE_1\n"
    fixed, merged = sanitize_dxf_text(broken)

    assert merged == 1
    assert "\\fISOCPEUR|b0;texto" in fixed
    assert "ISOC\nPEUR" not in fixed


def test_sanitize_dxf_text_is_noop_for_well_formed_dxf():
    well_formed = "  0\nLINE\n  8\n0\n 10\n0.0\n 20\n0.0\n"
    fixed, merged = sanitize_dxf_text(well_formed)

    assert merged == 0
    assert fixed == well_formed


def test_sanitize_dxf_text_handles_multiple_consecutive_wraps():
    # Uma string tão longa que quebra em 3 linhas físicas, não só 2.
    broken = "  1\nAAA\nBBB\nCCC\n  0\nENDSEC\n"
    fixed, merged = sanitize_dxf_text(broken)

    assert merged == 2
    assert "AAABBBCCC" in fixed


# --------------------------------------------------------------------- #
# Nome de arquivo com acento (achado da varredura da base, 01/10/2026)
#
# O binário do LibreDWG no Windows abre o arquivo pela API de byte do
# sistema: um caminho com caractere fora da página de código chega truncado
# e a ferramenta responde `ERROR: File not found` pra um arquivo que existe.
# Quatro arquivos da base real não abriam por causa disso — acento
# DECOMPOSTO (NFD), do jeito que o macOS/iCloud grava: "ELÉTRICA" guardado
# como E + acento combinante, que não existe no cp1252. Um deles tinha
# 66.166 entidades. 28 dos 218 arquivos da base têm acento no nome.
# --------------------------------------------------------------------- #


def test_entrada_ascii_nao_e_copiada():
    """Caminho que a ferramenta já abre passa direto: nada de copiar 79 MB
    à toa no caso comum."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        origem = tmp_dir / "PLANTA_TERREO.dwg"
        origem.write_bytes(b"AC1018")
        trabalho = tmp_dir / "trabalho"
        trabalho.mkdir()

        assert entrada_que_a_ferramenta_abre(origem, trabalho) == origem
        assert list(trabalho.iterdir()) == []


@pytest.mark.parametrize(
    "nome",
    [
        unicodedata.normalize("NFD", "PE04_ELÉTRICA.dwg"),  # como o macOS grava
        unicodedata.normalize("NFC", "PE06_ILUMINAÇÃO.dwg"),
        "PLANTA_TÉRREO_ÁREA_EXTERNA.dwg",
    ],
)
def test_entrada_com_acento_vira_copia_ascii(nome):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        origem = tmp_dir / nome
        origem.write_bytes(b"AC1018-conteudo-do-dwg")
        trabalho = tmp_dir / "trabalho"
        trabalho.mkdir()

        entrada = entrada_que_a_ferramenta_abre(origem, trabalho)

        assert str(entrada).isascii(), "a ferramenta não enxerga caminho fora do ASCII"
        assert entrada.exists()
        assert entrada.read_bytes() == origem.read_bytes(), "a cópia tem que ser fiel"
        assert entrada.suffix == ".dwg"
        assert entrada.parent == trabalho, "a cópia fica na pasta temporária, não ao lado do original"


def test_pasta_de_saida_ascii_passa_direto():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pasta = Path(tmp_dir)
        assert pasta_que_a_ferramenta_enxerga(pasta) == pasta


def test_dwg_com_acento_no_nome_abre():
    """O defeito de verdade, ponta a ponta: o mesmo .dwg com nome acentuado
    tem que abrir igual ao de nome neutro."""
    _require_dwg2dxf()
    amostra = Path(__file__).parent / "data"
    dwgs = sorted(amostra.glob("*.dwg")) if amostra.is_dir() else []
    if not dwgs:
        pytest.skip("sem .dwg de amostra em tests/data para o teste ponta a ponta")

    with tempfile.TemporaryDirectory() as tmp_dir:
        acentuado = Path(tmp_dir) / unicodedata.normalize("NFD", "PLANTA_ELÉTRICA.dwg")
        acentuado.write_bytes(dwgs[0].read_bytes())

        documento, _ = dwg_to_document(acentuado)
        referencia, _ = dwg_to_document(dwgs[0])

        assert len(documento.entities) == len(referencia.entities)



# --------------------------------------------------------------------- #
# POLYLINE sem SEQEND (achado da varredura da base, 01/10/2026)
#
# A POLYLINE "clássica" guarda os vértices como entidades VERTEX soltas
# depois dela, terminadas por um SEQEND obrigatório. O `dwg2dxf` às vezes não
# emite esse SEQEND, e aí o leitor não sabe onde a polilinha acaba e recusa o
# arquivo INTEIRO: o projetista vê "arquivo inválido ou corrompido" num .dwg
# que o AutoCAD abre sem reclamar. Seis arquivos de dois clientes da base
# estavam assim (Mauro e Marcia, Casa Alphaville R00/R01/R02); num deles
# faltavam 4 pares de linhas em 6,9 milhões.
# --------------------------------------------------------------------- #

_POLYLINE_ABERTA = (
    "  0\nPOLYLINE\n  8\nEIXO\n 66\n1\n 70\n0\n"
    "  0\nVERTEX\n  8\nEIXO\n 10\n0.0\n 20\n0.0\n"
    "  0\nVERTEX\n  8\nEIXO\n 10\n1.0\n 20\n0.0\n"
    "  0\nVERTEX\n  8\nEIXO\n 10\n1.0\n 20\n1.0\n"
)
_LINHA = "  0\nLINE\n  8\nPAREDE\n 10\n0.0\n 20\n0.0\n 11\n5.0\n 21\n5.0\n"


def _dxf_de_entidades(corpo: str) -> str:
    return "  0\nSECTION\n  2\nENTITIES\n" + corpo + "  0\nENDSEC\n  0\nEOF\n"


def _entidades_lidas(texto: str) -> list[tuple[str, str]]:
    import io

    import ezdxf

    doc = ezdxf.read(io.StringIO(texto))
    return [(e.dxftype(), e.dxf.layer) for e in doc.modelspace()]


def test_repara_seqend_nao_toca_arquivo_bom():
    bom = _dxf_de_entidades(_POLYLINE_ABERTA + "  0\nSEQEND\n  8\nEIXO\n" + _LINHA)
    saida, remendos = repara_seqend(bom)

    assert remendos == 0
    assert saida == bom, "arquivo íntegro não pode ser reescrito"


def test_repara_seqend_fecha_polyline_cortada():
    quebrado = _dxf_de_entidades(_POLYLINE_ABERTA + _LINHA)
    with pytest.raises(Exception):
        _entidades_lidas(quebrado)  # é exatamente isto que o projetista via

    saida, remendos = repara_seqend(quebrado)

    assert remendos == 1
    assert _entidades_lidas(saida) == [("POLYLINE", "EIXO"), ("LINE", "PAREDE")]


def test_repara_seqend_usa_a_camada_de_quem_abriu():
    """O SEQEND pertence à entidade que abriu a sequência, não à que a
    interrompeu — camada errada ali move a polilinha de camada."""
    saida, _ = repara_seqend(_dxf_de_entidades(_POLYLINE_ABERTA + _LINHA))
    linhas = saida.splitlines()
    assert linhas[linhas.index("SEQEND") + 2] == "EIXO"


def test_repara_seqend_varias_sequencias_e_no_fim_do_arquivo():
    """Os dois casos reais: polilinha cortada pela polilinha seguinte, e
    polilinha que fica aberta até o fim da seção."""
    duas = _dxf_de_entidades(_POLYLINE_ABERTA + _POLYLINE_ABERTA + _LINHA)
    saida, remendos = repara_seqend(duas)
    assert remendos == 2
    assert _entidades_lidas(saida) == [
        ("POLYLINE", "EIXO"), ("POLYLINE", "EIXO"), ("LINE", "PAREDE"),
    ]

    no_fim, remendos = repara_seqend(_dxf_de_entidades(_POLYLINE_ABERTA))
    assert remendos == 1
    assert _entidades_lidas(no_fim) == [("POLYLINE", "EIXO")]


def test_repara_seqend_fecha_insert_com_atributo():
    """INSERT com `attribs_follow` (código 66 = 1) também precisa de SEQEND."""
    insert = (
        "  0\nINSERT\n  8\nSIMBOLO\n 66\n1\n  2\nTOMADA\n 10\n0.0\n 20\n0.0\n"
        "  0\nATTRIB\n  8\nSIMBOLO\n 10\n0.0\n 20\n0.0\n  1\nT1\n  2\nTAG\n 40\n2.5\n"
    )
    saida, remendos = repara_seqend(_dxf_de_entidades(insert + _LINHA))
    assert remendos == 1
    linhas = saida.splitlines()
    assert linhas[linhas.index("SEQEND") + 2] == "SIMBOLO"
