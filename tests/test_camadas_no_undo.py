"""Ligar/desligar, travar, recolorir, renomear e criar camada pelo painel de
Camadas ou pelos botões do ribbon ficavam FORA do undo.

O estrago não era só "não dá pra desfazer": o Ctrl+Z seguinte, feito para
desfazer a última edição de geometria, levava junto TODO o trabalho de camada
feito depois dela — e seguir trabalhando descartava o redo, então as cores não
voltavam mais. Renomear camada era irreversível (auditoria de 07/09/2026 com
as amostras oficiais da Autodesk).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from newsicad.core.entities import Line, Point  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402
from newsicad.ui.ribbon import _set_current_layer_locked, _turn_all_layers_on  # noqa: E402


@pytest.fixture
def janela():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    doc = w.document
    for nome in ("Walls", "Doors", "Text"):
        doc.add_layer(nome, "#FFFFFF")
    doc.add_entity(Line(start=Point(0, 0), end=Point(1, 1), layer="Walls"))
    yield w
    # Sem isto, o `closeEvent` abre o "Salvar alterações?" (estes testes sujam
    # o documento de propósito) e o teste trava num diálogo modal.
    for sessao in w.sessions:
        sessao.mark_saved()
    w.close()


def test_apagar_a_lampada_entra_no_undo(janela):
    painel = janela.layer_dock
    painel._set_visible("Walls", False)
    assert janela.document.layers["Walls"].visible is False
    janela._do_undo()
    assert janela.document.layers["Walls"].visible is True


def test_cor_de_camada_entra_no_undo(janela):
    janela.layer_dock._set_color_with_hex("Doors", "#FF0000")
    assert janela.document.layers["Doors"].color == "#FF0000"
    janela._do_undo()
    assert janela.document.layers["Doors"].color == "#FFFFFF"


def test_renomear_camada_e_reversivel(janela):
    doc = janela.document
    (linha,) = [e for e in doc.all_entities() if isinstance(e, Line)]
    janela.layer_dock._rename_layer_with_names("Walls", "Paredes")
    assert "Paredes" in doc.layers and "Walls" not in doc.layers
    assert linha.layer == "Paredes"

    janela._do_undo()
    assert "Walls" in doc.layers and "Paredes" not in doc.layers
    atual = next(e for e in doc.all_entities() if isinstance(e, Line))
    assert atual.layer == "Walls", "a entidade tem de voltar para a camada antiga"


def test_criar_camada_e_reversivel(janela):
    janela.layer_dock._create_layer_with_name("Nova")
    assert "Nova" in janela.document.layers
    janela._do_undo()
    assert "Nova" not in janela.document.layers


def test_travar_pelo_ribbon_entra_no_undo_e_suja_a_aba(janela):
    doc = janela.document
    doc.set_current_layer("Walls")
    sessao = janela._active_session()
    sessao.mark_saved()
    assert sessao.is_dirty() is False

    _set_current_layer_locked(janela, True)
    assert doc.layers["Walls"].locked is True
    assert sessao.is_dirty() is True, "trava vai pro .dxf, tem de sujar a aba"

    janela._do_undo()
    assert doc.layers["Walls"].locked is False


def test_ligar_todas_as_camadas_entra_no_undo(janela):
    doc = janela.document
    doc.layers["Doors"].visible = False
    doc.layers["Text"].visible = False
    _turn_all_layers_on(janela)
    assert all(c.visible for c in doc.layers.values())
    janela._do_undo()
    assert doc.layers["Doors"].visible is False and doc.layers["Text"].visible is False


def test_um_ctrl_z_nao_leva_junto_todo_o_trabalho_de_camada(janela):
    """O caso que o agente reproduziu: geometria, depois várias cores, e um
    Ctrl+Z reflexo levava as cores todas embora."""
    doc = janela.document
    doc.add_entity(Line(start=Point(5, 5), end=Point(6, 6)))
    for nome in ("Walls", "Doors", "Text"):
        janela.layer_dock._set_color_with_hex(nome, "#123456")
    janela.layer_dock._set_visible("Text", False)

    janela._do_undo()
    assert doc.layers["Text"].visible is True, "só a última ação devia ser desfeita"
    assert all(doc.layers[n].color == "#123456" for n in ("Walls", "Doors", "Text")), (
        "as cores não podem ir junto"
    )


def test_renomear_recusado_nao_deixa_passo_fantasma(janela, monkeypatch):
    import newsicad.ui.layer_panel as lp

    monkeypatch.setattr(lp.QMessageBox, "warning", lambda *a, **k: None)
    antes = len(janela.undo_stack._undo_stack)
    janela.layer_dock._rename_layer_with_names("Walls", "Doors")  # nome já existe
    assert janela.document.layers["Walls"].name == "Walls"
    assert len(janela.undo_stack._undo_stack) == antes, "sobrou um Ctrl+Z que não faz nada"
