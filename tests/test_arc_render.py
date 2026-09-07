"""O arco desenhado tem de cair no mesmo lugar que a geometria diz.

Defeito achado na auditoria de 2026-09-07 e presente desde o commit inicial:
`cad_to_scene` inverte o Y do centro e o código negava também o ângulo do
`arcTo`, uma segunda inversão — todo arco saía espelhado na horizontal que
passa pelo centro. Um arco de 0° a 90°, que ocupa o primeiro quadrante no
DXF e no AutoCAD, era desenhado no quarto.
"""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Arc, Point  # noqa: E402
from newsicad.ui.canvas import _plain_entity_path, cad_to_scene  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    yield win
    win.hide()
    win.deleteLater()
    app.processEvents()


def _ponto_cad(arco: Arc, angulo: float) -> Point:
    """Onde a geometria diz que o arco passa, nesse ângulo (é a mesma conta
    que DIVIDE/MEASURE usam em core/geometry_ops.py)."""
    return Point(
        arco.center.x + arco.radius * math.cos(angulo),
        arco.center.y + arco.radius * math.sin(angulo),
    )


CASOS = [
    (0.0, math.pi / 2),                 # primeiro quadrante
    (math.pi / 2, math.pi),             # segundo
    (math.pi, 3 * math.pi / 2),         # terceiro
    (3 * math.pi / 2, 2 * math.pi),     # quarto
    (math.radians(30), math.radians(300)),  # varredura longa, cruzando 0°
]


@pytest.mark.parametrize("inicio,fim", CASOS)
def test_tracado_do_arco_comeca_e_termina_onde_a_geometria_diz(inicio, fim):
    arco = Arc(center=Point(3, -7), radius=10, start_angle=inicio, end_angle=fim)
    path = _plain_entity_path(arco)
    assert path is not None

    esperado_ini = cad_to_scene(_ponto_cad(arco, inicio))
    esperado_fim = cad_to_scene(_ponto_cad(arco, fim))
    obtido_ini = path.elementAt(0)
    obtido_fim = path.elementAt(path.elementCount() - 1)

    assert obtido_ini.x == pytest.approx(esperado_ini.x(), abs=0.05)
    assert obtido_ini.y == pytest.approx(esperado_ini.y(), abs=0.05)
    assert obtido_fim.x == pytest.approx(esperado_fim.x(), abs=0.05)
    assert obtido_fim.y == pytest.approx(esperado_fim.y(), abs=0.05)


def test_arco_de_um_quadrante_fica_no_quadrante_certo():
    """Guarda contra a inversão dupla voltar: o arco de 0° a 90° em torno da
    origem tem de ficar inteiro em x>=0 e y>=0 (CAD)."""
    arco = Arc(center=Point(0, 0), radius=10, start_angle=0.0, end_angle=math.pi / 2)
    caixa = _plain_entity_path(arco).boundingRect()
    # cena: y invertido, então o primeiro quadrante do CAD é y <= 0 na cena
    assert caixa.left() >= -0.05 and caixa.right() == pytest.approx(10, abs=0.05)
    assert caixa.bottom() <= 0.05 and caixa.top() == pytest.approx(-10, abs=0.05)


def test_item_do_canvas_usa_o_mesmo_tracado_do_caminho_simples(window):
    """O arco tem duas implementações (o item do canvas e o traçado usado na
    fusão dentro de blocos); as duas têm de concordar."""
    arco = window.document.add_entity(
        Arc(center=Point(1, 2), radius=4, start_angle=math.radians(20), end_angle=math.radians(200))
    )
    window.canvas.refresh_entities()
    do_item = window.canvas._entity_items[arco.id].path().boundingRect()
    do_caminho = _plain_entity_path(arco).boundingRect()
    assert do_item.topLeft().x() == pytest.approx(do_caminho.topLeft().x(), abs=0.05)
    assert do_item.topLeft().y() == pytest.approx(do_caminho.topLeft().y(), abs=0.05)
    assert do_item.size().width() == pytest.approx(do_caminho.size().width(), abs=0.05)
    assert do_item.size().height() == pytest.approx(do_caminho.size().height(), abs=0.05)
