"""INSERT que não aponta para bloco nenhum: a geometria não existe, o texto sim.

Achado da varredura da base. Um INSERT com o nome do bloco VAZIO é arquivo
malformado — não há definição para desenhar, e o próprio ezdxf recusa
expandi-lo ("Required block definition for '' does not exist"). Mas o ATTRIB
pendurado nele tem conteúdo e posição absoluta, e sumia junto.

Caso real: o `PATRICIA E FABIO - SALA 2 - EX - R03.dwg` tem 42 INSERT assim,
cada um com uma etiqueta de corte ('S" 34 e 35', 'S"36', 'S" 51, 52,53,54 e
55'). São 72 na base inteira, em 12 arquivos.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf

from newsicad.core.entities import Text
from newsicad.io.dxf_io import load_dxf


def _le(construir):
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        construir(doc)
        caminho = Path(tmp) / "orfao.dxf"
        doc.saveas(caminho)
        return load_dxf(caminho)


def _sem_nome_com_attrib(msp, valor: str, ponto=(10.0, 20.0)):
    """Um INSERT com nome de bloco vazio e um ATTRIB preenchido."""
    insercao = msp.add_blockref("TEMPORARIO", ponto)
    insercao.add_attrib(tag="CORTE", text=valor, insert=ponto, dxfattribs={"height": 2.5})
    insercao.dxf.name = ""
    return insercao


def test_texto_do_atributo_sobrevive_ao_insert_orfao():
    def construir(doc):
        doc.blocks.new("TEMPORARIO").add_line((0, 0), (1, 1))
        _sem_nome_com_attrib(doc.modelspace(), 'S" 34 e 35')

    documento, descartadas = _le(construir)

    textos = [e for e in documento.entities.values() if isinstance(e, Text)]
    assert [t.content for t in textos] == ['S" 34 e 35']
    assert (textos[0].insertion_point.x, textos[0].insertion_point.y) == (10.0, 20.0)
    # a GEOMETRIA do símbolo se perdeu de verdade — isso continua no aviso
    assert dict(getattr(descartadas, "by_type", {}) or {}) == {"INSERT": 1}


def test_insert_orfao_sem_atributo_nao_inventa_nada():
    def construir(doc):
        doc.blocks.new("TEMPORARIO").add_line((0, 0), (1, 1))
        insercao = doc.modelspace().add_blockref("TEMPORARIO", (0, 0))
        insercao.dxf.name = ""

    documento, _ = _le(construir)

    assert not documento.entities


def test_insert_com_bloco_de_verdade_continua_sendo_bloco():
    """A contrapartida: um INSERT normal não pode virar texto solto."""
    def construir(doc):
        bloco = doc.blocks.new("SIMBOLO")
        bloco.add_line((0, 0), (1, 1))
        insercao = doc.modelspace().add_blockref("SIMBOLO", (5, 5))
        insercao.add_attrib(tag="NUM", text="07", insert=(5, 5), dxfattribs={"height": 2.5})

    documento, _ = _le(construir)

    from newsicad.core.entities import BlockReference

    blocos = [e for e in documento.entities.values() if isinstance(e, BlockReference)]
    assert len(blocos) == 1
    assert [t.content for t in blocos[0].attributes] == ["07"], (
        "a etiqueta tem de continuar presa ao bloco, não virar texto solto"
    )


def test_texto_do_atributo_sobrevive_tambem_na_prancha():
    def construir(doc):
        doc.blocks.new("TEMPORARIO").add_line((0, 0), (1, 1))
        _sem_nome_com_attrib(doc.layouts.get("Layout1"), "REV 01", ponto=(3.0, 4.0))

    documento, _ = _le(construir)

    da_prancha = list(documento.layouts.get("Layout1", {}).values())
    assert [e.content for e in da_prancha if isinstance(e, Text)] == ["REV 01"]
