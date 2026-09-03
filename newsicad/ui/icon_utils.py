"""Renderização de ícones desenhados via QPainter (sem depender de arquivos
de imagem externos) — compartilhado entre o ribbon (newsicad/ui/ribbon.py) e
o painel de camadas (newsicad/ui/layer_panel.py), pra não duplicar a lógica
de nitidez em telas HiDPI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

# Espaço de coordenadas lógico em que todo draw_fn desenha (independente da
# resolução final do bitmap — ver `_RENDER_SCALE` abaixo).
LOGICAL_CANVAS = 32
# Renderiza em resolução mais alta que o tamanho de exibição e marca
# `setDevicePixelRatio` de acordo — sem isso, o ícone fica borrado em
# qualquer tela com escala do Windows > 100% (notebook 4K/HiDPI comum).
RENDER_SCALE = 3
PIXMAP_SIZE = LOGICAL_CANVAS * RENDER_SCALE
STROKE_COLOR = "#d8d8d8"


def make_icon(draw_fn: Callable[[QPainter, QRectF], None], color: str = STROKE_COLOR) -> QIcon:
    pixmap = QPixmap(PIXMAP_SIZE, PIXMAP_SIZE)
    pixmap.setDevicePixelRatio(RENDER_SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # NÃO chamar painter.scale(RENDER_SCALE, ...) aqui: QPainter já aplica
    # esse fator sozinho porque o pixmap tem devicePixelRatio=RENDER_SCALE
    # (comportamento HiDPI padrão do Qt — coordenadas passadas ao painter
    # são "lógicas", a conversão pra pixel físico é automática). Uma versão
    # anterior desta função tinha as DUAS coisas ao mesmo tempo — um bug de
    # escala dupla (3x × 3x = 9x) que fazia praticamente todo ícone ser
    # desenhado fora dos limites físicos do pixmap e cortado silenciosamente
    # pelo próprio QPainter, sobrando só um fragmento perto da origem. Nunca
    # detectado porque não dava pra ver a janela rodando neste ambiente até
    # 2026-08-22 — reportado por Hamilton como "os ícones estão todos
    # cortados" assim que ele finalmente conseguiu ver a tela de verdade.
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    margin = 5.0
    rect = QRectF(margin, margin, LOGICAL_CANVAS - 2 * margin, LOGICAL_CANVAS - 2 * margin)
    draw_fn(painter, rect)
    painter.end()
    return QIcon(pixmap)


def resolve_app_icon_path() -> Path:
    """Caminho do logo NewSI (`.ico`) tanto rodando a partir do código-fonte
    quanto empacotado com PyInstaller (dados extras do build_windows.spec
    ficam soltos na raiz do bundle, `sys._MEIPASS`) — mesmo padrão de
    `newsicad/main.py:_icon_path` e `dwg_bridge.py:_bundled_bin_dir`,
    reaproveitado aqui pra não duplicar a lógica uma terceira vez (usado
    tanto pelo ícone da janela/taskbar quanto pelo logo dentro do próprio
    Quick Access Toolbar — ver `newsicad/ui/ribbon.py`)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "resources" / "newsi_icon.ico"
