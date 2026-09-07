"""Os toggles dos painéis (Command Line e Properties) e o dock que eles
comandam tinham cada um o seu próprio estado, e se descolavam: fechar o
painel no "X" deixava o item de menu marcado, e o atalho seguinte só
desmarcava — era preciso apertar Ctrl+1 duas vezes para o painel voltar.
O botão do ribbon e o item de menu do Command Line também divergiam
(auditoria de 2026-09-07)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela():
    app = _app()
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    yield w, app
    w.close()


def _acao(w: MainWindow, rotulo: str) -> QAction:
    return next(a for a in w.findChildren(QAction) if a.text() == rotulo)


def test_um_toque_reabre_o_painel_fechado_no_x(janela):
    """Só o painel de Propriedades tem o "X": o do Command Line é criado com
    `NoDockWidgetFeatures` e barra de título vazia, então não fecha por ali."""
    w, app = janela
    acao = _acao(w, "Properties")
    dock = w.properties_dock
    assert acao.isChecked() and not dock.isHidden()

    dock.close()
    app.processEvents()
    assert not acao.isChecked(), "fechar no X tem de desmarcar o item de menu"

    acao.trigger()
    app.processEvents()
    assert not dock.isHidden(), "um toque só tem de trazer o painel de volta"
    assert acao.isChecked(), "e o item de menu tem de ficar marcado junto"


def test_botao_do_ribbon_e_item_de_menu_andam_juntos(janela):
    w, app = janela
    acao = _acao(w, "Command Line")
    botao = next(
        b for b in w.findChildren(QToolButton) if b.text() == "Command Line"
    )
    dock = w.command_dock

    botao.click()
    app.processEvents()
    assert dock.isHidden() and not acao.isChecked() and not botao.isChecked()

    acao.trigger()
    app.processEvents()
    assert not dock.isHidden() and acao.isChecked() and botao.isChecked()


def test_dock_sem_botao_de_fechar_nao_desmarca_o_controle(janela):
    """O dock do Command Line não é fechável: o `close()` é recusado, mas o Qt
    ainda emite `visibilityChanged(False)` no caminho. Levar esse sinal ao pé
    da letra desmarcava o controle de um painel que continuava aberto."""
    w, app = janela
    acao = _acao(w, "Command Line")
    w.command_dock.close()
    app.processEvents()
    assert not w.command_dock.isHidden(), "esse dock não fecha mesmo"
    assert acao.isChecked(), "e o controle não pode se desmarcar sozinho"
