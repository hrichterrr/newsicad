"""Só o bloco anônimo "*U" era carregado. Na amostra oficial
"blocks_and_tables" da Autodesk, 38 das 161 inserções apontavam para "*B13" a
"*B37" — a cópia anônima que o AutoCAD cria para um bloco COM ATRIBUTOS cujos
valores são únicos por instância. Sumiam 3 vasos, 3 pias, 19 interruptores,
fogão, geladeira e 11 portas (840 traços) sem aviso nenhum, e ao gravar os 38
INSERT saíam apontando para blocos inexistentes — um .dxf que o `ezdxf.audit`
reprova (auditoria de 07/09/2026).
"""

from __future__ import annotations

import ezdxf
import pytest

from newsicad.core.entities import BlockReference, Line
from newsicad.io.dxf_io import load_dxf, save_dxf


def _desenho_com_blocos_anonimos(tmp_path):
    doc = ezdxf.new("R2018")
    for nome in ("*B1", "*U1", "*T1", "*D1", "*X1"):
        bloco = doc.blocks.new(name=nome)
        bloco.add_line((0, 0), (1, 1))
    ms = doc.modelspace()
    for nome in ("*B1", "*U1"):
        ms.add_blockref(nome, (0, 0))
    caminho = tmp_path / "anon.dxf"
    doc.saveas(str(caminho))
    return caminho


@pytest.mark.parametrize("nome", ["*B1", "*U1", "*T1"])
def test_bloco_anonimo_de_usuario_e_carregado(tmp_path, nome):
    doc, _ = load_dxf(_desenho_com_blocos_anonimos(tmp_path))
    assert nome in doc.block_definitions
    assert len(doc.block_definitions[nome]) == 1


@pytest.mark.parametrize("nome", ["*D1", "*X1"])
def test_tripas_do_autocad_continuam_de_fora(tmp_path, nome):
    """"*D" é geometria interna de cota e "*X" é hachura associativa — o
    AutoCAD as remonta sozinho, não são desenho do usuário."""
    doc, _ = load_dxf(_desenho_com_blocos_anonimos(tmp_path))
    assert nome not in doc.block_definitions


def test_nenhuma_insercao_fica_sem_definicao(tmp_path):
    doc, ignoradas = load_dxf(_desenho_com_blocos_anonimos(tmp_path))
    orfas = [
        e for e in doc.all_entities()
        if isinstance(e, BlockReference) and e.block_name not in doc.block_definitions
    ]
    assert orfas == []
    assert not any("apontam para" in nota for nota in getattr(ignoradas, "notes", []))


def test_gravar_nao_produz_insercao_sem_bloco(tmp_path):
    doc, _ = load_dxf(_desenho_com_blocos_anonimos(tmp_path))
    saida = tmp_path / "saida.dxf"
    save_dxf(doc, saida)
    gravado = ezdxf.readfile(str(saida))
    auditoria = gravado.audit()
    assert auditoria.errors == []
    assert auditoria.fixes == [], "INSERT sem BLOCK é descartado pelo AutoCAD"


def test_insercao_orfa_vira_aviso(tmp_path):
    """Rede de segurança: se ainda assim sobrar INSERT sem definição, o
    usuário tem de saber — antes só via um buraco na planta."""
    origem = ezdxf.new("R2018")
    bloco = origem.blocks.new(name="*D9")  # descartado de propósito
    bloco.add_line((0, 0), (1, 1))
    origem.modelspace().add_blockref("*D9", (0, 0))
    caminho = tmp_path / "orfa.dxf"
    origem.saveas(str(caminho))

    _doc, ignoradas = load_dxf(caminho)
    notas = list(getattr(ignoradas, "notes", []))
    assert any("*D9" in nota and "não aparecem no desenho" in nota for nota in notas), notas
