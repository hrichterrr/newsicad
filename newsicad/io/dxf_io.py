"""Leitura/gravação de arquivos .dxf, convertendo para/do modelo
Document/Entity do NewSIcad (newsicad/core/). Base também da ponte .dwg
(newsicad/io/dwg_bridge.py), que só converte .dwg↔.dxf e delega para cá."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from newsicad.core.document import Document
from newsicad.core.entities import Arc, Circle, Ellipse, Entity, Line, LWPolyline, Point

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

    raise DxfIoError(f"Tipo de entidade não suportado para gravação DXF: {type(entity)!r}")
