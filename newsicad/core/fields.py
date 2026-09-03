"""Comando FIELD: texto (`Text`) cujo conteúdo é recalculado a partir de um
valor vivo em vez de digitado — subconjunto pragmático do FIELD de verdade do
AutoCAD (que tem dezenas de categorias). Suporta os três tipos mais úteis num
CAD 2D: AREA/LENGTH (vinculados a uma entidade via `Text.field_ref`) e DATE
(sem referência). FILENAME ficou de fora: exigiria plumbing do caminho do
arquivo até `CommandContext`, que hoje só conhece `Document` (ver README)."""

from __future__ import annotations

import math
from datetime import date

from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Entity, LWPolyline, Text

#: Tipos de FIELD suportados (comparados em UPPERCASE — mesma normalização
#: que o interpretador já aplica a respostas `kind="keyword"`).
FIELD_TYPES = ("AREA", "LENGTH", "DATE")

_MISSING_REF = "#REF!"


def field_supports_reference(field_type: str) -> bool:
    """AREA/LENGTH precisam de uma entidade selecionada (`field_ref`); DATE
    não referencia nada."""
    return field_type in ("AREA", "LENGTH")


def _entity_area(entity: Entity) -> float | None:
    if isinstance(entity, Circle):
        return math.pi * entity.radius**2
    if isinstance(entity, LWPolyline) and entity.closed and len(entity.points) >= 3:
        from newsicad.core.geometry_ops import polygon_area

        return polygon_area(entity.points)
    return None


def _entity_length(entity: Entity) -> float | None:
    if hasattr(entity, "length") and callable(entity.length):
        return entity.length()
    if isinstance(entity, Circle):
        return 2 * math.pi * entity.radius
    if isinstance(entity, Arc):
        sweep = (entity.end_angle - entity.start_angle) % (2 * math.pi)
        return entity.radius * sweep
    if isinstance(entity, LWPolyline):
        from newsicad.core.geometry_ops import polygon_perimeter

        return polygon_perimeter(entity.points, entity.closed)
    return None


def compute_field_value(field_type: str, document: Document, ref_id: str | None) -> str:
    """Valor de exibição atual para `field_type` — chamado tanto pelo comando
    FIELD (preview inicial) quanto por `CanvasView.refresh_entities()` (valor
    sempre em dia a cada redesenho, sem precisar de um "atualizar campos")."""
    field_type = field_type.upper()
    if field_type == "DATE":
        return date.today().strftime("%d/%m/%Y")

    entity = document.entities.get(ref_id or "")
    if entity is None:
        return _MISSING_REF

    if field_type == "AREA":
        area = _entity_area(entity)
        return f"{area:.2f} m²" if area is not None else _MISSING_REF
    if field_type == "LENGTH":
        length = _entity_length(entity)
        return f"{length:.2f} m" if length is not None else _MISSING_REF
    return _MISSING_REF


def resolve_field_text(text: Text, document: Document) -> str:
    """Conteúdo a exibir/gravar para `text`: o valor vivo se for um FIELD,
    senão o `content` digitado normalmente."""
    if not text.field_type:
        return text.content
    return compute_field_value(text.field_type, document, text.field_ref)
