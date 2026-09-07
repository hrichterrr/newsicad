"""CLIP com contorno vazio fazia o bloco sumir da tela — e com ele o único
jeito de clicar nele. O CLIPOFF, que também depende de acertar o objeto com o
cursor, nunca mais o achava: o recorte virava irreversível fora do Ctrl+Z
(auditoria de 2026-09-07)."""

from __future__ import annotations

import pytest

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Line, Point
from newsicad.core.selection import Selection


class _ViewFalsa:
    """`nearest_entity` (o caminho de quando não há `ctx.view`) não sabe medir
    distância até BlockReference, então o hit test do canvas é imitado aqui:
    devolve o id combinado, ou nada quando o clique é no vazio."""

    def __init__(self, entity_id: str | None) -> None:
        self._entity_id = entity_id

    def _hit_test(self, _point: Point) -> str | None:
        return self._entity_id


def _cenario(acerta: bool = True):
    doc = Document()
    doc.block_definitions["CAIXA"] = [Line(start=Point(0, 0), end=Point(10, 10))]
    bloco = doc.add_entity(BlockReference(block_name="CAIXA", insertion_point=Point(0, 0)))
    ctx = CommandContext(document=doc, selection=Selection())
    ctx.view = _ViewFalsa(bloco.id if acerta else None)
    return CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES), doc, bloco


@pytest.mark.parametrize("oposto", [Point(5, 5), Point(5, 9), Point(1, 5)])
def test_clip_recusa_contorno_de_area_zero(oposto):
    interp, doc, bloco = _cenario()
    interp.start("CLIP")
    interp.submit_point(Point(5, 5))  # acerta o bloco
    interp.submit_point(Point(5, 5))
    interp.submit_point(oposto)
    assert bloco.clip_boundary is None, "contorno degenerado não podia ser aceito"


def test_clipoff_acha_o_recorte_mesmo_clicando_no_vazio():
    interp, doc, bloco = _cenario(acerta=False)
    bloco.clip_boundary = [Point(100, 100), Point(101, 100), Point(101, 101), Point(100, 101)]

    interp.start("CLIPOFF")
    interp.submit_point(Point(-500, -500))  # longe de tudo
    assert bloco.clip_boundary is None


def test_clipoff_com_varios_recortados_pede_o_numero():
    interp, doc, bloco = _cenario(acerta=False)
    outro = doc.add_entity(BlockReference(block_name="CAIXA", insertion_point=Point(50, 50)))
    fora = [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)]
    bloco.clip_boundary = list(fora)
    outro.clip_boundary = list(fora)

    interp.start("CLIPOFF")
    interp.submit_point(Point(-500, -500))
    assert "1=" in interp.current_prompt.message and "2=" in interp.current_prompt.message
    interp.submit_text("2")
    assert outro.clip_boundary is None
    assert bloco.clip_boundary is not None, "só o escolhido podia perder o recorte"


def test_clipoff_sem_nada_recortado_apenas_avisa():
    interp, doc, bloco = _cenario(acerta=False)
    interp.start("CLIPOFF")
    interp.submit_point(Point(-500, -500))
    assert not interp.active
    assert any("não há nenhum objeto recortado" in linha for linha in interp.log)
