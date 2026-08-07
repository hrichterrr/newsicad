"""Testes de newsicad/core/document.py: camadas (visibilidade/trava) e as
funções puras usadas pelo canvas e pelo painel de camadas pra decidir o que
renderizar/selecionar (`is_layer_visible`/`is_layer_locked`)."""

from __future__ import annotations

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Line, Point


def test_new_layer_defaults_visible_and_unlocked():
    document = Document()
    layer = document.add_layer("PAREDES")
    assert layer.visible is True
    assert layer.locked is False


def test_is_layer_visible_true_by_default():
    document = Document()
    entity = document.add_entity(Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0)))
    assert document.is_layer_visible(entity) is True
    assert document.is_layer_locked(entity) is False


def test_is_layer_visible_false_after_hiding_layer():
    document = Document()
    entity = document.add_entity(Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0)))
    document.layers["PAREDES"].visible = False
    assert document.is_layer_visible(entity) is False


def test_is_layer_locked_true_after_locking_layer():
    document = Document()
    entity = document.add_entity(Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0)))
    document.layers["PAREDES"].locked = True
    assert document.is_layer_locked(entity) is True
    # Trancar não esconde — só impede seleção (ver testes de canvas).
    assert document.is_layer_visible(entity) is True


def test_is_layer_visible_treats_entity_on_unknown_layer_as_visible():
    """Entidade cujo `entity.layer` não está em `document.layers` (não deveria
    acontecer via add_entity normal, mas é um estado defensivo razoável)
    não deve travar/sumir por causa de um lookup ausente."""
    document = Document()
    entity = Line(layer="INEXISTENTE", start=Point(0, 0), end=Point(1, 0))
    assert document.is_layer_visible(entity) is True
    assert document.is_layer_locked(entity) is False


def test_add_entity_never_overrides_an_explicitly_set_layer():
    """`Document.add_entity` só cai pro current_layer se `entity.layer` for
    "falsy" (nunca acontece via construção normal, já que o default do
    dataclass é "0", não vazio) — de propósito: precisa preservar o layer
    exato de uma entidade vinda de um .dxf carregado, mesmo que seja "0" e o
    current_layer no momento seja outro. Quem precisa aplicar o current_layer
    a uma entidade nova de verdade (LINE, CIRCLE, MTEXT...) faz isso
    explicitamente ao construir a entidade — ver commands/draw_commands.py,
    annotation_commands.py e block_commands.py."""
    document = Document()
    document.add_layer("ELETRICA")
    document.set_current_layer("ELETRICA")

    entity = document.add_entity(Line(start=Point(0, 0), end=Point(1, 0)))
    assert entity.layer == "0"

    entity_on_current = document.add_entity(
        Line(start=Point(0, 0), end=Point(1, 0), layer=document.current_layer)
    )
    assert entity_on_current.layer == "ELETRICA"


# ---------------------------------------------------------------------- #
# rename_layer (RENAME/REN) e purge_unused_layers/purge_unused_blocks (PURGE/PU)
# ---------------------------------------------------------------------- #
def test_rename_layer_updates_entities_and_current_layer():
    document = Document()
    document.add_layer("PAREDES")
    document.set_current_layer("PAREDES")
    entity = document.add_entity(Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0)))

    document.rename_layer("PAREDES", "ALVENARIA")

    assert "PAREDES" not in document.layers
    assert "ALVENARIA" in document.layers
    assert entity.layer == "ALVENARIA"
    assert document.current_layer == "ALVENARIA"


def test_rename_layer_updates_entities_inside_block_definitions():
    document = Document()
    document.add_layer("PAREDES")
    block_line = Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0))
    document.define_block("CHAIR", [block_line])

    document.rename_layer("PAREDES", "ALVENARIA")
    assert block_line.layer == "ALVENARIA"


def test_rename_layer_rejects_layer_zero():
    document = Document()
    with pytest.raises(ValueError):
        document.rename_layer("0", "QUALQUER")


def test_rename_layer_rejects_duplicate_name():
    document = Document()
    document.add_layer("A")
    document.add_layer("B")
    with pytest.raises(ValueError):
        document.rename_layer("A", "B")


def test_purge_unused_layers_removes_layer_with_no_entities():
    document = Document()
    document.add_layer("SEM_USO")
    document.add_entity(Line(layer="0", start=Point(0, 0), end=Point(1, 0)))

    removed = document.purge_unused_layers()

    assert removed == ["SEM_USO"]
    assert "SEM_USO" not in document.layers


def test_purge_unused_layers_never_removes_layer_zero():
    document = Document()
    removed = document.purge_unused_layers()
    assert "0" not in removed
    assert "0" in document.layers


def test_purge_unused_layers_keeps_layer_used_inside_a_block_definition():
    document = Document()
    document.add_layer("PAREDES")
    document.define_block("CHAIR", [Line(layer="PAREDES", start=Point(0, 0), end=Point(1, 0))])

    removed = document.purge_unused_layers()
    assert "PAREDES" not in removed
    assert "PAREDES" in document.layers


def test_purge_unused_layers_resets_current_layer_to_zero():
    document = Document()
    document.add_layer("SEM_USO")
    document.set_current_layer("SEM_USO")

    document.purge_unused_layers()
    assert document.current_layer == "0"


def test_purge_unused_blocks_removes_block_with_no_references():
    document = Document()
    document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 0))])

    removed = document.purge_unused_blocks()
    assert removed == ["CHAIR"]
    assert "CHAIR" not in document.block_definitions


def test_purge_unused_blocks_keeps_block_with_a_reference():
    document = Document()
    document.define_block("CHAIR", [Line(start=Point(0, 0), end=Point(1, 0))])
    document.add_entity(BlockReference(block_name="CHAIR", insertion_point=Point(0, 0)))

    removed = document.purge_unused_blocks()
    assert removed == []
    assert "CHAIR" in document.block_definitions
