"""Render de texto do canvas (WP-B 2026-09, achado
text-invisivel-windows-pointsize): a altura CAD vira escala de uma fonte de
referência, não um tamanho em pontos — texto de 0.18 m (planta em metros)
tem que pintar e medir em qualquer plataforma, inclusive na "windows" de
verdade (onde `setPointSizeF(0.18)` não pintava nada). Também: baseline em
justify B?, quebra por largura, DimStyle no texto da cota, fallback SHX."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from newsicad.commands.context import CommandContext
from newsicad.commands.interpreter import CommandInterpreter
from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
from newsicad.core.document import DimStyle, Document, TextStyle
from newsicad.core.entities import Dimension, Point, Table, Text
from newsicad.core.selection import Selection
from newsicad.ui.canvas import BACKGROUND_COLOR, CanvasView, resolve_font_family

_ROOT = Path(__file__).resolve().parent.parent


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _view(document: Document) -> CanvasView:
    _app()
    ctx = CommandContext(document=document, selection=Selection())
    view = CanvasView(document, CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES))
    view.refresh_entities()
    return view


def _ink_rows(view: CanvasView, src: QRectF, px: int = 300) -> list[int]:
    """Linhas (em px) da imagem que têm algum pixel diferente do fundo,
    renderizando a região CAD `src` (coordenadas de cena) em `px` x `px`."""
    image = QImage(px, px, QImage.Format_RGB32)
    image.fill(QColor(BACKGROUND_COLOR))
    painter = QPainter(image)
    view.scene().render(painter, QRectF(0, 0, px, px), src)
    painter.end()
    background = QColor(BACKGROUND_COLOR).rgb()
    return sorted({y for y in range(px) for x in range(px) if image.pixel(x, y) != background})


def test_small_text_has_real_scene_rect():
    document = Document()
    text = document.add_entity(Text(insertion_point=Point(0, 0), content="TOMADA", height=0.18))
    view = _view(document)

    rect = view._entity_items[text.id].sceneBoundingRect()

    # tinta de maiúsculas sem descendentes: ~capHeight (a fonte de referência
    # pode ficar uns % abaixo de 0.18), nunca 0x0 como antes no Windows
    assert 0.15 <= rect.height() <= 0.3
    assert rect.width() > 0.18


@pytest.mark.parametrize("height", [2.5, 0.18, 0.01])
def test_ink_height_matches_cad_height(height):
    document = Document()
    document.add_entity(Text(insertion_point=Point(0, 0), content="H", height=height, justify="BL"))
    view = _view(document)

    # região de 3h x 3h em cena (Y pra baixo): de y=-2h (CAD +2h) a y=+h
    px = 300
    rows = _ink_rows(view, QRectF(-height, -2 * height, 3 * height, 3 * height), px)

    assert rows, "texto não pintou nada"
    ink_height = (rows[-1] - rows[0] + 1) / px * 3 * height
    assert 0.9 <= ink_height / height <= 1.1


def test_baseline_justify_keeps_ink_above_anchor():
    document = Document()
    text = document.add_entity(Text(insertion_point=Point(0, 0), content="H", height=1.0, justify="BL"))
    view = _view(document)

    rect = view._entity_items[text.id].sceneBoundingRect()

    # cena tem Y pra baixo: tinta acima de y=0 (CAD) = rect inteiro em y <= ~0
    assert rect.top() < -0.9
    assert rect.bottom() <= 0.15


def test_text_wraps_by_width_in_words():
    document = Document()
    text = document.add_entity(Text(insertion_point=Point(0, 0), content="AAAA BBBB", height=1.0, width=3.0))
    view = _view(document)

    assert view._text_layout(text).lines == ["AAAA", "BBBB"]
    unwrapped = document.add_entity(Text(insertion_point=Point(0, 5), content="AAAA BBBB", height=1.0))
    assert view._text_layout(unwrapped).lines == ["AAAA BBBB"]


def test_zero_height_text_draws_nothing():
    document = Document()
    text = document.add_entity(Text(insertion_point=Point(0, 0), content="X", height=0.0))
    view = _view(document)

    assert view._entity_items[text.id].boundingRect().isEmpty()


def test_dimension_text_follows_document_dim_style():
    document = Document()
    document.dim_style = DimStyle(text_height=0.1, arrow_size=0.05)
    dim = document.add_entity(Dimension(kind="linear", point1=Point(0, 0), point2=Point(2, 0), dim_line_point=Point(0, 0.5)))
    view = _view(document)

    rect = view._entity_items[dim.id].sceneBoundingRect()

    # antes: texto fixo de 2.0 unidades cobria uma cota de 2 m inteira
    assert rect.height() < 1.0
    assert rect.width() < 2.6


def test_table_cell_text_is_visible_in_meters():
    document = Document()
    table = document.add_entity(
        Table(insertion_point=Point(0, 0), rows=1, cols=1, col_width=1.0, row_height=0.3, text_height=0.1, cells=[["A"]], show_borders=False)
    )
    view = _view(document)

    children = view._entity_items[table.id].childItems()

    assert len(children) == 1
    assert not children[0].boundingRect().isEmpty()
    assert 0.08 <= children[0].sceneBoundingRect().height() <= 0.15


def test_shx_style_resolves_to_narrow_fallback_font():
    _app()
    family, stretch = resolve_font_family("romans", "romans.shx")
    assert family
    assert stretch == 85
    family_ttf, stretch_ttf = resolve_font_family("Arial", "arial.ttf")
    assert stretch_ttf == 100


_WINDOWS_SCRIPT = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from newsicad.commands.context import CommandContext
    from newsicad.commands.interpreter import CommandInterpreter
    from newsicad.commands.registry import ALIASES, COMMAND_REGISTRY
    from newsicad.core.document import Document
    from newsicad.core.entities import Point, Text
    from newsicad.core.selection import Selection
    from newsicad.ui.canvas import BACKGROUND_COLOR, CanvasView
    document = Document()
    text = document.add_entity(Text(insertion_point=Point(0, 0), content="TOMADA", height=0.18))
    ctx = CommandContext(document=document, selection=Selection())
    view = CanvasView(document, CommandInterpreter(ctx, COMMAND_REGISTRY, ALIASES))
    view.refresh_entities()
    rect = view._entity_items[text.id].sceneBoundingRect()
    image = QImage(300, 100, QImage.Format_RGB32)
    image.fill(QColor(BACKGROUND_COLOR))
    painter = QPainter(image)
    view.scene().render(painter, QRectF(0, 0, 300, 100), QRectF(-0.05, -0.25, 0.9, 0.3))
    painter.end()
    bg = QColor(BACKGROUND_COLOR).rgb()
    ink = sum(1 for y in range(100) for x in range(300) if image.pixel(x, y) != bg)
    print(app.platformName(), ink, rect.width(), rect.height())
    """
)


@pytest.mark.skipif(sys.platform != "win32", reason="plataforma Qt 'windows' só existe no Windows")
def test_small_text_paints_on_real_windows_platform():
    env = dict(os.environ, QT_QPA_PLATFORM="windows")
    result = subprocess.run(
        [sys.executable, "-c", _WINDOWS_SCRIPT, str(_ROOT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        cwd=str(_ROOT),
    )
    assert result.returncode == 0, result.stderr
    platform_name, ink, width, height = result.stdout.split()[-4:]
    assert platform_name == "windows"
    assert int(ink) > 50
    assert float(width) > 0.18 and 0.18 <= float(height) <= 0.3
