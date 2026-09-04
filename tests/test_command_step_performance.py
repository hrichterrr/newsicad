"""Etapa 3 do programa de otimização (v2.15.2): o que roda a cada passo de
comando não pode custar uma varredura do desenho inteiro.

Medições de 2026-09-04 na planta NEWSI-CASA PAU BRASIL-R01: `zoom_extents`
recalculava a bbox de todas as entidades em Python (2,09 s) e o painel de
camadas era reconstruído a cada passo (0,25 s), sem nada ter mudado.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import BlockReference, Circle, Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1200, 800)
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def test_extents_usa_os_itens_da_cena_e_ignora_camada_oculta(window):
    doc, canvas = window.document, window.canvas
    doc.add_layer("LONGE")
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 10)))
    doc.add_entity(Line(layer="LONGE", start=Point(0, 0), end=Point(1000, 1000)))
    doc.define_block("B", [Circle(center=Point(0, 0), radius=5)])
    doc.add_entity(BlockReference(block_name="B", insertion_point=Point(50, 50)))
    canvas.refresh_entities()

    chamadas = {"n": 0}
    original = canvas._entity_bbox_scene

    def espiao(entity):
        chamadas["n"] += 1
        return original(entity)

    canvas._entity_bbox_scene = espiao

    tudo = canvas.compute_extents_rect(margin_ratio=0.0)
    assert chamadas["n"] == 0  # veio dos itens, não da geometria em Python
    # os itens incluem a espessura cosmética da caneta (~1 unidade por lado)
    assert tudo.width() == pytest.approx(1000, abs=3)

    doc.layers["LONGE"].visible = False
    canvas.apply_layer_visibility()
    sem = canvas.compute_extents_rect(margin_ratio=0.0)
    assert sem.width() < 100  # a linha longa escondida não conta
    assert sem.width() >= 55 - 1  # bloco em (50,50) raio 5 continua contando


def test_extents_cai_na_geometria_quando_a_cena_esta_desatualizada(window):
    doc, canvas = window.document, window.canvas
    doc.add_entity(Line(start=Point(0, 0), end=Point(10, 0)))
    canvas.refresh_entities()
    doc.add_entity(Line(start=Point(0, 0), end=Point(500, 0)))  # sem refresh
    rect = canvas.compute_extents_rect(margin_ratio=0.0)
    assert rect.width() == pytest.approx(500, abs=3)


def test_painel_de_camadas_so_reconstroi_quando_algo_de_camada_muda(window):
    chamadas = {"n": 0}
    original = window.layer_dock.refresh

    def espiao():
        chamadas["n"] += 1
        original()

    window.layer_dock.refresh = espiao

    window._after_interpreter_step()
    primeira = chamadas["n"]
    window._after_interpreter_step()
    window._after_interpreter_step()
    assert chamadas["n"] == primeira  # nada mudou: nada reconstruído

    window.document.add_layer("NOVA")
    window._after_interpreter_step()
    assert chamadas["n"] == primeira + 1

    window.document.set_current_layer("NOVA")
    window._after_interpreter_step()
    assert chamadas["n"] == primeira + 2

    window.document.layers["NOVA"].color = "#FF0000"
    window.document.touch()
    window._after_interpreter_step()
    assert chamadas["n"] == primeira + 3
