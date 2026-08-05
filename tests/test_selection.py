from newsicad.core.document import Document
from newsicad.core.entities import Circle, Point
from newsicad.core.selection import Selection


def test_add_and_entities():
    doc = Document()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=1))
    sel = Selection()
    sel.add(circle.id)
    assert sel.entities(doc) == [circle]


def test_toggle():
    sel = Selection()
    sel.toggle("a")
    assert "a" in sel.ids
    sel.toggle("a")
    assert "a" not in sel.ids


def test_remove_missing_is_noop():
    sel = Selection()
    sel.remove("nope")  # não deve lançar exceção
    assert sel.ids == set()


def test_entities_skips_deleted_ids():
    doc = Document()
    circle = doc.add_entity(Circle(center=Point(0, 0), radius=1))
    sel = Selection()
    sel.add(circle.id)
    doc.remove_entity(circle.id)
    assert sel.entities(doc) == []


def test_clear():
    sel = Selection()
    sel.set({"a", "b"})
    sel.clear()
    assert sel.ids == set()
