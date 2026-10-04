"""ATTDEF solto no espaço de desenho é DESENHO, não molde.

Achado da varredura da base. Um ATTDEF dentro da definição de um bloco é um
molde: o que aparece no desenho é o ATTRIB preenchido de cada inserção. Mas
um ATTDEF SOLTO no modelspace — o que o AutoCAD cria com o comando ATTDEF
antes de você transformar aquilo num bloco — é desenho de verdade, e o
AutoCAD mostra a **TAG** dele, não o valor padrão.

O `282-PLANTA-EXE-R00.dwg` do Fernando Labes tem **413 ATTDEF soltos** no
modelspace, com tag de circuito elétrico (1P/02 em 123 deles, 2P/01 em 120,
1P/03 em 82, 2P/02 em 55) e valor padrão "X". Eram descartados sem nem
entrar na conta de "não suportadas": o projetista abria a planta elétrica
sem nenhuma identificação de circuito.

Mostrar o VALOR em vez da tag daria 413 letras "X" espalhadas pela planta —
é o que faz um renderizador que usa `plain_text()`, e não é o que o cliente
vê no AutoCAD dele.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import ezdxf

from newsicad.core.entities import BlockReference, Text
from newsicad.io.dxf_annotations import attdef_solto_como_texto
from newsicad.io.dxf_io import load_dxf


def _documento_com(attdefs_soltos: int = 1, dentro_de_bloco: bool = True):
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        for i in range(attdefs_soltos):
            msp.add_attdef(
                tag=f"1P/{i + 1:02d}", text="X", insert=(i, 1), height=0.085,
                dxfattribs={"layer": "ARQ_ELET_ILUM_TEXTO"},
            )
        if dentro_de_bloco:
            bloco = doc.blocks.new("SIMBOLO")
            bloco.add_attdef(tag="NUM", text="00", insert=(0, 0), height=2.5)
            bloco.add_line((0, 0), (1, 1))
            insercao = msp.add_blockref("SIMBOLO", (10, 10))
            insercao.add_auto_attribs({"NUM": "07"})
        caminho = Path(tmp) / "attdef.dxf"
        doc.saveas(caminho)
        return load_dxf(caminho)


def test_attdef_solto_vira_texto_com_a_tag():
    documento, descartadas = _documento_com(attdefs_soltos=1, dentro_de_bloco=False)

    textos = [e for e in documento.entities.values() if isinstance(e, Text)]
    assert len(textos) == 1
    assert textos[0].content == "1P/01", "o AutoCAD mostra a TAG, não o valor padrão"
    assert textos[0].content != "X"
    assert textos[0].layer == "ARQ_ELET_ILUM_TEXTO"
    assert not dict(getattr(descartadas, "by_type", {}))


def test_attdef_dentro_de_bloco_continua_sendo_molde():
    """A contrapartida: dentro do bloco ele NÃO pode virar desenho, senão a
    etiqueta aparece duplicada (o molde mais o valor preenchido)."""
    documento, _ = _documento_com(attdefs_soltos=0, dentro_de_bloco=True)

    assert documento.block_attdefs.get("SIMBOLO")
    assert [a.tag for a in documento.block_attdefs["SIMBOLO"]] == ["NUM"]
    soltos = [e for e in documento.entities.values() if isinstance(e, Text)]
    assert not soltos, "o molde do bloco não pode virar texto no desenho"
    blocos = [e for e in documento.entities.values() if isinstance(e, BlockReference)]
    assert len(blocos) == 1


def test_os_dois_casos_convivem_no_mesmo_arquivo():
    documento, _ = _documento_com(attdefs_soltos=3, dentro_de_bloco=True)

    textos = [e for e in documento.entities.values() if isinstance(e, Text)]
    assert sorted(t.content for t in textos) == ["1P/01", "1P/02", "1P/03"]
    assert [a.tag for a in documento.block_attdefs["SIMBOLO"]] == ["NUM"]


def test_attdef_sem_tag_nao_vira_texto():
    """Sem tag não há o que desenhar."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        doc.modelspace().add_attdef(tag="", text="X", insert=(0, 0), height=2.5)
        caminho = Path(tmp) / "sem_tag.dxf"
        doc.saveas(caminho)
        documento, _ = load_dxf(caminho)

    assert not [e for e in documento.entities.values() if isinstance(e, Text)]


class _AttdefMinimo:
    """O bastante para o guarda de altura: o ezdxf tem validador que recusa
    altura zero num ATTDEF (ele conserta para a altura do estilo), então esse
    caso não dá para construir pela API dele — mas o `dwg2dxf` produz, e o
    AutoCAD não desenha um texto de altura zero."""

    def __init__(self, **campos):
        self.dxf = self
        self._campos = campos

    def get(self, nome, padrao=None):
        return self._campos.get(nome, padrao)

    def dxftype(self):
        return "ATTDEF"


def test_attdef_sem_altura_nao_vira_texto():
    assert attdef_solto_como_texto(_AttdefMinimo(tag="SEM_ALTURA", text="X", height=0.0)) is None
    assert attdef_solto_como_texto(_AttdefMinimo(tag="", text="X", height=2.5)) is None


def test_attdef_solto_na_prancha_tambem_desenha():
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.new("R2010")
        prancha = doc.layouts.get("Layout1")
        prancha.add_attdef(tag="REV/01", text="X", insert=(5, 5), height=2.5)
        caminho = Path(tmp) / "prancha.dxf"
        doc.saveas(caminho)
        documento, _ = load_dxf(caminho)

    da_prancha = list(documento.layouts.get("Layout1", {}).values())
    assert [e.content for e in da_prancha if isinstance(e, Text)] == ["REV/01"]
