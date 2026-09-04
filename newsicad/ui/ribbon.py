"""Ribbon no padrão do AutoCAD 2020 (abas Home/Insert/Annotate/View/Manage/
Output; painéis com botões grandes de 32 px, pilhas de botões pequenos de
16 px com rótulo, colunas só de ícone, split-buttons com flyout, slide-out
no título do painel e a setinha ↘ de "dialog box launcher") — fica abaixo do
menu clássico, não o substitui. A planta de cada painel segue a proposta
aprovada em docs/design/ribbon-proposta-2026-09.html (03/09/2026).

Os ícones vêm de newsicad/resources/icons/*.svg (ver icon_utils.svg_icon),
coloridos pela FAMÍLIA do painel (Draw laranja, Modify azul, Annotation/Block
roxo, o resto neutro), com um acento branco — estilo "B" escolhido pelo
Hamilton entre as duas variantes da proposta.

Cada botão dispara exatamente o mesmo caminho que digitar o comando na linha
de comando (`window._start_command(nome)`) ou chama os mesmos métodos que o
menu clássico já usa (`newsicad/ui/menu_bar.py`) — o ribbon é só mais uma
forma de disparar as mesmas ações, não uma via paralela de lógica. Comandos
que o AutoCAD tem e o NewSIcad ainda não ficam no mesmo lugar, desabilitados
com tooltip (regra do README: nada some da interface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStyleFactory,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from newsicad.ui.icon_utils import (
    COMMAND_ICONS,
    FAMILY_ANNOTATE,
    FAMILY_DRAW,
    FAMILY_MODIFY,
    FAMILY_NEUTRAL,
    resolve_app_icon_path,
    svg_icon,
)

if TYPE_CHECKING:
    from newsicad.ui.main_window import MainWindow

ICON_BIG = 32
ICON_SMALL = 16
BIG_BUTTON_HEIGHT = 66
SMALL_BUTTON_HEIGHT = 22
NOT_IMPLEMENTED_TIP = "Ainda não implementado — previsto para um próximo marco do NewSIcad."
GITHUB_URL = "https://github.com/hrichterrr/newsicad"

# Cor por FAMÍLIA de painel (não por comando individual) — mantidas as
# constantes antigas com os nomes que o resto do código já conhece.
COLOR_DRAW = FAMILY_DRAW
COLOR_MODIFY = FAMILY_MODIFY
COLOR_ANNOTATE = FAMILY_ANNOTATE
COLOR_NEUTRAL = FAMILY_NEUTRAL

RIBBON_STYLE = """
    QTabWidget { background-color: #232323; }
    QTabWidget::pane { border: none; background-color: #2f2f2f; }
    QTabWidget QWidget { background-color: #2f2f2f; }
    QTabBar { background-color: #232323; border: none; }
    QTabBar::tab {
        background-color: #232323;
        color: #a0a0a0;
        padding: 5px 12px;
        border: none;
        font-size: 12px;
    }
    QTabBar::tab:selected {
        background-color: #2f2f2f;
        color: #ffffff;
        border-bottom: 2px solid #4da3ff;
    }
    QToolButton {
        background-color: transparent;
        color: #d0d0d0;
        border: none;
        padding: 2px 3px;
        font-size: 11px;
    }
    QToolButton:hover { background-color: #3a3a3a; border-radius: 2px; }
    QToolButton:pressed { background-color: #444444; }
    QToolButton:checked { background-color: #3a5a8c; border-radius: 2px; color: #ffffff; }
    QToolButton:disabled { color: #5a5a5a; }
    QToolButton::menu-button { border: none; width: 11px; }
    QToolButton::menu-arrow { image: none; }
    QToolButton::menu-indicator { image: none; width: 0px; }
    QToolButton#small { padding: 0px 4px 0px 2px; }
    QToolButton#iconOnly { padding: 1px 2px; }
    QToolButton#panelTitle {
        color: #8a8a8a;
        font-size: 11px;
        padding: 0px 8px;
        border: none;
        border-top: 1px solid #3a3a3a;
        border-radius: 0px;
    }
    QToolButton#panelTitle:hover { background-color: #3a3a3a; color: #d0d0d0; }
    QLabel#panelTitle {
        color: #8a8a8a;
        font-size: 11px;
        padding: 0px 8px;
        border-top: 1px solid #3a3a3a;
    }
    QToolButton#panelLauncher {
        color: #7a7a7a;
        font-size: 9px;
        padding: 0px 2px;
        border: none;
        border-top: 1px solid #3a3a3a;
        border-radius: 0px;
    }
    QToolButton#panelLauncher:hover { color: #d0d0d0; background-color: #3a3a3a; }
    QComboBox {
        background-color: #262626;
        color: #d0d0d0;
        border: 1px solid #4a4a4a;
        border-radius: 2px;
        padding: 0px 4px;
        font-size: 11px;
        min-height: 18px;
        max-height: 18px;
    }
    QComboBox:disabled { color: #6a6a6a; border-color: #3a3a3a; }
    QComboBox::drop-down { border: none; width: 14px; }
    QComboBox QAbstractItemView {
        background-color: #2b2b2b;
        color: #d8d8d8;
        selection-background-color: #3a5a8c;
        outline: none;
    }
    QFrame#slideOut { background-color: #2f2f2f; border: 1px solid #4a4a4a; }
    QMenu { background-color: #2b2b2b; color: #d8d8d8; border: 1px solid #3a3a3a; padding: 3px 0px; }
    QMenu::item { padding: 5px 28px 5px 10px; }
    QMenu::item:selected { background-color: #3a5a8c; color: #ffffff; }
    QMenu::item:disabled { color: #5a5a5a; }
    QMenu::separator { height: 1px; background: #3a3a3a; margin: 4px 8px; }
"""


# ---------------------------------------------------------------------- #
# blocos de construção
# ---------------------------------------------------------------------- #
def _finish(button: QToolButton, handler, checkable: bool, tooltip: str | None, menu: QMenu | None) -> QToolButton:
    button.setCheckable(checkable)
    if tooltip:
        button.setToolTip(tooltip)
    if menu is not None:
        # setMenu NÃO toma posse do QMenu: sem um parent, o Python coletava o
        # menu logo depois e o flyout sumia (button.menu() voltava None).
        # Precisa manter as window flags (Popup): setParent(button) sozinho
        # zerava as flags e o menu virava um widget-filho desenhado DENTRO
        # do botão, com os itens aparecendo inline no ribbon.
        menu.setParent(button, menu.windowFlags())
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
    if handler is not None:
        button.clicked.connect(handler)
    elif not checkable:
        button.setEnabled(False)
        button.setToolTip(tooltip or NOT_IMPLEMENTED_TIP)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _big(
    label: str,
    icon: str,
    handler: Callable[[], None] | None = None,
    color: str = COLOR_NEUTRAL,
    tooltip: str | None = None,
    checkable: bool = False,
    menu: QMenu | None = None,
) -> QToolButton:
    """Botão grande do AutoCAD: ícone de 32 px, rótulo embaixo (pode ter
    duas linhas com "\\n"), 66 px de altura."""
    button = QToolButton()
    button.setObjectName("big")
    button.setIcon(svg_icon(icon, color, ICON_BIG))
    button.setIconSize(QSize(ICON_BIG, ICON_BIG))
    button.setText(label)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setFixedHeight(BIG_BUTTON_HEIGHT)
    button.setMinimumWidth(48)
    return _finish(button, handler, checkable, tooltip, menu)


def _small(
    label: str,
    icon: str,
    handler: Callable[[], None] | None = None,
    color: str = COLOR_NEUTRAL,
    tooltip: str | None = None,
    checkable: bool = False,
    menu: QMenu | None = None,
) -> QToolButton:
    """Botão pequeno: ícone de 16 px com o rótulo à direita, 22 px de
    altura — empilhado em colunas de três."""
    button = QToolButton()
    button.setObjectName("small")
    button.setIcon(svg_icon(icon, color, ICON_SMALL))
    button.setIconSize(QSize(ICON_SMALL, ICON_SMALL))
    button.setText(label)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setFixedHeight(SMALL_BUTTON_HEIGHT)
    return _finish(button, handler, checkable, tooltip, menu)


def _icon_only(
    label: str,
    icon: str,
    handler: Callable[[], None] | None = None,
    color: str = COLOR_NEUTRAL,
    tooltip: str | None = None,
    checkable: bool = False,
    menu: QMenu | None = None,
) -> QToolButton:
    """Botão só de ícone (16 px); o rótulo vira tooltip (e continua em
    `text()` pra busca/testes, só não é desenhado)."""
    button = QToolButton()
    button.setObjectName("iconOnly")
    button.setIcon(svg_icon(icon, color, ICON_SMALL))
    button.setIconSize(QSize(ICON_SMALL, ICON_SMALL))
    button.setText(label)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setFixedHeight(SMALL_BUTTON_HEIGHT)
    return _finish(button, handler, checkable, tooltip or label, menu)


def _col(widgets: list[QWidget]) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for w in widgets:
        layout.addWidget(w, 0, Qt.AlignmentFlag.AlignLeft)
    layout.addStretch(1)
    return box


def _hrow(widgets: list[QWidget], spacing: int = 1) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w, 0, Qt.AlignmentFlag.AlignTop)
    return box


def _menu(window: "MainWindow", items: list[tuple[str, str] | None], parent: QWidget | None = None) -> QMenu:
    """Flyout de split-button: lista de (rótulo, COMANDO) — `None` vira
    separador; rótulo começando com "!" fica desabilitado (não implementado).
    Cada item leva o mesmo ícone que o comando tem no menu clássico."""
    menu = QMenu(parent)
    menu.setStyleSheet(RIBBON_STYLE)
    for item in items:
        if item is None:
            menu.addSeparator()
            continue
        label, command = item
        disabled = label.startswith("!")
        label = label.lstrip("!")
        action = QAction(label, menu)
        entry = COMMAND_ICONS.get(command)
        if entry is not None:
            action.setIcon(svg_icon(entry[0], entry[1], ICON_SMALL))
        if disabled:
            action.setEnabled(False)
            action.setToolTip(NOT_IMPLEMENTED_TIP)
        else:
            action.triggered.connect(lambda checked=False, c=command: window._start_command(c))
        menu.addAction(action)
    return menu


class _SlideOut(QFrame):
    """Segunda linha do painel (os comandos secundários), aberta clicando no
    título "Draw ▾" — mesma ideia do slide-out do AutoCAD, só que como popup
    (fecha ao clicar fora), sem o pino."""

    def __init__(self, title: str, content: QWidget) -> None:
        super().__init__(None, Qt.WindowType.Popup)
        self.setObjectName("slideOut")
        self.setStyleSheet(RIBBON_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)
        layout.addWidget(content)
        label = QLabel(f"{title} ▴")
        label.setObjectName("panelTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)


def _panel(
    title: str,
    content: list[QWidget],
    launcher: Callable[[], None] | None = None,
    more: list[QWidget] | None = None,
) -> QWidget:
    """Painel do ribbon: `content` lado a lado em cima, título embaixo.
    `launcher`: setinha ↘ no canto (dialog box launcher) — só onde existe
    mesmo um diálogo/comando por trás. `more`: widgets do slide-out, aberto
    pelo título (que ganha um ▾)."""
    panel = QWidget()
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(4, 2, 4, 0)
    outer.setSpacing(2)
    outer.addWidget(_hrow(content), 1)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(0)
    if more:
        title_btn = QToolButton()
        title_btn.setObjectName("panelTitle")
        title_btn.setText(f"{title} ▾")
        title_btn.setToolTip(f"Mais comandos de {title}")
        title_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        slide = _SlideOut(title, _hrow(more, spacing=2))
        panel._slide_out = slide  # mantém vivo junto com o painel

        def open_slide() -> None:
            slide.adjustSize()
            slide.move(panel.mapToGlobal(QPoint(0, panel.height())))
            slide.show()

        title_btn.clicked.connect(open_slide)
        title_row.addWidget(title_btn, 1)
    else:
        label = QLabel(title)
        label.setObjectName("panelTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_row.addWidget(label, 1)
    if launcher is not None:
        launcher_btn = QToolButton()
        launcher_btn.setText("↘")
        launcher_btn.setObjectName("panelLauncher")
        launcher_btn.setToolTip("Mais opções")
        launcher_btn.clicked.connect(launcher)
        title_row.addWidget(launcher_btn)
    outer.addLayout(title_row)
    return panel


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: #3f3f3f;")
    return line


def _row(widgets: list[QWidget]) -> QWidget:
    """Conteúdo de uma aba (painéis lado a lado) dentro de um QScrollArea
    horizontal — numa janela mais estreita que a soma dos painéis, os da
    direita continuam alcançáveis (o AutoCAD colapsa painéis; aqui rola)."""
    page = QWidget()
    layout = QHBoxLayout(page)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(2)
    for i, w in enumerate(widgets):
        if i > 0:
            layout.addWidget(_separator())
        layout.addWidget(w)
    layout.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidget(page)
    scroll.setWidgetResizable(False)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    # Barra de rolagem fina e escura: a nativa (cinza claro, 17 px) aparecia
    # POR CIMA dos títulos dos painéis na aba Home em janelas de ~1400 px.
    scroll.setStyleSheet(
        "QScrollArea { background-color: #2f2f2f; border: none; }"
        "QScrollBar:horizontal { background: #2f2f2f; height: 6px; margin: 0px; }"
        "QScrollBar::handle:horizontal { background: #5a5a5a; border-radius: 3px; min-width: 40px; }"
        "QScrollBar::handle:horizontal:hover { background: #7a7a7a; }"
        "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
    )
    return scroll


SCROLLBAR_ALLOWANCE = 6  # altura da barra de rolagem fina acima


def _cmd(window: "MainWindow", name: str) -> Callable[[], None]:
    return lambda: window._start_command(name)


def _toggle_button(window: "MainWindow", label: str, icon: str, status_button, small: bool = True) -> QToolButton:
    """Botão marcável espelhado num toggle da barra de status (GRID/SNAP/
    ORTHO/POLAR/OSNAP/DYN) — os dois lados ficam sincronizados."""
    factory = _small if small else _big
    button = factory(label, icon, checkable=True, color=COLOR_NEUTRAL, tooltip=status_button.toolTip())
    button.setChecked(status_button.isChecked())
    button.setEnabled(status_button.isEnabled())
    button.toggled.connect(status_button.setChecked)
    status_button.toggled.connect(button.setChecked)
    return button


# ---------------------------------------------------------------------- #
# combo de camada atual (painel Layers da aba Home)
# ---------------------------------------------------------------------- #
class LayerCombo(QComboBox):
    """Lista as camadas do desenho ativo com a lâmpada de visibilidade e
    seleciona a camada atual; escolher outra chama document.set_current_layer
    — o mesmo caminho do duplo clique no painel de Camadas, que por sua vez
    chama `refresh()` aqui de volta (ver layer_panel.LayerPanel.refresh)."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._updating = False
        self.setFixedWidth(176)
        self.setToolTip("Camada atual — onde as entidades novas são desenhadas")
        self.activated.connect(self._on_activated)
        self.refresh()

    def refresh(self) -> None:
        document = self.window.document
        self._updating = True
        try:
            self.clear()
            for name in sorted(document.layers.keys()):
                layer = document.layers[name]
                icon = QIcon()
                icon.addPixmap(_layer_swatch_pixmap(layer))
                self.addItem(icon, name)
            index = self.findText(document.current_layer)
            if index >= 0:
                self.setCurrentIndex(index)
        finally:
            self._updating = False

    def _on_activated(self, index: int) -> None:
        if self._updating:
            return
        name = self.itemText(index)
        document = self.window.document
        if name and name in document.layers and name != document.current_layer:
            document.set_current_layer(name)
            self.window.layer_dock.refresh()


def _layer_swatch_pixmap(layer) -> QPixmap:
    """Lâmpada (amarela ligada / cinza desligada) + quadradinho da cor da
    camada, lado a lado, como o combo de camadas do AutoCAD."""
    from PySide6.QtGui import QPainter

    size = ICON_SMALL
    pixmap = QPixmap(size * 2 * 3, size * 3)
    pixmap.setDevicePixelRatio(3)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    bulb = svg_icon("bulb" if layer.visible else "bulboff", COLOR_NEUTRAL, size).pixmap(size, size)
    painter.drawPixmap(0, 0, bulb)
    painter.setPen(QColor("#1a1a1a"))
    painter.setBrush(QColor(layer.color))
    painter.drawRect(size + 2, 3, size - 6, size - 6)
    painter.end()
    return pixmap


def _property_combo(text: str, swatch: bool = False, line_width: int = 0) -> QComboBox:
    """Combos Color/Linetype/Lineweight "ByLayer" do painel Properties —
    ainda sem função (propriedades por objeto vêm num próximo marco), ficam
    desabilitados no mesmo lugar em que o AutoCAD os tem."""
    combo = QComboBox()
    combo.setFixedWidth(124)
    if swatch:
        pixmap = QPixmap(ICON_SMALL, ICON_SMALL)
        pixmap.fill(QColor("#ffffff"))
        combo.addItem(QIcon(pixmap), text)
    elif line_width:
        pixmap = QPixmap(28, ICON_SMALL)
        pixmap.fill(Qt.GlobalColor.transparent)
        from PySide6.QtGui import QPainter, QPen

        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#d0d0d0"), line_width))
        painter.drawLine(0, ICON_SMALL // 2, 28, ICON_SMALL // 2)
        painter.end()
        combo.addItem(QIcon(pixmap), text)
    else:
        combo.addItem(text)
    combo.setEnabled(False)
    combo.setToolTip(NOT_IMPLEMENTED_TIP)
    return combo


# ---------------------------------------------------------------------- #
# ações de camada que não existem como comando digitado
# ---------------------------------------------------------------------- #
def _set_current_layer_locked(window: "MainWindow", locked: bool) -> None:
    document = window.document
    layer = document.layers.get(document.current_layer)
    if layer is None:
        return
    layer.locked = locked
    window.selection.clear()
    window.canvas.refresh_selection_highlight()
    window.canvas.viewport().update()
    window.layer_dock.refresh()


def _turn_all_layers_on(window: "MainWindow") -> None:
    for layer in window.document.layers.values():
        layer.visible = True
    window.canvas.refresh_entities()
    window.canvas.viewport().update()
    window.layer_dock.refresh()


def _deselect_all(window: "MainWindow") -> None:
    window.selection.clear()
    window.canvas.refresh_selection_highlight()
    window.canvas.viewport().update()


# ---------------------------------------------------------------------- #
# abas
# ---------------------------------------------------------------------- #
def _build_home_tab(window: "MainWindow") -> QWidget:
    c = lambda name: _cmd(window, name)  # noqa: E731
    D, M, A, N = COLOR_DRAW, COLOR_MODIFY, COLOR_ANNOTATE, COLOR_NEUTRAL

    draw_panel = _panel(
        "Draw",
        [
            _big("Line", "line", c("LINE"), D),
            _big("Polyline", "pline", c("PLINE"), D),
            _big("Circle", "circle", c("CIRCLE"), D, menu=_menu(window, [("Circle", "CIRCLE"), ("Donut", "DONUT")])),
            _big("Arc", "arc", c("ARC"), D, menu=_menu(window, [("Arc", "ARC"), ("Ellipse", "ELLIPSE"), ("Spline", "SPLINE")])),
            _col([
                _icon_only("Rectangle", "rect", c("RECTANG"), D, menu=_menu(window, [("Rectangle", "RECTANG"), ("Polygon", "POLYGON")])),
                _icon_only("Ellipse", "ellipse", c("ELLIPSE"), D, menu=_menu(window, [("Ellipse", "ELLIPSE"), ("Spline", "SPLINE")])),
                _icon_only("Hatch", "hatch", c("HATCH"), D, menu=_menu(window, [("Hatch", "HATCH"), ("Boundary", "BOUNDARY"), ("!Gradient", "GRADIENT")])),
            ]),
        ],
        more=[
            _col([_small("Spline", "spline", c("SPLINE"), D), _small("Construction Line", "xline", c("XLINE"), D), _small("Ray", "ray", c("RAY"), D)]),
            _col([_small("Point", "point", c("POINT"), D), _small("Donut", "donut", c("DONUT"), D), _small("Multiline", "mline", c("MLINE"), D)]),
            _col([_small("Revision Cloud", "revcloud", c("REVCLOUD"), D), _small("Wipeout", "wipeout", c("WIPEOUT"), D), _small("Boundary", "boundary", c("BOUNDARY"), D)]),
            _col([_small("Polygon", "polygon", c("POLYGON"), D), _small("Region", "region", None, D), _small("Gradient", "gradient", None, D)]),
        ],
    )

    modify_panel = _panel(
        "Modify",
        [
            _col([_small("Move", "move", c("MOVE"), M), _small("Copy", "copy", c("COPY"), M), _small("Stretch", "stretch", c("STRETCH"), M)]),
            _col([_small("Rotate", "rotate", c("ROTATE"), M), _small("Mirror", "mirror", c("MIRROR"), M), _small("Scale", "scale", c("SCALE"), M)]),
            _col([
                _small("Trim", "trim", c("TRIM"), M, menu=_menu(window, [("Trim", "TRIM"), ("Extend", "EXTEND")])),
                _small("Fillet", "fillet", c("FILLET"), M, menu=_menu(window, [("Fillet", "FILLET"), ("Chamfer", "CHAMFER")])),
                _small("Array", "array", c("ARRAY"), M),
            ]),
            _col([_icon_only("Erase", "erase", c("ERASE"), M), _icon_only("Explode", "explode", c("EXPLODE"), M), _icon_only("Offset", "offset", c("OFFSET"), M)]),
        ],
        more=[
            _col([_small("Extend", "extend", c("EXTEND"), M), _small("Chamfer", "chamfer", c("CHAMFER"), M), _small("Break", "break", c("BREAK"), M)]),
            _col([_small("Break at Point", "breakpt", c("BREAKATPOINT"), M), _small("Join", "join", c("JOIN"), M), _small("Lengthen", "lengthen", c("LENGTHEN"), M)]),
            _col([_small("Edit Polyline", "pedit", c("PEDIT"), M), _small("Edit Hatch", "hatchedit", c("HATCHEDIT"), M), _small("Edit Text", "ddedit", c("DDEDIT"), M)]),
            _col([_small("Align", "align", c("ALIGN"), M), _small("Divide", "divide", c("DIVIDE"), M), _small("Measure", "measure", c("MEASURE"), M)]),
            _col([_small("Set to ByLayer", "layers", None, M), _small("Change Space", "model", None, M), _small("Reverse", "reverse", None, M)]),
        ],
    )

    dim_items = [
        ("Linear", "DIMLINEAR"), ("Aligned", "DIMALIGNED"), ("Angular", "DIMANGULAR"),
        ("Radius", "DIMRADIUS"), ("Diameter", "DIMDIAMETER"), None,
        ("Center Mark", "CENTERMARK"), ("Dimension Break", "DIMBREAK"), None, ("Dimension Style...", "DIMSTYLE"),
    ]
    annotation_panel = _panel(
        "Annotation",
        [
            _big("Text", "text", c("MTEXT"), A, menu=_menu(window, [("Multiline Text", "MTEXT"), ("Edit Text", "DDEDIT"), ("Find...", "FIND"), None, ("Text Style...", "STYLE")])),
            _big("Dimension", "dim", c("DIMLINEAR"), A, menu=_menu(window, dim_items)),
            _col([
                _small("Linear", "dim", c("DIMLINEAR"), A, menu=_menu(window, dim_items[:5])),
                _small("Leader", "leader", c("LEADER"), A, menu=_menu(window, [("Leader", "LEADER"), ("Multileader Style...", "MLEADERSTYLE")])),
                _small("Table", "table", c("TABLE"), A),
            ]),
        ],
        more=[
            _col([_small("Text Style", "textstyle", c("STYLE"), A), _small("Dimension Style", "dimstyle", c("DIMSTYLE"), A)]),
            _col([_small("Multileader Style", "mleaderstyle", c("MLEADERSTYLE"), A), _small("Table Style", "tablestyle", c("TABLESTYLE"), A)]),
            _col([_small("Aligned", "dimaligned", c("DIMALIGNED"), A), _small("Angular", "dimangular", c("DIMANGULAR"), A)]),
            _col([_small("Radius", "dimradius", c("DIMRADIUS"), A), _small("Diameter", "dimdiameter", c("DIMDIAMETER"), A)]),
        ],
    )

    window.layer_combo = LayerCombo(window)
    layers_panel = _panel(
        "Layers",
        [
            _big("Layer\nProperties", "layers", c("LAYER"), N),
            _col([
                window.layer_combo,
                _hrow([
                    _icon_only("Off", "bulboff", None, N, tooltip="Layer Off — ainda não implementado"),
                    _icon_only("Isolate", "layiso", c("LAYISO"), N),
                    _icon_only("Freeze", "freeze", None, N),
                    _icon_only("Lock", "lock", lambda: _set_current_layer_locked(window, True), N, tooltip="Trava a camada atual"),
                    _icon_only("Match Layer", "laymch", c("LAYMCH"), N),
                    _icon_only("Layer States", "laystate", None, N),
                ]),
                _hrow([
                    _icon_only("Make Current", "laycur", None, N, tooltip="Escolha a camada atual no combo acima"),
                    _icon_only("Unisolate", "layuniso", c("LAYUNISO"), N),
                    _icon_only("Turn All Layers On", "layon", lambda: _turn_all_layers_on(window), N),
                    _icon_only("Unlock", "unlock", lambda: _set_current_layer_locked(window, False), N, tooltip="Destrava a camada atual"),
                    _icon_only("Rename", "rename", c("RENAME"), N, tooltip="Renomeia a camada atual"),
                    _icon_only("Layer Previous", "layprev", None, N),
                ]),
            ]),
        ],
        launcher=c("LAYER"),
    )

    block_panel = _panel(
        "Block",
        [
            _big("Insert", "insert", c("INSERT"), A, menu=_menu(window, [("Insert Block...", "INSERT"), ("Create Block...", "BLOCK"), ("Block Editor...", "BEDIT")])),
            _big("Create", "block", c("BLOCK"), A),
            _big("Edit", "bedit", c("BEDIT"), A),
            _col([
                _icon_only("Define Attributes", "attr", None, A),
                _icon_only("Manage Attributes", "attr", None, A),
                _icon_only("Attribute Sync", "attrsync", None, A),
            ]),
        ],
    )

    properties_panel = _panel(
        "Properties",
        [
            _big("Match\nProperties", "matchprop", c("MATCHPROP"), N),
            _col([_property_combo("ByLayer", swatch=True), _property_combo("ByLayer", line_width=1), _property_combo("ByLayer", line_width=3)]),
            _col([_icon_only("Transparency", "transp", None, N), _icon_only("List", "list", window._show_properties_dock, N, tooltip="Painel de Propriedades (Ctrl+1)")]),
        ],
        launcher=window._show_properties_dock,
    )

    groups_panel = _panel(
        "Groups",
        [
            _big("Group", "group", None, N),
            _col([_small("Ungroup", "ungroup", None, N), _small("Group Edit", "gedit", None, N), _small("Group Selection", "gsel", None, N)]),
        ],
    )

    utilities_panel = _panel(
        "Utilities",
        [
            _big("Measure", "measure", c("DIST"), N, menu=_menu(window, [("Distance", "DIST"), ("Area", "AREA"), ("ID Point", "ID")])),
            _col([_small("Quick Select", "qselect", c("QSELECT"), N), _small("Quick Calculator", "calc", None, N), _small("ID Point", "id", c("ID"), N)]),
        ],
        more=[
            _col([_small("Distance", "dist", c("DIST"), N), _small("Area", "area", c("AREA"), N), _small("ID Point", "id", c("ID"), N)]),
            _col([
                _small("Select Similar", "selsim", c("SELECTSIMILAR"), N),
                _small("Deselect All", "deselect", lambda: _deselect_all(window), N),
                _small("Purge", "purge", c("PURGE"), N),
            ]),
        ],
    )

    clipboard_panel = _panel(
        "Clipboard",
        [
            _big("Paste", "paste", c("PASTECLIP"), N),
            _col([
                _icon_only("Cut", "cut", c("CUTCLIP"), N, tooltip="Cut (Ctrl+X)"),
                _icon_only("Copy Clip", "copyclip", c("COPYCLIP"), N, tooltip="Copy Clip (Ctrl+C)"),
                _icon_only("Copy with Base Point", "copybase", c("COPY"), N, tooltip="Copy with Base Point (Ctrl+Shift+C)"),
            ]),
        ],
    )

    view_panel = _panel(
        "View",
        [_col([_icon_only("UCS Icon", "ucs", None, N), _icon_only("View Cube", "viewcube", None, N), _icon_only("Navigation Bar", "navbar", None, N)])],
    )

    return _row([
        draw_panel, modify_panel, annotation_panel, layers_panel, block_panel,
        properties_panel, groups_panel, utilities_panel, clipboard_panel, view_panel,
    ])


def _build_insert_tab(window: "MainWindow") -> QWidget:
    c = lambda name: _cmd(window, name)  # noqa: E731
    A, N = COLOR_ANNOTATE, COLOR_NEUTRAL

    block_panel = _panel(
        "Block Definition",
        [
            _big("Insert", "insert", c("INSERT"), A, menu=_menu(window, [("Insert Block...", "INSERT"), ("Create Block...", "BLOCK"), ("Block Editor...", "BEDIT")])),
            _big("Create\nBlock", "block", c("BLOCK"), A),
            _big("Block\nEditor", "bedit", c("BEDIT"), A),
            _col([_small("Define Attributes", "attr", None, A), _small("Manage Attributes", "attr", None, A), _small("Attribute Sync", "attrsync", None, A)]),
        ],
    )
    reference_panel = _panel(
        "Reference",
        [
            _big("Attach\nXREF", "xref", c("XREF"), N),
            _big("Attach\nImage", "image", c("IMAGEATTACH"), N),
            _big("Clip", "clip", c("CLIP"), N),
            _col([
                _small("External References", "xrefpanel", c("EXTERNALREFERENCES"), N),
                _small("Remove Clip", "clipoff", c("CLIPOFF"), N),
                _small("Frames", "clip", None, N),
            ]),
        ],
        launcher=c("EXTERNALREFERENCES"),
    )
    import_panel = _panel(
        "Import",
        [_big("PDF\nImport", "importpdf", c("IMPORTPDF"), N), _big("Import", "open", None, N)],
    )
    data_panel = _panel(
        "Data",
        [
            _big("Field", "field", c("FIELD"), A),
            _big("Data\nLink", "datalink", c("DATALINK"), A),
            _col([_small("OLE Object", "ole", None, A), _small("Update Fields", "updatefield", None, A), _small("Extract Data", "dataextract", None, A)]),
        ],
    )
    point_cloud_panel = _panel(
        "Point Cloud",
        [_big("Attach", "namedview", None, N), _col([_small("Crop", "clip", None, N), _small("Point Cloud Manager", "list", None, N)])],
    )
    return _row([block_panel, reference_panel, import_panel, data_panel, point_cloud_panel])


def _build_annotate_tab(window: "MainWindow") -> QWidget:
    c = lambda name: _cmd(window, name)  # noqa: E731
    A, D, N = COLOR_ANNOTATE, COLOR_DRAW, COLOR_NEUTRAL

    text_panel = _panel(
        "Text",
        [
            _big("Multiline\nText", "mtext", c("MTEXT"), A, menu=_menu(window, [("Multiline Text", "MTEXT"), ("Edit Text", "DDEDIT"), ("Find...", "FIND")])),
            _col([
                _small("Text Style", "textstyle", c("STYLE"), A),
                _small("Find Text", "find", c("FIND"), A, tooltip="Find (Ctrl+F)"),
                _small("Edit Text", "ddedit", c("DDEDIT"), A),
            ]),
            _col([_icon_only("Check Spelling", "spell", None, A)]),
        ],
        launcher=c("STYLE"),
    )
    dim_panel = _panel(
        "Dimensions",
        [
            _big("Dimension", "dim", c("DIMLINEAR"), A),
            _col([
                _small("Dimension Style", "dimstyle", c("DIMSTYLE"), A),
                _hrow([
                    _small("Linear", "dim", c("DIMLINEAR"), A, menu=_menu(window, [("Linear", "DIMLINEAR"), ("Aligned", "DIMALIGNED"), ("Angular", "DIMANGULAR")])),
                    _icon_only("Aligned", "dimaligned", c("DIMALIGNED"), A),
                    _icon_only("Angular", "dimangular", c("DIMANGULAR"), A),
                ]),
                _hrow([
                    _small("Radius", "dimradius", c("DIMRADIUS"), A, menu=_menu(window, [("Radius", "DIMRADIUS"), ("Diameter", "DIMDIAMETER")])),
                    _icon_only("Diameter", "dimdiameter", c("DIMDIAMETER"), A),
                    _icon_only("Continue", "dimcont", None, A),
                ]),
            ]),
            _col([
                _icon_only("Center Mark", "centermark", c("CENTERMARK"), A),
                _icon_only("Dimension Break", "dimbreak", c("DIMBREAK"), A),
                _icon_only("Distance", "dist", c("DIST"), A),
            ]),
        ],
        launcher=c("DIMSTYLE"),
    )
    leader_panel = _panel(
        "Leaders",
        [
            _big("Leader", "leader", c("LEADER"), A),
            _col([_small("Multileader Style", "mleaderstyle", c("MLEADERSTYLE"), A), _small("Add Leader", "addsel", None, A), _small("Align", "align", None, A)]),
        ],
        launcher=c("MLEADERSTYLE"),
    )
    table_panel = _panel(
        "Tables",
        [
            _big("Table", "table", c("TABLE"), A),
            _col([_small("Table Style", "tablestyle", c("TABLESTYLE"), A), _small("Extract Data", "dataextract", None, A), _small("Link Data", "datalink", None, A)]),
        ],
        launcher=c("TABLESTYLE"),
    )
    markup_panel = _panel(
        "Markup",
        [_big("Revision\nCloud", "revcloud", c("REVCLOUD"), D), _big("Wipeout", "wipeout", c("WIPEOUT"), D)],
    )
    scaling_panel = _panel(
        "Annotation Scaling",
        [_col([_small("Add Current Scale", "addsel", None, N), _small("Scale List", "list", None, N)])],
    )
    return _row([text_panel, dim_panel, leader_panel, table_panel, markup_panel, scaling_panel])


def _build_view_tab(window: "MainWindow") -> QWidget:
    c = lambda name: _cmd(window, name)  # noqa: E731
    N = COLOR_NEUTRAL

    navigate_panel = _panel(
        "Navigate",
        [
            _big("Extents", "zoomext", lambda: window.canvas.zoom_extents(), N),
            _col([
                _small("Zoom In", "zoomin", lambda: window.canvas.zoom_in(), N),
                _small("Zoom Out", "zoomout", lambda: window.canvas.zoom_out(), N),
                _small("Pan", "pan", None, N, tooltip="Pan — arraste com o botão do meio do mouse"),
            ]),
        ],
    )
    viewport_tools_panel = _panel(
        "Viewport Tools",
        [_col([_small("UCS Icon", "ucs", None, N), _small("View Cube", "viewcube", None, N), _small("Navigation Bar", "navbar", None, N)])],
    )
    model_viewports_panel = _panel(
        "Model Viewports",
        [
            _big("Viewport\nConfiguration", "viewports", c("VIEWPORTS"), N),
            _col([_small("Restore", "model", None, N), _small("Join", "join", None, N), _small("Named", "namedview", None, N)]),
        ],
    )

    cmdline_btn = _small("Command Line", "cmdline", checkable=True, color=N, tooltip="Command Line (Ctrl+9)")
    cmdline_btn.setChecked(window.command_dock.isVisible() or not window.isVisible())
    cmdline_btn.toggled.connect(window.command_dock.setVisible)

    palettes_panel = _panel(
        "Palettes",
        [
            _big("Properties", "props", window._show_properties_dock, N, tooltip="Properties (Ctrl+1)"),
            _big("Layers", "layers", c("LAYER"), N),
            _col([
                cmdline_btn,
                _small("Command History", "history", window._show_command_history, N, tooltip="Command History (F2)"),
                _small("External References", "xrefpanel", c("EXTERNALREFERENCES"), N),
            ]),
            _col([_small("Tool Palettes", "toolpal", None, N)]),
        ],
    )
    drafting_panel = _panel(
        "Drafting Settings",
        [
            _col([
                _toggle_button(window, "Grid", "grid", window.grid_button),
                _toggle_button(window, "Snap", "snap", window.snap_button),
                _toggle_button(window, "Ortho", "ortho", window.ortho_button),
            ]),
            _col([
                _toggle_button(window, "Polar", "polar", window.polar_button),
                _toggle_button(window, "Object Snap", "osnap", window.osnap_button),
                _toggle_button(window, "Dynamic Input", "dyn", window.dynamic_input_button),
            ]),
        ],
    )
    interface_panel = _panel(
        "Interface",
        [_col([_small("Tile Vertically", "viewports", None, N), _small("Tile Horizontally", "viewports", None, N), _small("Cascade", "copy", None, N)])],
    )
    return _row([navigate_panel, viewport_tools_panel, model_viewports_panel, palettes_panel, drafting_panel, interface_panel])


def _build_manage_tab(window: "MainWindow") -> QWidget:
    c = lambda name: _cmd(window, name)  # noqa: E731
    N = COLOR_NEUTRAL

    recorder_panel = _panel(
        "Action Recorder",
        [_big("Record", "history", None, N), _col([_small("Play", "list", None, N), _small("Preference", "options", None, N)])],
    )
    customization_panel = _panel(
        "Customization",
        [_big("User\nInterface", "cui", None, N), _big("Tool\nPalettes", "toolpal", None, N)],
    )
    applications_panel = _panel("Applications", [_big("Load\nApplication", "loadapp", None, N)])
    cleanup_panel = _panel(
        "Cleanup",
        [
            _big("Purge", "purge", c("PURGE"), N),
            _col([_small("Audit", "audit", None, N), _small("Drawing Units", "units", c("UNITS"), N), _small("Rename Layer", "rename", c("RENAME"), N)]),
        ],
    )
    settings_panel = _panel(
        "Settings",
        [
            _big("Options", "options", None, N),
            _big("Help", "help", lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)), N, tooltip="README no GitHub (F1)"),
        ],
    )
    return _row([recorder_panel, customization_panel, applications_panel, cleanup_panel, settings_panel])


def _build_output_tab(window: "MainWindow") -> QWidget:
    N = COLOR_NEUTRAL
    plot_panel = _panel(
        "Plot",
        [
            _big("Plot", "plot", window._export_pdf, N, tooltip="Plot / Export PDF (Ctrl+P)"),
            _big("Batch\nPlot", "batchplot", None, N),
            _col([_small("Preview", "preview", None, N), _small("Page Setup", "pagesetup", None, N), _small("Plotter Manager", "plot", None, N)]),
        ],
        launcher=window._export_pdf,
    )
    export_panel = _panel(
        "Export to DWG/PDF",
        [
            _big("Export\nPDF", "exportpdf", window._export_pdf, N),
            _big("Export\nDWG", "exportdwg", window._export_dwg, N),
        ],
    )
    window_panel = _panel(
        "Window",
        [_big("Close\nTab", "closetab", window._close_current_tab, N, tooltip="Close Tab (Ctrl+W)")],
    )
    return _row([plot_panel, export_panel, window_panel])


# ---------------------------------------------------------------------- #
# Quick Access Toolbar
# ---------------------------------------------------------------------- #
QAT_STYLE = """
    QWidget#qat { background-color: #1c1c1c; border-bottom: 1px solid #333333; }
    QToolButton { background-color: transparent; border: none; padding: 3px; }
    QToolButton:hover { background-color: #3a3a3a; border-radius: 3px; }
    QLabel#appLogo { background-color: #c9a227; border-radius: 2px; }
"""
_QAT_ICON_SIZE = 16


def build_quick_access_toolbar(window: "MainWindow") -> QWidget:
    """Barra fina acima do ribbon com o botão do aplicativo (o "N" dourado,
    no lugar do "A" vermelho do AutoCAD) e os comandos sempre visíveis —
    New/Open/Save/Save As/Plot/Undo/Redo, os mesmos da QAT padrão do
    AutoCAD. Pedido do Hamilton a partir do print do AutoCAD 2019:
    "principais comandos sempre no menu aparente"."""
    bar = QWidget()
    bar.setObjectName("qat")
    bar.setStyleSheet(QAT_STYLE)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(6, 2, 8, 2)
    layout.setSpacing(1)

    def qat_button(icon: str, handler, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(svg_icon(icon, COLOR_NEUTRAL, _QAT_ICON_SIZE))
        button.setIconSize(QSize(_QAT_ICON_SIZE, _QAT_ICON_SIZE))
        button.setToolTip(tooltip)
        button.clicked.connect(handler)
        return button

    logo_label = QLabel()
    logo_label.setObjectName("appLogo")
    logo_pixmap = QIcon(str(resolve_app_icon_path())).pixmap(_QAT_ICON_SIZE + 4, _QAT_ICON_SIZE + 4)
    if not logo_pixmap.isNull():
        logo_label.setPixmap(logo_pixmap)
        logo_label.setFixedSize(40, 24)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setToolTip("NewSIcad")
        layout.addWidget(logo_label)
        layout.addSpacing(4)

    layout.addWidget(qat_button("new", window._new_document, "New (Ctrl+N)"))
    layout.addWidget(qat_button("open", window._open_file, "Open... (Ctrl+O)"))
    layout.addWidget(qat_button("save", window._save_file, "Save (Ctrl+S)"))
    layout.addWidget(qat_button("saveas", window._save_file_as, "Save As... (Ctrl+Shift+S)"))
    layout.addWidget(qat_button("plot", window._export_pdf, "Plot / Export PDF (Ctrl+P)"))
    layout.addWidget(qat_button("undo", window._do_undo, "Undo (Ctrl+Z)"))
    layout.addWidget(qat_button("redo", window._do_redo, "Redo (Ctrl+Y)"))
    layout.addStretch(1)
    return bar


def build_ribbon(window: "MainWindow") -> QTabWidget:
    ribbon = QTabWidget()
    ribbon.setStyleSheet(RIBBON_STYLE)
    ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    ribbon.setDocumentMode(True)
    # No macOS, documentMode=True desenha a tira "vazia" da barra de abas
    # (depois da última aba) com o fundo nativo claro do Cocoa, ignorando o
    # stylesheet — só o estilo Fusion (não-nativo) respeita background-color
    # aí. Aplicado só neste widget (não no app inteiro), pra não perder a
    # aparência nativa do resto da janela.
    ribbon.setStyle(QStyleFactory.create("Fusion"))

    ribbon.addTab(_build_home_tab(window), "Home")
    ribbon.addTab(_build_insert_tab(window), "Insert")
    ribbon.addTab(_build_annotate_tab(window), "Annotate")
    ribbon.addTab(_build_view_tab(window), "View")
    ribbon.addTab(_build_manage_tab(window), "Manage")
    ribbon.addTab(_build_output_tab(window), "Output")

    # Altura calculada a partir do sizeHint() real (tab bar + maior página de
    # botões), em vez de um número fixo — um valor fixo menor que o
    # necessário cortava a parte de baixo de todo rótulo e do título de cada
    # painel. +4px de folga pra fontes um pouco mais altas que a testada.
    # + a barra de rolagem horizontal, que em janela estreita apareceria por
    # cima da linha de títulos dos painéis.
    ribbon.setFixedHeight(ribbon.sizeHint().height() + 4 + SCROLLBAR_ALLOWANCE)

    return ribbon
