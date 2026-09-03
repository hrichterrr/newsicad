"""Leitura/gravação de arquivos .dxf, convertendo para/do modelo
Document/Entity do NewSIcad (newsicad/core/). Base também da ponte .dwg
(newsicad/io/dwg_bridge.py), que só converte .dwg↔.dxf e delega para cá."""

from __future__ import annotations

import collections
import math
import re
from pathlib import Path

import ezdxf
import ezdxf.colors
import ezdxf.recover

from newsicad.core.document import DimStyle, Document, TextStyle
from newsicad.io.dxf_annotations import (
    ATTACHMENT_TO_JUSTIFY as _ATTACHMENT_TO_JUSTIFY,
    JUSTIFY_TO_ATTACHMENT as _JUSTIFY_TO_ATTACHMENT,
    AnnotationImporter,
    attrib_texts,
    read_dim_style,
    text_from_dxf_mtext,
    text_from_dxf_text,
)
from newsicad.core.entities import (
    BYBLOCK,
    Arc,
    BlockReference,
    Circle,
    Dimension,
    Ellipse,
    Entity,
    Hatch,
    ImageReference,
    Line,
    LWPolyline,
    Point,
    PointEntity,
    Ray,
    Spline,
    Table,
    Text,
    XLine,
)
from newsicad.core.geometry_ops import translate_entity
from newsicad.io import dxf_fills

# Mapeamento justify <-> attachment_point do MTEXT: mora em
# newsicad/io/dxf_annotations.py (importado acima com os nomes antigos).

DXF_VERSION = "R2000"

# AppID sob o qual o NewSIcad grava os campos exatos de Dimension como XDATA
# (extended entity data). O DIMENSION do DXF é, ele mesmo, uma geometria
# derivada/renderizada (bloco anônimo) que não guarda "kind" nem os pontos
# originais de forma direta e sem ambiguidade entre LINEAR e ALIGNED — então
# gravamos os campos do nosso próprio modelo à parte, garantindo round-trip
# exato pros arquivos salvos pelo NewSIcad. Ao abrir um .dxf de outro
# programa (sem esse XDATA), fazemos um melhor-esforço a partir da geometria
# padrão do DIMENSION (ver `_dimension_from_geometry`).
NEWSICAD_APPID = "NEWSICAD"

# $INSUNITS do cabeçalho DXF <-> Document.units (opções do diálogo Units:
# mm/cm/m/in/ft) — sem esse mapeamento a unidade do desenho voltava sempre
# pra "mm" ao reabrir, não importa o que tivesse sido salvo (bug real de
# auditoria, 2026-08-22).
_UNITS_TO_INSUNITS = {"mm": 4, "cm": 5, "m": 6, "in": 1, "ft": 2}
_INSUNITS_TO_UNITS = {v: k for k, v in _UNITS_TO_INSUNITS.items()}

# Nome de bloco anônimo válido no DXF ("*U42", "*D3", "*T1"...) — ver save_dxf.
_ANONYMOUS_BLOCK_NAME_RE = re.compile(r"^\*[A-Za-z]\d+$")


class DxfIoError(RuntimeError):
    pass


class SkippedCount(int):
    """`int` do total de entidades ignoradas na leitura, com um extra
    `.by_type` (dxftype -> quantidade) pendurado no mesmo objeto. Sendo uma
    subclasse de `int`, todo o código existente que faz `if skipped:`,
    `skipped > 0`, `f"{skipped}"` etc. continua funcionando sem mudança —
    só quem quer o detalhe (ex.: a mensagem de aviso do File > Open) precisa
    olhar `.by_type`. Motivo: um aviso genérico "98 entidades ignoradas" não
    dá pista nenhuma de qual tipo de entidade falta suportar; o breakdown por
    tipo transforma isso em algo acionável sem precisar pedir o arquivo de
    novo pra descobrir (caso real: DWG de cliente com POLYLINE/SOLID/etc.
    reportado pelos testers em 2026-08-24)."""

    by_type: dict[str, int]
    #: Avisos em texto sobre conteúdo do arquivo que o NewSIcad não exibe
    #: (layouts em paper space, xrefs não carregadas) — mostrados na linha
    #: de comando ao abrir, junto do aviso de entidades ignoradas.
    notes: list[str]

    def __new__(cls, total: int, by_type: dict[str, int], notes: list[str] | None = None):
        obj = super().__new__(cls, total)
        obj.by_type = by_type
        obj.notes = list(notes or [])
        return obj

    def __reduce__(self):
        # Subclasse de int com atributos: sem isto o pickle (cache de
        # abertura, ver newsicad/io/open_cache.py) perdia by_type/notes.
        return (SkippedCount, (int(self), self.by_type, self.notes))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def _hex_to_aci(hex_color: str | None) -> int | None:
    """Cor hex (#RRGGBB) -> ACI (AutoCAD Color Index, 1-255) mais próxima na
    paleta fixa de 255 cores. `DXF_VERSION` aqui é R2000, que não suporta
    true color (grupo 420, só a partir do R2004) — ACI é o único jeito de
    gravar cor de camada/entidade de verdade nesse formato. Sem nenhum
    mapeamento de cor (o estado antes deste conserto), cor de camada e cor
    por entidade eram descartadas silenciosamente ao salvar."""
    if not hex_color:
        return None
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None
    best_aci, best_dist = 7, None
    for aci in range(1, 256):
        try:
            candidate = ezdxf.colors.aci2rgb(aci)
        except (IndexError, ValueError):
            continue
        dist = sum((a - b) ** 2 for a, b in zip(rgb, candidate))
        if best_dist is None or dist < best_dist:
            best_dist, best_aci = dist, aci
    return best_aci


def _aci_to_hex(aci: int) -> str:
    r, g, b = ezdxf.colors.aci2rgb(aci)
    return f"#{r:02X}{g:02X}{b:02X}"


def load_dxf(path: str | Path) -> tuple[Document, int]:
    """Lê um .dxf e retorna (Document, quantidade de entidades ignoradas)."""
    try:
        dxf_doc = ezdxf.readfile(str(path))
    except OSError as exc:
        raise DxfIoError(f"Não foi possível abrir '{path}': {exc}") from exc
    except ezdxf.DXFStructureError as strict_exc:
        # A leitura estrita rejeita o arquivo inteiro por qualquer
        # inconsistência estrutural — comum em .dxf gerados por conversores
        # de terceiros (ex.: dwg2dxf do LibreDWG em arquivos .dwg
        # complexos/antigos), mesmo quando a maior parte do desenho está
        # intacta. `ezdxf.recover` é tolerante a isso: reconstrói o quanto
        # for possível e reporta os problemas via `auditor.errors` em vez de
        # recusar o arquivo inteiro — melhor-esforço explícito, não fingimos
        # que o arquivo estava perfeito.
        try:
            dxf_doc, _auditor = ezdxf.recover.readfile(str(path))
        except Exception as recover_exc:
            raise DxfIoError(
                f"Arquivo DXF inválido ou corrompido: '{path}': {strict_exc}"
            ) from recover_exc

    document = Document()
    for layer in dxf_doc.layers:
        # Cor negativa no DXF = camada desligada (convenção do formato); o
        # valor absoluto é a cor ACI de verdade. Sem isso, cor/visibilidade/
        # trava de camada eram todas descartadas silenciosamente ao reabrir
        # (bug real de auditoria, 2026-08-22).
        aci = abs(layer.dxf.get("color", 7)) or 7
        # `add_layer` só usa o `color=` no momento de CRIAR a camada — a "0"
        # já existe de fábrica em `Document()`, então setar `.color` direto
        # no objeto retornado é o que garante que ela também pegue a cor
        # lida do arquivo, não só camadas novas.
        new_layer = document.add_layer(layer.dxf.name)
        new_layer.color = _aci_to_hex(aci)
        new_layer.visible = not layer.is_off()
        new_layer.locked = layer.is_locked()

    # STYLE (nome do estilo de texto -> fonte/altura, ver Document.text_styles
    # em core/document.py) — sem isso, todo Text lido de volta ficava preso
    # no estilo "Standard" mesmo se tivesse sido salvo com outro.
    # `font_file` (nome do arquivo como está no .dxf, ex. "romans.shx") e
    # `width` (fator de largura, group code 41) vão junto: o canvas usa o
    # primeiro pra saber que uma fonte SHX nunca existe no sistema e escolher
    # uma substituta estreita, e o segundo vira `QFont.setStretch` (achado
    # fontes-shx-fallback).
    for style in dxf_doc.styles:
        name = style.dxf.name
        font = style.dxf.get("font", "") or "Menlo"
        family = font.rsplit(".", 1)[0] if "." in font else font
        height = style.dxf.get("height", 0.0) or 2.5
        document.text_styles[name] = TextStyle(
            name=name,
            font_family=family,
            height=height,
            width=float(style.dxf.get("width", 1.0) or 1.0),
            font_file=font if "." in font else "",
        )

    clayer = dxf_doc.header.get("$CLAYER")
    if clayer and clayer in document.layers:
        document.current_layer = clayer

    insunits = dxf_doc.header.get("$INSUNITS")
    if insunits in _INSUNITS_TO_UNITS:
        document.units = _INSUNITS_TO_UNITS[insunits]

    skipped_by_type: dict[str, int] = collections.Counter()

    # MULTILEADER/LEADER/DIMENSION externa/ACAD_TABLE viram bloco anônimo +
    # BlockReference (ver newsicad/io/dxf_annotations.py); `import_entity`
    # devolve None pra tudo que não é anotação — aí segue `_from_dxf_entity`.
    importer = AnnotationImporter(
        document,
        lambda dxf_entity: _from_dxf_entity(dxf_entity, units=document.units),
        _apply_dxf_color,
        NEWSICAD_APPID,
    )

    # Definições de bloco precisam existir ANTES de processar o modelspace,
    # já que uma entidade INSERT vira uma BlockReference que só faz sentido
    # (renderiza/faz hit-test certo) se `document.block_definitions` já tiver
    # a definição correspondente. "*Model_Space"/"*Paper_Space", "*D..."
    # (setas/geometria interna de cota) e "*X..." (hachuras associativas) não
    # são blocos do usuário — pulamos. EXCEÇÃO IMPORTANTE: "*U..." (blocos
    # anônimos "de usuário") PRECISAM ser carregados — é neles que o AutoCAD
    # materializa a representação atual de cada BLOCO DINÂMICO, e num .dwg
    # real de arquiteto a maioria dos símbolos de infraestrutura (tomada,
    # CFTV, som, rede...) vira um INSERT apontando pra um "*U". Descartá-los
    # fazia 2/3 a 3/4 dos símbolos do desenho renderizarem como grupos
    # VAZIOS — a causa-raiz de verdade do bug "planta explodida/sumida"
    # reportado pelos testers (auditoria 2026-08-28; a conversão .dwg→.dxf
    # em si foi provada correta comparando dois conversores independentes).
    # Os blocos de seta que o ezdxf cria sozinho ao renderizar uma Dimension
    # ("_CLOSEDFILLED", "_DOT"...) também não são blocos do usuário — sem
    # esse filtro, o SOLID da seta contava como entidade "não suportada" ao
    # reabrir qualquer .dxf com cota. O filtro é o conjunto EXPLÍCITO de
    # nomes de seta do ezdxf (`dxf_fills.EZDXF_ARROW_BLOCKS`), não "qualquer
    # nome começando com '_'": a biblioteca da New SI tem blocos reais com
    # esse prefixo ("_PRANCHA_LEGENDA" = o selo da prancha, "_SIMBOLO_USB")
    # que o filtro antigo derrubava (auditoria 2026-09-01).
    #
    # As entidades são percorridas em `entities_in_redraw_order()` (a ordem
    # de desenho do AutoCAD, tabela SORTENTS) — o canvas desenha na ordem do
    # dict, então é isso que faz um WIPEOUT cobrir só o que está atrás dele
    # e uma hachura sólida ficar por baixo das linhas do próprio ícone.
    for block in dxf_doc.blocks:
        name = block.name
        if name.startswith("*") and not name.upper().startswith("*U"):
            continue
        if name in dxf_fills.EZDXF_ARROW_BLOCKS:
            continue
        block_entities: list[Entity] = []
        for dxf_entity in block.entities_in_redraw_order():
            imported = importer.import_entity(dxf_entity)
            if imported is not None:
                block_entities.extend(imported)
                continue
            entity = _from_dxf_entity(dxf_entity, units=document.units)
            if entity is None:
                if dxf_entity.dxftype() != "ATTDEF":
                    # ATTDEF (molde de atributo dentro da definição) não é
                    # geometria perdida: o valor preenchido chega como
                    # ATTRIB no INSERT e é promovido a Text no loop do
                    # modelspace abaixo — contar aqui era só ruído no aviso.
                    skipped_by_type[dxf_entity.dxftype()] += 1
                continue
            _apply_dxf_color(entity, dxf_entity)
            block_entities.append(entity)
            if dxf_entity.dxftype() == "INSERT":
                # ATTRIB de INSERT ANINHADO (bloco dentro de bloco): as
                # coordenadas já estão no espaço deste bloco pai — vira
                # Text aqui mesmo (achado attrib-aninhado; ver attrib_texts).
                block_entities.extend(attrib_texts(dxf_entity, entity.layer, _apply_dxf_color))
        # O modelo do NewSIcad assume ponto base do bloco na origem (os
        # filhos ficam em coordenadas relativas ao ponto de inserção); um
        # BLOCK com base_point ≠ 0 (2 deles num .dwg real de 2026-09-01)
        # abria com todas as instâncias deslocadas — subtrai o base_point de
        # cada filho (inclusive de INSERTs aninhados, que translate_entity
        # também move).
        base = block.block.dxf.get("base_point", (0, 0, 0))
        bx, by = float(base[0]), float(base[1])
        if abs(bx) > 1e-12 or abs(by) > 1e-12:
            for entity in block_entities:
                translate_entity(entity, -bx, -by)
        document.define_block(block.name, block_entities)

    for dxf_entity in dxf_doc.modelspace().entities_in_redraw_order():
        imported = importer.import_entity(dxf_entity)
        if imported is not None:
            for entity in imported:
                document.add_entity(entity)
            continue
        entity = _from_dxf_entity(dxf_entity, units=document.units)
        if entity is None:
            if dxf_entity.dxftype() != "ATTDEF":
                # ATTDEF é só o "molde" do atributo dentro da definição do
                # bloco — o valor preenchido de verdade vem como ATTRIB
                # pendurado em cada INSERT (lido logo abaixo). Contá-lo como
                # "não suportado" era ruído puro no aviso de abertura.
                skipped_by_type[dxf_entity.dxftype()] += 1
            continue
        _apply_dxf_color(entity, dxf_entity)
        document.add_entity(entity)

        if dxf_entity.dxftype() == "INSERT":
            # ATTRIBs (valores de atributo preenchidos — as etiquetas/tags
            # dos símbolos, ex.: numeração de tomada) viram entidades Text
            # independentes: o ATTRIB já carrega posição/altura/rotação
            # ABSOLUTAS no DXF, então não precisa herdar a transformação do
            # INSERT. Simplificação documentada: o vínculo texto↔bloco não é
            # modelado (mover o bloco depois não arrasta a etiqueta junto) —
            # antes disso as etiquetas simplesmente NUNCA eram lidas
            # (auditoria 2026-08-28, 139 ATTRIBs invisíveis no arquivo real
            # do bug). Alinhamento/baseline via get_placement — ver
            # newsicad/io/dxf_annotations.py:attrib_texts.
            for text_entity in attrib_texts(dxf_entity, entity.layer, _apply_dxf_color):
                document.add_entity(text_entity)

    # Tamanho de texto/seta das cotas nativas proporcional ao arquivo (ver
    # read_dim_style) — antes era fixo em 2.0/0.6 unidades de desenho, o que
    # numa planta em metros dava cotas maiores que a própria planta.
    text_height, arrow_size = read_dim_style(dxf_doc.header, importer.dimension_text_heights)
    document.dim_style = DimStyle(text_height=text_height, arrow_size=arrow_size)

    skipped = SkippedCount(sum(skipped_by_type.values()), dict(skipped_by_type), _file_notes(dxf_doc))
    return document, skipped


def _file_notes(dxf_doc) -> list[str]:
    """Avisos sobre o que existe no arquivo mas o NewSIcad não mostra: os
    LAYOUTS (pranchas em paper space — selo, legenda, tabelas das pranchas
    da New SI moram lá; o NewSIcad só exibe o Model) e as XREFs (a base
    arquitetônica costuma ser uma referência externa a outro .dwg, que não
    vem junto quando só um arquivo é enviado — no AutoCAD também aparece
    como "referência não encontrada"). Sem esses avisos o tester via uma
    planta "sem legenda"/"sem base" e não tinha como saber o motivo (relato
    de 2026-08-31, plantas Ana Beatriz e Casa Pau Brasil)."""
    notes: list[str] = []
    layouts: list[str] = []
    for layout in dxf_doc.layouts:
        if layout.name == "Model":
            continue
        count = sum(1 for e in layout if e.dxftype() != "VIEWPORT")
        if count:
            layouts.append(f"{layout.name} ({count})")
    if layouts:
        notes.append(
            f"Aviso: o arquivo tem {len(layouts)} layout(s)/prancha(s) em paper space "
            f"que o NewSIcad ainda não exibe (só o Model): {', '.join(layouts)}."
        )
    xrefs: list[str] = []
    for block in dxf_doc.blocks:
        if not block.block_record.is_xref:
            continue
        xref_path = block.block.dxf.get("xref_path", "") if block.block.dxf.hasattr("xref_path") else ""
        xrefs.append(f"{block.name} ({xref_path})" if xref_path else block.name)
    if xrefs:
        notes.append(
            "Aviso: referência(s) externa(s) (XREF) não carregada(s) — o desenho base pode "
            f"estar faltando: {', '.join(xrefs)}. Peça o .dwg com a xref incorporada (BIND) "
            "ou abra o arquivo da xref separadamente."
        )
    return notes


def _point(v) -> Point:
    return Point(float(v[0]), float(v[1]))


def _apply_dxf_color(entity: Entity, e) -> None:
    """Cor própria da entidade (exceção ao ByLayer): true color, ACI, e o
    sentinel BYBLOCK pra cor 0 — ver `dxf_fills.apply_dxf_color`. Sem essa
    função a cor por entidade nunca era lida de volta (bug real de
    auditoria, 2026-08-22)."""
    dxf_fills.apply_dxf_color(entity, e)


def _from_dxf_entity(e, units: str = "mm") -> Entity | None:
    """Entidade DXF -> entidade do NewSIcad (None = tipo não suportado).
    `units` (Document.units) só entra no espaçamento aproximado de HATCH com
    padrão vindas de outro programa (ver `dxf_fills.hatch_from_dxf`)."""
    dxftype = e.dxftype()
    layer = e.dxf.layer

    if dxftype == "LINE":
        return Line(layer=layer, start=_point(e.dxf.start), end=_point(e.dxf.end))

    # CIRCLE/ARC/LWPOLYLINE/ELLIPSE/INSERT passam por dxf_fills porque podem
    # estar definidos num OCS (extrusão (0,0,-1) = espelhados pelo MIRROR do
    # AutoCAD); lê-los como WCS espelhava a planta (175 arcos numa planta
    # real caíam em x≈-2600 e o zoom-extents abria o desenho a 9%).
    if dxftype == "CIRCLE":
        return dxf_fills.circle_from_dxf(e, layer)

    if dxftype == "ARC":
        return dxf_fills.arc_from_dxf(e, layer)

    if dxftype == "LWPOLYLINE":
        return dxf_fills.lwpolyline_from_dxf(e, layer)

    if dxftype == "POLYLINE":
        # Entidade POLYLINE "clássica" (pré-LWPOLYLINE, ainda comum em .dwg
        # reais/mais antigos ou vindos de outros programas — foi o caso
        # reportado pelos testers 2026-08-24, arquivo com muita entidade
        # "não suportada"). Malha 3D (polyface/polygon mesh) não é geometria
        # de desenho 2D simples — fora de escopo, deixa cair pro `return
        # None` de baixo e conta como ignorada (não tenta achatar em algo
        # que ficaria errado).
        if e.is_poly_face_mesh or e.is_polygon_mesh:
            return None
        points = [Point(float(v.dxf.location[0]), float(v.dxf.location[1])) for v in e.vertices]
        if len(points) < 2:
            return None
        return LWPolyline(layer=layer, points=points, closed=bool(e.is_closed))

    if dxftype == "SPLINE":
        fit_points = [Point(float(p[0]), float(p[1])) for p in e.fit_points]
        if len(fit_points) < 2:
            fit_points = [Point(float(p[0]), float(p[1])) for p in e.control_points]
        if len(fit_points) < 2:
            return None
        return Spline(layer=layer, points=fit_points, closed=bool(e.closed))

    if dxftype == "INSERT":
        if not (e.dxf.get("name", "") or "").strip():
            # INSERT sem nome (arquivo malformado) não aponta pra bloco
            # nenhum — vira uma BlockReference vazia e invisível; melhor
            # contar como ignorada no aviso de abertura.
            return None
        insert, xscale, yscale, rotation = dxf_fills.insert_placement(e)
        return BlockReference(
            layer=layer,
            block_name=e.dxf.name,
            insertion_point=insert,
            scale=xscale,
            # Só materializa scale_y quando realmente difere — mantém o caso
            # uniforme (todo bloco criado pelo próprio NewSIcad) idêntico ao
            # de antes. Ler só o xscale ignorando o yscale colapsava blocos
            # dinâmicos esticados/espelhados (xscale ≠ yscale, ou negativo)
            # numa escala uniforme errada (auditoria 2026-08-28).
            scale_y=yscale if abs(yscale - xscale) > 1e-12 else None,
            rotation=rotation,
        )

    if dxftype == "ELLIPSE":
        return dxf_fills.ellipse_from_dxf(e, layer)

    if dxftype == "MTEXT":
        # rotação real (text_direction), largura da caixa e espaçamento —
        # ver newsicad/io/dxf_annotations.py:text_from_dxf_mtext
        return text_from_dxf_mtext(e)

    if dxftype == "TEXT":
        # halign/valign/align_point via get_placement, baseline — ver
        # newsicad/io/dxf_annotations.py:text_from_dxf_text
        return text_from_dxf_text(e)

    if dxftype == "DIMENSION":
        return _from_dxf_dimension(e, layer)

    if dxftype == "HATCH":
        return _from_dxf_hatch(e, layer, units)

    if dxftype in ("SOLID", "TRACE"):
        # Polígono preenchido (corpo de ícone, seta) -> Hatch sólida na cor
        # da entidade. Antes era "não suportado" (169 SOLID num único .dwg
        # real de rack).
        return dxf_fills.solid_from_dxf(e, layer)

    if dxftype == "WIPEOUT":
        return dxf_fills.wipeout_from_dxf(e, layer)

    if dxftype == "POINT":
        return PointEntity(layer=layer, location=_point(e.dxf.location))

    if dxftype == "XLINE":
        vec = e.dxf.unit_vector
        return XLine(layer=layer, point=_point(e.dxf.start), angle=math.atan2(vec[1], vec[0]))

    if dxftype == "RAY":
        vec = e.dxf.unit_vector
        return Ray(layer=layer, point=_point(e.dxf.start), angle=math.atan2(vec[1], vec[0]))

    return None


def _from_dxf_dimension(e, layer: str) -> Entity | None:
    try:
        xdata = e.get_xdata(NEWSICAD_APPID)
    except Exception:
        xdata = None

    if xdata:
        values = [tag.value for tag in xdata]
        kind = values[0]
        floats = values[1:11]
        radius = values[11]
        point1, point2, dim_line_point, center, leader_point = (
            Point(floats[i], floats[i + 1]) for i in range(0, 10, 2)
        )
        return Dimension(
            layer=layer,
            kind=kind,
            point1=point1,
            point2=point2,
            dim_line_point=dim_line_point,
            center=center,
            radius=radius,
            leader_point=leader_point,
        )

    return _dimension_from_geometry(e, layer)


def _dimension_from_geometry(e, layer: str) -> Entity | None:
    """Melhor-esforço pra DIMENSION vindas de outro programa (sem o XDATA do
    NewSIcad): decodifica o tipo pelos 3 bits baixos de `dimtype` e os
    defpoints padrão do DXF. Cobertura parcial (linear/aligned/radius/
    diameter) — cotas angulares de arquivos externos são ignoradas (contadas
    como "skipped"), reconstruir os 3 pontos originais a partir só da
    geometria derivada do DIMENSION não é confiável o bastante."""
    try:
        base_type = e.dxf.get("dimtype", 0) & 7
        if base_type in (0, 1):
            dim_line_point = _point(e.dxf.defpoint)
            point1 = _point(e.dxf.defpoint2)
            point2 = _point(e.dxf.defpoint3)
            kind = "aligned" if base_type == 1 else "linear"
            return Dimension(layer=layer, kind=kind, point1=point1, point2=point2, dim_line_point=dim_line_point)
        if base_type == 4:  # radius: defpoint=centro, defpoint4=ponto no círculo
            center = _point(e.dxf.defpoint)
            leader_point = _point(e.dxf.defpoint4)
            radius = center.distance_to(leader_point)
            return Dimension(layer=layer, kind="radius", center=center, radius=radius, leader_point=leader_point)
        if base_type == 3:  # diameter: defpoint/defpoint4 são os 2 pontos opostos no círculo
            edge1 = _point(e.dxf.defpoint)
            edge2 = _point(e.dxf.defpoint4)
            center = Point((edge1.x + edge2.x) / 2, (edge1.y + edge2.y) / 2)
            radius = center.distance_to(edge1)
            return Dimension(layer=layer, kind="diameter", center=center, radius=radius, leader_point=edge1)
    except (AttributeError, KeyError):
        return None
    return None


def _from_dxf_hatch(e, layer: str, units: str = "mm") -> Entity | None:
    """HATCH -> Hatch com TODOS os contornos achatados (externo + furos,
    arestas curvas viram polígonos) — ver `dxf_fills.hatch_from_dxf`. O
    leitor antigo lia só o 1º contorno e só `edge.start` (que ArcEdge/
    EllipseEdge/SplineEdge não têm): contorno só de arcos virava <3 pontos
    e a hachura era descartada (846 delas num .dwg real de rack)."""
    return dxf_fills.hatch_from_dxf(e, layer, NEWSICAD_APPID, units=units)


def save_dxf(document: Document, path: str | Path) -> None:
    dxf_doc = ezdxf.new(DXF_VERSION)
    if NEWSICAD_APPID not in dxf_doc.appids:
        dxf_doc.appids.new(NEWSICAD_APPID)
    msp = dxf_doc.modelspace()

    for layer in document.layers.values():
        if layer.name != "0" and layer.name not in dxf_doc.layers:
            dxf_doc.layers.add(layer.name)
        dxf_layer = dxf_doc.layers.get(layer.name)
        # Cor negativa = camada desligada, convenção do formato — setar a
        # cor ANTES de off()/lock() (mesma ordem verificada empiricamente
        # contra o ezdxf). Sem isso, cor/visibilidade/trava de camada eram
        # todas descartadas silenciosamente ao salvar (bug real de
        # auditoria, 2026-08-22) — mina bastante o trabalho de "cor de
        # camada afeta o desenho de verdade" feito nesta mesma sessão.
        dxf_layer.dxf.color = _hex_to_aci(layer.color) or 7
        if not layer.visible:
            dxf_layer.off()
        if layer.locked:
            dxf_layer.lock()

    for name, style in document.text_styles.items():
        # arquivo de fonte original preservado (romans.shx continua
        # romans.shx pra quem abrir no AutoCAD); estilo criado no NewSIcad
        # (font_file vazio) grava `<família>.ttf` como sempre.
        font_file = style.font_file or f"{style.font_family}.ttf"
        if name in dxf_doc.styles:
            dxf_entry = dxf_doc.styles.get(name)
            dxf_entry.dxf.font = font_file
            dxf_entry.dxf.height = style.height
            dxf_entry.dxf.width = style.width or 1.0
        else:
            dxf_doc.styles.add(name, font=font_file, dxfattribs={"height": style.height, "width": style.width or 1.0})

    dxf_doc.header["$CLAYER"] = document.current_layer
    if document.units in _UNITS_TO_INSUNITS:
        dxf_doc.header["$INSUNITS"] = _UNITS_TO_INSUNITS[document.units]
    # DIMSTYLE simplificado (ver DimStyle em core/document.py): volta igual
    # ao reabrir (read_dim_style) e é o que outros programas usam pra
    # desenhar as cotas gravadas aqui (override em _write_dimension).
    dxf_doc.header["$DIMTXT"] = float(document.dim_style.text_height)
    dxf_doc.header["$DIMASZ"] = float(document.dim_style.arrow_size)

    # Cria TODAS as definições de bloco vazias primeiro (num passo à parte
    # de popular o conteúdo) pra que um bloco A que contenha uma
    # BlockReference apontando pro bloco B não dependa da ordem de iteração
    # do dict — B já existe em dxf_doc.blocks quando A for populado.
    # Blocos com nome "*X_..." são as anotações importadas (ver
    # dxf_annotations.py: "*D_<handle>", "*ML_...") — no DXF um nome com "*"
    # só é válido pra bloco ANÔNIMO ("*U12", "*D3"...), então vão como
    # "*U<n>" de verdade (new_anonymous_block), que é também o que load_dxf
    # reconhece de volta; `dxf_block_names` traduz o nome interno pro nome
    # gravado. Um "*U42" lido de um bloco dinâmico já é válido e fica igual.
    dxf_block_names: dict[str, str] = {}
    for name in document.block_definitions:
        if name.startswith("*") and not _ANONYMOUS_BLOCK_NAME_RE.match(name):
            dxf_block_names[name] = dxf_doc.blocks.new_anonymous_block(type_char="U").name
            continue
        if name not in dxf_doc.blocks:
            dxf_doc.blocks.new(name=name)
        dxf_block_names[name] = name
    for name, entities in document.block_definitions.items():
        block_layout = dxf_doc.blocks.get(dxf_block_names[name])
        for entity in entities:
            _to_dxf_entity(block_layout, entity, dxf_block_names, document.dim_style)

    for entity in document.all_entities():
        _to_dxf_entity(msp, entity, dxf_block_names, document.dim_style)

    try:
        dxf_doc.saveas(str(path))
    except OSError as exc:
        raise DxfIoError(f"Não foi possível salvar '{path}': {exc}") from exc


def _to_dxf_entity(
    msp,
    entity: Entity,
    block_names: dict[str, str] | None = None,
    dim_style: DimStyle | None = None,
) -> None:
    """`block_names`: nome interno -> nome gravado (ver save_dxf; None =
    mesmo nome). `dim_style`: tamanho de texto/seta das cotas (None =
    padrão DimStyle())."""
    attribs = {"layer": entity.layer}
    if entity.color == BYBLOCK:
        # Sentinel BYBLOCK (core/entities.py) = cor 0 do DXF: herda do INSERT.
        attribs["color"] = 0
    elif entity.color:
        # ByLayer (entity.color=None) fica de fora de propósito: omitir a
        # chave "color" faz o ezdxf usar o padrão DXF 256/BYLAYER sozinho.
        # Sem esse bloco, uma cor própria de entidade (exceção ao ByLayer)
        # era sempre descartada ao salvar (bug real de auditoria,
        # 2026-08-22).
        aci = _hex_to_aci(entity.color)
        if aci is not None:
            attribs["color"] = aci

    if isinstance(entity, Line):
        msp.add_line((entity.start.x, entity.start.y), (entity.end.x, entity.end.y), dxfattribs=attribs)
        return

    if isinstance(entity, Circle):
        msp.add_circle((entity.center.x, entity.center.y), entity.radius, dxfattribs=attribs)
        if entity.inner_radius > 1e-9:
            # DONUT: sem um jeito robusto de gravar "preenchido" em DXF sem
            # arriscar HATCH/handle issues (ver dwg_bridge.py sobre o estado
            # do LibreDWG), grava o círculo interno como um segundo CIRCLE
            # simples — o anel fica visualmente reconhecível ao reabrir,
            # mas sem o preenchimento (limitação documentada no README).
            msp.add_circle((entity.center.x, entity.center.y), entity.inner_radius, dxfattribs=attribs)
        return

    if isinstance(entity, Arc):
        msp.add_arc(
            (entity.center.x, entity.center.y),
            entity.radius,
            math.degrees(entity.start_angle),
            math.degrees(entity.end_angle),
            dxfattribs=attribs,
        )
        return

    if isinstance(entity, Ellipse):
        major_axis = (
            entity.radius_major * math.cos(entity.rotation),
            entity.radius_major * math.sin(entity.rotation),
        )
        ratio = entity.radius_minor / entity.radius_major if entity.radius_major else 1.0
        msp.add_ellipse(
            (entity.center.x, entity.center.y),
            major_axis=major_axis,
            ratio=ratio,
            start_param=0.0,
            end_param=math.tau,
            dxfattribs=attribs,
        )
        return

    if isinstance(entity, LWPolyline):
        points = [(p.x, p.y) for p in entity.points]
        polyline = msp.add_lwpolyline(points, dxfattribs=attribs)
        polyline.closed = entity.closed
        return

    if isinstance(entity, Spline):
        points = [(p.x, p.y) for p in entity.points]
        spline = msp.add_spline(fit_points=points, dxfattribs=attribs)
        spline.closed = entity.closed
        return

    if isinstance(entity, BlockReference):
        # Uma xref (is_xref=True) é gravada como um INSERT comum apontando
        # pra um bloco cujo conteúdo já foi copiado pro documento (ver
        # MainWindow._start_xref) — ao reabrir, ela volta como um bloco
        # normal, perdendo o vínculo com o arquivo externo original. Isso é
        # uma simplificação documentada no README (sem "live link" de xref).
        sx, sy = entity.scale_xy()
        insert_attribs = {
            **attribs,
            "xscale": sx,
            "yscale": sy,
            "rotation": math.degrees(entity.rotation),
        }
        dxf_name = (block_names or {}).get(entity.block_name, entity.block_name)
        msp.add_blockref(dxf_name, (entity.insertion_point.x, entity.insertion_point.y), dxfattribs=insert_attribs)
        return

    if isinstance(entity, ImageReference):
        # Imagem raster não é gravada no .dxf (ver README) — silenciosamente
        # ignorada em vez de levantar erro, pra não impedir salvar o resto
        # do desenho.
        return

    if isinstance(entity, Text):
        # Sempre MTEXT (também os Text que vieram de TEXT/ATTRIB): justify
        # "B?" vira attachment 7/8/9 (bottom = borda inferior no MTEXT, ~0.2·h
        # abaixo da baseline — diferença aceita, ver Text em core/entities).
        # `width` > 0 grava a caixa de quebra (41) e `line_spacing_factor`
        # o 44; `width_factor` (só existe no TEXT) não tem equivalente no
        # MTEXT e é descartado ao gravar.
        text_attribs = {
            **attribs,
            "insert": (entity.insertion_point.x, entity.insertion_point.y),
            "char_height": max(entity.height, 1e-3),
            "rotation": math.degrees(entity.rotation),
            "attachment_point": _JUSTIFY_TO_ATTACHMENT.get(entity.justify, 1),
            "style": entity.style,
        }
        if entity.width > 0:
            text_attribs["width"] = float(entity.width)
        if abs(entity.line_spacing_factor - 1.0) > 1e-9:
            text_attribs["line_spacing_factor"] = float(entity.line_spacing_factor)
        msp.add_mtext(entity.content, dxfattribs=text_attribs)
        return

    if isinstance(entity, PointEntity):
        msp.add_point((entity.location.x, entity.location.y), dxfattribs=attribs)
        return

    if isinstance(entity, XLine):
        ux, uy = math.cos(entity.angle), math.sin(entity.angle)
        msp.add_xline((entity.point.x, entity.point.y), unit_vector=(ux, uy), dxfattribs=attribs)
        return

    if isinstance(entity, Ray):
        ux, uy = math.cos(entity.angle), math.sin(entity.angle)
        msp.add_ray((entity.point.x, entity.point.y), unit_vector=(ux, uy), dxfattribs=attribs)
        return

    if isinstance(entity, Table):
        _write_table(msp, entity, attribs)
        return

    if isinstance(entity, Dimension):
        _write_dimension(msp, entity, attribs, dim_style or DimStyle())
        return

    if isinstance(entity, Hatch):
        _write_hatch(msp, entity, attribs)
        return

    raise DxfIoError(f"Tipo de entidade não suportado para gravação DXF: {type(entity)!r}")


def _perp_offset(p1: Point, p2: Point, other: Point) -> float:
    """Deslocamento perpendicular (com sinal) de `other` em relação à reta
    p1->p2, usado pra converter `dim_line_point` no parâmetro `distance` que
    o `add_aligned_dim` do ezdxf espera."""
    dx, dy = p2.x - p1.x, p2.y - p1.y
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    return (other.x - p1.x) * nx + (other.y - p1.y) * ny


def _write_dimension(msp, entity: Dimension, attribs: dict, dim_style: DimStyle) -> None:
    """Grava tanto a geometria DIMENSION padrão do DXF (pra abrir/visualizar
    corretamente em qualquer programa CAD) quanto os campos exatos do nosso
    modelo como XDATA sob NEWSICAD_APPID (pra round-trip 100% fiel dentro do
    próprio NewSIcad — ver comentário no topo do arquivo). Texto e seta com
    o tamanho do `dim_style` do documento (o mesmo que o canvas desenha), em
    vez do padrão do estilo "EZDXF" — numa planta em metros esse padrão
    (2.5 unidades) era maior que a própria cota."""
    dimattribs = dict(attribs)
    style_override = {"dimtxt": float(dim_style.text_height), "dimasz": float(dim_style.arrow_size)}
    override = None

    if entity.kind == "linear":
        override = msp.add_linear_dim(
            base=(entity.dim_line_point.x, entity.dim_line_point.y),
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            angle=0.0 if entity.is_horizontal() else 90.0,
            dimstyle="EZDXF",
            override=style_override,
            dxfattribs=dimattribs,
        )
    elif entity.kind == "aligned":
        override = msp.add_aligned_dim(
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            distance=_perp_offset(entity.point1, entity.point2, entity.dim_line_point),
            dimstyle="EZDXF",
            override=style_override,
            dxfattribs=dimattribs,
        )
    elif entity.kind == "radius":
        angle = math.degrees(
            math.atan2(entity.leader_point.y - entity.center.y, entity.leader_point.x - entity.center.x)
        )
        override = msp.add_radius_dim(
            center=(entity.center.x, entity.center.y),
            radius=entity.radius,
            angle=angle,
            dimstyle="EZ_RADIUS",
            override=style_override,
            dxfattribs=dimattribs,
        )
    elif entity.kind == "diameter":
        angle = math.degrees(
            math.atan2(entity.leader_point.y - entity.center.y, entity.leader_point.x - entity.center.x)
        )
        override = msp.add_diameter_dim(
            center=(entity.center.x, entity.center.y),
            radius=entity.radius,
            angle=angle,
            dimstyle="EZ_RADIUS",
            override=style_override,
            dxfattribs=dimattribs,
        )
    elif entity.kind == "angular":
        override = msp.add_angular_dim_3p(
            base=(entity.dim_line_point.x, entity.dim_line_point.y),
            center=(entity.center.x, entity.center.y),
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            dimstyle="EZ_CURVED",
            override=style_override,
            dxfattribs=dimattribs,
        )
    else:
        raise DxfIoError(f"Tipo de Dimension não suportado: {entity.kind!r}")

    override.render()

    tags: list[tuple[int, object]] = [(1000, entity.kind)]
    for pt in (entity.point1, entity.point2, entity.dim_line_point, entity.center, entity.leader_point):
        tags.append((1040, float(pt.x)))
        tags.append((1040, float(pt.y)))
    tags.append((1040, float(entity.radius)))
    override.dimension.set_xdata(NEWSICAD_APPID, tags)


def _write_table(msp, entity: Table, attribs: dict) -> None:
    """TABLE (comando TABLE/TB) não é gravada como um ACAD_TABLE de verdade
    — a API do ezdxf pra isso exige estilos de tabela nomeados e um modelo
    de célula bem mais elaborado do que `Table` modela aqui. Decompõe em
    Line (grade) + Text (cada célula não-vazia), mesmo espírito de MLINE/
    DONUT: não volta como Table ao reabrir, mas o desenho continua
    reconhecível (ver Table em core/entities.py)."""
    cos_a, sin_a = math.cos(entity.rotation), math.sin(entity.rotation)

    def to_world(lx: float, ly: float) -> tuple[float, float]:
        return (
            entity.insertion_point.x + lx * cos_a - ly * sin_a,
            entity.insertion_point.y + lx * sin_a + ly * cos_a,
        )

    total_w = entity.cols * entity.col_width
    total_h = entity.rows * entity.row_height
    if entity.show_borders:
        for r in range(entity.rows + 1):
            y = -r * entity.row_height
            msp.add_line(to_world(0, y), to_world(total_w, y), dxfattribs=attribs)
        for c in range(entity.cols + 1):
            x = c * entity.col_width
            msp.add_line(to_world(x, 0), to_world(x, -total_h), dxfattribs=attribs)

    pad = min(entity.col_width, entity.row_height) * 0.1
    for r, row_cells in enumerate(entity.cells[: entity.rows]):
        for c, text in enumerate(row_cells[: entity.cols]):
            if not text:
                continue
            x, y = to_world(c * entity.col_width + pad, -r * entity.row_height - pad - entity.text_height * 0.8)
            text_entity = msp.add_text(
                text,
                dxfattribs={
                    **attribs,
                    "height": max(entity.text_height, 1e-3),
                    "rotation": math.degrees(entity.rotation),
                },
            )
            text_entity.set_placement((x, y))


def _write_hatch(msp, entity: Hatch, attribs: dict) -> None:
    if entity.wipeout:
        # WIPEOUT de verdade (comando WIPEOUT ou lido do .dxf): entidade
        # WIPEOUT do DXF, que qualquer programa CAD entende como "área que
        # esconde o que está atrás" — antes era gravado como HATCH sólida na
        # cor do fundo do canvas, que abria como um borrão cinza-escuro no
        # AutoCAD.
        msp.add_wipeout([(p.x, p.y) for p in entity.boundary_points], dxfattribs=dict(attribs))
        return

    hatch = msp.add_hatch(color=attribs.get("color", 256), dxfattribs=dict(attribs))
    # Todos os anéis (`fill_paths()`): o externo com flag EXTERNAL, os furos
    # com OUTERMOST — o mesmo par que o AutoCAD grava pra ilhas, lido de
    # volta como even-odd por `dxf_fills.hatch_boundary_polygons`.
    for index, ring in enumerate(entity.fill_paths()):
        if len(ring) < 3:
            continue
        hatch.paths.add_polyline_path([(p.x, p.y) for p in ring], is_closed=True, flags=1 if index == 0 else 16)
    if entity.solid_fill:
        # Preenchimento sólido na cor da própria entidade (0 = BYBLOCK, 256 =
        # ByLayer, ou o ACI da cor explícita) — igual a uma HATCH sólida do
        # AutoCAD.
        hatch.set_solid_fill(color=attribs.get("color", 256))
        return
    pattern = entity.pattern_name or "ANSI31"
    if pattern not in _known_pattern_names():
        pattern = "ANSI31"
    hatch.set_pattern_fill(pattern, color=attribs.get("color", 256), scale=max(entity.spacing, 0.1), angle=math.degrees(entity.angle))
    # o "scale"/"angle" do padrão do ezdxf não mapeia 1:1 de volta pro nosso
    # `spacing`/`angle` ao reler — grava os valores exatos como XDATA, igual
    # à Dimension, pra round-trip fiel dentro do NewSIcad.
    hatch.set_xdata(NEWSICAD_APPID, [(1040, float(entity.angle)), (1040, float(entity.spacing))])


_KNOWN_PATTERNS: set[str] | None = None


def _known_pattern_names() -> set[str]:
    """Nomes de padrão que o ezdxf sabe definir (ANSI31, AR-CONC, ...) — um
    `Hatch.pattern_name` fora dessa lista é regravado como ANSI31 em vez de
    virar um HATCH sem definição de padrão (que abre vazio no AutoCAD)."""
    global _KNOWN_PATTERNS
    if _KNOWN_PATTERNS is None:
        try:
            from ezdxf.tools import pattern as ezdxf_pattern

            _KNOWN_PATTERNS = set(ezdxf_pattern.load().keys())
        except Exception:
            _KNOWN_PATTERNS = {"ANSI31"}
    return _KNOWN_PATTERNS
