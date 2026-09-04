"""Etapa 1 do programa de otimização (v2.15.1): "arquivo modificado?" e undo
sem copiar o documento inteiro.

Antes, `DocumentSession.is_dirty()` fazia deepcopy de entidades + camadas +
blocos e comparava com o snapshot salvo — a cada passo de comando (10 s por
clique numa planta de 43 mil entidades), e `UndoStack.push()` fazia deepcopy
de todas as entidades antes de cada comando (2,7 s). Estes testes travam o
comportamento novo: identificador de estado no lugar de cópia, e pickle no
lugar de deepcopy, com o mesmo resultado para o usuário.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.document import Document  # noqa: E402
from newsicad.core.entities import Circle, Line, Point  # noqa: E402
from newsicad.core.undo import UndoStack  # noqa: E402
from newsicad.ui.document_session import DocumentSession  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _session() -> DocumentSession:
    _app()
    return DocumentSession("Desenho1")


# ---------------------------------------------------------------- is_dirty


def test_is_dirty_nao_copia_o_documento():
    session = _session()
    for i in range(500):
        session.document.add_entity(Line(start=Point(i, 0), end=Point(i, 1)))
    session.mark_saved()
    with patch.object(copy, "deepcopy", side_effect=AssertionError("deepcopy no caminho quente")):
        assert session.is_dirty() is False
        session.undo_stack.push()
        session.document.add_entity(Circle(center=Point(0, 0), radius=1))
        assert session.is_dirty() is True
        session.mark_saved()
        assert session.is_dirty() is False


def test_undo_ate_o_estado_salvo_volta_a_ficar_limpo():
    """Igual ao QUndoStack::isClean: desfazer até o ponto salvo = limpo;
    refazer = limpo de novo; um comando novo depois de um undo = sujo para
    sempre (o redo foi descartado)."""
    session = _session()
    stack = session.undo_stack
    stack.push()
    session.document.add_entity(Circle(center=Point(0, 0), radius=1))
    session.mark_saved()

    stack.push()
    session.document.add_entity(Circle(center=Point(5, 5), radius=1))
    assert session.is_dirty() is True

    assert stack.undo() is True
    assert session.is_dirty() is False
    assert stack.redo() is True
    assert session.is_dirty() is True
    assert stack.undo() is True
    assert session.is_dirty() is False

    stack.push()
    session.document.add_entity(Circle(center=Point(9, 9), radius=1))
    assert session.is_dirty() is True
    stack.undo()
    # o undo restaurou exatamente o estado salvo: limpo de novo
    assert session.is_dirty() is False
    stack.redo()
    assert session.is_dirty() is True


def test_mudancas_de_camada_e_unidades_sujam_sem_undo():
    session = _session()
    session.mark_saved()
    layer = session.document.add_layer("PAREDES")
    assert session.is_dirty() is True  # criar camada
    session.mark_saved()

    layer.visible = False
    session.document.touch()  # o painel de camadas chama isto
    assert session.is_dirty() is True
    session.mark_saved()

    session.document.units = "m"
    assert session.is_dirty() is True
    session.mark_saved()

    session.document.rename_layer("PAREDES", "WALLS")
    assert session.is_dirty() is True


# ---------------------------------------------------------------- undo


def test_undo_nao_usa_deepcopy_e_restaura_o_desenho():
    doc = Document()
    stack = UndoStack(doc)
    with patch.object(copy, "deepcopy", side_effect=AssertionError("deepcopy no undo")):
        stack.push()
        line = doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
        stack.push()
        line.end = Point(20, 0)  # mutação em memória, como MOVE/STRETCH fazem
        doc.add_entity(Circle(center=Point(0, 0), radius=1))

        assert stack.undo() is True
        assert len(doc.entities) == 1
        restored = next(iter(doc.entities.values()))
        assert restored.end == Point(10, 0)  # o snapshot é uma cópia de verdade
        assert stack.undo() is True
        assert len(doc.entities) == 0
        assert stack.redo() is True and len(doc.entities) == 1


def test_state_id_muda_a_cada_push_e_anda_com_undo_redo():
    doc = Document()
    stack = UndoStack(doc)
    a = stack.state_id()
    stack.push()
    b = stack.state_id()
    assert b != a
    stack.undo()
    assert stack.state_id() == a
    stack.redo()
    assert stack.state_id() == b


def test_state_id_sobrevive_ao_descarte_dos_snapshots_mais_antigos():
    """Profundidade não serviria como id: quando o teto da pilha descarta o
    snapshot mais antigo, todas as posições deslocam e um estado NOVO
    ganharia o mesmo id de um estado antigo (limpo por engano = perder
    trabalho). Token único não tem esse problema."""
    from newsicad.core import undo as undo_module

    doc = Document()
    stack = UndoStack(doc)
    with patch.object(undo_module, "_MAX_UNDO_DEPTH", 3):
        vistos = set()
        for i in range(10):
            stack.push()
            doc.add_entity(Circle(center=Point(i, i), radius=1))
            token = stack.state_id()
            assert token not in vistos
            vistos.add(token)
        assert len(stack._undo_stack) == 3


def test_teto_de_memoria_do_undo_descarta_os_mais_antigos():
    from newsicad.core import undo as undo_module

    doc = Document()
    for i in range(3000):
        doc.add_entity(Line(start=Point(i, 0), end=Point(i, 1)))
    stack = UndoStack(doc)
    one = len(stack._snapshot())
    with patch.object(undo_module, "_MAX_UNDO_BYTES", one * 3):
        for _ in range(10):
            stack.push()
        assert 1 <= len(stack._undo_stack) <= 3
        assert stack.memory_bytes() <= one * 3 + one  # o redo está vazio
