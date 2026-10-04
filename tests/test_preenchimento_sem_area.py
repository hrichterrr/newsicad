"""Preenchimento de área zero não é entidade perdida.

Achado da varredura da base em 03/10/2026, e o valor dele está em NÃO
consertar o que parecia defeito. A varredura acusava 4.579 SOLID e 1.229
HATCH "não lidos" em 14 arquivos cada — números grandes o bastante para
parecer o pior defeito aberto. Olhando um por um:

    SOLID  recusado: [(22.657, 22.480), (23.009, 22.480), (23.009, 22.480)]
    HATCH  recusado: contorno A -> B -> A, três vezes seguidas

São polígonos de DOIS cantos distintos: área zero. Não há o que preencher, e
o AutoCAD também não desenha nada (o preenchimento é o padrão, FILLMODE
ligado). Vêm aos milhares de arquivo importado de PDF — as camadas das
hachuras recusadas começam com `PDF2_`.

Recusá-los estava certo. O que estava errado era CONTÁ-LOS como entidade
perdida no aviso de abertura: o projetista do Carla e Raymond abria o
projeto e lia que o programa tinha comido 2.146 coisas do arquivo dele, sem
ter comido nenhuma. Depois deste conserto o aviso desse arquivo caiu para
uma entidade, e o do Escritório H&M de 1.080 para zero.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf

from newsicad.io.dxf_io import load_dxf, nada_a_desenhar


def _descartadas(construir) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        construir(doc.modelspace())
        caminho = Path(tmp) / "fill.dxf"
        doc.saveas(caminho)
        _documento, descartadas = load_dxf(caminho)
        return dict(getattr(descartadas, "by_type", {}) or {})


def test_solid_de_area_zero_nao_conta_como_perdido():
    def construir(msp):
        # o terceiro canto repete o segundo: triângulo degenerado = reta
        msp.add_solid([(0, 0), (10, 0), (10, 0)])

    assert _descartadas(construir) == {}


def test_solid_de_verdade_continua_entrando():
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        doc.modelspace().add_solid([(0, 0), (10, 0), (10, 10), (0, 10)])
        caminho = Path(tmp) / "solid.dxf"
        doc.saveas(caminho)
        documento, descartadas = load_dxf(caminho)

    assert not dict(getattr(descartadas, "by_type", {}) or {})
    assert len(documento.entities) == 1, "SOLID com área vira Hatch sólida"


def test_hatch_cujo_contorno_vai_e_volta_nao_conta_como_perdida():
    def construir(msp):
        hatch = msp.add_hatch()
        hatch.paths.add_polyline_path([(5, 5), (15, 5), (5, 5)], is_closed=True)

    assert _descartadas(construir) == {}


def test_hatch_com_um_contorno_de_area_ja_desenha():
    """Basta UM contorno com área: o resto pode ser degenerado."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        hatch = doc.modelspace().add_hatch()
        hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10)], is_closed=True)
        hatch.paths.add_polyline_path([(5, 5), (15, 5), (5, 5)], is_closed=True)
        caminho = Path(tmp) / "mista.dxf"
        doc.saveas(caminho)
        documento, descartadas = load_dxf(caminho)

    assert not dict(getattr(descartadas, "by_type", {}) or {})
    assert len(documento.entities) == 1


def test_nada_a_desenhar_nao_mente_sobre_outros_tipos():
    """A regra é só para preenchimento e texto — uma LINE nunca pode ser
    classificada como 'não desenha nada'."""
    doc = ezdxf.new("R2010")
    linha = doc.modelspace().add_line((0, 0), (1, 1))
    circulo = doc.modelspace().add_circle((0, 0), 5)

    assert not nada_a_desenhar(linha)
    assert not nada_a_desenhar(circulo)
