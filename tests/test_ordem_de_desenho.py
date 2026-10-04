"""Ordem de desenho corrompida não pode derrubar a abertura do arquivo.

Achado da varredura da base em 03/10/2026. O `NEWSI-CSA-03-PV1_R07.dwg` da
Casa Sanchez (2,4 MB) tem um bloco cuja tabela de ordem de desenho
(SORTENTSTABLE) o `dwg2dxf` grava com um item pela metade. O ezdxf levanta
`ValueError: dictionary update sequence element #0 has length 1; 2 is
required` lá no fundo, e o erro subia até o topo: o projetista via "o .dwg
foi convertido, mas o DXF resultante não pôde ser lido" e ficava sem o
arquivo.

Ordem de desenho é acabamento — é o que faz um WIPEOUT cobrir só o que está
atrás dele e uma hachura sólida ficar por baixo das linhas do próprio ícone.
Perder o acabamento de um bloco é incomparavelmente melhor do que não abrir
o projeto.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf

from newsicad.io.dxf_io import load_dxf, ordem_de_desenho


class _LayoutFalso:
    """Imita o que o ezdxf entrega: iterável, com `entities_in_redraw_order`
    que pode levantar."""

    def __init__(self, entidades, erro: Exception | None = None):
        self._entidades = entidades
        self._erro = erro

    def __iter__(self):
        return iter(self._entidades)

    def entities_in_redraw_order(self):
        if self._erro is not None:
            raise self._erro
        return reversed(self._entidades)


def test_usa_a_ordem_de_desenho_quando_ela_existe():
    layout = _LayoutFalso(["a", "b", "c"])

    assert ordem_de_desenho(layout) == ["c", "b", "a"]


def test_cai_na_ordem_natural_quando_a_tabela_esta_quebrada():
    """O erro real do arquivo da Casa Sanchez."""
    quebrado = ValueError("dictionary update sequence element #0 has length 1; 2 is required")
    layout = _LayoutFalso(["a", "b", "c"], erro=quebrado)

    assert ordem_de_desenho(layout) == ["a", "b", "c"], "nenhuma entidade pode se perder"


def test_nenhuma_entidade_se_perde_com_a_tabela_quebrada():
    """Ponta a ponta: a entidade tem que chegar no documento mesmo com a
    ordem de desenho inutilizável."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        for i in range(5):
            msp.add_line((0, i), (10, i), dxfattribs={"layer": "PAREDE"})
        caminho = Path(tmp) / "ordem.dxf"
        doc.saveas(caminho)

        documento, _ = load_dxf(caminho)

    assert len(documento.entities) == 5
