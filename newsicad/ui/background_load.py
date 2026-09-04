"""Executa trabalho pesado fora da thread da interface, mantendo a janela viva.

Abrir uma planta grande custa dezenas de segundos (dwg2dxf + parser do ezdxf,
puro Python) e o Windows carimba a janela como "não respondendo" depois de ~5 s
sem eventos — o usuário acha que travou e mata o programa (relato de
2026-09-04 na planta NEWSI-CASA PAU BRASIL-R01). `run_with_progress` roda a
função numa `QThread` e, enquanto ela trabalha, mostra um `QProgressDialog`
modal (barra "ocupada") girando um `QEventLoop` local: a janela repinta, pode
ser movida, e o chamador continua síncrono — recebe o resultado como se
tivesse chamado a função direto, inclusive a exceção, se houver.

Só entra aqui trabalho que NÃO toca em objetos Qt (leitura de arquivo,
conversão para `Document`); montar a cena continua na thread da interface,
em lotes, com o mesmo diálogo mostrando o andamento (ver
`CanvasView.refresh_entities(progress=...)`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEventLoop, Qt, QThread, QTimer
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget


class _Worker(QThread):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.result: Any = None
        self.error: BaseException | None = None

    def run(self) -> None:  # noqa: D401 - contrato do QThread
        try:
            self.result = self._fn()
        except BaseException as exc:  # repassado na thread da interface
            self.error = exc


def make_progress_dialog(parent: QWidget | None, title: str, text: str) -> QProgressDialog:
    """Diálogo modal de progresso no tema do app, sem botão de cancelar (o
    parser do ezdxf não tem como ser interrompido no meio)."""
    dialog = QProgressDialog(text, "", 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setCancelButton(None)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setMinimumDuration(0)
    dialog.setMinimumWidth(420)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    return dialog


def run_with_progress(parent: QWidget | None, title: str, text: str, fn: Callable[[], Any]) -> Any:
    """Roda `fn` numa thread mostrando um diálogo de progresso; devolve o
    resultado (ou levanta a exceção de `fn`) quando terminar."""
    app = QApplication.instance()
    if app is None:
        return fn()
    dialog = make_progress_dialog(parent, title, text)
    dialog.show()
    app.processEvents()

    worker = _Worker(fn)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    worker.start()
    if worker.isRunning():
        # Rede de segurança contra o sinal chegar antes do loop começar.
        QTimer.singleShot(50, lambda: None if worker.isRunning() else loop.quit())
        loop.exec()
    worker.wait()
    dialog.close()
    dialog.deleteLater()
    if worker.error is not None:
        raise worker.error
    return worker.result
