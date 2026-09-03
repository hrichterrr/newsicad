"""Importação das anotações "prontas" do DXF — TEXT/ATTRIB com alinhamento,
MTEXT com rotação/largura, MULTILEADER, LEADER, DIMENSION de outros
programas e ACAD_TABLE — pro modelo do NewSIcad (newsicad/core/).

Módulo à parte de `newsicad/io/dxf_io.py` de propósito (WP-B 2026-09):
`dxf_io.py` chama daqui em poucas linhas e continua dono do mapeamento
entidade-a-entidade (`_from_dxf_entity`), da cor (`_apply_dxf_color`) e da
gravação; aqui fica só o que é anotação.

Princípio: MULTILEADER, LEADER, DIMENSION e ACAD_TABLE são entidades cuja
aparência o próprio AutoCAD já calculou e gravou no arquivo (bloco anônimo
`*D…`/`*T…` da cota/tabela, "context data" do leader). Em vez de tentar
reconstruir cada uma com o nosso DIMSTYLE fixo (o que dava cotas com texto
20x maior que a planta em desenhos em metros, leaders ignorados e tabelas
"explodidas"), usamos `ezdxf.virtual_entities()` — que materializa essa
geometria pronta em LINE/TEXT/MTEXT/SOLID/HATCH/POLYLINE já em coordenadas
do desenho — e empacotamos tudo num BLOCO ANÔNIMO por anotação
(`*ML_<handle>`, `*LD_<handle>`, `*D_<handle>`, `*T_<handle>`) com uma
`BlockReference` em (0,0) na camada/cor da anotação original. Decisão:
bloco (e não entidades soltas) pra cada anotação continuar UM objeto
selecionável/movível/apagável, como no AutoCAD, sem espalhar dezenas de
linhas e textos soltos no desenho. A anotação importada é ESTÁTICA (não
re-mede ao mover os pontos — ver README); só uma `Dimension` gravada pelo
próprio NewSIcad (XDATA `NEWSICAD`) volta como cota nativa/editável.
"""

from __future__ import annotations

import math
import statistics
from typing import Callable, Iterable, Iterator

from ezdxf.enums import TextEntityAlignment

from newsicad.core.document import Document
from newsicad.core.entities import BlockReference, Entity, Hatch, Point, Text

# Altura abaixo da qual um TEXT/ATTRIB/MTEXT é descartado na leitura: não é
# visível em nenhuma escala e só polui seleção/zoom extents (o canvas
# também não desenha h <= 1e-6). Caso real: ATTRIBs "vazios" com altura
# 2.5e-05 em blocos de fabricante — ficam, são inofensivos; o corte é só
# pro que é zero de verdade.
TEXT_HEIGHT_MIN = 1e-6

# Mapeamento entre TEXT_JUSTIFY_OPTIONS (core/entities.py) e o group code 71
# (attachment_point) do MTEXT — mesma numeração 1-9 usada pelo AutoCAD/DXF
# (1=Top Left ... 9=Bottom Right, varrendo por linha).
JUSTIFY_TO_ATTACHMENT = {
    "TL": 1, "TC": 2, "TR": 3,
    "ML": 4, "MC": 5, "MR": 6,
    "BL": 7, "BC": 8, "BR": 9,
}
ATTACHMENT_TO_JUSTIFY = {v: k for k, v in JUSTIFY_TO_ATTACHMENT.items()}

# TEXT/ATTRIB: halign (72) + valign (73) -> `Text.justify`. O ponto 10 do
# TEXT é sempre ESQUERDA-BASELINE; pra qualquer alinhamento diferente de
# LEFT a âncora de verdade é o ponto 11 (align_point) — `get_placement()`
# do ezdxf devolve o ponto certo pra cada caso. "B?" no NewSIcad = linha de
# base (ver Text em core/entities.py), então LEFT/CENTER/RIGHT (valign 0 =
# baseline) viram BL/BC/BR; MIDDLE (valign 0 + halign 4) é o centro
# vertical da caixa; ALIGNED/FIT (texto esticado entre dois pontos) viram
# BL no primeiro ponto, girados na direção do segundo — o esticamento em si
# não é modelado (simplificação documentada).
_ALIGN_TO_JUSTIFY = {
    TextEntityAlignment.LEFT: "BL",
    TextEntityAlignment.CENTER: "BC",
    TextEntityAlignment.RIGHT: "BR",
    TextEntityAlignment.ALIGNED: "BL",
    TextEntityAlignment.FIT: "BL",
    TextEntityAlignment.MIDDLE: "MC",
    TextEntityAlignment.MIDDLE_LEFT: "ML",
    TextEntityAlignment.MIDDLE_CENTER: "MC",
    TextEntityAlignment.MIDDLE_RIGHT: "MR",
    TextEntityAlignment.TOP_LEFT: "TL",
    TextEntityAlignment.TOP_CENTER: "TC",
    TextEntityAlignment.TOP_RIGHT: "TR",
    TextEntityAlignment.BOTTOM_LEFT: "BL",
    TextEntityAlignment.BOTTOM_CENTER: "BC",
    TextEntityAlignment.BOTTOM_RIGHT: "BR",
}

# Tipos de entidade que este módulo importa como bloco anônimo + prefixo do
# nome do bloco (o resto do nome é o handle da entidade original).
ANNOTATION_BLOCK_PREFIX = {
    "MULTILEADER": "*ML_",
    "LEADER": "*LD_",
    "DIMENSION": "*D_",
    "ACAD_TABLE": "*T_",
}

# Blocos de seta (`_CLOSEDFILLED`, `_DOT`, `_OBLIQUE`...) e blocos anônimos
# não entram em `Document.block_definitions` (ver o filtro de nomes em
# dxf_io.load_dxf) — um INSERT deles dentro de uma anotação é EXPANDIDO
# (virtual_entities) em vez de virar uma BlockReference órfã.
_EXPAND_INSERT_PREFIXES = ("_", "*")
_MAX_EXPAND_DEPTH = 4


def _point(v) -> Point:
    return Point(float(v[0]), float(v[1]))


def _style_name(e) -> str:
    return e.dxf.get("style", "Standard") or "Standard"


def entity_layer(e) -> str:
    """Camada da entidade. ACAD_TABLE chega como `AcadTableBlockContent`
    (armazenamento bruto de tags do ezdxf) que NÃO carrega a subclasse
    AcDbEntity em `dxf` — `e.dxf.layer` devolve sempre "0"; a camada de
    verdade está nas tags guardadas (group code 8 de AcDbEntity)."""
    if e.dxf.hasattr("layer"):
        return e.dxf.layer
    xtags = getattr(e, "xtags", None)
    if xtags is not None:
        try:
            return xtags.get_subclass("AcDbEntity").get_first_value(8, "0") or "0"
        except Exception:
            pass
    return e.dxf.get("layer", "0") or "0"


def text_from_dxf_text(e, layer: str | None = None) -> Text | None:
    """TEXT/ATTRIB -> `Text`, respeitando halign/valign/align_point via
    `get_placement()` (ver `_ALIGN_TO_JUSTIFY`). Antes disso todo TEXT era
    criado com `insertion_point=insert` e justify "TL": o ponto 10 é
    esquerda-BASELINE, então o texto aparecia uma altura abaixo do lugar, e
    pra TEXT centralizado/à direita (legendas, etiquetas de bloco) a âncora
    nem era o ponto certo (achado text-attrib-baseline-e-alinhamento).
    Devolve None pra texto vazio ou altura <= `TEXT_HEIGHT_MIN`. `layer`
    força a camada (ATTRIB herdando a do INSERT, TEXT de leader herdando a
    do MULTILEADER); padrão é a camada da própria entidade."""
    try:
        content = e.plain_text()
    except Exception:
        content = e.dxf.get("text", "") or ""
    height = float(e.dxf.get("height", 0.0) or 0.0)
    if not content.strip() or height <= TEXT_HEIGHT_MIN:
        return None
    try:
        align, p1, p2 = e.get_placement()
    except Exception:
        align, p1, p2 = TextEntityAlignment.LEFT, e.dxf.insert, None
    rotation = math.radians(float(e.dxf.get("rotation", 0.0) or 0.0))
    if align in (TextEntityAlignment.ALIGNED, TextEntityAlignment.FIT) and p2 is not None:
        dx, dy = float(p2[0]) - float(p1[0]), float(p2[1]) - float(p1[1])
        if abs(dx) > 1e-12 or abs(dy) > 1e-12:
            rotation = math.atan2(dy, dx)
    return Text(
        layer=layer or e.dxf.layer,
        insertion_point=_point(p1),
        content=content,
        height=height,
        rotation=rotation,
        justify=_ALIGN_TO_JUSTIFY.get(align, "BL"),
        style=_style_name(e),
        width_factor=float(e.dxf.get("width", 1.0) or 1.0),
    )


def text_from_dxf_mtext(e, layer: str | None = None) -> Text | None:
    """MTEXT -> `Text` com attachment_point, ROTAÇÃO real (`get_rotation()`
    — o dwg2dxf só grava `text_direction`, group code 11, nunca o 50; ler
    `dxf.rotation` deixava 100% dos textos girados na horizontal), LARGURA
    da caixa (41, quebra por palavras no canvas) e espaçamento de linha (44)
    — achado mtext-rotacao-largura-quebra. None pra altura <=
    `TEXT_HEIGHT_MIN`."""
    height = float(e.dxf.get("char_height", 0.0) or 0.0)
    if height <= TEXT_HEIGHT_MIN:
        return None
    try:
        rotation = math.radians(float(e.get_rotation()))
    except Exception:
        rotation = math.radians(float(e.dxf.get("rotation", 0.0) or 0.0))
    attachment = e.dxf.get("attachment_point", 1)
    return Text(
        layer=layer or e.dxf.layer,
        insertion_point=_point(e.dxf.insert),
        content=e.plain_text(),
        height=height,
        rotation=rotation,
        justify=ATTACHMENT_TO_JUSTIFY.get(attachment, "TL"),
        style=_style_name(e),
        width=max(float(e.dxf.get("width", 0.0) or 0.0), 0.0),
        line_spacing_factor=float(e.dxf.get("line_spacing_factor", 1.0) or 1.0),
    )


def _solid_to_hatch(v, layer: str) -> Hatch | None:
    """SOLID/TRACE (seta de cota/leader) -> `Hatch` sólida. A ordem dos
    vértices do SOLID é 0-1-3-2 (o formato troca os dois últimos)."""
    try:
        v0, v1, v2, v3 = v.dxf.vtx0, v.dxf.vtx1, v.dxf.vtx2, v.dxf.vtx3
    except AttributeError:
        return None
    pts = [_point(v0), _point(v1), _point(v3), _point(v2)]
    # SOLID triangular: vtx3 == vtx2 — tira o vértice repetido
    if pts[2].distance_to(pts[3]) < 1e-12:
        pts.pop()
    if len(pts) < 3:
        return None
    return Hatch(layer=layer, boundary_points=pts, solid_fill=True)


def has_newsicad_xdata(e, appid: str) -> bool:
    try:
        return bool(e.get_xdata(appid))
    except Exception:
        return False


class AnnotationImporter:
    """Converte as anotações de um arquivo DXF em blocos anônimos +
    `BlockReference` (ver docstring do módulo). `convert_entity` e
    `apply_color` são os `_from_dxf_entity`/`_apply_dxf_color` de dxf_io —
    injetados pra reaproveitar o mapeamento de LINE/LWPOLYLINE/POLYLINE/
    HATCH/CIRCLE/ARC/INSERT sem import circular. `dimension_text_heights`
    acumula a altura real do texto de cada cota importada, pra
    `Document.dim_style` acompanhar o arquivo (ver `read_dim_style`)."""

    def __init__(
        self,
        document: Document,
        convert_entity: Callable[[object], Entity | None],
        apply_color: Callable[[Entity, object], None],
        native_appid: str,
    ) -> None:
        self.document = document
        self.convert_entity = convert_entity
        self.apply_color = apply_color
        self.native_appid = native_appid
        self.dimension_text_heights: list[float] = []
        self._fallback_counter = 0

    # ------------------------------------------------------------------ #
    def import_entity(self, e) -> list[Entity] | None:
        """Entidades a adicionar no lugar de `e` (a `BlockReference` do
        bloco anônimo), ou None quando `e` não é anotação deste módulo — ou
        é uma DIMENSION do próprio NewSIcad (XDATA) / uma anotação sem
        geometria utilizável: nesses casos `dxf_io` segue o caminho normal
        (`_from_dxf_entity`: Dimension nativa, ou contagem em "skipped")."""
        dxftype = e.dxftype()
        prefix = ANNOTATION_BLOCK_PREFIX.get(dxftype)
        if prefix is None:
            return None
        if dxftype == "DIMENSION" and has_newsicad_xdata(e, self.native_appid):
            return None
        try:
            virtual = list(e.virtual_entities())
        except Exception:
            return None
        parts = self._convert_parts(e, virtual)
        if not parts:
            return None
        if dxftype == "DIMENSION":
            self.dimension_text_heights.extend(
                part.height for part in parts if isinstance(part, Text) and part.height > TEXT_HEIGHT_MIN
            )
        return [self._as_block(e, prefix, parts)]

    # ------------------------------------------------------------------ #
    def _block_name(self, e, prefix: str) -> str:
        handle = e.dxf.get("handle", None)
        if not handle:
            self._fallback_counter += 1
            handle = f"V{self._fallback_counter}"
        name = f"{prefix}{handle}"
        while name in self.document.block_definitions:
            self._fallback_counter += 1
            name = f"{prefix}{handle}_{self._fallback_counter}"
        return name

    def _as_block(self, e, prefix: str, parts: list[Entity]) -> BlockReference:
        name = self._block_name(e, prefix)
        self.document.define_block(name, parts)
        ref = BlockReference(layer=entity_layer(e), block_name=name, insertion_point=Point(0, 0))
        self.apply_color(ref, e)
        return ref

    def _convert_parts(self, parent, virtual: Iterable, depth: int = 0) -> list[Entity]:
        layer = entity_layer(parent)
        out: list[Entity] = []
        for v in virtual:
            dxftype = v.dxftype()
            if dxftype == "POINT":
                continue  # defpoints da cota — não são desenho
            if dxftype == "TEXT":
                entity = text_from_dxf_text(v)
            elif dxftype == "MTEXT":
                entity = text_from_dxf_mtext(v)
            elif dxftype in ("SOLID", "TRACE"):
                entity = _solid_to_hatch(v, layer)
            elif dxftype == "INSERT" and self._should_expand(v):
                if depth < _MAX_EXPAND_DEPTH:
                    try:
                        nested = list(v.virtual_entities())
                    except Exception:
                        nested = []
                    out.extend(self._convert_parts(parent, nested, depth + 1))
                continue
            else:
                entity = self.convert_entity(v)
            if entity is None:
                continue
            # Sub-entidade na camada "0" herda a camada da anotação (mesma
            # regra do AutoCAD pra conteúdo de bloco na camada 0); cor
            # própria da sub-entidade vale, senão a da anotação.
            if not v.dxf.get("layer", "0") or v.dxf.get("layer", "0") == "0":
                entity.layer = layer
            self.apply_color(entity, v)
            if entity.color is None:
                self.apply_color(entity, parent)
            out.append(entity)
        return out

    def _should_expand(self, insert) -> bool:
        name = insert.dxf.get("name", "") or ""
        if name.startswith(_EXPAND_INSERT_PREFIXES):
            return True
        return name not in self.document.block_definitions


def attrib_texts(
    insert,
    fallback_layer: str,
    apply_color: Callable[[Entity, object], None] | None = None,
) -> Iterator[Text]:
    """ATTRIBs (valores de atributo preenchidos — as etiquetas/tags dos
    símbolos, ex.: numeração de tomada) de um INSERT como entidades `Text`
    independentes, com alinhamento/baseline via `text_from_dxf_text`. O
    ATTRIB já carrega posição/altura/rotação no MESMO espaço do INSERT
    (absolutas no modelspace; no espaço do bloco pai quando o INSERT está
    dentro de uma definição de bloco — achado attrib-aninhado: as 225
    etiquetas da R04 moravam em INSERTs aninhados e nunca eram lidas).
    Simplificação documentada: o vínculo texto<->bloco não é modelado
    (mover o bloco depois não arrasta a etiqueta junto). `apply_color` (o
    `_apply_dxf_color` de dxf_io) aplica a cor própria do ATTRIB."""
    for attrib in getattr(insert, "attribs", ()):
        try:
            if attrib.is_invisible:
                continue
        except AttributeError:
            pass
        text = text_from_dxf_text(attrib, layer=attrib.dxf.get("layer", fallback_layer) or fallback_layer)
        if text is None:
            continue
        if apply_color is not None:
            apply_color(text, attrib)
        yield text


def read_dim_style(header, imported_text_heights: list[float]) -> tuple[float, float]:
    """(altura do texto, tamanho da seta) das cotas NATIVAS pra
    `Document.dim_style`, proporcionais ao arquivo: mediana da altura real
    do texto das cotas importadas quando houver (é o que o desenhista está
    usando de fato, já com overrides), senão `$DIMTXT*$DIMSCALE`; a seta
    segue a razão `$DIMASZ/$DIMTXT` do cabeçalho (0.3 se faltar). Sem nada
    disso ficam os padrões históricos do canvas (2.0/0.6, desenho em mm) —
    achado dimension-rerender-escala-errada."""
    from newsicad.core.document import DimStyle

    default = DimStyle()
    scale = float(header.get("$DIMSCALE", 1.0) or 1.0)
    dimtxt = float(header.get("$DIMTXT", 0.0) or 0.0)
    dimasz = float(header.get("$DIMASZ", 0.0) or 0.0)
    heights = [h for h in imported_text_heights if h > TEXT_HEIGHT_MIN]
    if heights:
        text_height = float(statistics.median(heights))
    elif dimtxt > 0:
        text_height = dimtxt * scale
    else:
        return default.text_height, default.arrow_size
    ratio = (dimasz / dimtxt) if (dimasz > 0 and dimtxt > 0) else (default.arrow_size / default.text_height)
    return text_height, text_height * ratio
