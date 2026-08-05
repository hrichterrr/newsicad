"""Nome de comando + aliases (idênticos aos do AutoCAD) -> função geradora.

ALIASES cobre TODOS os atalhos do guia rápido do AutoCAD fornecido pelo
usuário, mesmo os comandos cujo nome canônico ainda não está em
COMMAND_REGISTRY — nesse caso o CommandInterpreter reconhece o atalho mas
avisa que o comando ainda não foi implementado, em vez de dizer "comando
desconhecido".

UNDO/REDO não entram em COMMAND_REGISTRY: não são comandos geradores de
prompts, são tratados à parte pela MainWindow (pilha de undo por snapshot).
"""

from __future__ import annotations

from newsicad.commands import draw_commands as dc
from newsicad.commands import modify_commands as mc

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
}

# Comandos conhecidos (do guia de atalhos do AutoCAD) que ainda não têm
# implementação em COMMAND_REGISTRY — ficam desabilitados no menu e dão um
# aviso claro na linha de comando em vez de "comando desconhecido".
PLANNED_COMMANDS = {
    "HATCH",
    "BLOCK",
    "INSERT",
    "REGION",
    "MTEXT",
    "DIMLINEAR",
    "DIMALIGNED",
    "DIMANGULAR",
    "DIMRADIUS",
    "DIMSTYLE",
    "MATCHPROP",
    "TRIM",
    "EXTEND",
    "OFFSET",
    "FILLET",
    "CHAMFER",
    "EXPLODE",
    "JOIN",
    "STRETCH",
}

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
    # --- anotação e medição ---
    "MTEXT": "MTEXT", "T": "MTEXT", "MT": "MTEXT",
    "DIMLINEAR": "DIMLINEAR", "DLI": "DIMLINEAR",
    "DIMALIGNED": "DIMALIGNED", "DAL": "DIMALIGNED",
    "DIMANGULAR": "DIMANGULAR", "DAN": "DIMANGULAR",
    "DIMRADIUS": "DIMRADIUS", "DRA": "DIMRADIUS",
    "DIST": "DIST", "DI": "DIST",
    "MATCHPROP": "MATCHPROP", "MA": "MATCHPROP",
    "DIMSTYLE": "DIMSTYLE", "D": "DIMSTYLE",
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
    # --- desfazer (tratados à parte pela MainWindow) ---
    "UNDO": "UNDO", "U": "UNDO",
    "REDO": "REDO",
}
