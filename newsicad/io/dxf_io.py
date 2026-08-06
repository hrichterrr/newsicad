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
    Ellipse,
    Entity,
    ImageReference,
    Line,
    LWPolyline,
    Point,
)

DXF_VERSION = "R2000"


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

    return None


def save_dxf(document: Document, path: str | Path) -> None:
    dxf_doc = ezdxf.new(DXF_VERSION)
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

    raise DxfIoError(f"Tipo de entidade não suportado para gravação DXF: {type(entity)!r}")
