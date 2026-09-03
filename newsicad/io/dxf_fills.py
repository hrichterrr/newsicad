"""Auxiliares de leitura do .dxf pra `newsicad/io/dxf_io.py`: preenchimentos
(HATCH com vários contornos e arestas curvas, SOLID/TRACE, WIPEOUT), cor por
entidade (ACI, true color e o sentinel BYBLOCK) e geometria definida em OCS
(entidades com `extrusion` diferente de (0,0,1) — CIRCLE/ARC/ELLIPSE/
LWPOLYLINE/INSERT).

Tudo aqui nasceu da auditoria de 2026-09-01 com seis .dwg reais da New SI
(plantas JOE LEE R00/R04/QA/DIAGRAMA, TEMPLATE de módulos e a instalação
fina JOÃO E BRENDA): os ícones das legendas abriam "em branco" porque toda
HATCH sólida era tratada como WIPEOUT, centenas de hachuras com contorno só
de arcos eram descartadas, filhos de bloco BYBLOCK/camada "0" saíam brancos
e 175 arcos com extrusão (0,0,-1) espelhados faziam a planta abrir minúscula
no zoom-extents. Ver README, seção "Arquivos `.dwg`"."""

from __future__ import annotations

import math

import ezdxf.colors
import ezdxf.path
from ezdxf.math import OCS, Vec3
from ezdxf.render.arrows import ARROWS

from newsicad.core.entities import (
    BYBLOCK,
    Arc,
    Circle,
    Ellipse,
    Entity,
    Hatch,
    LWPolyline,
    Point,
)

#: Espaçamento entre linhas do padrão ANSI31 (1/8" = 3,175 mm por unidade de
#: `pattern_scale`, definição métrica do acadiso.pat — a mesma que o ezdxf
#: usa). Usado nos dois sentidos: ler um HATCH de outro programa sem o XDATA
#: do NewSIcad, e gravar `Hatch.spacing` como `pattern_scale`.
ANSI31_LINE_SPACING = 3.175

#: Milímetros por unidade de desenho (Document.units) — converte o 3,175 mm
#: do ANSI31 pra unidade do arquivo ($INSUNITS 6 = metros -> 0,003175 por
#: unidade de pattern_scale; 4 = mm -> 3,175; 5 = cm -> 0,3175).
_MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}


def ansi31_spacing(pattern_scale: float, units: str = "mm") -> float:
    """Espaçamento em unidades de desenho das linhas do ANSI31 na escala
    `pattern_scale` — o que o AutoCAD desenha pra um HATCH sem a definição
    do padrão gravada no arquivo."""
    return max(float(pattern_scale), 1e-6) * ANSI31_LINE_SPACING / _MM_PER_UNIT.get(units, 1.0)


#: Blocos de seta que o ezdxf cria sozinho ao renderizar uma Dimension
#: ("_CLOSEDFILLED", "_DOT", "_OBLIQUE", "EZ_ARROW"...). Não são blocos do
#: usuário — só existem pra alimentar os blocos anônimos "*D" das cotas, que
#: também não são carregados. Antes o filtro era "qualquer nome começando com
#: sublinhado", o que descartava blocos REAIS da biblioteca New SI
#: ("_PRANCHA_LEGENDA" = o selo da prancha, "_SIMBOLO_USB", "_Prancha-Margem").
EZDXF_ARROW_BLOCKS: frozenset[str] = frozenset(
    ARROWS.block_name(name) for name in ARROWS.__all_arrows__
)

_WCS_Z = Vec3(0, 0, 1)
#: Achatamento de arcos/elipses/splines de HATCH: a tolerância é (extensão do
#: 1º contorno) / _FLATTEN_DIVISOR, então um círculo vira ~20-30 segmentos
#: independente da unidade do arquivo (as amostras misturam m e mm).
_FLATTEN_DIVISOR = 200.0


# ---------------------------------------------------------------------- #
# cor
# ---------------------------------------------------------------------- #
def aci_to_hex(aci: int) -> str:
    r, g, b = ezdxf.colors.aci2rgb(aci)
    return f"#{r:02X}{g:02X}{b:02X}"


def apply_dxf_color(entity: Entity, e) -> None:
    """Cor própria da entidade DXF -> `Entity.color`: true color (grupo 420,
    tem prioridade no AutoCAD) vira "#RRGGBB"; ACI 256 = ByLayer (None); ACI
    0 = BYBLOCK (sentinel, herda do INSERT — antes era descartado como
    ByLayer, o que pintava de branco o corpo de todo símbolo da New SI);
    demais ACI viram o hex da paleta fixa."""
    if e.dxf.hasattr("true_color"):
        r, g, b = ezdxf.colors.int2rgb(int(e.dxf.true_color))
        entity.color = f"#{r:02X}{g:02X}{b:02X}"
        return
    aci = e.dxf.get("color", 256)
    if aci == 0:
        entity.color = BYBLOCK
    elif aci != 256 and 1 <= aci <= 255:
        entity.color = aci_to_hex(aci)


# ---------------------------------------------------------------------- #
# OCS (extrusão)
# ---------------------------------------------------------------------- #
def extrusion_of(e) -> Vec3:
    return Vec3(e.dxf.get("extrusion", (0, 0, 1)))


def has_ocs(e) -> bool:
    """True se a entidade define um OCS próprio (extrusão diferente do eixo
    Z do mundo) — o caso real das amostras é (0,0,-1): o AutoCAD grava assim
    entidades espelhadas com MIRROR, e lê-las como se fossem WCS espelha o
    desenho."""
    ext = e.dxf.get("extrusion", None)
    return ext is not None and not Vec3(ext).isclose(_WCS_Z)


def ocs_point(e, v) -> Point:
    """Ponto em OCS da entidade -> Point 2D em WCS."""
    w = OCS(e.dxf.get("extrusion", (0, 0, 1))).to_wcs(Vec3(v))
    return Point(float(w.x), float(w.y))


def _xy(v) -> Point:
    return Point(float(v[0]), float(v[1]))


def circle_from_dxf(e, layer: str) -> Circle:
    center = ocs_point(e, e.dxf.center) if has_ocs(e) else _xy(e.dxf.center)
    return Circle(layer=layer, center=center, radius=float(e.dxf.radius))


def arc_from_dxf(e, layer: str) -> Arc:
    start = math.radians(float(e.dxf.start_angle))
    end = math.radians(float(e.dxf.end_angle))
    radius = float(e.dxf.radius)
    if not has_ocs(e):
        return Arc(layer=layer, center=_xy(e.dxf.center), radius=radius, start_angle=start, end_angle=end)
    # Arco definido em OCS: leva centro e extremos pro WCS e recalcula os
    # ângulos a partir deles. Com extrusão (0,0,-1) o OCS espelha X, o que
    # inverte o sentido de percurso (anti-horário em OCS = horário em WCS)
    # — daí a troca início/fim (start,end = pi-end, pi-start nesse caso).
    c = Vec3(e.dxf.center)
    center = ocs_point(e, c)
    p_start = ocs_point(e, (c.x + radius * math.cos(start), c.y + radius * math.sin(start), c.z))
    p_end = ocs_point(e, (c.x + radius * math.cos(end), c.y + radius * math.sin(end), c.z))
    a_start = center.angle_to(p_start) % math.tau
    a_end = center.angle_to(p_end) % math.tau
    if extrusion_of(e).z < 0:
        a_start, a_end = a_end, a_start
    return Arc(layer=layer, center=center, radius=radius, start_angle=a_start, end_angle=a_end)


def ellipse_from_dxf(e, layer: str) -> Entity | None:
    """ELLIPSE: centro/eixo maior já são WCS no DXF. Elipse COMPLETA vira
    `Ellipse`; um ARCO de elipse (start/end_param parciais — o leitor antigo
    nem lia esses campos e fechava a elipse) é aproximado por uma LWPolyline
    achatada pelo `ezdxf.path` (que já respeita a extrusão): a entidade
    `Ellipse` do NewSIcad não modela arco parcial — simplificação documentada
    no README."""
    major = e.dxf.major_axis
    radius_major = math.hypot(float(major[0]), float(major[1]))
    if radius_major < 1e-9:
        return None
    start_param = float(e.dxf.get("start_param", 0.0))
    end_param = float(e.dxf.get("end_param", math.tau))
    sweep = (end_param - start_param) % math.tau
    if 1e-9 < sweep < math.tau - 1e-9:
        try:
            pts = [
                Point(float(v.x), float(v.y))
                for v in ezdxf.path.make_path(e).flattening(radius_major / _FLATTEN_DIVISOR)
            ]
        except Exception:
            pts = []
        if len(pts) < 2:
            return None
        return LWPolyline(layer=layer, points=pts, closed=False)
    return Ellipse(
        layer=layer,
        center=_xy(e.dxf.center),
        radius_major=radius_major,
        radius_minor=radius_major * float(e.dxf.ratio),
        rotation=math.atan2(float(major[1]), float(major[0])),
    )


def lwpolyline_from_dxf(e, layer: str) -> LWPolyline:
    if has_ocs(e):
        points = [Point(float(v.x), float(v.y)) for v in e.vertices_in_wcs()]
    else:
        points = [Point(float(p[0]), float(p[1])) for p in e.get_points("xy")]
    return LWPolyline(layer=layer, points=points, closed=bool(e.closed))


def insert_placement(e) -> tuple[Point, float, float, float]:
    """(ponto de inserção WCS, xscale, yscale, rotação em radianos) de um
    INSERT, corrigindo a extrusão: o INSERT posiciona o bloco em OCS, e com
    extrusão (0,0,-1) (X espelhado) a mesma transformação em WCS vira
    rotação -theta com xscale negativa — verificado contra
    `Insert.virtual_entities()` do ezdxf."""
    xscale = float(e.dxf.xscale)
    yscale = float(e.dxf.yscale)
    rotation = math.radians(float(e.dxf.rotation))
    if not has_ocs(e):
        return _xy(e.dxf.insert), xscale, yscale, rotation
    insert = ocs_point(e, e.dxf.insert)
    if extrusion_of(e).z < 0:
        return insert, -xscale, yscale, -rotation
    return insert, xscale, yscale, rotation


# ---------------------------------------------------------------------- #
# preenchimentos
# ---------------------------------------------------------------------- #
def _dedupe(points: list[Point]) -> list[Point]:
    """Remove vértices consecutivos repetidos e o vértice de fechamento
    (último == primeiro) que HATCH/WIPEOUT costumam gravar."""
    out: list[Point] = []
    for p in points:
        if out and abs(out[-1].x - p.x) < 1e-12 and abs(out[-1].y - p.y) < 1e-12:
            continue
        out.append(p)
    if len(out) > 1 and abs(out[0].x - out[-1].x) < 1e-12 and abs(out[0].y - out[-1].y) < 1e-12:
        out.pop()
    return out


def hatch_boundary_polygons(e) -> list[list[Point]]:
    """TODOS os contornos do HATCH como polígonos (índice 0 = externo, demais
    = furos/ilhas), com arcos/elipses/splines/bulges achatados via
    `ezdxf.path.from_hatch_boundary_path`. O leitor antigo pegava só o
    primeiro contorno e, num edge path, só `edge.start` — atributo que no
    ezdxf 1.4.4 existe apenas em LineEdge — então contorno só de arcos virava
    <3 pontos e a hachura inteira era descartada (846 delas num único .dwg
    real de rack)."""
    ocs = e.ocs() if has_ocs(e) else None
    elevation = float(e.dxf.elevation.z) if e.dxf.hasattr("elevation") else 0.0
    tol: float | None = None
    polys: list[list[Point]] = []
    for bp in e.paths:
        try:
            path = ezdxf.path.from_hatch_boundary_path(bp, ocs=ocs, elevation=elevation)
            if tol is None:
                tol = _flatten_tolerance(path.control_vertices())
            pts = _dedupe([Point(float(v.x), float(v.y)) for v in path.flattening(tol)])
        except Exception:
            # Edge path com uma aresta que o ezdxf recusa (caso real: SPLINE
            # com vetor de nós inconsistente, "96 knot values required, got
            # 189" — 5 hachuras numa planta real): achata aresta por aresta
            # e, na que falhar, usa os próprios pontos de ajuste/controle.
            pts = _dedupe(_edge_path_fallback(bp, ocs, elevation, tol))
            if tol is None and pts:
                tol = _flatten_tolerance([Vec3(p.x, p.y) for p in pts])
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def _flatten_tolerance(vertices) -> float:
    vertices = list(vertices)
    if not vertices:
        return 1e-9
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    return max(extent / _FLATTEN_DIVISOR, 1e-9)


def _edge_path_fallback(bp, ocs, elevation: float, tol: float | None) -> list[Point]:
    """Achata um edge path aresta por aresta (ver `hatch_boundary_polygons`)."""
    from ezdxf.entities.boundary_paths import EdgePath

    edges = getattr(bp, "edges", None)
    if not edges:
        return []
    pts: list[Point] = []
    for edge in edges:
        try:
            single = EdgePath()
            single.edges = [edge]
            path = ezdxf.path.from_hatch_edge_path(single, ocs=ocs, elevation=elevation)
            ctrl = path.control_vertices()
            pts.extend(Point(float(v.x), float(v.y)) for v in path.flattening(tol if tol is not None else _flatten_tolerance(ctrl)))
            continue
        except Exception:
            pass
        raw = list(getattr(edge, "fit_points", None) or []) or list(getattr(edge, "control_points", None) or [])
        for v in raw:
            w = ocs.to_wcs(Vec3(v[0], v[1], elevation)) if ocs is not None else Vec3(v[0], v[1], 0)
            pts.append(Point(float(w.x), float(w.y)))
    return pts


def hatch_from_dxf(e, layer: str, appid: str, units: str = "mm") -> Hatch | None:
    polys = hatch_boundary_polygons(e)
    if not polys:
        return None
    hatch = Hatch(layer=layer, boundary_points=polys[0], boundary_paths=polys)
    if bool(e.dxf.get("solid_fill", 0)):
        hatch.solid_fill = True
        return hatch

    hatch.pattern_name = str(e.dxf.get("pattern_name", "ANSI31") or "ANSI31")
    try:
        # HATCH gravada pelo próprio NewSIcad: valores exatos no XDATA.
        values = [tag.value for tag in e.get_xdata(appid)]
        hatch.angle, hatch.spacing = float(values[0]), float(values[1])
        return hatch
    except Exception:
        pass
    # HATCH de outro programa: aproxima o padrão por linhas paralelas com o
    # ângulo/espaçamento da PRIMEIRA família de linhas da definição gravada
    # no arquivo (já escalada/rotacionada pelo AutoCAD) — fidelidade visual,
    # não exata. Sem definição, cai em pattern_angle/pattern_scale x ANSI31
    # na unidade do desenho (`ansi31_spacing`).
    angle = math.radians(float(e.dxf.get("pattern_angle", 45.0)))
    spacing = ansi31_spacing(e.dxf.get("pattern_scale", 1.0), units)
    try:
        line = e.pattern.lines[0]
        offset = math.hypot(float(line.offset[0]), float(line.offset[1]))
        if offset > 1e-9:
            angle = math.radians(float(line.angle))
            spacing = offset
    except Exception:
        pass
    hatch.angle = angle % math.pi
    hatch.spacing = spacing
    return hatch


def solid_from_dxf(e, layer: str) -> Hatch | None:
    """SOLID/TRACE (polígono preenchido de 3-4 vértices, a entidade que o
    AutoCAD usa pras setas de cota e pra pequenos corpos de ícone) -> Hatch
    sólida. `wcs_vertices()` já devolve os vértices em ordem de polígono (o
    DXF grava o 3º e o 4º trocados) e em WCS."""
    pts = _dedupe([Point(float(v.x), float(v.y)) for v in e.wcs_vertices()])
    if len(pts) < 3:
        return None
    return Hatch(layer=layer, boundary_points=pts, boundary_paths=[pts], solid_fill=True)


def wipeout_from_dxf(e, layer: str) -> Hatch | None:
    """WIPEOUT de verdade -> Hatch(solid_fill=True, wipeout=True), com o
    contorno já em WCS (`boundary_path_wcs`)."""
    try:
        pts = _dedupe([Point(float(v[0]), float(v[1])) for v in e.boundary_path_wcs()])
    except Exception:
        return None
    if len(pts) < 3:
        return None
    return Hatch(layer=layer, boundary_points=pts, boundary_paths=[pts], solid_fill=True, wipeout=True)
