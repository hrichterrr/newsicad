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

from newsicad.commands import annotation_commands as ac
from newsicad.commands import block_commands as bc
from newsicad.commands import draw_commands as dc
from newsicad.commands import modify_commands as mc
from newsicad.commands import utility_commands as uc
from newsicad.commands import view_commands as vc

COMMAND_REGISTRY = {
    # desenho
    "LINE": dc.line_command,
    "PLINE": dc.pline_command,
    "CIRCLE": dc.circle_command,
    "RECTANG": dc.rectangle_command,
    "ARC": dc.arc_command,
    "ELLIPSE": dc.ellipse_command,
    "POLYGON": dc.polygon_command,
    "SPLINE": dc.spline_command,
    "BOUNDARY": dc.boundary_command,
    "POINT": dc.point_command,
    "XLINE": dc.xline_command,
    "RAY": dc.ray_command,
    "MLINE": dc.mline_command,
    "DONUT": dc.donut_command,
    "REVCLOUD": dc.revcloud_command,
    "WIPEOUT": dc.wipeout_command,
    # medição
    "DIST": dc.dist_command,
    # modificação
    "ERASE": mc.erase_command,
    "MOVE": mc.move_command,
    "COPY": mc.copy_command,
    "ROTATE": mc.rotate_command,
    "SCALE": mc.scale_command,
    "MIRROR": mc.mirror_command,
    "ALIGN": mc.align_command,
    "ARRAY": mc.array_command,
    # blocos
    "BLOCK": bc.block_command,
    "INSERT": bc.insert_command,
    # edição geométrica
    "TRIM": mc.trim_command,
    "EXTEND": mc.extend_command,
    "OFFSET": mc.offset_command,
    "FILLET": mc.fillet_command,
    "CHAMFER": mc.chamfer_command,
    "JOIN": mc.join_command,
    "EXPLODE": mc.explode_command,
    "STRETCH": mc.stretch_command,
    "DIVIDE": mc.divide_command,
    "MEASURE": mc.measure_command,
    "PEDIT": mc.pedit_command,
    "BREAK": mc.break_command,
    "BREAKATPOINT": mc.breakatpoint_command,
    "LENGTHEN": mc.lengthen_command,
    # navegação
    "ZOOM": vc.zoom_command,
    "PAN": vc.pan_command,
    # anotação
    "MTEXT": ac.mtext_command,
    "DIMLINEAR": ac.dimlinear_command,
    "DIMALIGNED": ac.dimaligned_command,
    "DIMANGULAR": ac.dimangular_command,
    "DIMRADIUS": ac.dimradius_command,
    "DIMDIAMETER": ac.dimdiameter_command,
    "DIMSTYLE": ac.dimstyle_command,
    "HATCH": ac.hatch_command,
    "HATCHEDIT": ac.hatchedit_command,
    "LEADER": ac.leader_command,
    "CENTERMARK": ac.centermark_command,
    "DIMBREAK": ac.dimbreak_command,
    "TABLE": ac.table_command,
    "FIELD": ac.field_command,
    # utilitários
    "AREA": uc.area_command,
    "ID": uc.id_command,
    "DDEDIT": uc.edit_text_command,
    "PURGE": uc.purge_command,
    "MATCHPROP": uc.matchprop_command,
    "SELECTSIMILAR": uc.select_similar_command,
    "LAYMCH": uc.laymch_command,
    "LAYISO": uc.layiso_command,
    "LAYUNISO": uc.layuniso_command,
    "QSELECT": uc.qselect_command,
    "CLIP": mc.clip_command,
    "CLIPOFF": mc.clipoff_command,
    "COPYCLIP": mc.copyclip_command,
    "CUTCLIP": mc.cutclip_command,
    "PASTECLIP": mc.pasteclip_command,
}

# Comandos que NUNCA mutam `document.entities` (só consultam/leem, ou mexem
# só em `ctx.selection` — que não é parte do snapshot de undo). `MainWindow`
# pulava `undo_stack.push()` só nos comandos tratados à parte antes de
# `interpreter.start(text)` (UNDO/REDO/UNITS/BEDIT/...); todo o resto,
# incluindo ZOOM/PAN/DIST/ID/AREA (puro texto informativo, sem nenhuma
# geometria criada) e SELECTSIMILAR/QSELECT/COPYCLIP (só tocam seleção/
# clipboard), empilhava um snapshot profundo do desenho inteiro à toa —
# além de gastar memória sem necessidade num desenho grande, isso fazia um
# Ctrl+Z depois de um ZOOM "engolir" o passo de undo real anterior sem
# desfazer nada visível (bug real de auditoria, 2026-08-22).
READ_ONLY_COMMANDS = {
    "ZOOM", "PAN", "DIST", "AREA", "ID", "SELECTSIMILAR", "QSELECT", "COPYCLIP",
}

# Comandos conhecidos (do guia de atalhos do AutoCAD) que ainda não têm
# implementação em COMMAND_REGISTRY nem tratamento especial em
# MainWindow._start_command — ficam desabilitados no menu/ribbon e dão um
# aviso claro na linha de comando em vez de "comando desconhecido".
PLANNED_COMMANDS = {
    "REGION",
    "DIM", "DIMEDIT", "DIMREASSOCIATE",
    "INTERSECT",
    "OPTIONS", "GEOMCONSTRAINT", "DSETTINGS",
    "DVIEW",
    # INSERTOBJ (OLE Object) fica planejado de propósito: embutir um objeto
    # OLE de verdade (Excel, Word...) exige integração COM do Windows
    # (win32com/pywin32), uma tecnologia inteiramente à parte de tudo que o
    # resto do NewSIcad usa (Qt puro, sem nenhuma dependência de plataforma
    # hoje) — implementar de mentira (ex.: só um retângulo com um ícone)
    # fingiria uma funcionalidade que não existe de verdade, o que vai contra
    # o espírito documentado em todo o resto do projeto.
    "INSERTOBJ",
}

# BEDIT, REFEDIT, XREF, EXTERNALREFERENCES, IMAGEATTACH, PLOT, PUBLISH,
# LAYER e RENAME estão implementados, mas — assim como UNITS/REGEN — não
# passam pelo sistema de Prompt (point/distance/text/keyword/selection):
# precisam de um QDialog, QFileDialog ou QDockWidget (LAYER/RENAME abrem o
# painel de camadas), então a MainWindow os intercepta antes de chamar
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
    "POINT": "POINT", "PO": "POINT",
    "XLINE": "XLINE", "XL": "XLINE",
    "RAY": "RAY",
    "MLINE": "MLINE", "ML": "MLINE",
    "DONUT": "DONUT", "DO": "DONUT",
    "REVCLOUD": "REVCLOUD",
    "WIPEOUT": "WIPEOUT",
    "IMAGEATTACH": "IMAGEATTACH", "IM": "IMAGEATTACH",
    "IMPORTPDF": "IMPORTPDF",
    "VIEWPORTS": "VIEWPORTS", "VM": "VIEWPORTS",
    # --- anotação e medição ---
    "MTEXT": "MTEXT", "T": "MTEXT", "MT": "MTEXT",
    "DIMLINEAR": "DIMLINEAR", "DLI": "DIMLINEAR",
    "DIMALIGNED": "DIMALIGNED", "DAL": "DIMALIGNED",
    "DIMANGULAR": "DIMANGULAR", "DAN": "DIMANGULAR",
    "DIMRADIUS": "DIMRADIUS", "DRA": "DIMRADIUS",
    "DIMDIAMETER": "DIMDIAMETER", "DDI": "DIMDIAMETER",
    "DIST": "DIST", "DI": "DIST",
    "AREA": "AREA", "AA": "AREA",
    "ID": "ID",
    "DDEDIT": "DDEDIT", "ED": "DDEDIT",
    "MATCHPROP": "MATCHPROP", "MA": "MATCHPROP",
    "DIMSTYLE": "DIMSTYLE", "D": "DIMSTYLE", "DS": "DIMSTYLE",
    "DIM": "DIM",
    "CENTERMARK": "CENTERMARK", "DIMCENTER": "CENTERMARK",
    "DIMBREAK": "DIMBREAK",
    "DIMEDIT": "DIMEDIT", "DED": "DIMEDIT",
    "DIMREASSOCIATE": "DIMREASSOCIATE", "DRE": "DIMREASSOCIATE",
    "STYLE": "STYLE", "ST": "STYLE",
    "FIELD": "FIELD",
    "TABLESTYLE": "TABLESTYLE", "TS": "TABLESTYLE",
    "MLEADERSTYLE": "MLEADERSTYLE", "MLS": "MLEADERSTYLE",
    "FIND": "FIND",
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
    "BREAK": "BREAK", "BR": "BREAK",
    "BREAKATPOINT": "BREAKATPOINT",
    "LENGTHEN": "LENGTHEN", "LEN": "LENGTHEN",
    "HATCHEDIT": "HATCHEDIT", "HE": "HATCHEDIT",
    "ALIGN": "ALIGN", "AL": "ALIGN",
    "ARRAY": "ARRAY", "AR": "ARRAY",
    "MEASURE": "MEASURE", "ME": "MEASURE",
    "INTERSECT": "INTERSECT", "IN": "INTERSECT",
    "SELECTSIMILAR": "SELECTSIMILAR", "SIM": "SELECTSIMILAR",
    "LAYMCH": "LAYMCH",
    "LAYISO": "LAYISO",
    "LAYUNISO": "LAYUNISO",
    "QSELECT": "QSELECT",
    "COPYCLIP": "COPYCLIP",
    "CUTCLIP": "CUTCLIP",
    "PASTECLIP": "PASTECLIP",
    # --- blocos / referências externas ---
    "BEDIT": "BEDIT", "BE": "BEDIT",
    "REFEDIT": "REFEDIT",
    "XREF": "XREF", "XR": "XREF",
    "EXTERNALREFERENCES": "EXTERNALREFERENCES", "ER": "EXTERNALREFERENCES",
    "CLIP": "CLIP", "XCLIP": "CLIP",
    "CLIPOFF": "CLIPOFF",
    # --- navegação de vista ---
    "ZOOM": "ZOOM", "Z": "ZOOM",
    "PAN": "PAN", "P": "PAN",
    "REGEN": "REGEN", "RE": "REGEN", "REA": "REGEN",
    "DVIEW": "DVIEW",
    # --- configuração / saída ---
    "LAYER": "LAYER", "LA": "LAYER",
    "RENAME": "RENAME", "REN": "RENAME",
    "PURGE": "PURGE", "PU": "PURGE",
    "OPTIONS": "OPTIONS", "OP": "OPTIONS",
    "UNITS": "UNITS",
    "GEOMCONSTRAINT": "GEOMCONSTRAINT", "GCON": "GEOMCONSTRAINT",
    "DSETTINGS": "DSETTINGS",
    "PLOT": "PLOT",
    "PUBLISH": "PUBLISH",
    "DATALINK": "DATALINK",
    "INSERTOBJ": "INSERTOBJ",
    # --- desfazer / restaurar (tratados à parte pela MainWindow) ---
    "UNDO": "UNDO", "U": "UNDO",
    "REDO": "REDO",
    "OOPS": "OOPS",
}
