"""Leitura/gravação de arquivos .dxf, convertendo para/do modelo
Document/Entity do NewSIcad (newsicad/core/). Base também da ponte .dwg
(newsicad/io/dwg_bridge.py), que só converte .dwg↔.dxf e delega para cá."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from newsicad.core.document import Document
from newsicad.core.entities import (
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
    Text,
)

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


class DxfIoError(RuntimeError):
    pass


def load_dxf(path: str | Path) -> tuple[Document, int]:
    """Lê um .dxf e retorna (Document, quantidade de entidades ignoradas)."""
    try:
        dxf_doc = ezdxf.readfile(str(path))
    except OSError as exc:
        raise DxfIoError(f"Não foi possível abrir '{path}': {exc}") from exc
    except ezdxf.DXFStructureError as exc:
        raise DxfIoError(f"Arquivo DXF inválido ou corrompido: '{path}': {exc}") from exc

    document = Document()
    for layer in dxf_doc.layers:
        document.add_layer(layer.dxf.name)

    skipped = 0

    # Definições de bloco precisam existir ANTES de processar o modelspace,
    # já que uma entidade INSERT vira uma BlockReference que só faz sentido
    # (renderiza/faz hit-test certo) se `document.block_definitions` já tiver
    # a definição correspondente. "*Model_Space"/"*Paper_Space" e blocos
    # anônimos (nomes começando com "*", ex.: gerados por hachura/dimensão)
    # não são blocos nomeados de verdade — pulamos.
    for block in dxf_doc.blocks:
        if block.name.startswith("*"):
            continue
        block_entities: list[Entity] = []
        for dxf_entity in block:
            entity = _from_dxf_entity(dxf_entity)
            if entity is None:
                skipped += 1
                continue
            block_entities.append(entity)
        document.define_block(block.name, block_entities)

    for dxf_entity in dxf_doc.modelspace():
        entity = _from_dxf_entity(dxf_entity)
        if entity is None:
            skipped += 1
            continue
        document.add_entity(entity)

    return document, skipped


def _point(v) -> Point:
    return Point(float(v[0]), float(v[1]))


def _from_dxf_entity(e) -> Entity | None:
    dxftype = e.dxftype()
    layer = e.dxf.layer

    if dxftype == "LINE":
        return Line(layer=layer, start=_point(e.dxf.start), end=_point(e.dxf.end))

    if dxftype == "CIRCLE":
        return Circle(layer=layer, center=_point(e.dxf.center), radius=e.dxf.radius)

    if dxftype == "ARC":
        return Arc(
            layer=layer,
            center=_point(e.dxf.center),
            radius=e.dxf.radius,
            start_angle=math.radians(e.dxf.start_angle),
            end_angle=math.radians(e.dxf.end_angle),
        )

    if dxftype == "LWPOLYLINE":
        points = [Point(float(p[0]), float(p[1])) for p in e.get_points("xy")]
        return LWPolyline(layer=layer, points=points, closed=bool(e.closed))

    if dxftype == "INSERT":
        return BlockReference(
            layer=layer,
            block_name=e.dxf.name,
            insertion_point=_point(e.dxf.insert),
            scale=float(e.dxf.xscale),
            rotation=math.radians(e.dxf.rotation),
        )

    if dxftype == "ELLIPSE":
        major = e.dxf.major_axis
        radius_major = math.hypot(major[0], major[1])
        if radius_major < 1e-9:
            return None
        rotation = math.atan2(major[1], major[0])
        radius_minor = radius_major * e.dxf.ratio
        return Ellipse(
            layer=layer,
            center=_point(e.dxf.center),
            radius_major=radius_major,
            radius_minor=radius_minor,
            rotation=rotation,
        )

    if dxftype == "MTEXT":
        return Text(
            layer=layer,
            insertion_point=_point(e.dxf.insert),
            content=e.plain_text(),
            height=e.dxf.char_height,
            rotation=math.radians(e.dxf.get("rotation", 0.0)),
        )

    if dxftype == "TEXT":
        return Text(
            layer=layer,
            insertion_point=_point(e.dxf.insert),
            content=e.dxf.text,
            height=e.dxf.height,
            rotation=math.radians(e.dxf.get("rotation", 0.0)),
        )

    if dxftype == "DIMENSION":
        return _from_dxf_dimension(e, layer)

    if dxftype == "HATCH":
        return _from_dxf_hatch(e, layer)

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


def _from_dxf_hatch(e, layer: str) -> Entity | None:
    boundary_points: list[Point] = []
    for path in e.paths:
        vertices = getattr(path, "vertices", None)
        if vertices:
            boundary_points = [Point(float(v[0]), float(v[1])) for v in vertices]
            break
        edges = getattr(path, "edges", None)
        if edges:
            pts = []
            for edge in edges:
                start = getattr(edge, "start", None)
                if start is not None:
                    pts.append(Point(float(start[0]), float(start[1])))
            if pts:
                boundary_points = pts
                break
    if len(boundary_points) < 3:
        return None

    angle = 0.7853981633974483  # 45°, mesmo default do dataclass Hatch
    spacing = 1.0
    try:
        xdata = e.get_xdata(NEWSICAD_APPID)
        values = [tag.value for tag in xdata]
        angle, spacing = float(values[0]), float(values[1])
    except Exception:
        pass  # HATCH de outro programa: fica no padrão (fidelidade visual, não exata)

    return Hatch(layer=layer, boundary_points=boundary_points, angle=angle, spacing=spacing)


def save_dxf(document: Document, path: str | Path) -> None:
    dxf_doc = ezdxf.new(DXF_VERSION)
    if NEWSICAD_APPID not in dxf_doc.appids:
        dxf_doc.appids.new(NEWSICAD_APPID)
    msp = dxf_doc.modelspace()

    for layer in document.layers.values():
        if layer.name != "0" and layer.name not in dxf_doc.layers:
            dxf_doc.layers.add(layer.name)

    # Cria TODAS as definições de bloco vazias primeiro (num passo à parte
    # de popular o conteúdo) pra que um bloco A que contenha uma
    # BlockReference apontando pro bloco B não dependa da ordem de iteração
    # do dict — B já existe em dxf_doc.blocks quando A for populado.
    for name in document.block_definitions:
        if name not in dxf_doc.blocks:
            dxf_doc.blocks.new(name=name)
    for name, entities in document.block_definitions.items():
        block_layout = dxf_doc.blocks.get(name)
        for entity in entities:
            _to_dxf_entity(block_layout, entity)

    for entity in document.all_entities():
        _to_dxf_entity(msp, entity)

    try:
        dxf_doc.saveas(str(path))
    except OSError as exc:
        raise DxfIoError(f"Não foi possível salvar '{path}': {exc}") from exc


def _to_dxf_entity(msp, entity: Entity) -> None:
    attribs = {"layer": entity.layer}

    if isinstance(entity, Line):
        msp.add_line((entity.start.x, entity.start.y), (entity.end.x, entity.end.y), dxfattribs=attribs)
        return

    if isinstance(entity, Circle):
        msp.add_circle((entity.center.x, entity.center.y), entity.radius, dxfattribs=attribs)
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

    if isinstance(entity, BlockReference):
        # Uma xref (is_xref=True) é gravada como um INSERT comum apontando
        # pra um bloco cujo conteúdo já foi copiado pro documento (ver
        # MainWindow._start_xref) — ao reabrir, ela volta como um bloco
        # normal, perdendo o vínculo com o arquivo externo original. Isso é
        # uma simplificação documentada no README (sem "live link" de xref).
        insert_attribs = {
            **attribs,
            "xscale": entity.scale,
            "yscale": entity.scale,
            "rotation": math.degrees(entity.rotation),
        }
        msp.add_blockref(entity.block_name, (entity.insertion_point.x, entity.insertion_point.y), dxfattribs=insert_attribs)
        return

    if isinstance(entity, ImageReference):
        # Imagem raster não é gravada no .dxf (ver README) — silenciosamente
        # ignorada em vez de levantar erro, pra não impedir salvar o resto
        # do desenho.
        return

    if isinstance(entity, Text):
        msp.add_mtext(
            entity.content,
            dxfattribs={
                **attribs,
                "insert": (entity.insertion_point.x, entity.insertion_point.y),
                "char_height": max(entity.height, 1e-3),
                "rotation": math.degrees(entity.rotation),
            },
        )
        return

    if isinstance(entity, Dimension):
        _write_dimension(msp, entity, attribs)
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


def _write_dimension(msp, entity: Dimension, attribs: dict) -> None:
    """Grava tanto a geometria DIMENSION padrão do DXF (pra abrir/visualizar
    corretamente em qualquer programa CAD) quanto os campos exatos do nosso
    modelo como XDATA sob NEWSICAD_APPID (pra round-trip 100% fiel dentro do
    próprio NewSIcad — ver comentário no topo do arquivo)."""
    dimattribs = dict(attribs)
    override = None

    if entity.kind == "linear":
        override = msp.add_linear_dim(
            base=(entity.dim_line_point.x, entity.dim_line_point.y),
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            angle=0.0 if entity.is_horizontal() else 90.0,
            dimstyle="EZDXF",
            dxfattribs=dimattribs,
        )
    elif entity.kind == "aligned":
        override = msp.add_aligned_dim(
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            distance=_perp_offset(entity.point1, entity.point2, entity.dim_line_point),
            dimstyle="EZDXF",
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
            dxfattribs=dimattribs,
        )
    elif entity.kind == "angular":
        override = msp.add_angular_dim_3p(
            base=(entity.dim_line_point.x, entity.dim_line_point.y),
            center=(entity.center.x, entity.center.y),
            p1=(entity.point1.x, entity.point1.y),
            p2=(entity.point2.x, entity.point2.y),
            dimstyle="EZ_CURVED",
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


def _write_hatch(msp, entity: Hatch, attribs: dict) -> None:
    hatch = msp.add_hatch(color=256, dxfattribs=dict(attribs))
    points = [(p.x, p.y) for p in entity.boundary_points]
    hatch.paths.add_polyline_path(points, is_closed=True)
    hatch.set_pattern_fill("ANSI31", scale=max(entity.spacing, 0.1), angle=math.degrees(entity.angle))
    # o "scale"/"angle" do padrão ANSI31 do ezdxf não mapeia 1:1 de volta pro
    # nosso `spacing`/`angle` ao reler — grava os valores exatos como XDATA,
    # igual à Dimension, pra round-trip fiel dentro do NewSIcad.
    hatch.set_xdata(NEWSICAD_APPID, [(1040, float(entity.angle)), (1040, float(entity.spacing))])
