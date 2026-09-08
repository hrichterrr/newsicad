"""O histórico da linha de comando era reescrito INTEIRO na tela a cada passo
de comando, e nunca era truncado: com 250 comandos já dados uma LINE custava
208 ms em vez de 21 ms, e com 2.500 comandos, 1,6 s — sem nenhuma relação com
o tamanho do desenho. Era a causa do "o programa vai ficando pesado, tenho
que fechar e abrir" (auditoria de 07/09/2026 com as amostras da Autodesk).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.commands.interpreter import (  # noqa: E402
    _DESCARTE_LOG,
    _MAX_LINHAS_LOG,
    CommandLog,
)
from newsicad.ui.command_line import MAX_LINHAS_VISIVEIS, CommandLineWidget  # noqa: E402


@pytest.fixture
def widget():
    QApplication.instance() or QApplication([])
    return CommandLineWidget()


def test_nao_redesenha_o_historico_inteiro_a_cada_comando(widget):
    chamadas = []
    original = widget.history_view.setPlainText
    widget.history_view.setPlainText = lambda t: (chamadas.append(t), original(t))[1]

    log = CommandLog()
    for passo in range(200):
        log.append(f"linha {passo}")
        widget.set_log(log)

    assert chamadas == [], "o histórico foi remontado do zero"
    assert widget.history_view.toPlainText().endswith("linha 199")
    assert widget.history_view.document().blockCount() == 200


def test_chamar_de_novo_sem_novidade_nao_faz_nada(widget):
    log = CommandLog(["a", "b"])
    widget.set_log(log)
    antes = widget.history_view.toPlainText()
    widget.set_log(log)
    assert widget.history_view.toPlainText() == antes


def test_o_log_tem_teto_mas_a_contagem_nao_recua():
    log = CommandLog()
    for i in range(_MAX_LINHAS_LOG + _DESCARTE_LOG + 5):
        log.append(str(i))
    assert len(log) <= _MAX_LINHAS_LOG
    assert log.total == _MAX_LINHAS_LOG + _DESCARTE_LOG + 5
    assert log[-1] == str(log.total - 1), "as linhas descartadas são as mais velhas"


def test_a_tela_tambem_para_de_crescer(widget):
    log = CommandLog()
    for i in range(MAX_LINHAS_VISIVEIS + 500):
        log.append(f"linha {i}")
        widget.set_log(log)
    assert widget.history_view.document().blockCount() <= MAX_LINHAS_VISIVEIS
    assert widget.history_view.toPlainText().endswith(f"linha {MAX_LINHAS_VISIVEIS + 499}")


def test_prompt_com_sinal_de_menor_nao_vira_marcacao(widget):
    """`append` do QTextEdit adivinha se o texto é HTML; "Enter number of
    sides <4>:" não pode sumir da tela por parecer uma tag."""
    log = CommandLog(["Enter number of sides <4>:", "<b>não é negrito</b>"])
    widget.set_log(log)
    texto = widget.history_view.toPlainText()
    assert "<4>" in texto
    assert "<b>não é negrito</b>" in texto


def test_historico_trocado_remonta(widget):
    widget.set_log(CommandLog(["velho 1", "velho 2", "velho 3"]))
    widget.set_log(CommandLog(["novo"]))
    assert widget.history_view.toPlainText() == "novo"


def test_lista_comum_ainda_funciona(widget):
    """Alguém pode passar uma lista qualquer (o editor de blocos monta a sua
    própria) — sem `total`, o comportamento é o de sempre."""
    widget.set_log(["uma", "duas"])
    assert widget.history_view.toPlainText() == "uma\nduas"
