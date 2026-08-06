"""Testes de newsicad/core/document.py: camadas (visibilidade/trava) e as
funções puras usadas pelo canvas e pelo painel de camadas pra decidir o que
renderizar/selecionar (`is_layer_visible`/`is_layer_locked`)."""

from __future__ import annotations

from newsicad.core.document import Document
from newsicad.core.entities import Line, Point


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
