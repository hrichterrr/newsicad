"""Etapa 4 do programa de otimização (v2.15.3): abertura sem congelar a
janela — leitura numa thread com diálogo de progresso e montagem da cena em
lotes com callback de progresso."""

from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.background_load import run_with_progress  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def test_run_with_progress_devolve_o_resultado_de_outra_thread():
    _app()
    seen = {}

    def work():
        seen["thread"] = threading.current_thread().name
        return 42

    assert run_with_progress(None, "t", "x", work) == 42
    assert seen["thread"] != threading.main_thread().name


def test_run_with_progress_repassa_a_excecao():
    _app()

    def work():
        raise ValueError("falhou na thread")

    with pytest.raises(ValueError, match="falhou na thread"):
        run_with_progress(None, "t", "x", work)


def test_refresh_entities_chama_o_progresso_por_lote():
    _app()
    win = MainWindow()
    doc = win.document
    for i in range(2500):
        doc.add_entity(Line(start=Point(i, 0), end=Point(i, 1)))
    calls = []
    win.canvas.refresh_entities(full=True, progress=lambda done, total: calls.append((done, total)))
    assert calls, "progresso nunca chamado"
    assert calls[0] == (0, 2500)
    assert all(total == 2500 for _done, total in calls)
    assert len(calls) >= 3  # lotes de 1000: 0, 1000, 2000
    win.hide()
    win.deleteLater()


def test_abrir_arquivo_usa_a_thread_e_mostra_o_desenho(tmp_path, monkeypatch):
    import ezdxf

    _app()
    dxf = ezdxf.new("R2000")
    msp = dxf.modelspace()
    for i in range(50):
        msp.add_line((i, 0), (i, 5))
    path = tmp_path / "planta.dxf"
    dxf.saveas(path)

    monkeypatch.setenv("NEWSICAD_CACHE_DIR", str(tmp_path / "cache"))
    win = MainWindow()
    loaded, skipped = win._load_document_file(path)
    assert len(loaded.entities) == 50
    session = win._make_untitled_session()
    win._populate_session_from_loaded(session, loaded, path, skipped)
    assert len(session.canvas._entity_items) == 50
    assert session.is_dirty() is False
    win.hide()
    win.deleteLater()
