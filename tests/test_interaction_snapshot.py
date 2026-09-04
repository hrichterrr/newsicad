"""Etapa 5 do programa de otimização (v2.15.4): arrastar e zoom mostram um
retrato da viewport em vez de repintar a cena a cada evento.

Na Casa Pau Brasil (50 mil itens) repintar custa 60 ms por evento de arrasto
e 170 ms por passo de zoom — o teto do raster. Durante a interação a tela
mostra o pixmap deslocado/escalado; a repintura de verdade acontece uma vez,
quando a mão para (soltar o botão do meio / fim da rajada de roda).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1000, 700)
    for i in range(50):
        win.document.add_entity(Line(start=Point(i * 10, 0), end=Point(i * 10, 500)))
    win.canvas.refresh_entities()
    win.show()
    app.processEvents()
    yield win.canvas
    win.hide()
    win.deleteLater()
    app.processEvents()


def _mouse(canvas, typ, pos, button, buttons):
    ev = QMouseEvent(typ, QPointF(pos), QPointF(pos), button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(canvas.viewport(), ev)


def test_arrastar_desloca_o_retrato_e_so_rola_ao_soltar(canvas):
    app = QApplication.instance()
    h0, v0 = canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value()

    _mouse(canvas, QEvent.Type.MouseButtonPress, QPoint(400, 300), Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton)
    _mouse(canvas, QEvent.Type.MouseMove, QPoint(430, 310), Qt.MouseButton.NoButton, Qt.MouseButton.MiddleButton)
    _mouse(canvas, QEvent.Type.MouseMove, QPoint(460, 320), Qt.MouseButton.NoButton, Qt.MouseButton.MiddleButton)
    app.processEvents()

    assert canvas._snapshot is not None  # retrato em uso
    assert canvas._snapshot_offset == QPoint(60, 20)
    # as barras de rolagem NÃO se mexeram durante o arrasto
    assert (canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value()) == (h0, v0)

    _mouse(canvas, QEvent.Type.MouseButtonRelease, QPoint(460, 320), Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton)
    app.processEvents()
    assert canvas._snapshot is None
    assert canvas._snapshot_offset == QPoint(0, 0)
    # ...e ao soltar, rolaram o total acumulado (se houver espaço de rolagem)
    hs, vs = canvas.horizontalScrollBar(), canvas.verticalScrollBar()
    if hs.maximum() > hs.minimum():
        assert hs.value() == max(hs.minimum(), min(hs.maximum(), h0 - 60))
    if vs.maximum() > vs.minimum():
        assert vs.value() == max(vs.minimum(), min(vs.maximum(), v0 - 20))


def test_zoom_escala_o_retrato_e_aplica_de_uma_vez(canvas):
    app = QApplication.instance()
    escala0 = canvas.transform().m11()
    for _ in range(3):
        canvas.wheelEvent(
            QWheelEvent(QPointF(500, 350), QPointF(500, 350), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
        )
    app.processEvents()
    assert canvas._snapshot is not None
    assert canvas._snapshot_scale == pytest.approx(1.15 ** 3)
    assert canvas.transform().m11() == escala0  # ainda não aplicado

    canvas._apply_pending_zoom()
    assert canvas._snapshot is None
    assert canvas.transform().m11() == pytest.approx(escala0 * 1.15 ** 3)


def test_pintura_normal_volta_depois_da_interacao(canvas):
    """Sem retrato ativo, paintEvent é o do QGraphicsView (a cena é pintada)."""
    app = QApplication.instance()
    canvas._begin_snapshot()
    assert canvas._snapshot is not None
    canvas._end_pan_snapshot()
    app.processEvents()
    assert canvas._snapshot is None
    canvas.viewport().update()
    app.processEvents()  # não pode levantar exceção
