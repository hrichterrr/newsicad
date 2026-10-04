"""Acento partido no meio dos bytes pelo `dwg2dxf`.

Achado da varredura da base em 03/10/2026, na contracapa do LEVANTAMENTO do
Joe Lee. O `dwg2dxf` quebra string longa de MTEXT em pedaços e quebra
CONTANDO BYTES: quando a fatia cai no meio de um caractere de dois bytes
(C3 95 = Õ em UTF-8), cada metade vira um byte solto que o leitor não sabe
decodificar e guarda como substituto. A nota do projeto chegava
"ALTERAÇ??ES E/OU INCLUSÕES".

O detalhe que quase virou um defeito reportado errado: o arquivo que a gente
GRAVA já saía CERTO, porque a string volta inteira num pedaço só e os dois
bytes se reencontram. Quem via o problema era o projetista, na TELA. A
auditoria chegou a acusar "1 etiqueta sem correspondente" nesse arquivo — e
a etiqueta que não casava era a do ORIGINAL, não a nossa.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf
import pytest

from newsicad.io.dxf_annotations import remonta_acento
from newsicad.io.dxf_io import load_dxf

#: Como o texto chega quando o Õ (bytes C3 95) é partido entre dois pedaços.
PARTIDO = "ALTERAÇ" + chr(0xDCC3) + chr(0xDC95) + "ES E/OU INCLUSÕES"
INTEIRO = "ALTERAÇÕES E/OU INCLUSÕES"


def test_remonta_o_caractere_partido():
    assert remonta_acento(PARTIDO) == INTEIRO


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "SEM ACENTO NENHUM",
        "PLANTA DE ILUMINAÇÃO — TÉRREO",
        "ÁÉÍÓÚ ÃÕ ÇÑ",
    ],
)
def test_texto_integro_passa_intacto(texto):
    """A esmagadora maioria dos textos não tem byte solto: não pode haver
    nem alteração nem custo."""
    assert remonta_acento(texto) is texto or remonta_acento(texto) == texto


def test_byte_solto_que_nao_forma_par_vira_substituto_visivel():
    """Byte que não casa com nenhum caractere não pode continuar solto: um
    substituto na tela é ruim, mas um byte solto quebra a GRAVAÇÃO."""
    saida = remonta_acento("x" + chr(0xDCFF) + "y")

    assert not any(0xDC80 <= ord(c) <= 0xDCFF for c in saida)
    assert saida.startswith("x") and saida.endswith("y")


def test_mtext_com_acento_partido_chega_limpo_no_documento():
    """Ponta a ponta: o texto entra no documento já remontado, que é o que
    o projetista vê na tela."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho = Path(tmp) / "partido.dxf"
        doc = ezdxf.new("R2010")
        doc.modelspace().add_mtext(PARTIDO, dxfattribs={"char_height": 2.5})
        doc.saveas(caminho)

        documento, _ = load_dxf(caminho)

    textos = [e for e in documento.entities.values() if getattr(e, "content", "")]
    assert len(textos) == 1
    assert not any(0xDC80 <= ord(c) <= 0xDCFF for c in textos[0].content)
    assert "ALTERAÇÕES" in textos[0].content
