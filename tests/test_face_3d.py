"""3DFACE: o contorno da face do arquiteto, que era descartado inteiro.

Achado da varredura da base em 01/10/2026. O 3DFACE é o triângulo ou
quadrilátero plano com que o arquiteto entrega laje, telhado e malha de
terreno no .dwg base. O `BASE_XREF_LEE` do Joe Lee tem 72 deles — em duas
revisões do mesmo arquivo — e nenhum era lido: o projetista abria o arquivo
base para projetar em cima e aqueles traços simplesmente não estavam lá.

A sutileza que custou uma volta: o sinalizador de aresta invisível (group
code 70) é indexado pelas QUATRO arestas do DXF, não pela lista de cantos
distintos. Num triângulo gravado como A,B,C,C a aresta de volta é a de
índice 3 (C→A) e a de índice 2 é a degenerada — casar errado esconde a
aresta errada. Nesse arquivo real, 32 das 72 faces usam exatamente essa
combinação (flags 3 e 5), e a primeira versão do conserto descartava as 32.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf
import pytest

from newsicad.core.entities import LWPolyline
from newsicad.io.dxf_io import load_dxf

A = (0.0, 0.0, 0.0)
B = (10.0, 0.0, 0.0)
C = (10.0, 10.0, 0.0)
D = (0.0, 10.0, 0.0)
T = (5.0, 8.0, 0.0)


def _le_face(cantos, flags: int = 0):
    """Devolve a entidade lida de um .dxf com um único 3DFACE (ou None)."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        doc.modelspace().add_3dface(cantos, dxfattribs={"layer": "BASE", "invisible_edges": flags})
        caminho = Path(tmp) / "face.dxf"
        doc.saveas(caminho)
        documento, _ = load_dxf(caminho)
        entidades = list(documento.entities.values())
        return entidades[0] if entidades else None


def _xy(entidade) -> list[tuple[float, float]]:
    return [(round(p.x, 6), round(p.y, 6)) for p in entidade.points]


def test_quadrilatero_vira_contorno_fechado():
    lido = _le_face([A, B, C, D])

    assert isinstance(lido, LWPolyline)
    assert lido.closed
    assert _xy(lido) == [(0, 0), (10, 0), (10, 10), (0, 10)]


@pytest.mark.parametrize("cantos", [[A, B, T, A], [A, B, T, T]])
def test_triangulo_fecha_nos_dois_jeitos_de_gravar(cantos):
    """O quarto canto pode repetir o primeiro ou o terceiro — os dois
    aparecem em arquivo real e os dois são o mesmo triângulo."""
    lido = _le_face(cantos)

    assert lido.closed
    assert _xy(lido) == [(0, 0), (10, 0), (5, 8)]


def test_diagonal_escondida_mantem_as_outras_arestas():
    """O caso que motiva o sinalizador: um quadrilátero partido em dois
    triângulos, com a diagonal oculta. As três arestas restantes têm que
    sair inteiras — e elas dão a volta pelo fim da lista."""
    lido = _le_face([A, B, C, D], flags=2)  # esconde a aresta B->C

    assert not lido.closed
    assert _xy(lido) == [(10, 10), (0, 10), (0, 0), (10, 0)]
    assert (10.0, 0.0) not in _xy(lido)[1:-1], "a aresta oculta não pode virar traço"


@pytest.mark.parametrize(
    "flags,esperado",
    [
        (3, [(5, 8), (0, 0)]),    # sobra só a aresta de volta (índice 2)
        (5, [(10, 0), (5, 8)]),   # sobra só a aresta do meio (índice 1)
        (6, [(0, 0), (10, 0)]),   # sobra só a primeira
    ],
)
def test_triangulo_com_duas_arestas_ocultas(flags, esperado):
    """32 das 72 faces do arquivo real do Joe Lee são assim: mostram UMA
    aresta só. É o jeito de desenhar malha de terreno sem virar arame."""
    lido = _le_face([A, B, T, A], flags=flags)

    assert lido is not None, "uma aresta visível ainda é desenho"
    assert not lido.closed
    assert _xy(lido) == esperado


def test_face_toda_oculta_e_descartada():
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        doc.modelspace().add_3dface([A, B, C, D], dxfattribs={"invisible_edges": 15})
        caminho = Path(tmp) / "face.dxf"
        doc.saveas(caminho)
        documento, descartadas = load_dxf(caminho)

    assert not documento.entities
    assert dict(getattr(descartadas, "by_type", {})).get("3DFACE") == 1


def test_face_degenerada_nao_vira_entidade():
    """Face com os quatro cantos no mesmo ponto não tem aresta nenhuma."""
    assert _le_face([A, A, A, A]) is None
