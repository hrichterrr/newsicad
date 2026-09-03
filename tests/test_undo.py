from newsicad.core.document import Document
from newsicad.core.entities import Circle, Point
from newsicad.core.undo import UndoStack


def test_undo_restores_previous_state():
    doc = Document()
    stack = UndoStack(doc)

    stack.push()  # snapshot: vazio
    doc.add_entity(Circle(center=Point(0, 0), radius=1))
    assert len(doc.entities) == 1

    assert stack.undo() is True
    assert len(doc.entities) == 0


def test_redo_reapplies_undone_state():
    doc = Document()
    stack = UndoStack(doc)

    stack.push()
    doc.add_entity(Circle(center=Point(0, 0), radius=1))
    stack.undo()
    assert len(doc.entities) == 0

    assert stack.redo() is True
    assert len(doc.entities) == 1


def test_undo_with_empty_stack_returns_false():
    doc = Document()
    stack = UndoStack(doc)
    assert stack.undo() is False


def test_new_push_clears_redo_stack():
    doc = Document()
    stack = UndoStack(doc)

    stack.push()
    doc.add_entity(Circle(center=Point(0, 0), radius=1))
    stack.undo()

    stack.push()  # nova ação depois de um undo invalida o redo
    assert stack.redo() is False


def test_undo_stack_depth_is_capped_not_unbounded():
    from newsicad.core.undo import _MAX_UNDO_DEPTH

    doc = Document()
    stack = UndoStack(doc)

    for _ in range(_MAX_UNDO_DEPTH + 50):
        stack.push()
        doc.add_entity(Circle(center=Point(0, 0), radius=1))

    assert len(stack._undo_stack) == _MAX_UNDO_DEPTH
    # ainda funciona normalmente depois do teto ser atingido (só descarta o
    # mais antigo, não trava nem perde o undo mais recente)
    total_before = len(doc.entities)
    assert stack.undo() is True
    assert len(doc.entities) == total_before - 1
