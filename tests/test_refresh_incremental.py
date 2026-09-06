"""Etapa 6 do programa de otimização (v2.15.5): refresh incremental e undo
que preserva a identidade das entidades.

Medições de 2026-09-05 na planta NEWSI-CASA PAU BRASIL-R01 (43 mil
entidades): Ctrl+Z levava 292 s (265 s em QGraphicsScene.addItem, porque o
pickle.loads do snapshot trocava a identidade de TODAS as entidades e o
canvas recriava a cena inteira); cada passo de comando varria as 43 mil
entidades (0,4-0,6 s) e o fim de comando ainda calculava o repr() de todas
(0,95 s).
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
    win.resize(1000, 700)
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def _conta_criacoes(canvas):
    contador = {"n": 0}
    original = canvas._create_item

    def espiao(entity, color=None):
        if color is None:
            contador["n"] += 1
        return original(entity, color)

    canvas._create_item = espiao
    return contador


def _conta_visitas(canvas):
    contador = {"n": 0}
    original = canvas._effective_color

    def espiao(entity, inherited=None):
        contador["n"] += 1
        return original(entity, inherited)

    canvas._effective_color = espiao
    return contador


def test_refresh_sem_mudanca_nao_visita_nenhuma_entidade(window):
    doc, canvas = window.document, window.canvas
    for i in range(500):
        doc.add_entity(Line(start=Point(i, 0), end=Point(i, 10)))
    canvas.refresh_entities()
    visitas = _conta_visitas(canvas)
    criados = _conta_criacoes(canvas)
    canvas.refresh_entities()
    canvas.refresh_entities(full=False)
    assert visitas["n"] == 0
    assert criados["n"] == 0


def test_refresh_incremental_so_toca_o_que_mudou(window):
    doc, canvas = window.document, window.canvas
    linhas = [doc.add_entity(Line(start=Point(i, 0), end=Point(i, 10))) for i in range(300)]
    canvas.refresh_entities()
    visitas = _conta_visitas(canvas)
    criados = _conta_criacoes(canvas)

    linhas[5].end = Point(5, 99)
    nova = doc.add_entity(Circle(center=Point(0, 0), radius=3))
    doc.remove_entity(linhas[7].id)
    canvas.refresh_entities()

    # a alterada e a nova: impressao digital + criacao do item (2 visitas cada)
    assert visitas["n"] <= 4
    assert criados["n"] == 2
    assert linhas[7].id not in canvas._entity_items
    assert nova.id in canvas._entity_items
    # ordem de desenho: a nova (fim do documento) fica acima de todas
    z_nova = canvas._entity_items[nova.id].zValue()
    assert all(canvas._entity_items[l.id].zValue() < z_nova for l in linhas if l.id in canvas._entity_items)


def test_undo_preserva_identidade_e_recria_so_o_restaurado(window):
    doc, canvas = window.document, window.canvas
    linhas = [doc.add_entity(Line(start=Point(i, 0), end=Point(i, 10))) for i in range(300)]
    canvas.refresh_entities()
    apagar = {linhas[i].id for i in (3, 50, 120)}
    window.selection.set(apagar)
    window._delete_selected()
    assert len(doc.entities) == 297

    antes = {eid: e for eid, e in doc.entities.items()}
    criados = _conta_criacoes(canvas)
    window._do_undo()
    assert len(doc.entities) == 300
    # os 297 que não mudaram continuam sendo os MESMOS objetos
    assert all(doc.entities[eid] is e for eid, e in antes.items())
    assert criados["n"] == 3  # só os três restaurados ganharam item novo
    assert apagar <= set(canvas._entity_items)
    # restauradas no meio do documento: ordem de desenho renumerada e crescente
    zs = [canvas._entity_items[eid].zValue() for eid in doc.entities]
    assert zs == sorted(zs) and len(set(zs)) == len(zs)

    criados["n"] = 0
    window._do_redo()
    assert len(doc.entities) == 297
    assert criados["n"] == 0
    assert not (apagar & set(canvas._entity_items))


def test_cor_de_camada_recria_so_quem_esta_nela(window):
    doc, canvas = window.document, window.canvas
    doc.add_layer("A", "#ff0000")
    doc.add_layer("B", "#00ff00")
    a = [doc.add_entity(Line(layer="A", start=Point(i, 0), end=Point(i, 5))) for i in range(10)]
    b = [doc.add_entity(Line(layer="B", start=Point(i, 0), end=Point(i, 5))) for i in range(10)]
    doc.define_block("BL", [Circle(center=Point(0, 0), radius=1, layer="A")])
    ref = doc.add_entity(BlockReference(block_name="BL", insertion_point=Point(50, 50), layer="B"))
    canvas.refresh_entities()
    criados = _conta_criacoes(canvas)

    doc.layers["A"].color = "#0000ff"
    doc.touch()
    canvas.refresh_entities()
    # as 10 linhas de A + o bloco (usa a camada A na definição); as de B não
    assert criados["n"] == 11
    assert all(eid in canvas._entity_items for eid in (e.id for e in a + b + [ref]))


def test_comando_de_desenho_nao_recria_o_resto(window):
    doc, canvas = window.document, window.canvas
    for i in range(200):
        doc.add_entity(Line(start=Point(i, 0), end=Point(i, 10)))
    canvas.refresh_entities()
    criados = _conta_criacoes(canvas)
    visitas = _conta_visitas(canvas)
    window._handle_text_submitted("LINE")
    window._handle_canvas_point(Point(0, 0))
    window._handle_canvas_point(Point(5, 3))
    window._handle_text_submitted("")
    assert not window.interpreter.active
    assert len(doc.entities) == 201
    assert criados["n"] == 1
    assert visitas["n"] <= 4  # so a linha nova (impressao digital + criacao)
