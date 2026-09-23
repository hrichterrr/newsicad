"""Geometria pura das entidades desenháveis (sem dependência de Qt)."""

from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.hypot(other.x - self.x, other.y - self.y)

    def angle_to(self, other: "Point") -> float:
        return math.atan2(other.y - self.y, other.x - self.x)

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


#: Prefixo aleatório sorteado UMA vez por processo + contador: ids únicos
#: dentro da sessão e entre sessões (dois processos nunca compartilham o
#: prefixo), a um custo desprezível. Era `uuid.uuid4().hex` por entidade:
#: 2,7 s só de UUID ao ler a Casa Pau Brasil, com 186 mil entidades entre
#: desenho e definições de bloco (medição de 2026-09-06).
_ID_PREFIX = uuid.uuid4().hex[:8]
_ID_COUNTER = itertools.count(1)


def _new_id() -> str:
    return f"{_ID_PREFIX}{next(_ID_COUNTER):012x}"


#: Valor-sentinela de `Entity.color` para "BYBLOCK" (cor 0 do DXF): a entidade
#: herda a cor EFETIVA da instância de bloco (INSERT) que a contém — regra do
#: AutoCAD que a biblioteca de símbolos da New SI usa em massa (auditoria
#: 2026-09-01: 156/169 SOLID e a maioria das HATCH sólidas dos ícones de rack
#: são BYBLOCK). Fora de um bloco, cai pra cor da camada (ver
#: `CanvasView._effective_color`). Não é um "#RRGGBB" de propósito: quem
#: converte cor pra RGB/ACI (`newsicad/io/dxf_io.py`) precisa tratar o
#: sentinel antes.
BYBLOCK = "BYBLOCK"


# Relógio global de mutação: cada atribuição de atributo em qualquer entidade
# carimba nela o próximo valor (ver Entity.__setattr__). Não é um campo do
# dataclass — fica só em __dict__ — então não entra em ==, repr nem astuple.
_MUTATION_CLOCK = itertools.count(1)

# Registro das entidades alteradas desde o último `drain_dirty()`: quem
# consome (CanvasView.refresh_entities) descobre O QUE mudou sem percorrer
# as 43 mil entidades de uma planta real a cada passo de comando (0,4-0,6 s
# por passo só de varredura, medição de 2026-09-05). Chave = id() do objeto,
# valor = o próprio objeto (referência forte até o próximo drain).
_DIRTY: dict[int, "Entity"] = {}
#: Ligado por padrão; desligado durante a leitura de arquivo (ver bulk_load).
_TRACKING = True


class bulk_load:
    """Suspende o registro de alterações enquanto um desenho é LIDO de um
    arquivo: as entidades novas ainda não têm item gráfico, então o canvas
    as descobre pelo id que falta, não pelo registro. Sem isto, ler a Casa
    Pau Brasil fazia 1,15 milhão de inserções inúteis no registro."""

    def __enter__(self) -> "bulk_load":
        global _TRACKING
        _TRACKING = False
        return self

    def __exit__(self, *exc) -> None:
        global _TRACKING
        _TRACKING = True
        _DIRTY.clear()


def drain_dirty() -> list["Entity"]:
    """Devolve (e esvazia) a lista de entidades alteradas por atribuição ou
    `touch()` desde a chamada anterior — inclui as recém-criadas, já que o
    __init__ do dataclass também passa por __setattr__."""
    items = list(_DIRTY.values())
    _DIRTY.clear()
    return items


@dataclass
class Entity:
    layer: str = "0"
    #: None = ByLayer | `BYBLOCK` (sentinel acima) | "#RRGGBB" = cor própria.
    color: str | None = None
    id: str = field(default_factory=_new_id)

    def __setattr__(self, name: str, value) -> None:
        """Toda atribuição carimba a entidade com uma versão nova.

        É o que permite ao canvas saber, a cada passo de comando, quais
        entidades mudaram sem calcular o `repr()` de todas (0,35 s por passo
        numa planta de 43 mil entidades — medição de 2026-09-04). Os
        comandos mutam por atribuição (`line.end = ...`, `poly.points =
        [...]`, ver core/geometry_ops.py); quem altera uma lista NO LUGAR
        (`points.append`) deve chamar `touch()`."""
        object.__setattr__(self, name, value)
        if name != "_version":
            object.__setattr__(self, "_version", next(_MUTATION_CLOCK))
            if _TRACKING:
                _DIRTY[id(self)] = self

    def touch(self) -> None:
        """Marca a entidade como alterada sem trocar nenhum atributo."""
        object.__setattr__(self, "_version", next(_MUTATION_CLOCK))
        _DIRTY[id(self)] = self

    @property
    def version(self) -> int:
        return self.__dict__.get("_version", 0)


@dataclass
class Line(Entity):
    start: Point = field(default_factory=lambda: Point(0, 0))
    end: Point = field(default_factory=lambda: Point(0, 0))

    def length(self) -> float:
        return self.start.distance_to(self.end)

    def midpoint(self) -> Point:
        return Point((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)


@dataclass
class Circle(Entity):
    """`inner_radius` > 0 (usado pelo comando DONUT) faz este Circle
    renderizar como um anel preenchido (even-odd fill entre `radius` e
    `inner_radius`) em vez de um círculo simples; 0.0 (padrão) preserva o
    comportamento normal de Circle em todo o resto do código. Limitação
    documentada: gravado no .dxf como dois CIRCLE simples (outer/inner) sem
    preenchimento — ver newsicad/io/dxf_io.py e README."""

    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0
    inner_radius: float = 0.0


@dataclass
class Arc(Entity):
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0
    start_angle: float = 0.0  # radianos
    end_angle: float = 0.0  # radianos

    def start_point(self) -> Point:
        return Point(
            self.center.x + self.radius * math.cos(self.start_angle),
            self.center.y + self.radius * math.sin(self.start_angle),
        )

    def end_point(self) -> Point:
        return Point(
            self.center.x + self.radius * math.cos(self.end_angle),
            self.center.y + self.radius * math.sin(self.end_angle),
        )


@dataclass
class Ellipse(Entity):
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius_major: float = 0.0
    radius_minor: float = 0.0
    rotation: float = 0.0  # radianos, ângulo do eixo maior


@dataclass
class LWPolyline(Entity):
    points: list[Point] = field(default_factory=list)
    closed: bool = False
    #: Bulge por vértice (o arco do segmento que COMEÇA naquele vértice;
    #: `tan(θ/4)`, positivo anti-horário). Lista vazia = tudo reta — é o
    #: que toda polilinha desenhada no NewSIcad tem, e o que os arquivos de
    #: cache antigos entendem. Ver core/bulge.py.
    bulges: list[float] = field(default_factory=list)
    #: Espessura constante da linha, em unidades do desenho (o `const_width`
    #: do DXF). 0 = linha fina. Os símbolos da New SI usam 0,14 a 0,43.
    width: float = 0.0

    def segments(self) -> list[tuple[Point, Point]]:
        pts = self.points
        pairs = list(zip(pts, pts[1:]))
        if self.closed and len(pts) > 2:
            pairs.append((pts[-1], pts[0]))
        return pairs


@dataclass
class Spline(Entity):
    """Curva suave por pontos de ajuste (comando SPLINE/SP). Não é uma NURBS
    de verdade como o SPLINE do AutoCAD (sem vetor de nós/pesos) — é uma
    curva interpolante Catmull-Rom, que passa exatamente por `points` e é
    visualmente suave, gravada/lida como SPLINE de verdade no `.dxf` (com
    `fit_points`) pra abrir corretamente em outros programas CAD. Ver
    `newsicad/core/geometry_ops.py:catmull_rom_bezier`."""

    points: list[Point] = field(default_factory=list)
    closed: bool = False


@dataclass
class AttributeDef:
    """Molde de um atributo (ATTDEF) declarado DENTRO de uma definição de
    bloco: o campo preenchível que cada instância do bloco responde com um
    ATTRIB próprio (TÍTULO, ESCALA, PAVIMENTO, CIRCUITO...).

    Não é uma `Entity`: o molde em si não é desenhado no desenho — quem
    aparece é o ATTRIB de cada instância, que a leitura promove a `Text`
    (ver `Text.attrib_tag`). Fica em `Document.block_attdefs[nome]`, com
    coordenadas relativas ao ponto base do bloco, como qualquer filho de uma
    definição. Existe pra a ida e volta pelo .dxf ser completa: sem o ATTDEF
    de volta no bloco, os ATTRIBs gravados ficam órfãos e o AutoCAD perde os
    campos no primeiro ATTSYNC — e inserir uma cópia nova do bloco deixa de
    perguntar os valores."""

    tag: str = ""
    prompt: str = ""
    default: str = ""
    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    height: float = 2.5
    rotation: float = 0.0  # radianos
    justify: str = "BL"
    layer: str = "0"
    style: str = "Standard"
    width_factor: float = 1.0
    invisible: bool = False


#: Prefixos dos blocos ANÔNIMOS em que a importação empacota uma anotação
#: pronta de outro programa — multileader, leader, cota e tabela (ver
#: newsicad/io/dxf_annotations.py). Não são blocos do usuário: cada um tem
#: uma única instância e existe só pra anotação continuar sendo UM objeto
#: selecionável. Quem precisa saber "isto veio de uma anotação do AutoCAD?"
#: — o DDEDIT, o painel de Propriedades — pergunta por aqui.
ANNOTATION_BLOCK_PREFIXES = ("*ML_", "*LD_", "*D_", "*T_")


def is_annotation_block(name: str) -> bool:
    return name.startswith(ANNOTATION_BLOCK_PREFIXES)


@dataclass
class BlockReference(Entity):
    """Instância de um bloco inserida no desenho (comando INSERT). A
    geometria de verdade fica em `Document.block_definitions[block_name]`
    (uma lista de entidades "template" com coordenadas relativas ao ponto
    base do bloco) — esta entidade só guarda a transformação de inserção.

    `is_xref`/`xref_path` marcam uma referência externa (comando XREF):
    tecnicamente é a mesma coisa que um bloco comum, mas a definição foi
    importada de um arquivo .dxf externo em vez de ter sido desenhada no
    documento atual. Ver README para as limitações (sem watch de arquivo)."""

    block_name: str = ""
    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    #: Valores de atributo (ATTRIB) DESTA instância — os campos preenchíveis
    #: que a definição declara em `Document.block_attdefs` (TÍTULO, ESCALA,
    #: CIRCUITO...). Ficam aqui, e não soltos no desenho, em coordenadas
    #: RELATIVAS ao ponto base do bloco, exatamente como os filhos de uma
    #: definição: assim a etiqueta é desenhada, clicada, medida, movida,
    #: girada, escalada, copiada e apagada JUNTO com a instância, sem que
    #: nenhum comando precise saber que ela existe. Até a 2.16.1 o valor era
    #: uma entidade independente amarrada por id, e mover o bloco deixava a
    #: etiqueta para trás (feedback do grupo do NewSicad, 22/09/2026). No
    #: `.dxf` as coordenadas de um ATTRIB são absolutas — a conversão nos
    #: dois sentidos mora em newsicad/io/dxf_annotations.py.
    attributes: list["Text"] = field(default_factory=list)
    scale: float = 1.0
    #: Escala no eixo Y quando DIFERENTE da escala X (`scale`). `None` =
    #: uniforme (o caso de longe mais comum, e o único que os comandos do
    #: próprio NewSIcad criam). Blocos dinâmicos do AutoCAD esticados/
    #: espelhados chegam do .dxf com xscale ≠ yscale e/ou escala NEGATIVA
    #: (flip) — colapsar tudo num único float era parte do bug real dos
    #: "blocos explodidos" na importação de .dwg (auditoria 2026-08-28).
    #: Leia sempre via `scale_xy()` em vez de acessar os campos direto.
    scale_y: float | None = None
    rotation: float = 0.0  # radianos
    is_xref: bool = False
    xref_path: Path | None = None
    #: Limite de recorte (comando CLIP/XCLIP) em coordenadas LOCAIS do bloco
    #: (mesmo referencial dos filhos em `Document.block_definitions` — origem
    #: no ponto de inserção, sem a rotação/escala da instância aplicada).
    #: Guardar em espaço local em vez de mundo evita ter que retransformar o
    #: contorno em translate_entity/rotate_entity/scale_entity/mirror_entity:
    #: ele "acompanha" a instância de graça, do mesmo jeito que a geometria
    #: do próprio bloco já acompanha. `None` = sem recorte (padrão).
    clip_boundary: list[Point] | None = None

    def scale_xy(self) -> tuple[float, float]:
        """(escala X, escala Y) efetivas da instância, com fallback pra 1.0
        num campo zerado (arquivo malformado) e `scale_y=None` significando
        "igual à X". Valores NEGATIVOS são válidos (espelhamento)."""
        sx = self.scale if self.scale else 1.0
        sy = self.scale_y if self.scale_y is not None else sx
        return sx, (sy if sy else 1.0)


@dataclass
class ImageReference(Entity):
    """Referência a uma imagem raster (.png/.jpg) inserida no desenho
    (comando IMAGEATTACH). Não sobrevive à gravação em .dxf — ver README."""

    path: Path = field(default_factory=Path)
    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    width: float = 100.0
    height: float = 100.0
    #: Limite de recorte (comando CLIP), em coordenadas relativas ao
    #: `insertion_point` (ImageReference não tem rotação própria — ver
    #: acima). `None` = sem recorte.
    clip_boundary: list[Point] | None = None


#: Códigos de justificação de MTEXT suportados pelo comando MTEXT (subconjunto
#: dos 9 attachment points do MTEXT de verdade do AutoCAD — mesmos códigos
#: usados em `newsicad/io/dxf_io.py` para o group code 71/`attachment_point`).
TEXT_JUSTIFY_OPTIONS = ("TL", "TC", "TR", "ML", "MC", "MR", "BL", "BC", "BR")


@dataclass
class Text(Entity):
    """Texto simples ou multilinha (comando MTEXT). `content` pode conter
    "\\n" para múltiplas linhas. `justify` é um dos `TEXT_JUSTIFY_OPTIONS`
    ("TL" = Top Left, o padrão/comportamento original antes da justificação
    existir) e determina qual ponto do bloco de texto fica ancorado em
    `insertion_point` — ver `newsicad/ui/canvas.py` para o cálculo do
    deslocamento de renderização/hit-test correspondente. Convenção
    (WP-B 2026-09): a linha "B?" (BL/BC/BR) ancora a LINHA DE BASE da última
    linha de texto (semântica do TEXT/ATTRIB do DXF, cujo ponto 10 é
    esquerda-baseline), não a borda inferior dos descendentes — a diferença
    pro "bottom" do MTEXT (~0.2·altura) é uma simplificação documentada.
    `height` é a altura de caixa-alta (cap height), igual ao AutoCAD; o
    canvas escala uma fonte de referência pra que a tinta de um "H" tenha
    exatamente essa altura, em qualquer plataforma."""

    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    content: str = ""
    height: float = 2.5
    rotation: float = 0.0  # radianos
    justify: str = "TL"
    #: Comando FIELD: quando setado ("AREA"/"LENGTH"/"DATE"), `content` é
    #: recalculado a cada `CanvasView.refresh_entities()` a partir do valor
    #: atual (ver `newsicad/core/fields.py`) em vez de usar o texto salvo —
    #: assim o texto acompanha a geometria referenciada (`field_ref`) sem
    #: precisar de um passo explícito de "atualizar campos". `content` guarda
    #: o último valor calculado só como cache pro `.dxf` (que grava/lê o
    #: texto travado — ver README, campo vivo é um recurso só do NewSIcad).
    field_type: str | None = None
    field_ref: str | None = None
    #: ATRIBUTO de bloco: nome do campo ("TÍTULO", "ESCALA", "CIRCUITO"...)
    #: quando este Text é o VALOR de um atributo. Preenchido, o Text mora em
    #: `BlockReference.attributes` e não no desenho; vazio, é um texto comum.
    #: Um atributo que perdeu o bloco (bloco apagado) guarda a tag e vira
    #: texto comum, que é o que ele de fato virou.
    attrib_tag: str = ""
    #: Atributo INVISÍVEL (bit 1 do group code 70 do ATTRIB): o campo existe
    #: e guarda valor, mas o AutoCAD não o desenha — é assim que um bloco
    #: carrega dado que não aparece na prancha (código de fabricante,
    #: quantidade, referência de lista). Até a 2.16.2 a leitura DESCARTAVA
    #: esse ATTRIB, então abrir e salvar apagava o dado do arquivo sem
    #: avisar. Agora ele entra no desenho como qualquer atributo e só não é
    #: desenhado, nem clicado, nem medido — e volta invisível no `.dxf`. O
    #: painel de Propriedades mostra e edita, que é o único lugar onde ele
    #: pode ser alcançado (o AutoCAD faz o mesmo no editor de atributos).
    invisible: bool = False
    #: STYLE: nome de uma entrada em `Document.text_styles` — controla a
    #: fonte usada no render (`CanvasView`); "Standard" sempre existe.
    style: str = "Standard"
    #: Largura da caixa do MTEXT (group code 41): > 0 quebra cada parágrafo
    #: por palavras nessa largura (unidades de desenho) antes de justificar
    #: — ver `newsicad/ui/canvas.py:_text_layout`. 0 (padrão) = sem quebra
    #: automática, só as quebras explícitas ("\n") — comportamento de
    #: antes deste campo existir. Sem isso, parágrafos de plantas reais
    #: (caixas de 15 m) atravessavam a prancha inteira (WP-B 2026-09).
    width: float = 0.0
    #: Fator de espaçamento entre linhas do MTEXT (group code 44; 1.0 =
    #: simples = 5/3 da altura, como no AutoCAD).
    line_spacing_factor: float = 1.0
    #: Fator de largura do TEXT/ATTRIB (group code 41 do TEXT, "Width
    #: factor" do AutoCAD) — multiplica o `TextStyle.width` do estilo;
    #: aplicado no render via `QFont.setStretch`. 1.0 = normal.
    width_factor: float = 1.0


@dataclass
class Dimension(Entity):
    """Cota (DIMLINEAR/DIMALIGNED/DIMANGULAR/DIMRADIUS/DIMDIAMETER), unificada
    num único tipo com `kind` selecionando a interpretação dos campos:

    - "linear"/"aligned": point1, point2 (origens das linhas de extensão) e
      dim_line_point (onde o usuário posicionou a linha de cota).
    - "radius"/"diameter": center + radius do círculo/arco medido, e
      leader_point (posição do texto/leader).
    - "angular": center é o vértice do ângulo, point1/point2 são os pontos
      que definem os dois lados, e dim_line_point é onde o arco da cota foi
      posicionado.
    """

    kind: str = "linear"
    point1: Point = field(default_factory=lambda: Point(0, 0))
    point2: Point = field(default_factory=lambda: Point(0, 0))
    dim_line_point: Point = field(default_factory=lambda: Point(0, 0))
    center: Point = field(default_factory=lambda: Point(0, 0))
    radius: float = 0.0
    leader_point: Point = field(default_factory=lambda: Point(0, 0))
    text_height: float | None = None
    """Altura do texto SÓ desta cota. `None` = usa a do documento
    (`Document.dim_style`). É o que o painel de Propriedades edita: o
    AutoCAD deixa mudar fonte e tamanho de uma cota isolada, e no NewSIcad
    a única forma era mudar o DIMSTYLE do desenho inteiro — pedido do grupo
    em 22/09/2026 ("precisamos alterar propriedades... por meio da opção
    Propriedades")."""
    arrow_size: float | None = None
    """Tamanho da marca de seta só desta cota. `None` = a do documento."""
    text_style: str = ""
    """Estilo de texto (STYLE) da medida. Vazio = "Standard"."""
    break_points: list[Point] = field(default_factory=list)
    """Pontos (comando DIMBREAK) onde a linha de cota deve ter uma folga —
    só tem efeito em `kind` "linear"/"aligned" (ver
    `geometry_ops.dimension_line_segment`/`split_segment_with_gaps`).
    Limitação documentada: não é gravado no .dxf (perdido ao salvar/reabrir)
    — DIMBREAK é ele mesmo uma simplificação, sem o XDATA de round-trip
    exato que o resto do modelo de Dimension já tem."""

    def is_horizontal(self) -> bool:
        return abs(self.point2.x - self.point1.x) >= abs(self.point2.y - self.point1.y)

    def measurement(self) -> float:
        if self.kind == "aligned":
            return self.point1.distance_to(self.point2)
        if self.kind == "linear":
            return (
                abs(self.point2.x - self.point1.x)
                if self.is_horizontal()
                else abs(self.point2.y - self.point1.y)
            )
        if self.kind == "radius":
            return self.radius
        if self.kind == "diameter":
            return self.radius * 2
        if self.kind == "angular":
            v1 = math.atan2(self.point1.y - self.center.y, self.point1.x - self.center.x)
            v2 = math.atan2(self.point2.y - self.center.y, self.point2.x - self.center.x)
            diff = abs((v2 - v1 + math.pi) % (2 * math.pi) - math.pi)
            return math.degrees(diff)
        return 0.0

    def measurement_text(self) -> str:
        if self.kind == "radius":
            return f"R{self.measurement():.2f}"
        if self.kind == "diameter":
            return f"Ø{self.measurement():.2f}"
        if self.kind == "angular":
            return f"{self.measurement():.2f}°"
        return f"{self.measurement():.2f}"


@dataclass
class Hatch(Entity):
    """Hachura: contorno fechado (`boundary_points`) preenchido por linhas
    diagonais paralelas (`angle`/`spacing`, padrão ANSI31) ou por um
    preenchimento SÓLIDO (`solid_fill`). O comando HATCH v1 sempre copia o
    contorno de uma LWPolyline fechada pré-existente (detecção automática de
    contorno a partir de várias entidades é o comando BOUNDARY).

    Um HATCH real de .dxf/.dwg pode ter VÁRIOS contornos (externo + furos/
    ilhas) e arestas curvas: `boundary_paths` guarda todos eles já achatados
    em polígonos (índice 0 = externo, demais = furos, preenchidos com regra
    even-odd), e `boundary_points` continua sendo o contorno externo — é ele
    que hit-test, HATCHEDIT, bbox e os testes antigos usam. Use
    `fill_paths()` pra obter a lista completa a preencher."""

    boundary_points: list[Point] = field(default_factory=list)
    angle: float = 0.7853981633974483  # 45°, radianos
    spacing: float = 1.0
    solid_fill: bool = False
    """True = preenchimento sólido (HATCH com solid_fill=1 no DXF, SOLID/
    TRACE) na cor efetiva da entidade, em vez do padrão de linhas diagonais.
    Antes de 2026-09-01 este campo significava "WIPEOUT" e o canvas pintava
    TODA hachura sólida na cor de fundo — o corpo de todo ícone da biblioteca
    New SI (blocos cheios de HATCH sólidas coloridas) sumia. Agora WIPEOUT é
    o campo `wipeout` abaixo."""
    wipeout: bool = False
    """True = comando WIPEOUT (draw_commands.py) ou entidade WIPEOUT lida do
    .dxf: área que oculta o que está atrás dela — preenchimento sólido na cor
    de FUNDO do canvas, gravada como WIPEOUT de verdade no .dxf. Sempre vem
    com `solid_fill=True`."""
    frame_visible: bool = True
    """Desenha o contorno do wipeout? A máscara de fundo de um MULTILEADER
    importado não tem contorno nenhum no AutoCAD — é só uma tarja da cor do
    papel atrás do texto (ver `_fix_annotation_hatch` em
    newsicad/io/dxf_annotations.py). Um WIPEOUT criado pelo usuário continua
    com moldura, que é como ele o enxerga pra selecionar e mover."""
    boundary_paths: list[list[Point]] = field(default_factory=list)
    """Todos os contornos (externo primeiro, depois furos/ilhas) — vazio
    quando a hachura só tem o contorno de `boundary_points` (caso de tudo que
    o próprio NewSIcad desenha)."""
    pattern_name: str = "ANSI31"
    """Nome do padrão do HATCH de origem (ANSI31, AR-CONC, ...) — só pra
    regravar o mesmo nome no .dxf; o canvas desenha todo padrão como linhas
    paralelas (`angle`/`spacing`)."""

    def fill_paths(self) -> list[list[Point]]:
        """Contornos a preencher: o externo (`boundary_points`, sempre a
        fonte de verdade) seguido dos furos/ilhas de `boundary_paths[1:]`."""
        if len(self.boundary_paths) > 1:
            return [self.boundary_points, *self.boundary_paths[1:]]
        return [self.boundary_points]


@dataclass
class PointEntity(Entity):
    """Ponto real (comando POINT/PO), gravado/lido como um POINT de verdade
    no .dxf. Chamado `PointEntity` (não `Point`) para não colidir com a
    classe `Point` de coordenada pura já definida no topo deste arquivo.
    DIVIDE/MEASURE também usam este tipo agora, em vez do Circle minúsculo
    (`_MARKER_RADIUS`) que usavam como marcador antes deste tipo existir."""

    location: Point = field(default_factory=lambda: Point(0, 0))


@dataclass
class XLine(Entity):
    """Linha de construção infinita nas DUAS direções a partir de `point`,
    na direção `angle` (radianos) — comando XLINE. Guardamos ponto+ângulo
    (não dois extremos) para preservar a semântica real de "infinita" nos
    dados, gravada como um XLINE de verdade no .dxf (`ezdxf.add_xline`). O
    canvas desenha um segmento bem comprido só para fins de renderização
    (ver `newsicad/ui/canvas.py`) e a exclui do cálculo de zoom-extents real
    (considera só `point`) para não "explodir" o zoom."""

    point: Point = field(default_factory=lambda: Point(0, 0))
    angle: float = 0.0


@dataclass
class Ray(Entity):
    """Linha de construção infinita numa ÚNICA direção a partir de `point`
    (comando RAY) — mesmas observações de XLine acima, gravada como um RAY
    de verdade no .dxf (`ezdxf.add_ray`)."""

    point: Point = field(default_factory=lambda: Point(0, 0))
    angle: float = 0.0


@dataclass
class Table(Entity):
    """Tabela (comando TABLE/TB) — `insertion_point` é o canto
    superior-esquerdo, `cells` é uma matriz `rows` x `cols` de strings
    (linha por linha). Simplificação documentada: grade UNIFORME — mesma
    `col_width` pra toda coluna e mesma `row_height` pra toda linha (o
    TABLE de verdade do AutoCAD permite customizar cada uma individualmente,
    e também tem estilos de tabela nomeados, células mescladas, etc., nada
    disso modelado aqui). Grava no `.dxf` como Line (grade) + Text (cada
    célula não-vazia) em vez de um ACAD_TABLE de verdade — não volta como
    Table ao reabrir (mesmo espírito de MLINE/DONUT: decompõe em primitivas
    mais simples na gravação)."""

    insertion_point: Point = field(default_factory=lambda: Point(0, 0))
    rows: int = 1
    cols: int = 1
    col_width: float = 2.5
    row_height: float = 1.0
    cells: list[list[str]] = field(default_factory=list)
    text_height: float = 0.5
    rotation: float = 0.0
    #: TABLESTYLE (Document.table_style.show_borders): se False, a grade não
    #: é desenhada — só o texto das células, igual a "No Border" no Table
    #: Style de verdade do AutoCAD.
    show_borders: bool = True
