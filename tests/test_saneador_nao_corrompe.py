"""O saneador do DXF não pode quebrar linha onde o DXF não quebra.

Achado da varredura da base, e dos piores: **a gente corrompia o arquivo do
cliente e depois adivinhava o conteúdo.**

`str.splitlines()` do Python quebra em oito separadores além do fim de linha
— U+000B, U+000C, U+001C, U+001D, U+001E, U+0085, U+2028 e U+2029. Nenhum
deles separa linha num DXF, e todos aparecem DENTRO de valor de texto quando
o arquivo é lido como latin-1.

Caso real: o texto `AFP-∅ 25 PPELO ENTREFORRO` do `NEWSI-CSA-02-TÉR_R07.dwg`
da Casa Sanchez tem o caractere "diâmetro" (U+2205), cujo terceiro byte em
UTF-8 é 0x85 — lido como latin-1 vira U+0085 (NEL) e o `splitlines()` partia
o valor em dois. O saneador via um valor partido onde não havia, perdia o
passo da contagem código/valor e saía COLANDO linhas boas: 208 mesclagens
indevidas nesse arquivo, produzindo tags inválidas como
`7hid-hidraulica-terreo$0$SIMPLEX`.

O programa não quebrava porque a leitura tolerante do ezdxf ADIVINHAVA os
valores ("recovered invalid integer value ... as 7") — o estrago ficava
invisível. Depois do conserto: 208 mesclagens viram 1 (a legítima), e o
ezdxf lê o arquivo SEM recuperação, com as 76.017 entidades.
"""

from __future__ import annotations

import pytest

from newsicad.io.dwg_bridge import linhas_do_dxf, sanitize_dxf_text

#: Os separadores que o `splitlines()` usa e o DXF não.
NAO_SEPARAM_LINHA = ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]


@pytest.mark.parametrize("caractere", NAO_SEPARAM_LINHA)
def test_caractere_de_controle_no_valor_nao_quebra_linha(caractere):
    texto = f"  1\nAFP-{caractere}25 PPELO ENTREFORRO\n  7\nestilo\n"

    linhas = linhas_do_dxf(texto)

    assert linhas[1] == f"AFP-{caractere}25 PPELO ENTREFORRO"
    assert linhas == ["  1", f"AFP-{caractere}25 PPELO ENTREFORRO", "  7", "estilo"], (
        "quatro linhas de verdade — e sem o vazio que o fim de linha final deixa"
    )


@pytest.mark.parametrize("caractere", NAO_SEPARAM_LINHA)
def test_saneador_nao_mexe_em_arquivo_com_esse_caractere(caractere):
    """O caso real: um valor com o byte 0x85 fazia o saneador colar as
    linhas seguintes e inventar tags inválidas."""
    bom = (
        "  0\nSECTION\n  2\nENTITIES\n"
        f"  0\nMTEXT\n  8\nHIDRAULICA\n  1\nAFP-{caractere}25 PPELO ENTREFORRO\n"
        "  7\nhid-hidraulica-terreo$0$SIMPLEX\n 40\n2.5\n"
        "  0\nENDSEC\n  0\nEOF\n"
    )

    saneado, mesclados = sanitize_dxf_text(bom)

    assert mesclados == 0, "arquivo íntegro não pode ser mexido"
    assert saneado == bom
    assert "7hid-hidraulica-terreo" not in saneado, "código não pode colar no valor"


def test_saneador_continua_consertando_a_quebra_de_verdade():
    """A contrapartida: a corrupção que o saneador existe para consertar —
    o `dwg2dxf` quebrando a string de UM código de grupo no meio de uma
    palavra — continua sendo consertada."""
    quebrado = "  1\nISOC\nPEUR|b0;texto\n 40\n2.5\n"

    saneado, mesclados = sanitize_dxf_text(quebrado)

    assert mesclados == 1
    assert "ISOCPEUR|b0;texto" in saneado


def test_crlf_e_lf_dao_as_mesmas_linhas():
    assert linhas_do_dxf("  1\r\nvalor\r\n  7\r\nestilo\r\n") == \
           linhas_do_dxf("  1\nvalor\n  7\nestilo\n")
