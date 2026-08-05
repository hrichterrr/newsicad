"""Nome de comando + aliases (idênticos aos do AutoCAD) -> função geradora."""

from __future__ import annotations

from newsicad.commands import draw_commands as dc

COMMAND_REGISTRY = {
    "LINE": dc.line_command,
    "CIRCLE": dc.circle_command,
    "ARC": dc.arc_command,
    "RECTANGLE": dc.rectangle_command,
    "PLINE": dc.pline_command,
}

ALIASES = {
    "LINE": "LINE",
    "L": "LINE",
    "CIRCLE": "CIRCLE",
    "C": "CIRCLE",
    "ARC": "ARC",
    "A": "ARC",
    "RECTANGLE": "RECTANGLE",
    "REC": "RECTANGLE",
    "PLINE": "PLINE",
    "PL": "PLINE",
}
