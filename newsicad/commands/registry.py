"""Nome de comando + aliases (idênticos aos do AutoCAD) -> função geradora.

ALIASES cobre TODOS os atalhos do guia rápido do AutoCAD fornecido pelo
usuário, mesmo os comandos cujo nome canônico ainda não está em
COMMAND_REGISTRY — nesse caso o CommandInterpreter reconhece o atalho mas
avisa que o comando ainda não foi implementado, em vez de dizer "comando
desconhecido".

UNDO/REDO/OOPS/REGEN/UNITS não entram em COMMAND_REGISTRY: não são comandos
geradores de prompts, são tratados à parte pela MainWindow (`_start_command`).
"""

from __future__ import annotations

from newsicad.commands import block_commands as bc
from newsicad.commands import draw_commands as dc
from newsicad.commands import modify_commands as mc
from newsicad.commands import view_commands as vc

COMMAND_REGISTRY = {
    # desenho
    "LINE": dc.line_command,
    "PLINE": dc.pline_command,
    "CIRCLE": dc.circle_command,
    "RECTANG": dc.rectangle_command,
    "ARC": dc.arc_command,
    "ELLIPSE": dc.ellipse_command,
    # medição
    "DIST": dc.dist_command,
    # modificação
    "ERASE": mc.erase_command,
    "MOVE": mc.move_command,
    "COPY": mc.copy_command,
    "ROTATE": mc.rotate_command,
    "SCALE": mc.scale_command,
    "MIRROR": mc.mirror_command,
    # blocos
    "BLOCK": bc.block_command,
    "INSERT": bc.insert_command,
    # navegação
    "ZOOM": vc.zoom_command,
    "PAN": vc.pan_command,
}

# Comandos conhecidos (do guia de atalhos do AutoCAD) que ainda não têm
# implementação em COMMAND_REGISTRY nem tratamento especial em
# MainWindow._start_command — ficam desabilitados no menu/ribbon e dão um
# aviso claro na linha de comando em vez de "comando desconhecido".
PLANNED_COMMANDS = {
    "HATCH", "REGION",
    "MTEXT", "TABLE", "LEADER",
    "DIMLINEAR", "DIMALIGNED", "DIMANGULAR", "DIMRADIUS", "DIMDIAMETER",
    "DIMSTYLE", "DIM", "DIMEDIT", "DIMREASSOCIATE",
    "MATCHPROP",
    "TRIM", "EXTEND", "OFFSET", "FILLET", "CHAMFER", "EXPLODE", "JOIN",
    "STRETCH", "DIVIDE", "PEDIT", "HATCHEDIT", "ALIGN", "ARRAY", "BOUNDARY",
    "MEASURE", "INTERSECT",
    "POLYGON", "SPLINE",
    # VIEWPORTS fica planejado de propósito: um viewport de verdade vive numa
    # layout de paper space, conceito que o NewSIcad não tem (só um espaço de
    # modelo único). Uma versão simplificada ("janela congelada" dentro do
    # próprio modelo) seria só um gadget de zoom duplicado sem paralelo real
    # no AutoCAD — decidimos não fingir essa funcionalidade (ver README).
    "VIEWPORTS",
    "OPTIONS", "STYLE", "GEOMCONSTRAINT", "DSETTINGS",
    "DVIEW",
}

# BEDIT, REFEDIT, XREF, EXTERNALREFERENCES, IMAGEATTACH, PLOT e PUBLISH estão
# implementados, mas — assim como UNITS/REGEN — não passam pelo sistema de
# Prompt (point/distance/text/keyword/selection): precisam de um QDialog ou
# QFileDialog, então a MainWindow os intercepta antes de chamar
# CommandInterpreter.start() (ver MainWindow._start_command em
# newsicad/ui/main_window.py). Por isso não aparecem em COMMAND_REGISTRY.

ALIASES = {
    # --- desenho (DRAW) ---
    "LINE": "LINE", "L": "LINE",
    "PLINE": "PLINE", "PL": "PLINE",
    "CIRCLE": "CIRCLE", "C": "CIRCLE",
    "RECTANG": "RECTANG", "REC": "RECTANG",
    "ARC": "ARC", "A": "ARC",
    "ELLIPSE": "ELLIPSE", "EL": "ELLIPSE",
    "HATCH": "HATCH", "H": "HATCH",
    "BLOCK": "BLOCK", "B": "BLOCK",
    "INSERT": "INSERT", "I": "INSERT",
    "REGION": "REGION", "REG": "REGION",
    "POLYGON": "POLYGON", "POL": "POLYGON",
    "SPLINE": "SPLINE", "SP": "SPLINE",
    "TABLE": "TABLE", "TB": "TABLE",
    "LEADER": "LEADER", "LE": "LEADER",
    "BOUNDARY": "BOUNDARY", "BO": "BOUNDARY",
    "IMAGEATTACH": "IMAGEATTACH", "IM": "IMAGEATTACH",
    "VIEWPORTS": "VIEWPORTS", "VM": "VIEWPORTS",
    # --- anotação e medição ---
    "MTEXT": "MTEXT", "T": "MTEXT", "MT": "MTEXT",
    "DIMLINEAR": "DIMLINEAR", "DLI": "DIMLINEAR",
    "DIMALIGNED": "DIMALIGNED", "DAL": "DIMALIGNED",
    "DIMANGULAR": "DIMANGULAR", "DAN": "DIMANGULAR",
    "DIMRADIUS": "DIMRADIUS", "DRA": "DIMRADIUS",
    "DIMDIAMETER": "DIMDIAMETER", "DDI": "DIMDIAMETER",
    "DIST": "DIST", "DI": "DIST",
    "MATCHPROP": "MATCHPROP", "MA": "MATCHPROP",
    "DIMSTYLE": "DIMSTYLE", "D": "DIMSTYLE", "DS": "DIMSTYLE",
    "DIM": "DIM",
    "DIMEDIT": "DIMEDIT", "DED": "DIMEDIT",
    "DIMREASSOCIATE": "DIMREASSOCIATE", "DRE": "DIMREASSOCIATE",
    "STYLE": "STYLE", "ST": "STYLE",
    # --- modificação (MODIFY) ---
    "MOVE": "MOVE", "M": "MOVE",
    "COPY": "COPY", "CO": "COPY", "CP": "COPY",
    "TRIM": "TRIM", "TR": "TRIM",
    "EXTEND": "EXTEND", "EX": "EXTEND",
    "OFFSET": "OFFSET", "O": "OFFSET",
    "ROTATE": "ROTATE", "RO": "ROTATE",
    "SCALE": "SCALE", "SC": "SCALE",
    "MIRROR": "MIRROR", "MI": "MIRROR",
    "FILLET": "FILLET", "F": "FILLET",
    "CHAMFER": "CHAMFER", "CHA": "CHAMFER",
    "ERASE": "ERASE", "E": "ERASE",
    "EXPLODE": "EXPLODE", "X": "EXPLODE",
    "JOIN": "JOIN", "J": "JOIN",
    "STRETCH": "STRETCH", "S": "STRETCH",
    "DIVIDE": "DIVIDE", "DIV": "DIVIDE",
    "PEDIT": "PEDIT", "PE": "PEDIT",
    "HATCHEDIT": "HATCHEDIT", "HE": "HATCHEDIT",
    "ALIGN": "ALIGN", "AL": "ALIGN",
    "ARRAY": "ARRAY", "AR": "ARRAY",
    "MEASURE": "MEASURE", "ME": "MEASURE",
    "INTERSECT": "INTERSECT", "IN": "INTERSECT",
    # --- blocos / referências externas ---
    "BEDIT": "BEDIT", "BE": "BEDIT",
    "REFEDIT": "REFEDIT",
    "XREF": "XREF", "XR": "XREF",
    "EXTERNALREFERENCES": "EXTERNALREFERENCES", "ER": "EXTERNALREFERENCES",
    # --- navegação de vista ---
    "ZOOM": "ZOOM", "Z": "ZOOM",
    "PAN": "PAN",
    "REGEN": "REGEN", "RE": "REGEN", "REA": "REGEN",
    "DVIEW": "DVIEW",
    # --- configuração / saída ---
    "OPTIONS": "OPTIONS", "OP": "OPTIONS",
    "UNITS": "UNITS",
    "GEOMCONSTRAINT": "GEOMCONSTRAINT", "GCON": "GEOMCONSTRAINT",
    "DSETTINGS": "DSETTINGS",
    "PLOT": "PLOT",
    "PUBLISH": "PUBLISH",
    # --- desfazer / restaurar (tratados à parte pela MainWindow) ---
    "UNDO": "UNDO", "U": "UNDO",
    "REDO": "REDO",
    "OOPS": "OOPS",
}
