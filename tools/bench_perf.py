"""Banco de medição de desempenho do NewSIcad num arquivo real.

Uso (janela real, como o usuário vê):

    set QT_QPA_PLATFORM=windows
    .venv_win\\Scripts\\python tools\\bench_perf.py "C:\\...\\NEWSI-CASA PAU BRASIL-R01.dxf"

Abre o arquivo pelo MESMO fluxo do File > Open (`MainWindow._load_document_file`
+ `_populate_session_from_loaded`) e cronometra, na ordem em que o usuário
sente: abertura por fase, o que roda a cada passo de comando, undo, zoom
extents, painel de camadas (lâmpada/cadeado/cor) e interação (mouse, arrastar,
zoom, clique). Imprime uma tabela — a referência para comparar cada etapa do
programa de otimização (ver README, marco 2.15.x). Não faz parte da suíte de
testes: tempo de relógio não é critério de teste, é de medição.
"""

from __future__ import annotations

import collections
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from newsicad.core.entities import Point  # noqa: E402
from newsicad.io.dwg_bridge import dwg_to_document  # noqa: E402
from newsicad.io.dxf_io import load_dxf  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402

ROWS: list[tuple[str, float, str]] = []


def rec(nome: str, segundos: float, unidade: str = "s") -> None:
    ROWS.append((nome, segundos, unidade))
    valor = f"{segundos * 1000:8.1f} ms" if unidade == "ms" else f"{segundos:8.2f} s "
    print(f"  {nome:58} {valor}", flush=True)


def timed(nome: str, fn, unidade: str = "s"):
    t0 = time.perf_counter()
    out = fn()
    rec(nome, time.perf_counter() - t0, unidade)
    return out


def main(path_str: str) -> None:
    path = Path(path_str)
    print(f"NewSIcad bench — {path.name} — plataforma {os.environ['QT_QPA_PLATFORM']}", flush=True)

    # ---------------------------------------------------------- abertura
    if path.suffix.lower() == ".dwg":
        loaded, skipped = timed("abrir: dwg2dxf + ezdxf + Document", lambda: dwg_to_document(path))
    else:
        loaded, skipped = timed("abrir: ezdxf + Document", lambda: load_dxf(path))
    win = MainWindow()
    win.resize(1600, 1000)
    session = win._make_untitled_session()
    timed("abrir: popular sessão + montar cena + zoom", lambda: win._populate_session_from_loaded(session, loaded, path, skipped))
    win._add_session_tab(session)
    win.show()
    app.processEvents()
    doc = session.document
    canvas = win.canvas
    print(f"  {'entidades / itens na cena / camadas':58} {len(doc.entities):>8} / {len(canvas._scene.items())} / {len(doc.layers)}")

    # ---------------------------------------------------------- por passo
    timed("mark_saved (snapshot 'salvo')", session.mark_saved)
    timed("is_dirty() (a cada passo de comando)", session.is_dirty)
    timed("_after_interpreter_step (cada clique num comando)", lambda: (win._after_interpreter_step(), app.processEvents()))
    timed("undo_stack.push() (antes de cada comando)", session.undo_stack.push)
    timed("refresh_entities sem mudança", canvas.refresh_entities)
    timed("zoom_extents", canvas.zoom_extents)
    app.processEvents()

    # ---------------------------------------------------------- camadas
    counts = collections.Counter(e.layer for e in doc.entities.values())
    if counts:
        big, n = counts.most_common(1)[0]
        layer = doc.layers[big]
        panel = win.layer_dock
        timed(f"lâmpada: desligar '{big}' ({n} entidades)", lambda: (panel._set_visible(big, False), app.processEvents()))
        timed("lâmpada: religar", lambda: (panel._set_visible(big, True), app.processEvents()))
        timed("cadeado: travar", lambda: (panel._set_locked(big, True), app.processEvents()))
        panel._set_locked(big, False)
        timed("cor da camada", lambda: (panel._set_color_with_hex(big, "#FF00FF"), app.processEvents()))
        panel._set_color_with_hex(big, layer.color)

    # ---------------------------------------------------------- interação
    vp = canvas.viewport()
    canvas.zoom_extents()
    app.processEvents()

    def move(n=25):
        for i in range(n):
            p = QPointF(300 + (i * 37) % 900, 250 + (i * 53) % 600)
            QApplication.sendEvent(vp, QMouseEvent(QEvent.Type.MouseMove, p, p, Qt.MouseButton.NoButton,
                                                   Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
            app.processEvents()
        return n

    def pan(n=12):
        s = QPointF(800, 500)
        QApplication.sendEvent(vp, QMouseEvent(QEvent.Type.MouseButtonPress, s, s, Qt.MouseButton.MiddleButton,
                                               Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier))
        for i in range(n):
            p = QPointF(800 + (i % 2) * 6 - 3, 500 + (i % 3) * 4 - 4)
            QApplication.sendEvent(vp, QMouseEvent(QEvent.Type.MouseMove, p, p, Qt.MouseButton.NoButton,
                                                   Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier))
            app.processEvents()
        QApplication.sendEvent(vp, QMouseEvent(QEvent.Type.MouseButtonRelease, s, s, Qt.MouseButton.MiddleButton,
                                               Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        return n

    def zoom(n=8):
        for i in range(n):
            d = 120 if i % 2 == 0 else -120
            QApplication.sendEvent(vp, QWheelEvent(QPointF(800, 500), QPointF(800, 500), QPoint(0, 0), QPoint(0, d),
                                                   Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                                   Qt.ScrollPhase.NoScrollPhase, False))
            fim = time.perf_counter() + 0.03  # deixa o acúmulo de roda disparar
            while time.perf_counter() < fim:
                app.processEvents()
        return n

    def per_event(nome, fn):
        t0 = time.perf_counter()
        n = fn()
        rec(nome, (time.perf_counter() - t0) / n, "ms")

    per_event("mover o mouse (por evento)", move)
    per_event("arrastar a tela (por evento)", pan)
    per_event("zoom com a roda (por passo, inclui 30 ms de espera)", zoom)
    center = canvas.mapToScene(800, 500)
    from newsicad.ui.canvas import scene_to_cad
    timed("clique de seleção (hit-test no centro)", lambda: canvas._hit_test(scene_to_cad(center)), "ms")
    timed("clique em área vazia (hit-test)", lambda: canvas._hit_test(Point(1e9, 1e9)), "ms")

    print("\nRESUMO (copie para o README/commit):")
    for nome, seg, unidade in ROWS:
        valor = f"{seg * 1000:.1f} ms" if unidade == "ms" else f"{seg:.2f} s"
        print(f"| {nome} | {valor} |")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
