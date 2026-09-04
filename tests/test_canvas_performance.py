"""Desempenho de interação no canvas (v2.14.1).

Os testes aqui travam as três decisões que fizeram a planta real voltar a ser
navegável (medições de 2026-09-03 na planta NEWSI-ANA BEATRIZ-R01, relatada
pelo grupo de testers como "lenta demais"):

* mover o mouse repinta só a vizinhança do cursor, não faixas de borda a
  borda da viewport (40 ms -> 5 ms por movimento);
* o clique de seleção consulta o índice espacial da cena antes do teste
  geométrico exato (860 ms -> 105 ms por clique);
* o destaque de seleção toca só os itens que entraram/saíram da seleção.

São testes de COMPORTAMENTO (o que é repintado, quantos candidatos passam
pelo teste exato, quais itens mudam de caneta), não de tempo de relógio —
cronômetro em teste é instável em máquina compartilhada.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.canvas import CROSSHAIR_SIZE_PERCENT, _ENTITY_ID_DATA_KEY  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def qt_canvas():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1200, 800)
    yield window.canvas
    # Sem `close()`: a janela pergunta "salvar alterações?" quando o desenho
    # está sujo, e um QMessageBox modal trava a suíte. Basta soltar a janela.
    window.hide()
    window.deleteLater()
    app.processEvents()


def _add_line(canvas, start, end):
    entity = Line(start=Point(*start), end=Point(*end))
    canvas.document.add_entity(entity)
    canvas.refresh_entities()
    return entity.id, entity


def test_cursor_region_cobre_so_a_vizinhanca_do_cursor(qt_canvas):
    """A área repintada a cada movimento do mouse é uma caixa em volta das
    posições velha e nova — não a viewport inteira. Era o oposto disso que
    deixava o mover do mouse arrastado numa planta cheia."""
    canvas = qt_canvas
    canvas.viewport().resize(1200, 800)
    region = canvas._cursor_region(QPoint(400, 300), QPoint(410, 306))
    rect = region.boundingRect()

    # Cobre as duas posições, com folga para pickbox/OSNAP/crosshair...
    assert rect.contains(QPoint(400, 300))
    assert rect.contains(QPoint(410, 306))
    # ...e é MUITO menor que a viewport (a faixa antiga tinha 1200 de largura).
    assert rect.width() < 400
    assert rect.height() < 400
    # O crosshair tem CROSSHAIR_SIZE_PERCENT% da viewport: a caixa precisa
    # comportá-lo inteiro, senão sobra rastro na tela.
    half = 1200 * CROSSHAIR_SIZE_PERCENT / 100 / 2
    assert rect.width() / 2 >= half


def test_itens_carregam_o_id_da_entidade(qt_canvas):
    """Cada item de primeiro nível guarda o id da entidade nos dados do Qt —
    é o que permite ao pré-filtro do hit-test mapear item -> entidade (em
    PySide a cena devolve wrappers novos, comparar por identidade falha)."""
    canvas = qt_canvas
    entity_id, _ = _add_line(canvas, (0, 0), (10, 0))
    item = canvas._entity_items[entity_id]
    assert item.data(_ENTITY_ID_DATA_KEY) == entity_id


def test_hit_candidates_descarta_o_que_esta_longe(qt_canvas):
    """Clicar longe de tudo não pode mandar todas as entidades para o teste
    geométrico exato: a cena já sabe que não há nada ali."""
    canvas = qt_canvas
    _add_line(canvas, (0, 0), (10, 0))
    _add_line(canvas, (0, 50), (10, 50))
    _add_line(canvas, (0, 100), (10, 100))
    tolerance = canvas._hit_tolerance_world()

    longe = list(canvas._hit_candidates(Point(500, 500), tolerance))
    assert longe == []

    perto = list(canvas._hit_candidates(Point(5, 0), tolerance))
    assert len(perto) < 3
    assert any(isinstance(entity, Line) and entity.start.y == 0 for _id, entity in perto)


def test_hit_test_continua_achando_a_entidade_sob_o_cursor(qt_canvas):
    """O pré-filtro só pode acelerar: o resultado do clique é o mesmo."""
    canvas = qt_canvas
    linha_id, _ = _add_line(canvas, (0, 0), (10, 0))
    _add_line(canvas, (0, 40), (10, 40))

    assert canvas._hit_test(Point(5, 0)) == linha_id
    assert canvas._hit_test(Point(5, 20)) is None


def test_hit_candidates_volta_a_varrer_tudo_com_a_cena_desatualizada(qt_canvas):
    """Entidade criada no meio de um comando ainda não tem item na cena —
    nesse caso o pré-filtro se desliga em vez de esconder a entidade."""
    canvas = qt_canvas
    _add_line(canvas, (0, 0), (10, 0))
    # entidade nova SEM refresh_entities: a cena fica com menos itens
    canvas.document.add_entity(Line(start=Point(0, 5), end=Point(10, 5)))

    candidatos = list(canvas._hit_candidates(Point(500, 500), canvas._hit_tolerance_world()))
    assert len(candidatos) == len(canvas.document.entities)


def test_destaque_de_selecao_toca_so_o_que_mudou(qt_canvas):
    """Selecionar uma entidade não pode custar uma varredura de todos os
    itens do desenho — só o que entrou e o que saiu da seleção."""
    canvas = qt_canvas
    id_a, _ = _add_line(canvas, (0, 0), (10, 0))
    id_b, _ = _add_line(canvas, (0, 10), (10, 10))
    selection = canvas.interpreter.context.selection

    tocados: list[str] = []
    original = canvas._apply_pen
    restaurados: list[str] = []
    original_restore = canvas._restore_base_pen

    def espiao_apply(item, pen):
        tocados.append(item.data(_ENTITY_ID_DATA_KEY))
        original(item, pen)

    def espiao_restore(item):
        restaurados.append(item.data(_ENTITY_ID_DATA_KEY))
        original_restore(item)

    canvas._apply_pen = espiao_apply
    canvas._restore_base_pen = espiao_restore

    selection.set([id_a])
    canvas.refresh_selection_highlight()
    assert tocados == [id_a]
    assert restaurados == []

    tocados.clear()
    selection.set([id_b])
    canvas.refresh_selection_highlight()
    assert tocados == [id_b]
    assert restaurados == [id_a]

def test_bloco_vira_poucos_itens_por_cor(qt_canvas):
    """A geometria de uma instância de bloco é fundida num item por cor: era
    um item gráfico por segmento (21.378 itens numa planta real), e cada
    repintura percorre item por item."""
    from newsicad.core.entities import BlockReference

    canvas = qt_canvas
    canvas.document.define_block(
        "GRADE",
        [Line(start=Point(x, 0), end=Point(x, 10)) for x in range(20)],
    )
    instancia = BlockReference(block_name="GRADE", insertion_point=Point(0, 0))
    canvas.document.add_entity(instancia)
    canvas.refresh_entities()

    grupo = canvas._entity_items[instancia.id]
    # 20 linhas da mesma cor -> um único traçado
    assert len(grupo.childItems()) == 1


def test_zoom_acumula_a_rajada_de_roda(qt_canvas):
    """Girar a roda várias vezes seguidas resulta em UM passo de zoom (um
    repaint), com o mesmo fator total."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import Qt as QtCore_Qt

    canvas = qt_canvas
    escala_inicial = canvas.transform().m11()
    for _ in range(3):
        canvas.wheelEvent(
            QWheelEvent(
                QPointF(100, 100), QPointF(100, 100), QPoint(0, 0), QPoint(0, 120),
                QtCore_Qt.MouseButton.NoButton, QtCore_Qt.KeyboardModifier.NoModifier,
                QtCore_Qt.ScrollPhase.NoScrollPhase, False,
            )
        )
    # nada aplicado ainda: só o acumulado
    assert canvas.transform().m11() == escala_inicial
    assert canvas._pending_zoom_factor > 1.0

    canvas._apply_pending_zoom()
    assert canvas.transform().m11() > escala_inicial
    assert canvas._pending_zoom_factor == 1.0
