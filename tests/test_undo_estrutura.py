"""O undo cobre também o que NÃO é entidade: definições de bloco, camadas,
unidades e estilos.

Auditoria de 2026-09-07: `UndoStack._snapshot` fotografava só
`document.entities`. Redefinir um bloco por engano era irreversível, e desfazer
um PURGE devolvia as entidades sem devolver a definição de bloco nem a camada —
sobrava INSERT órfão e entidade em camada inexistente, e o .dxf gravado assim é
reprovado pelo `ezdxf.audit`.
"""

from __future__ import annotations

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Circle, Line, LWPolyline, Point
from newsicad.core.undo import UndoStack


@pytest.fixture
def doc():
    return Document()


def test_redefinir_bloco_e_reversivel(doc):
    doc.define_block("SENSOR", [Circle(center=Point(0, 0), radius=1)])
    doc.add_entity(BlockReference(block_name="SENSOR", insertion_point=Point(5, 5)))
    undo = UndoStack(doc)

    undo.push()
    doc.define_block("SENSOR", [LWPolyline(points=[Point(0, 0), Point(1, 1)], closed=True)])
    assert [type(e).__name__ for e in doc.block_definitions["SENSOR"]] == ["LWPolyline"]

    assert undo.undo()
    assert [type(e).__name__ for e in doc.block_definitions["SENSOR"]] == ["Circle"]

    assert undo.redo()
    assert [type(e).__name__ for e in doc.block_definitions["SENSOR"]] == ["LWPolyline"]


def test_desfazer_purge_devolve_definicao_e_camada(doc):
    doc.add_layer("ELETRICA", "#ff0000")
    doc.define_block("S", [Circle(center=Point(0, 0), radius=1)])
    ref = doc.add_entity(BlockReference(block_name="S", insertion_point=Point(0, 0)))
    linha = doc.add_entity(Line(layer="ELETRICA", start=Point(0, 0), end=Point(1, 1)))
    undo = UndoStack(doc)

    undo.push()
    doc.remove_entity(ref.id)
    doc.remove_entity(linha.id)
    undo.push()
    doc.purge_unused_blocks()
    doc.purge_unused_layers()

    assert "S" not in doc.block_definitions
    assert "ELETRICA" not in doc.layers

    assert undo.undo()  # desfaz o purge
    assert undo.undo()  # devolve as entidades
    assert "S" in doc.block_definitions, "INSERT ficaria órfão"
    assert "ELETRICA" in doc.layers, "entidade ficaria em camada inexistente"
    assert all(e.layer in doc.layers for e in doc.all_entities())
    assert all(
        e.block_name in doc.block_definitions
        for e in doc.all_entities()
        if isinstance(e, BlockReference)
    )


def test_undo_devolve_cor_e_visibilidade_de_camada(doc):
    doc.add_layer("A", "#111111")
    undo = UndoStack(doc)
    undo.push()
    doc.layers["A"].color = "#999999"
    doc.layers["A"].visible = False
    doc.touch()

    assert undo.undo()
    assert doc.layers["A"].color == "#111111"
    assert doc.layers["A"].visible is True


def test_undo_sem_mudanca_de_estrutura_nao_mexe_na_revisao(doc):
    """A revisão é o que diz se o arquivo está modificado — um undo que só
    mexe em entidade não pode fazê-la avançar."""
    linha = doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1)))
    undo = UndoStack(doc)
    revisao = doc.revision

    undo.push()
    linha.end = Point(9, 9)
    undo.undo()

    assert doc.revision == revisao
    assert doc.entities[linha.id].end == Point(1, 1)


def test_estrutura_e_compartilhada_entre_passos(doc):
    """Fotografar as definições de bloco a cada comando seria caro; enquanto
    nada de estrutura muda, todos os passos usam o MESMO objeto."""
    doc.define_block("B", [Circle(center=Point(0, 0), radius=1) for _ in range(50)])
    undo = UndoStack(doc)
    for i in range(5):
        undo.push()
        doc.add_entity(Line(start=Point(i, 0), end=Point(i, 1)))
    estruturas = {id(entrada[1]) for entrada in undo._undo_stack}
    assert len(estruturas) == 1
