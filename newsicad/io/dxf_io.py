"""Leitura/gravação de arquivos .dxf, convertendo para/do modelo
Document/Entity do NewSIcad (newsicad/core/). Base também da ponte .dwg
(newsicad/io/dwg_bridge.py), que só converte .dwg↔.dxf e delega para cá."""

from __future__ import annotations

import collections
import functools
import hashlib
import math
import re
import struct
from pathlib import Path

import ezdxf
import ezdxf.colors
import ezdxf.recover
from ezdxf.enums import TextEntityAlignment
from ezdxf.lldxf.tags import Tags
from ezdxf.lldxf.types import DXFBinaryTag, DXFTag, DXFVertex

import newsicad.core.entities as entities_module
from newsicad.core.document import (
    DimStyle,
    Document,
    LineType,
    TextStyle,
    dim_arrow_size,
    dim_text_height,
)
from newsicad.io.dxf_annotations import (
    attdef_solto_como_texto,
    texto_do_dxf,
    ATTACHMENT_TO_JUSTIFY as _ATTACHMENT_TO_JUSTIFY,
    impressao_do_bloco,
    JUSTIFY_TO_ATTACHMENT as _JUSTIFY_TO_ATTACHMENT,
    TEXT_HEIGHT_MIN,
    AnnotationImporter,
    attdef_from_dxf,
    attrib_texts,
    read_dim_style,
    text_from_dxf_mtext,
    text_from_dxf_text,
)
from newsicad.core.entities import (
    BYBLOCK,
    Arc,
    AttributeDef,
    BlockReference,
    Circle,
    Dimension,
    Ellipse,
    Entity,
    Hatch,
    ImageReference,
    Line,
    LWPolyline,
    OleFrame,
    OleObjeto,
    Point,
    PointEntity,
    Ray,
    Spline,
    Table,
    Text,
    XLine,
)
from newsicad.core.geometry_ops import attribute_to_block_local, attribute_to_world, translate_entity
from newsicad.io import dxf_fills

# Mapeamento justify <-> attachment_point do MTEXT: mora em
# newsicad/io/dxf_annotations.py (importado acima com os nomes antigos).

# `Text.justify` -> alinhamento do TEXT/ATTRIB/ATTDEF (group codes 72/73 +
# ponto 11), o inverso exato do `_ALIGN_TO_JUSTIFY` da leitura em
# dxf_annotations.py. Usado só na gravação de atributo, que é TEXT-like —
# o resto dos textos sai como MTEXT, que usa attachment_point.
_JUSTIFY_TO_ALIGN = {
    "BL": TextEntityAlignment.LEFT,
    "BC": TextEntityAlignment.CENTER,
    "BR": TextEntityAlignment.RIGHT,
    "ML": TextEntityAlignment.MIDDLE_LEFT,
    "MC": TextEntityAlignment.MIDDLE_CENTER,
    "MR": TextEntityAlignment.MIDDLE_RIGHT,
    "TL": TextEntityAlignment.TOP_LEFT,
    "TC": TextEntityAlignment.TOP_CENTER,
    "TR": TextEntityAlignment.TOP_RIGHT,
}

# R2018 (AC1032) e não R2000, por dois motivos medidos na auditoria de
# 2026-09-07: (a) o R2000 grava em ANSI, e o ezdxf escapa o que não couber na
# cp1252 como o literal "\\U+XXXX" sem desescapar na leitura — o Ω de
# impedância ("Z = 6Ω", 21 textos na planta João e Brenda) voltava como
# "Z = 6\\U+2126", e nome de camada com CJK era destruído do mesmo jeito;
# (b) o R2000 não tem o grupo 420 (true color), então toda cor exata da
# entidade era trocada pela ACI mais próxima ao salvar — na Casa Pau Brasil
# 85 entidades #2776BB viravam #007CA5, e no Template um cinza #373737 virava
# o marrom #4C3926. A partir do R2007 o DXF é UTF-8, o que resolve (a); o R2018 é a mesma versão que os .dxf de projeto da New SI já declaram ($ACADVER AC1032).
DXF_VERSION = "R2018"

# AppID sob o qual o NewSIcad grava os campos exatos de Dimension como XDATA
# (extended entity data). O DIMENSION do DXF é, ele mesmo, uma geometria
# derivada/renderizada (bloco anônimo) que não guarda "kind" nem os pontos
# originais de forma direta e sem ambiguidade entre LINEAR e ALIGNED — então
# gravamos os campos do nosso próprio modelo à parte, garantindo round-trip
# exato pros arquivos salvos pelo NewSIcad. Ao abrir um .dxf de outro
# programa (sem esse XDATA), fazemos um melhor-esforço a partir da geometria
# padrão do DIMENSION (ver `_dimension_from_geometry`).
NEWSICAD_APPID = "NEWSICAD"

#: Cabeçalhos que o NewSIcad não interpreta mas devolve como estavam ao
#: gravar. `$LUNITS`/`$AUNITS`/`$LUPREC`/`$AUPREC` são o FORMATO de leitura
#: (arquitetônico pés-polegadas, decimal, casas depois da vírgula),
#: `$MEASUREMENT` diz se o desenho é imperial ou métrico, e `$LIMMIN`/
#: `$LIMMAX` são os limites da área de desenho. Nada disso muda a geometria,
#: e por isso passava despercebido: o `ezdxf.new()` do save punha o default
#: dele por cima, e um arquivo imperial voltava decimal e métrico, com os
#: limites virando a folha A3 do ezdxf (auditoria de 07/09/2026 com as
#: amostras da Autodesk). $INSUNITS fica de FORA de propósito — esse o
#: NewSIcad interpreta de verdade, em Document.units.
_CABECALHOS_PRESERVADOS = (
    "$LUNITS",
    "$AUNITS",
    "$LUPREC",
    "$AUPREC",
    "$MEASUREMENT",
    "$LIMMIN",
    "$LIMMAX",
)

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


@functools.lru_cache(maxsize=1)
def _paleta_aci() -> tuple[tuple[int, tuple[int, int, int]], ...]:
    """A paleta ACI inteira, montada UMA vez. Ela é fixa: perguntar o RGB de
    cada um dos 255 índices ao ezdxf a cada conversão de cor era o grosso do
    custo de `_hex_to_aci`."""
    tabela = []
    for aci in range(1, 256):
        try:
            tabela.append((aci, tuple(ezdxf.colors.aci2rgb(aci))))
        except (IndexError, ValueError):
            continue
    return tuple(tabela)


@functools.lru_cache(maxsize=4096)
def _hex_to_aci(hex_color: str | None) -> int | None:
    """Cor hex (#RRGGBB) -> ACI (AutoCAD Color Index, 1-255) mais próxima na
    paleta fixa de 255 cores. O `DXF_VERSION` de hoje é R2018 e grava a cor
    exata no true color (grupo 420) — o ACI vai junto para quem só lê a
    paleta antiga, e é por isso que esta conversão continua existindo. (O
    comentário aqui dizia "R2000, que não suporta true color"; ficou para
    trás quando a versão de gravação subiu.) Sem nenhum mapeamento de cor
    (o estado antes deste conserto), cor de camada e cor por entidade eram
    descartadas silenciosamente ao salvar.

    Memorizada: um desenho usa um punhado de cores distintas, mas a função
    era chamada uma vez por entidade gravada. No perfil da gravação do
    `2412_EX_105_CR_ELÉTRICA_R01_BIND` (4.384 blocos, 57.852 entidades
    dentro deles) ela custava 8,5 s dos 41 s — a função mais cara da
    gravação inteira, com uma varredura da paleta a cada chamada."""
    if not hex_color:
        return None
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None
    melhor_aci, melhor_dist = 7, None
    for aci, candidato in _paleta_aci():
        dr = rgb[0] - candidato[0]
        dg = rgb[1] - candidato[1]
        db = rgb[2] - candidato[2]
        dist = dr * dr + dg * dg + db * db
        if melhor_dist is None or dist < melhor_dist:
            melhor_dist, melhor_aci = dist, aci
    return melhor_aci


@functools.lru_cache(maxsize=512)
def _aci_to_hex(aci: int) -> str:
    r, g, b = ezdxf.colors.aci2rgb(aci)
    return f"#{r:02X}{g:02X}{b:02X}"


def _is_invisible(dxf_entity) -> bool:
    """Group code 60 (Invisibility flag) do DXF: True = o AutoCAD nunca
    desenha esta entidade. É assim que um BLOCO DINÂMICO com parâmetro de
    Visibilidade fica gravado em DXF puro: TODAS as variantes (ex.: um
    símbolo com opções Baixo/Médio/Alto/Piso/Teto) viram INSERTs aninhados
    na mesma definição de bloco, na origem — só o INSERT do estado ativo no
    momento em que o arquivo foi salvo fica com invisible=0 (ausente); os
    outros ganham invisible=1. Sem filtrar isso, todas as variantes eram
    desenhadas empilhadas no mesmo ponto — o símbolo "explodido"/gigante
    reportado pelo Michael no grupo de feedback (planta PATRICIA E FABIO,
    09/09/2026): 202 dos 355 blocos do arquivo tinham essa forma. O group
    code é genérico do AcDbEntity (qualquer entidade pode ter invisible=1,
    não só INSERT de bloco dinâmico), então o filtro vale tanto dentro de
    uma definição de bloco quanto solto no modelspace."""
    return bool(dxf_entity.dxf.get("invisible", 0))


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
    # Leitura em massa: nao registrar cada atribuicao no diario de alteracoes
    # do canvas (1,15 milhao de insercoes inuteis nesta planta) — as entidades
    # novas sao descobertas pelo id que ainda nao tem item grafico.
    bulk = entities_module.bulk_load()
    bulk.__enter__()
    try:
        return _load_dxf_body(dxf_doc, document)
    finally:
        bulk.__exit__(None, None, None)


def _load_dxf_body(dxf_doc, document: Document) -> tuple[Document, int]:
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
        # True color (grupo 420) tem prioridade sobre o ACI quando existe —
        # senão a cor exata da camada era trocada pela da paleta de 255 ao
        # reabrir, mesmo tendo sido gravada certa (auditoria de 2026-09-07).
        rgb = getattr(layer, "rgb", None)
        if rgb:
            new_layer.color = "#{:02X}{:02X}{:02X}".format(*rgb)
        else:
            new_layer.color = _aci_to_hex(aci)
        new_layer.visible = not layer.is_off()
        new_layer.locked = layer.is_locked()
        # Tipo de linha e espessura DA CAMADA: é o que uma entidade ByLayer
        # herda, e é onde o projetista configura o tracejado na prática (7
        # das 64 camadas de um projeto da amostra; 25 das 346 de outro).
        new_layer.linetype = layer.dxf.get("linetype", "CONTINUOUS") or "CONTINUOUS"
        new_layer.lineweight = int(layer.dxf.get("lineweight", -3))

    # LTYPE: o padrão de traço de cada tipo de linha. Sem essa tabela o nome
    # ("DASHED", "LINHA TRACEJADA 2_1") não significaria nada nem pra
    # desenhar nem pra gravar de volta — a linha de eixo do cliente voltava
    # contínua. Elemento positivo é traço, negativo é lacuna, zero é ponto.
    for ltype in dxf_doc.linetypes:
        nome = ltype.dxf.name
        if nome.upper() in ("BYLAYER", "BYBLOCK"):
            continue
        elementos: list[float] = []
        total = 0.0
        for tag in ltype.pattern_tags.tags:
            if tag.code == 40:
                total = float(tag.value)
            elif tag.code == 49:
                elementos.append(float(tag.value))
        document.linetypes[nome] = LineType(
            name=nome,
            pattern=elementos,
            length=total or sum(abs(v) for v in elementos),
            description=ltype.dxf.get("description", "") or "",
        )
    # LTSCALE global: multiplica o comprimento de todo padrão. Numa planta em
    # centímetros o projetista deixa em 10 ou 50; gravar 1.0 fixo entregaria
    # a linha "tracejada" visualmente contínua.
    ltscale = dxf_doc.header.get("$LTSCALE")
    if ltscale:
        document.linetype_scale = float(ltscale)

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
        # O nome CRU, como está no arquivo. Guardar só o que tivesse ponto
        # ("romans.shx") fazia um STYLE com fonte "txt" — nome sem extensão,
        # comum em desenho antigo — ser regravado como "txt.ttf", um arquivo
        # que não existe (auditoria de 2026-09-07). Vazio continua querendo
        # dizer "estilo criado aqui, sem fonte de origem".
        font_cru = style.dxf.get("font", "") or ""
        font = font_cru or "Menlo"
        family = font.rsplit(".", 1)[0] if "." in font else font
        height = style.dxf.get("height", 0.0) or 2.5
        document.text_styles[name] = TextStyle(
            name=name,
            font_family=family,
            height=height,
            width=float(style.dxf.get("width", 1.0) or 1.0),
            font_file=font_cru,
        )

    clayer = dxf_doc.header.get("$CLAYER")
    if clayer and clayer in document.layers:
        document.current_layer = clayer

    for chave in _CABECALHOS_PRESERVADOS:
        if chave in dxf_doc.header:
            document.dxf_header_extras[chave] = dxf_doc.header.get(chave)

    insunits = dxf_doc.header.get("$INSUNITS")
    if insunits in _INSUNITS_TO_UNITS:
        document.units = _INSUNITS_TO_UNITS[insunits]

    skipped_by_type: dict[str, int] = collections.Counter()

    # MULTILEADER/LEADER/DIMENSION externa/ACAD_TABLE viram bloco anônimo +
    # BlockReference, e MLINE vira as linhas soltas (ver
    # newsicad/io/dxf_annotations.py); `import_entity` devolve None pra tudo
    # que não é anotação — aí segue `_from_dxf_entity`.
    importer = AnnotationImporter(
        document,
        lambda dxf_entity: _from_dxf_entity(dxf_entity, units=document.units),
        _apply_dxf_color,
        NEWSICAD_APPID,
        apply_stroke=_apply_dxf_traco,
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
    # A regra virou uma LISTA DE EXCLUSÃO em vez de uma lista de permissão
    # (`_BLOCOS_INTERNOS`, logo acima). Só "*U" era aceito, e em 07/09/2026 a
    # amostra oficial "blocks_and_tables" da Autodesk mostrou o mesmo estrago
    # com outra letra: 38 das 161 instâncias do desenho apontavam para "*B13"
    # a "*B37" — a cópia anônima que o AutoCAD cria para um bloco COM
    # ATRIBUTOS cujos valores são únicos por instância. Sumiam 3 vasos, 3
    # pias, 19 interruptores, fogão, geladeira e 11 portas (840 traços), sem
    # aviso nenhum; e ao gravar, os 38 INSERT saíam apontando para blocos
    # inexistentes, um .dxf que o `ezdxf.audit` reprova. Com a lista de
    # exclusão, o próximo prefixo anônimo que a Autodesk inventar já entra.
    #
    # As entidades são percorridas em `ordem_de_desenho()` (a ordem de
    # desenho do AutoCAD, tabela SORTENTS) — o canvas desenha na ordem do
    # dict, então é isso que faz um WIPEOUT cobrir só o que está atrás dele
    # e uma hachura sólida ficar por baixo das linhas do próprio ícone.
    def _importar_definicao(block) -> None:
        block_entities: list[Entity] = []
        attdefs: list[AttributeDef] = []
        for dxf_entity in ordem_de_desenho(block):
            if _is_invisible(dxf_entity):
                continue
            imported = importer.import_entity(dxf_entity)
            if imported is not None:
                block_entities.extend(imported)
                continue
            entity = _from_dxf_entity(dxf_entity, units=document.units)
            if entity is None:
                if dxf_entity.dxftype() == "ATTDEF":
                    # ATTDEF (molde de atributo dentro da definição) não é
                    # geometria perdida nem desenho: o valor preenchido chega
                    # como ATTRIB no INSERT e é promovido a Text no loop do
                    # modelspace abaixo. O molde é guardado à parte, só pra
                    # voltar ao bloco na gravação — sem ele os ATTRIBs
                    # gravados ficam órfãos (ver AttributeDef).
                    attdef = attdef_from_dxf(dxf_entity)
                    if attdef is not None:
                        attdefs.append(attdef)
                elif not nada_a_desenhar(dxf_entity):
                    skipped_by_type[dxf_entity.dxftype()] += 1
                continue
            _apply_dxf_color(entity, dxf_entity)
            _apply_dxf_traco(entity, dxf_entity)
            block_entities.append(entity)
            if dxf_entity.dxftype() == "INSERT":
                # ATTRIB de INSERT ANINHADO (bloco dentro de bloco): as
                # coordenadas já estão no espaço deste bloco pai — vira
                # Text aqui mesmo (achado attrib-aninhado; ver attrib_texts).
                entity.attributes = [
                    attribute_to_block_local(text_entity, entity)
                    for text_entity in attrib_texts(dxf_entity, entity.layer, _apply_dxf_color)
                ]
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
            for attdef in attdefs:
                attdef.insertion_point = Point(
                    attdef.insertion_point.x - bx, attdef.insertion_point.y - by
                )
        document.define_block(block.name, block_entities)
        if attdefs:
            document.block_attdefs[block.name] = attdefs

    for block in dxf_doc.blocks:
        name = block.name
        if name.upper().startswith(_BLOCOS_INTERNOS):
            continue
        if name in dxf_fills.EZDXF_ARROW_BLOCKS:
            continue
        _importar_definicao(block)

    for dxf_entity in ordem_de_desenho(dxf_doc.modelspace()):
        if _is_invisible(dxf_entity):
            continue
        imported = importer.import_entity(dxf_entity)
        if imported is not None:
            for entity in imported:
                document.add_entity(entity)
            continue
        entity = _from_dxf_entity(dxf_entity, units=document.units)
        if entity is None:
            if dxf_entity.dxftype() == "INSERT":
                # INSERT que não aponta para bloco nenhum (nome vazio) é
                # arquivo malformado e não desenha geometria — mas o ATTRIB
                # pendurado nele TEM conteúdo e posição, e some junto. Caso
                # real: 42 etiquetas de corte ('S" 34 e 35', 'S"36') num
                # arquivo da Patrícia e Fábio, 72 na base inteira.
                #
                # Continua contando como entidade perdida: a GEOMETRIA do
                # símbolo some de verdade, e esconder isso do aviso seria
                # dizer que nada se perdeu quando se perdeu.
                for texto in attrib_texts(dxf_entity, dxf_entity.dxf.layer, _apply_dxf_color):
                    document.add_entity(texto)
                skipped_by_type["INSERT"] += 1
                continue
            if dxf_entity.dxftype() == "ATTDEF":
                # ATTDEF DENTRO de um bloco é só o "molde" do atributo — o
                # valor preenchido vem como ATTRIB no INSERT (lido logo
                # abaixo) e o molde é guardado em `_importar_definicao`.
                # Aqui, porém, ele está SOLTO no espaço de desenho, e aí é
                # desenho de verdade: o AutoCAD mostra a TAG dele (ver
                # `attdef_solto_como_texto`).
                solto = attdef_solto_como_texto(dxf_entity)
                if solto is not None:
                    _apply_dxf_color(solto, dxf_entity)
                    _apply_dxf_traco(solto, dxf_entity)
                    document.add_entity(solto)
            elif not nada_a_desenhar(dxf_entity):
                # Texto que não desenha nada também não é perda (ver
                # `nada_a_desenhar`).
                skipped_by_type[dxf_entity.dxftype()] += 1
            continue
        _apply_dxf_color(entity, dxf_entity)
        _apply_dxf_traco(entity, dxf_entity)
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
            # Os valores de atributo entram DENTRO da instância, no
            # referencial do bloco — ver BlockReference.attributes.
            entity.attributes = [
                attribute_to_block_local(text_entity, entity)
                for text_entity in attrib_texts(dxf_entity, entity.layer, _apply_dxf_color)
            ]

    # Pranchas (paper space): mesma leitura do Model acima, mas guardada à
    # parte em `document.layouts[nome]` — camadas continuam sendo do
    # arquivo inteiro (`document.add_layer`), só a geometria é por espaço.
    # VIEWPORT (a "janela" que mostraria um recorte do Model dentro da
    # prancha) ainda não é desenhado — ver `_file_notes` pelo aviso dessa
    # limitação restante.
    for layout in dxf_doc.layouts:
        if layout.name == "Model":
            continue
        layout_entities: dict[str, Entity] = {}

        def _store_in_layout(entity: Entity) -> None:
            if not entity.layer:
                entity.layer = document.current_layer
            document.add_layer(entity.layer)
            layout_entities[entity.id] = entity

        for dxf_entity in ordem_de_desenho(layout):
            if dxf_entity.dxftype() == "VIEWPORT":
                continue
            if _is_invisible(dxf_entity):
                continue
            imported = importer.import_entity(dxf_entity)
            if imported is not None:
                for entity in imported:
                    _store_in_layout(entity)
                continue
            entity = _from_dxf_entity(dxf_entity, units=document.units)
            if entity is None:
                if dxf_entity.dxftype() == "INSERT":
                    # Ver o loop do modelspace: o bloco não existe, o texto
                    # do atributo existe — e a geometria perdida continua
                    # contando no aviso.
                    for texto in attrib_texts(dxf_entity, dxf_entity.dxf.layer, _apply_dxf_color):
                        _store_in_layout(texto)
                    skipped_by_type["INSERT"] += 1
                    continue
                if dxf_entity.dxftype() == "ATTDEF":
                    # Solto na prancha = desenho (ver o loop do modelspace).
                    solto = attdef_solto_como_texto(dxf_entity)
                    if solto is not None:
                        _apply_dxf_color(solto, dxf_entity)
                        _apply_dxf_traco(solto, dxf_entity)
                        _store_in_layout(solto)
                elif not nada_a_desenhar(dxf_entity):
                    skipped_by_type[dxf_entity.dxftype()] += 1
                continue
            _apply_dxf_color(entity, dxf_entity)
            _apply_dxf_traco(entity, dxf_entity)
            _store_in_layout(entity)
            if dxf_entity.dxftype() == "INSERT":
                entity.attributes = [
                    attribute_to_block_local(text_entity, entity)
                    for text_entity in attrib_texts(dxf_entity, entity.layer, _apply_dxf_color)
                ]
        if layout_entities:
            document.layouts[layout.name] = layout_entities

    # Tamanho de texto/seta das cotas nativas proporcional ao arquivo (ver
    # read_dim_style) — antes era fixo em 2.0/0.6 unidades de desenho, o que
    # numa planta em metros dava cotas maiores que a própria planta.
    text_height, arrow_size = read_dim_style(dxf_doc.header, importer.dimension_text_heights)
    document.dim_style = DimStyle(text_height=text_height, arrow_size=arrow_size)

    # Altura padrão do MTEXT neste desenho: a mais comum entre os textos que
    # ele já tem (ver Document.text_height). Numa planta em metros os textos
    # medem centésimos de unidade, e o padrão fixo de 2,5 saía gigante.
    heights = collections.Counter(
        round(entity.height, 9)
        for entity in document.entities.values()
        if isinstance(entity, Text) and entity.height > 0
    )
    if heights:
        document.text_height = heights.most_common(1)[0][0]

    # Segunda passada. A lista de exclusão acima é uma APOSTA sobre o que é
    # tripa do AutoCAD, e ela erra: na Casa Pau Brasil existe INSERT de "*X6"
    # no modelspace, e "*X" (hachura associativa) está na lista. O resultado
    # era o mesmo estrago do "*B" — a inserção ficava sem definição, não
    # desenhava nada, e ao gravar saía um .dxf que o `ezdxf` recusa a
    # percorrer ("Required block definition for *X6 does not exist",
    # 08/09/2026). Em vez de adivinhar melhor, a regra passa a ser: se
    # ALGUÉM insere, o bloco entra. Em laço porque uma definição recém-lida
    # pode inserir outra que também foi dispensada.
    for _ in range(_MAX_PASSADAS_ORFAOS):
        pendentes = [n for n in _orphan_block_names(document) if n in dxf_doc.blocks]
        if not pendentes:
            break
        for nome in pendentes:
            _importar_definicao(dxf_doc.blocks.get(nome))

    _recolhe_ole(document)

    notes = _file_notes(dxf_doc)
    orfas = _orphan_reference_note(document)
    if orfas:
        notes.append(orfas)
    skipped = SkippedCount(sum(skipped_by_type.values()), dict(skipped_by_type), notes)
    return document, skipped


#: Blocos que o AutoCAD usa para as PRÓPRIAS tripas do arquivo e que não são
#: desenho do usuário: os dois espaços de trabalho, "*D..." (setas e geometria
#: interna de cota) e "*X..." (hachura associativa). Todo o resto é carregado
#: — inclusive os anônimos "*U" (bloco dinâmico), "*B" (bloco com atributo
#: único por instância) e "*T" (conteúdo de tabela).
_BLOCOS_INTERNOS = ("*MODEL_SPACE", "*PAPER_SPACE", "*D", "*X")


#: Quantas vezes a segunda passada de blocos órfãos se repete. Cada volta
#: resolve um nível de aninhamento; mais que isso é ciclo ou arquivo doente.
_MAX_PASSADAS_ORFAOS = 8


def _orphan_block_names(document: Document) -> dict[str, int]:
    """Nomes de bloco que alguém INSERE e que não têm definição, com quantas
    inserções cada um tem. Olha o desenho e o miolo das definições de bloco
    (um bloco pode inserir outro)."""
    faltando: dict[str, int] = collections.Counter()
    grupos = [document.entities.values()] + list(document.block_definitions.values())
    for grupo in grupos:
        for entity in grupo:
            if isinstance(entity, BlockReference) and entity.block_name not in document.block_definitions:
                faltando[entity.block_name] += 1
    return faltando


def _orphan_reference_note(document: Document) -> str | None:
    """Aviso quando sobra INSERT sem definição de bloco.

    Rede de segurança para a família de defeitos "bloco carrega vazio": a
    entidade existe, ocupa lugar na contagem, e não desenha nada nem dá para
    clicar — o usuário só via um buraco na planta. Aconteceu duas vezes, com
    "*U" (2026-08-28) e com "*B" (2026-09-07)."""
    faltando = _orphan_block_names(document)
    if not faltando:
        return None
    nomes = ", ".join(sorted(faltando)[:5])
    reticencias = "…" if len(faltando) > 5 else ""
    return (
        f"Aviso: {sum(faltando.values())} inserção(ões) de bloco apontam para "
        f"{len(faltando)} definição(ões) que não vieram no arquivo ({nomes}{reticencias}) "
        "— elas não aparecem no desenho."
    )


def _file_notes(dxf_doc) -> list[str]:
    """Avisos sobre o que existe no arquivo mas o NewSIcad não mostra por
    completo, e as XREFs. As pranchas em paper space (LAYOUTS — selo,
    legenda, tabelas da New SI, e às vezes o projeto inteiro) passaram a
    ser carregadas em `document.layouts` (09/09/2026, achado do grupo de
    feedback do NewSicad — arquivos onde o Model space vinha praticamente
    vazio e o desenho de verdade estava todo em paper space). O que ainda
    falta é só o VIEWPORT: a "janela" que uma prancha normalmente tem pra
    mostrar um recorte/escala do Model space — o NewSIcad não recorta nem
    escala isso ainda, então uma prancha com viewport mostra só o resto do
    conteúdo desenhado direto nela. XREF: a base arquitetônica costuma ser
    uma referência externa a outro .dwg, que não vem junto quando só um
    arquivo é enviado — no AutoCAD também aparece como "referência não
    encontrada". Sem esses avisos o tester via uma planta "sem legenda"/
    "sem base" e não tinha como saber o motivo (relato de 2026-08-31,
    plantas Ana Beatriz e Casa Pau Brasil)."""
    notes: list[str] = []
    viewport_layouts: list[str] = []
    for layout in dxf_doc.layouts:
        if layout.name == "Model":
            continue
        if any(e.dxftype() == "VIEWPORT" for e in layout):
            viewport_layouts.append(layout.name)
    if viewport_layouts:
        notes.append(
            f"Aviso: {len(viewport_layouts)} prancha(s) em paper space têm um viewport "
            "(recorte/escala do Model space) que o NewSIcad ainda não desenha — só o "
            f"resto do conteúdo da prancha aparece: {', '.join(viewport_layouts)}."
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


def _apply_dxf_traco(entity: Entity, e) -> None:
    """Tipo de linha, espessura e escala do traço da entidade.

    Os três eram descartados na leitura: toda linha tracejada do cliente
    voltava contínua no arquivo entregue e toda espessura voltava "padrão".
    No censo da base (01/10/2026), 6 de 7 projetos têm linha não contínua —
    7 % das entidades em média, 25 % no pior caso — e 29 % das entidades têm
    espessura própria, 75 % no pior caso. A perda é silenciosa: o desenho
    continua lá, só deixou de distinguir eixo de parede e projeção de corte.
    """
    # Só ATRIBUI o que difere do padrão. Cada atribuição numa entidade passa
    # por `Entity.__setattr__`, que carimba uma versão nova (é o que deixa o
    # canvas saber o que mudou sem comparar tudo) — e a esmagadora maioria
    # das entidades é ByLayer, sem espessura e sem escala própria. Atribuir
    # os três sempre custava 3 carimbos por entidade: no perfil da Casa Pau
    # Brasil, `__setattr__` era a função mais cara da leitura, com 2,5
    # milhões de chamadas.
    linetype = e.dxf.get("linetype", "BYLAYER") or "BYLAYER"
    if linetype.upper() != "BYLAYER":
        # ByLayer fica como "" (o padrão do campo), e a resolução tem um
        # caminho só — ver `Document.linetype_of`.
        entity.linetype = linetype
    lineweight = int(e.dxf.get("lineweight", -1))
    if lineweight != -1:
        entity.lineweight = lineweight
    escala = float(e.dxf.get("ltscale", 1.0) or 1.0)
    if escala > 0 and escala != 1.0:
        entity.linetype_scale = escala


def _apply_dxf_color(entity: Entity, e) -> None:
    """Cor própria da entidade (exceção ao ByLayer): true color, ACI, e o
    sentinel BYBLOCK pra cor 0 — ver `dxf_fills.apply_dxf_color`. Sem essa
    função a cor por entidade nunca era lida de volta (bug real de
    auditoria, 2026-08-22)."""
    dxf_fills.apply_dxf_color(entity, e)


def ordem_de_desenho(layout):
    """Entidades do layout na ordem de desenho do AutoCAD (tabela SORTENTS),
    caindo na ordem natural quando essa tabela está corrompida.

    A tabela vem quebrada em arquivo real: o `NEWSI-CSA-03-PV1_R07` da Casa
    Sanchez tem um bloco cuja SORTENTSTABLE o `dwg2dxf` grava com um item
    pela metade, e o ezdxf levanta `ValueError: dictionary update sequence
    element #0 has length 1` — subindo até o topo e derrubando a abertura do
    arquivo INTEIRO. Ordem de desenho é acabamento (é o que faz o WIPEOUT
    cobrir só o que está atrás); perder o acabamento de um bloco é
    incomparavelmente melhor do que não abrir o projeto.
    """
    try:
        return list(layout.entities_in_redraw_order())
    except Exception:
        return list(layout)


def _imagem(e, layer: str) -> Entity | None:
    """IMAGE -> ImageReference.

    Era descartada inteira. Na varredura da base, 19% dos arquivos têm
    imagem e os três piores caem para 73,6%, 83,9% e 89,5% de cobertura por
    causa disso — o luminotécnico da Mauro e Marcia tem 92 imagens numa
    prancha só. Some da tela E do arquivo entregue ao cliente.

    O .dxf guarda o tamanho em PIXELS e dois vetores que dizem quanto vale
    um pixel no desenho; o tamanho em unidades é o produto dos dois. Rotação
    não é modelada (o `ImageReference` não tem): imagem girada entra com a
    caixa alinhada aos eixos, que é onde ela está em planta na prática.
    """
    try:
        pixels = e.dxf.get("image_size", (0, 0, 0))
        u = e.dxf.get("u_pixel", (1, 0, 0))
        v = e.dxf.get("v_pixel", (0, 1, 0))
        largura = abs(float(pixels[0])) * math.hypot(float(u[0]), float(u[1]))
        altura = abs(float(pixels[1])) * math.hypot(float(v[0]), float(v[1]))
    except Exception:
        return None
    if largura <= 0 or altura <= 0:
        return None
    try:
        caminho = e.image_def.dxf.get("filename", "") or ""
    except Exception:
        caminho = ""

    imagem = ImageReference(
        layer=layer,
        path=Path(caminho),
        insertion_point=_point(e.dxf.get("insert", (0, 0, 0))),
        width=largura,
        height=altura,
        pixel_size=(int(abs(float(pixels[0]))), int(abs(float(pixels[1])))),
    )

    # Recorte (CLIP): o .dxf dá o contorno em PIXELS a partir do canto, com
    # meio pixel de folga; o nosso modelo quer unidades de desenho a partir
    # do ponto de inserção.
    try:
        if e.dxf.get("clipping", 0) and len(e.boundary_path) > 2:
            por_pixel_x = largura / max(float(pixels[0]), 1.0)
            por_pixel_y = altura / max(float(pixels[1]), 1.0)
            imagem.clip_boundary = [
                Point((float(pt[0]) + 0.5) * por_pixel_x, (float(pt[1]) + 0.5) * por_pixel_y)
                for pt in e.boundary_path
            ]
    except Exception:
        pass
    return imagem


#: Retângulo FIXO que o `dwg2dxf` (LibreDWG) grava nos grupos 10/11 de TODO
#: OLE2FRAME, seja qual for o objeto: o mesmo par de cantos, com 14 casas
#: decimais iguais, em 9 arquivos de 8 projetos — blobs de 9 KB a 13 MB, todos
#: com o "mesmo" retângulo de 5,1 x 3,4. Não é geometria, é valor padrão.
_CANTOS_FIXOS_DWG2DXF = (
    (30.13602472538446, -18.98882829402869),
    (35.27188116753285, -22.39344715050545),
)

#: Os 4 cantos do retângulo (12 doubles) começam no byte 2 do conteúdo binário
#: do OLE2FRAME; o arquivo composto do Windows (assinatura D0CF11E0A1B11AE1)
#: vem logo depois, no byte 128.
_OLE_CANTOS_OFFSET = 2
_OLE_ASSINATURA = bytes.fromhex("d0cf11e0a1b11ae1")


def _retangulo_do_preambulo_ole(dados: bytes) -> tuple[float, float, float, float] | None:
    """(xmin, ymin, xmax, ymax) lido do PREÂMBULO do conteúdo do OLE2FRAME.

    O AutoCAD não guarda o retângulo do objeto OLE em campo próprio: ele vem
    nos primeiros 98 bytes do conteúdo binário — dois bytes de cabeçalho e
    os quatro cantos (esquerda-cima, direita-cima, direita-baixo,
    esquerda-baixo) como x, y, z em double. Foi o jeito de saber o lugar
    certo, porque os grupos 10/11 que o `dwg2dxf` grava são um valor fixo
    (`_CANTOS_FIXOS_DWG2DXF`). Conferido contra o ODA File Converter, que
    decodifica o .dwg por conta própria: 51 de 51 OLE2FRAME de 9 arquivos
    reais coincidem com os grupos 10/11 do ODA, até a última casa decimal.

    Só confia no que tem a forma medida: doubles finitos, z = 0 e o arquivo
    composto do Windows logo depois. Qualquer outra coisa devolve None.
    """
    if len(dados) < _OLE_CANTOS_OFFSET + 96:
        return None
    if _OLE_ASSINATURA not in dados[:256]:
        return None
    valores = struct.unpack_from("<12d", dados, _OLE_CANTOS_OFFSET)
    if not all(math.isfinite(v) and abs(v) < 1e12 for v in valores):
        return None
    if any(valores[i] != 0.0 for i in (2, 5, 8, 11)):
        return None
    xs = (valores[0], valores[3], valores[6], valores[9])
    ys = (valores[1], valores[4], valores[7], valores[10])
    return min(xs), min(ys), max(xs), max(ys)


def _ole2frame(e, layer: str) -> Entity | None:
    """OLE2FRAME -> OleFrame: a MOLDURA do objeto OLE, no lugar e no tamanho.

    É o tipo não lido mais espalhado da base: 143 entidades em 32 arquivos
    (11 pastas de projeto). Objeto incorporado — planilha do Excel, imagem
    colada de outro programa — e some da tela E do arquivo entregue ao
    cliente. Renderizar o conteúdo está fora de escopo (o AutoCAD também só
    mostra a moldura quando o objeto não está disponível); o conteúdo é
    guardado para voltar ao arquivo na gravação (`_escreve_ole`).

    O retângulo vem do preâmbulo do conteúdo (`_retangulo_do_preambulo_ole`),
    não dos grupos 10/11: os do `dwg2dxf` são sempre o mesmo valor. Só se o
    preâmbulo não for legível é que valem os grupos 10/11 — num .dxf do
    AutoCAD ou do ODA eles estão certos — e o valor fixo do `dwg2dxf` é
    recusado em vez de virar uma moldura mentirosa no canto errado.
    """
    tags = getattr(e, "acdb_ole2frame", None)
    if tags is None:
        return None
    try:
        dados = e.binary_data()
    except Exception:
        dados = b""
    retangulo = _retangulo_do_preambulo_ole(dados)
    if retangulo is None:
        c10 = tags.get_first_value(10, None)
        c11 = tags.get_first_value(11, None)
        if c10 is None or c11 is None:
            return None
        try:
            cantos = ((float(c10[0]), float(c10[1])), (float(c11[0]), float(c11[1])))
        except Exception:
            return None
        if all(
            abs(a - b) < 1e-9
            for canto, fixo in zip(cantos, _CANTOS_FIXOS_DWG2DXF)
            for a, b in zip(canto, fixo)
        ):
            return None
        retangulo = (
            min(cantos[0][0], cantos[1][0]), min(cantos[0][1], cantos[1][1]),
            max(cantos[0][0], cantos[1][0]), max(cantos[0][1], cantos[1][1]),
        )
    xmin, ymin, xmax, ymax = retangulo
    if xmax - xmin <= 0 or ymax - ymin <= 0:
        return None

    def escalar(grupo: int, padrao):
        try:
            valor = tags.get_first_value(grupo, None)
            return padrao if valor is None else int(valor)
        except Exception:
            return padrao

    quadro = OleFrame(
        layer=layer,
        insertion_point=Point(xmin, ymin),
        width=xmax - xmin,
        height=ymax - ymin,
    )
    if dados:
        quadro.bruto = OleObjeto(
            dados=dados,
            versao=escalar(70, 2),
            tipo=escalar(71, None),
            espaco=escalar(72, 1),
            qualidade=escalar(73, 2),
        )
    return quadro


def _recolhe_ole(document: Document) -> None:
    """Passa o conteúdo binário de cada OleFrame para `Document.ole_dados`.

    A leitura (`_ole2frame`) não conhece o documento, então devolve o quadro
    com o conteúdo pendurado em `bruto`. Aqui ele vai para o dicionário do
    documento, chaveado pelo SHA-1, e o quadro fica só com a chave: os 20
    OLE2FRAME do arquivo do Joe Lee são o MESMO objeto de 411 KB e passam a
    ocupar uma cópia. Percorre o desenho, as pranchas e as definições de
    bloco — o carimbo do H&M, com as três planilhas, está dentro de um bloco."""
    def passa(entidades) -> None:
        for entidade in entidades:
            if not isinstance(entidade, OleFrame) or entidade.bruto is None:
                continue
            objeto = entidade.bruto
            ficha = f"{objeto.versao}|{objeto.tipo}|{objeto.espaco}|{objeto.qualidade}".encode()
            chave = hashlib.sha1(objeto.dados + ficha).hexdigest()
            document.ole_dados.setdefault(chave, objeto)
            entidade.ole_key = chave
            entidade.bruto = None

    passa(document.entities.values())
    for entidades in document.layouts.values():
        passa(entidades.values())
    for entidades in document.block_definitions.values():
        passa(entidades)


#: Códigos do 3DFACE que marcam cada aresta como invisível (group code 70).
_ARESTA_INVISIVEL = (1, 2, 4, 8)


def _face_3d(e, layer: str) -> Entity | None:
    """3DFACE -> o CONTORNO dela como polilinha 2D.

    O 3DFACE é um triângulo ou quadrilátero plano — como o arquiteto entrega
    laje, telhado e terreno no .dwg base. Era descartado inteiro, e isso
    custava o desenho: o `BASE_XREF_LEE` do Joe Lee, com 72 deles, fechava em
    **4,0% de cobertura** — 4.213 dos 4.289 segmentos estavam lá, mas os 76
    que faltavam eram justamente os que cobrem a prancha. Duas revisões do
    mesmo arquivo, e o projetista abria praticamente sem desenho.

    Vira contorno, não superfície: o NewSIcad é editor 2D (ver docs/ESCOPO.md)
    e o que o projetista precisa é VER a base para projetar em cima. Aresta
    marcada como invisível no DXF é respeitada — é com ela que o AutoCAD
    esconde a diagonal de um quadrilátero partido em dois triângulos; desenhar
    essas diagonais encheria a planta de linhas que o cliente não vê.
    """
    try:
        cantos = [_point(e.dxf.get(nome)) for nome in ("vtx0", "vtx1", "vtx2", "vtx3")]
    except Exception:
        return None
    flags = int(e.dxf.get("invisible_edges", 0) or 0)

    def mesmo(a: Point, b: Point) -> bool:
        return abs(a.x - b.x) < 1e-9 and abs(a.y - b.y) < 1e-9

    # As quatro arestas do DXF, na ordem — e o sinalizador de invisibilidade é
    # indexado por ESSA ordem, não pela lista de cantos distintos. Num
    # triângulo gravado como A,B,C,C a aresta de volta é a 3 (C→A) e a 2 é a
    # degenerada; casar errado esconde a aresta errada.
    arestas: list[tuple[Point, Point]] = []
    for i in range(4):
        a, b = cantos[i], cantos[(i + 1) % 4]
        if mesmo(a, b):          # aresta degenerada do triângulo
            continue
        if flags & _ARESTA_INVISIVEL[i]:
            continue
        arestas.append((a, b))
    if not arestas:
        return None

    # Emenda as arestas visíveis em sequências contínuas (circularmente) e
    # devolve a MAIOR. Com todas visíveis sai o contorno fechado; com a
    # diagonal escondida — o quadrilátero partido em dois triângulos, que é
    # como vem a malha de terreno do arquiteto — sai o contorno aberto.
    cadeias: list[list[Point]] = []
    for a, b in arestas:
        if cadeias and mesmo(cadeias[-1][-1], a):
            cadeias[-1].append(b)
        else:
            cadeias.append([a, b])
    if len(cadeias) > 1 and mesmo(cadeias[-1][-1], cadeias[0][0]):
        cadeias[0] = cadeias[-1] + cadeias[0][1:]
        cadeias.pop()
    maior = max(cadeias, key=len)
    fechada = len(maior) > 3 and mesmo(maior[0], maior[-1])
    if fechada:
        maior = maior[:-1]
    return LWPolyline(layer=layer, points=maior, closed=fechada)


def _from_dxf_entity(e, units: str = "mm") -> Entity | None:
    """Entidade DXF -> entidade do NewSIcad (None = tipo não suportado).
    `units` (Document.units) só entra no espaçamento aproximado de HATCH com
    padrão vindas de outro programa (ver `dxf_fills.hatch_from_dxf`)."""
    dxftype = e.dxftype()
    layer = e.dxf.layer

    if dxftype == "LINE":
        return Line(layer=layer, start=_point(e.dxf.start), end=_point(e.dxf.end))

    if dxftype == "3DFACE":
        return _face_3d(e, layer)

    if dxftype == "IMAGE":
        return _imagem(e, layer)

    if dxftype == "OLE2FRAME":
        return _ole2frame(e, layer)

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


def escapa_mtext(conteudo: str) -> str:
    r"""Prepara um texto do modelo para virar o conteúdo CRU de um MTEXT.

    O modelo guarda o texto já legível ("Q.A. {INFRA}", "0,16^ m"); o MTEXT
    do DXF guarda uma linguagem de formatação, onde "{" e "}" agrupam, a
    barra invertida inicia comando e "^" é notação de caractere de controle.
    Gravar o texto legível direto fazia o leitor interpretá-lo de novo e
    devolver outra coisa: "Q.A. {INFRA}" voltava "Q.A. INFRA" e "a^b"
    voltava 'a"'. Ou seja, o texto do cliente era corrompido ao salvar —
    achado na varredura da base em 01/10/2026, nas etiquetas de área do
    projeto hidráulico da Academia Pegasus. Com o escape, os dez casos de
    teste sobrevivem à ida e volta; sem ele, três."""
    conteudo = conteudo.replace("\\", "\\\\")
    conteudo = conteudo.replace("{", r"\{").replace("}", r"\}")
    return conteudo.replace("^", "^ ")


def _preenchimento_sem_area(e) -> bool:
    """SOLID/TRACE/HATCH cujo contorno tem menos de 3 cantos distintos.

    Um polígono de dois cantos tem área zero: não há o que preencher, e o
    AutoCAD não desenha nada (o preenchimento é o padrão — FILLMODE ligado).
    São contornos que vão "ida e volta", A->B->A, e vêm aos milhares de
    arquivo importado de PDF: num único projeto da base (Carla e Raymond) são
    2.099 SOLID assim, e as camadas das hachuras começam com `PDF2_`.

    Recusá-los está certo; o que estava errado era contá-los como entidade
    perdida no aviso de abertura — dizer ao projetista que o programa comeu
    4.579 coisas do arquivo dele quando não comeu nenhuma.
    """
    def poucos(pontos) -> bool:
        distintos = {(round(float(x), 9), round(float(y), 9)) for x, y in pontos}
        return len(distintos) < 3

    try:
        if e.dxftype() in ("SOLID", "TRACE"):
            return poucos((v.x, v.y) for v in e.wcs_vertices())
        for bp in e.paths:  # HATCH: basta um contorno com área para desenhar
            vertices = getattr(bp, "vertices", None)
            if vertices is None:  # contorno por arestas (arco/spline): tem área
                return False
            if not poucos((v[0], v[1]) for v in vertices):
                return False
        return True
    except Exception:
        return False


def nada_a_desenhar(e) -> bool:
    """A entidade foi recusada porque não desenha NADA, não porque o
    NewSIcad não a suporta?

    Vale para TEXT/MTEXT/ATTRIB de conteúdo vazio ou só espaço e para altura
    zero — `text_from_dxf_text` recusa os dois, e com razão: o AutoCAD também
    não desenha. Contá-los como "não suportadas" inflava o aviso de abertura
    e dizia ao projetista que o programa tinha perdido coisa do arquivo dele
    quando não tinha perdido nada. Caso real da varredura da base
    (01/10/2026): os blocos de margem A0–A3 do padrão da New SI têm um TEXT
    de um espaço em branco cada, e todo projeto abria avisando "10 entidades
    não suportadas".

    Vale também para SOLID/TRACE/HATCH de ÁREA ZERO — ver
    `_preenchimento_sem_area`. Achado da varredura de 03/10/2026: 4.579
    SOLID e 1.229 HATCH da base caíam no aviso, e nenhum deles desenha nada.

    E para MLINE sem nenhuma linha a desenhar (um vértice só, ou vértices
    coincidentes) — ver o ramo da MLINE logo abaixo.
    """
    if e.dxftype() in ("SOLID", "TRACE", "HATCH"):
        return _preenchimento_sem_area(e)
    if e.dxftype() == "MLINE":
        # Multilinha de um vértice só, ou de vértices coincidentes: o ezdxf
        # materializa ZERO linhas e o AutoCAD também não desenha nada. É
        # diferente de a materialização levantar exceção (estilo quebrado),
        # que é multilinha NÃO lida e continua contando como perda.
        try:
            return not list(e.virtual_entities())
        except Exception:
            return False
    if e.dxftype() not in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
        return False
    conteudo = texto_do_dxf(e)
    if not str(conteudo).strip():
        return True
    # TEXT/ATTRIB guardam a altura em `height`; MTEXT em `char_height`.
    for campo in ("height", "char_height"):
        try:
            altura = float(e.dxf.get(campo, 0.0) or 0.0)
        except Exception:
            continue
        if altura:
            return altura <= TEXT_HEIGHT_MIN
    return True


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
        # Tamanhos próprios da cota e estilo de texto: gravados depois do
        # raio a partir da 2.16 (-1 = "sem tamanho próprio"). Arquivo mais
        # antigo não tem essas tags — daí o `len(values)`.
        own_text = values[12] if len(values) > 12 else -1.0
        own_arrow = values[13] if len(values) > 13 else -1.0
        own_style = values[14] if len(values) > 14 else ""
        return Dimension(
            layer=layer,
            kind=kind,
            point1=point1,
            point2=point2,
            dim_line_point=dim_line_point,
            center=center,
            radius=radius,
            leader_point=leader_point,
            text_height=None if own_text is None or float(own_text) < 0 else float(own_text),
            arrow_size=None if own_arrow is None or float(own_arrow) < 0 else float(own_arrow),
            text_style=str(own_style or ""),
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

    # LTYPE antes das camadas: uma camada não pode citar um tipo de linha que
    # ainda não está na tabela.
    for nome, ltype in document.linetypes.items():
        if nome.upper() in ("CONTINUOUS", "BYLAYER", "BYBLOCK") or nome in dxf_doc.linetypes:
            continue
        try:
            dxf_doc.linetypes.add(
                nome,
                pattern=([ltype.length or sum(abs(v) for v in ltype.pattern), *ltype.pattern]
                         if ltype.pattern else [0.0]),
                description=ltype.description,
            )
        except Exception:
            # Nome que o DXF não aceita ou padrão degenerado: perder o
            # tracejado desse tipo é menos grave que não gravar o arquivo.
            continue
    if document.linetype_scale and document.linetype_scale != 1.0:
        dxf_doc.header["$LTSCALE"] = float(document.linetype_scale)

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
        rgb_layer = _hex_to_rgb(layer.color)
        if rgb_layer is not None:
            dxf_layer.rgb = rgb_layer
        if layer.linetype and layer.linetype in dxf_doc.linetypes:
            dxf_layer.dxf.linetype = layer.linetype
        if layer.lineweight != -3:
            dxf_layer.dxf.lineweight = int(layer.lineweight)
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

    for chave, valor in document.dxf_header_extras.items():
        if chave not in _CABECALHOS_PRESERVADOS:
            continue
        dxf_doc.header[chave] = valor
        # Os limites moram em DOIS lugares: no cabeçalho e no próprio layout
        # do modelspace. O ezdxf reescreve o cabeçalho a partir do layout ao
        # gravar, então mexer só no header não adiantava nada.
        if chave in ("$LIMMIN", "$LIMMAX"):
            msp.dxf.set(chave[1:].lower(), valor)
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
    # Os nomes que vão ser gravados COMO ESTÃO são reservados antes: o
    # `new_anonymous_block` do ezdxf só olha o que já existe no documento
    # novo, então um "*ML_ABC" renomeado podia receber "*U1" e, mais adiante
    # na ordem do dict, um "*U1" legítimo do arquivo caía no "já existe" e ia
    # parar DENTRO do mesmo bloco — duas definições viravam uma, com os dois
    # INSERT apontando para ela (auditoria de 2026-09-07: latente, dependia
    # da ordem do dict).
    reservados = {
        name
        for name in document.block_definitions
        if not (name.startswith("*") and not _ANONYMOUS_BLOCK_NAME_RE.match(name))
    }
    for name in document.block_definitions:
        if name.startswith("*") and not _ANONYMOUS_BLOCK_NAME_RE.match(name):
            gerado = dxf_doc.blocks.new_anonymous_block(type_char="U").name
            while gerado in reservados:
                gerado = dxf_doc.blocks.new_anonymous_block(type_char="U").name
            dxf_block_names[name] = gerado
            continue
        if name not in dxf_doc.blocks:
            dxf_doc.blocks.new(name=name)
        dxf_block_names[name] = name
    for name, entities in document.block_definitions.items():
        block_layout = dxf_doc.blocks.get(dxf_block_names[name])
        _write_attdefs(block_layout, document.block_attdefs.get(name, []))
        for entity in entities:
            _to_dxf_entity(block_layout, entity, dxf_block_names, document.dim_style, document)

    for entity in document.all_entities():
        _to_dxf_entity(msp, entity, dxf_block_names, document.dim_style, document)

    # Pranchas (paper space): grava cada uma de volta no layout de mesmo
    # nome (cria se não existir — ex.: um .dwg de arquiteto com pranchas
    # "00 - Capa", "01"...). Sem isto, abrir um arquivo com conteúdo em
    # paper space e dar Save apagava esse conteúdo silenciosamente (ele
    # nunca ia pro `ezdxf.new()` do início desta função). O "Layout1" que
    # todo `ezdxf.new()` cria sozinho fica sem uso e é removido, a não ser
    # que o próprio arquivo já tivesse uma prancha chamada assim.
    existing_layout_names = set(dxf_doc.layouts.names())
    for name, entities in document.layouts.items():
        layout = dxf_doc.layouts.get(name) if name in existing_layout_names else dxf_doc.layouts.new(name)
        for entity in entities.values():
            _to_dxf_entity(layout, entity, dxf_block_names, document.dim_style, document)
    if document.layouts and "Layout1" not in document.layouts and "Layout1" in dxf_doc.layouts.names():
        dxf_doc.layouts.delete("Layout1")

    try:
        dxf_doc.saveas(str(path))
    except OSError as exc:
        raise DxfIoError(f"Não foi possível salvar '{path}': {exc}") from exc


def _apply_color_attribs(dxfattribs: dict, entity: Entity) -> None:
    """Escreve a cor da entidade no dicionário de atributos do DXF.

    ByLayer (`entity.color=None`) fica de fora de propósito: omitir a chave
    "color" faz o ezdxf usar o padrão DXF 256/BYLAYER sozinho. Sem isto,
    uma cor própria de entidade era descartada ao salvar (bug real de
    auditoria, 2026-08-22). `true_color` (grupo 420) preserva o RGB exato;
    o ACI vai junto como aproximação pra quem só lê a paleta antiga."""
    if entity.color == BYBLOCK:
        # Sentinel BYBLOCK (core/entities.py) = cor 0 do DXF: herda do INSERT.
        dxfattribs["color"] = 0
        return
    if not entity.color:
        return
    rgb = _hex_to_rgb(entity.color)
    if rgb is not None:
        dxfattribs["true_color"] = ezdxf.colors.rgb2int(rgb)
    aci = _hex_to_aci(entity.color)
    if aci is not None:
        dxfattribs["color"] = aci


def _escreve_imagem(msp, entity: ImageReference, attribs: dict) -> None:
    """Devolve a IMAGE ao .dxf, com a IMAGEDEF que a define.

    Até aqui a imagem era descartada ao gravar: o cliente recebia de volta um
    arquivo com a planta de fundo faltando. O .dxf nunca carrega os pixels —
    só o caminho —, então regravar é devolver a MESMA referência que veio.
    Sem caminho não há o que referenciar, e aí não se grava nada em vez de
    gravar uma referência quebrada.
    """
    # `Path("")` vira `Path(".")`, cujo texto NAO e vazio: sem tratar isso,
    # imagem sem arquivo virava uma IMAGE apontando para o diretorio atual.
    caminho = str(entity.path or "").strip()
    if not caminho or caminho in (".", ".."):
        return
    documento = getattr(msp, "doc", None)
    if documento is None:
        return
    pixels = entity.pixel_size if all(entity.pixel_size) else (1000, 1000)
    try:
        definicao = documento.add_image_def(filename=caminho, size_in_pixel=tuple(pixels))
        imagem = msp.add_image(
            definicao,
            insert=(entity.insertion_point.x, entity.insertion_point.y),
            size_in_units=(entity.width, entity.height),
            dxfattribs=dict(attribs),
        )
    except Exception:
        # Imagem é acabamento: não pode impedir a gravação do desenho.
        return
    if not entity.clip_boundary:
        return
    try:
        por_pixel_x = entity.width / max(pixels[0], 1)
        por_pixel_y = entity.height / max(pixels[1], 1)
        imagem.set_boundary_path([
            (p.x / por_pixel_x - 0.5, p.y / por_pixel_y - 0.5) for p in entity.clip_boundary
        ])
    except Exception:
        pass


#: Quantos bytes cada linha 310 leva — o que o AutoCAD grava: 127 bytes viram
#: 254 caracteres hexadecimais, abaixo do limite de linha do formato.
_OLE_BYTES_POR_LINHA = 127


def _dados_ole_com_retangulo(dados: bytes, retangulo: tuple[float, float, float, float]) -> bytes:
    """O conteúdo do OLE com o preâmbulo acertado para o retângulo ATUAL.

    O lugar do objeto mora em dois sítios — os grupos 10/11 e o preâmbulo do
    conteúdo (ver `_retangulo_do_preambulo_ole`). Se o projetista move ou
    escala a moldura no NewSIcad e só os grupos 10/11 acompanham, o arquivo
    entregue diz duas coisas diferentes e quem manda no AutoCAD é um chute.
    Sem mudança, devolve os bytes originais intactos; só reescreve um
    preâmbulo na forma canônica medida (esquerda-cima, direita-cima,
    direita-baixo, esquerda-baixo)."""
    atual = _retangulo_do_preambulo_ole(dados)
    if atual is None or all(
        math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9) for a, b in zip(atual, retangulo)
    ):
        return dados
    v = struct.unpack_from("<12d", dados, _OLE_CANTOS_OFFSET)
    canonico = (
        v[0] == v[9] and v[3] == v[6] and v[1] == v[4] and v[7] == v[10]
        and v[0] < v[3] and v[1] > v[7]
    )
    if not canonico:
        return dados
    x0, y0, x1, y1 = retangulo
    novo = bytearray(dados)
    struct.pack_into(
        "<12d", novo, _OLE_CANTOS_OFFSET,
        x0, y1, 0.0, x1, y1, 0.0, x1, y0, 0.0, x0, y0, 0.0,
    )
    return bytes(novo)


def _escreve_ole(layout, entity: OleFrame, attribs: dict, document: Document | None) -> None:
    """Devolve o OLE2FRAME ao .dxf, com o objeto dentro.

    Até aqui o objeto era descartado ao gravar: o cliente recebia de volta o
    carimbo sem as planilhas e a prancha sem a imagem colada. Aqui o NewSIcad
    devolve os MESMOS bytes que leu — não interpreta nem recodifica nada —,
    com o retângulo atual da moldura. Sem o conteúdo (quadro colado de outro
    desenho, onde `ole_dados` não veio junto) não se grava nada: uma moldura
    vazia no arquivo do cliente seria pior que nenhuma.

    Os grupos seguem o que o ODA File Converter grava, e o grupo 3 fica de
    fora: o `dwg2dxf` põe nele o literal "OLE", que não é o nome do objeto.

    DESLIGADO POR DECISÃO DO HAMILTON (04/10/2026), e a decisão foi tomada
    com o número na mesa: o objeto OLE vem como binário dentro do .dxf, que
    o formato guarda em hexadecimal — e o arquivo ENTREGUE ao cliente
    explodia. Medido na base real:

        Escritório H&M FLE04      1,0 MB  ->  78,3 MB   (um Excel de 13 MB
                                                         dentro do carimbo)
        Joe Lee 4.0_ELÉTRICA      3,3 MB  ->  20,3 MB

    78x o tamanho do arquivo para preservar um anexo que o projetista não
    edita aqui não paga. A MOLDURA continua sendo lida e aparece na tela no
    lugar certo (que é o ganho real: o projetista vê que existe um objeto
    ali); o que não volta ao arquivo é o conteúdo, exatamente como era antes
    deste trabalho — não há regressão.

    Para religar, basta apagar o `return` abaixo: todo o resto está pronto e
    coberto por teste, inclusive o acerto do retângulo no preâmbulo quando a
    moldura é movida. Se um dia valer, o caminho natural é um teto de
    tamanho (preservar o que for pequeno, declarar perda no que for grande).
    """
    return
    objeto = document.ole_dados.get(entity.ole_key) if document is not None else None
    if objeto is None or not objeto.dados:
        return
    x0, y0 = entity.insertion_point.x, entity.insertion_point.y
    x1, y1 = x0 + entity.width, y0 + entity.height
    dados = _dados_ole_com_retangulo(objeto.dados, (x0, y0, x1, y1))
    try:
        quadro = layout.new_entity("OLE2FRAME", dxfattribs=dict(attribs))
        marcas = [
            DXFTag(100, "AcDbOle2Frame"),
            DXFTag(70, objeto.versao),
            DXFVertex(10, (x0, y1, 0.0)),
            DXFVertex(11, (x1, y0, 0.0)),
        ]
        if objeto.tipo is not None:
            marcas.append(DXFTag(71, objeto.tipo))
        marcas += [DXFTag(72, objeto.espaco), DXFTag(73, objeto.qualidade), DXFTag(90, len(dados))]
        marcas += [
            DXFBinaryTag(310, dados[i:i + _OLE_BYTES_POR_LINHA])
            for i in range(0, len(dados), _OLE_BYTES_POR_LINHA)
        ]
        marcas.append(DXFTag(1, "OLE"))
        quadro.acdb_ole2frame = Tags(marcas)
    except Exception:
        # O objeto é acabamento: não pode impedir a gravação do desenho.
        return


def _apply_traco_attribs(dxfattribs: dict, entity: Entity, msp=None) -> None:
    """Tipo de linha, espessura e escala do traço no DXF gravado.

    ByLayer fica de fora de propósito (chave ausente = o próprio padrão do
    formato), igual à cor. O tipo de linha só é citado se a tabela LTYPE do
    arquivo o tiver: um nome órfão deixa o arquivo inválido pro AutoCAD, e um
    tracejado perdido é menos grave que um arquivo que não abre."""
    if entity.linetype:
        tabela = getattr(getattr(msp, "doc", None), "linetypes", None)
        if tabela is None or entity.linetype in tabela:
            dxfattribs["linetype"] = entity.linetype
    if entity.lineweight != -1:
        dxfattribs["lineweight"] = int(entity.lineweight)
    if entity.linetype_scale and entity.linetype_scale != 1.0:
        dxfattribs["ltscale"] = float(entity.linetype_scale)


def _escreve_dimension_preservada(msp, ref: BlockReference, fonte: dict,
                                  nome_do_bloco: str, attribs: dict) -> bool:
    """Regrava uma cota importada como DIMENSION de verdade, apontando para
    o bloco que carrega o desenho dela.

    Até a 2.16.3 ela voltava como INSERT de um bloco com linhas e texto: o
    cliente abria no AutoCAD e a cota tinha deixado de ser cota — não dava
    para editar nem remedir. Quantificado na varredura da base em
    01/10/2026: 37 cotas num arquivo do Town Houses, 46 num do Pegasus.

    Só vale quando a instância está intocada (sem mover/girar/escalar) e o
    conteúdo do bloco é o mesmo que foi importado. Mexeu, volta como
    geometria — o que o usuário vê é o que vale."""
    sx, sy = ref.scale_xy()
    intocada = (
        abs(ref.insertion_point.x) < 1e-9 and abs(ref.insertion_point.y) < 1e-9
        and abs(sx - 1.0) < 1e-9 and abs(sy - 1.0) < 1e-9
        and abs(ref.rotation) < 1e-12
    )
    if not intocada:
        return False

    dimattribs = {**attribs, "geometry": nome_do_bloco}
    for campo in ("dimtype", "text", "attachment_point", "line_spacing_style",
                  "line_spacing_factor", "angle", "oblique_angle",
                  "horizontal_direction", "text_rotation"):
        if campo in fonte:
            dimattribs[campo] = fonte[campo]
    for campo in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5",
                  "text_midpoint", "insert"):
        if campo in fonte:
            x, y = fonte[campo]
            dimattribs[campo] = (x, y, 0.0)
    estilo = fonte.get("dimstyle")
    doc = msp.doc
    dimattribs["dimstyle"] = estilo if (estilo and estilo in doc.dimstyles) else "Standard"
    try:
        msp.add_entity(ezdxf.entities.Dimension.new(dxfattribs=dimattribs))
    except Exception:
        return False
    return True


def _write_attdefs(block_layout, attdefs: list[AttributeDef]) -> None:
    """Devolve os moldes de atributo (ATTDEF) pra dentro da definição do
    bloco — ver AttributeDef em core/entities.py."""
    for attdef in attdefs:
        ponto = (attdef.insertion_point.x, attdef.insertion_point.y)
        dxfattribs = {
            "layer": attdef.layer,
            "height": max(attdef.height, 1e-3),
            "rotation": math.degrees(attdef.rotation),
            "style": attdef.style,
            "width": max(attdef.width_factor, 0.01),
            "prompt": attdef.prompt,
        }
        if attdef.invisible:
            dxfattribs["flags"] = 1
        escrito = block_layout.add_attdef(tag=attdef.tag, insert=ponto, text=attdef.default, dxfattribs=dxfattribs)
        alinhamento = _JUSTIFY_TO_ALIGN.get(attdef.justify)
        if alinhamento is not None and alinhamento is not TextEntityAlignment.LEFT:
            escrito.set_placement(ponto, align=alinhamento)


def _write_attribs(insert, ref: BlockReference) -> None:
    """Pendura os valores de atributo da instância no INSERT como ATTRIB de
    verdade, em vez de gravá-los como TEXT solto ao lado do bloco.

    Até a 2.16.0 todo atributo saía como texto comum: o campo funcionava
    dentro do NewSIcad, mas ao reabrir no AutoCAD deixava de ser um campo
    preenchível — o "Editar atributos" do bloco vinha vazio e a etiqueta
    virava um texto qualquer por cima do símbolo. As coordenadas voltam do
    referencial do bloco pro mundo, que é como o ATTRIB é sempre gravado.

    Conteúdo com quebra de linha não cabe num ATTRIB (que é TEXT-like, de
    uma linha só): esse sai como MTEXT comum no mesmo lugar, preservando o
    texto em vez de truncá-lo."""
    for local in ref.attributes:
        texto = attribute_to_world(local, ref)
        conteudo = texto.content
        if "\n" in conteudo:
            destino = None if local.invisible else insert.get_layout()
            if destino is not None:
                _to_dxf_entity(destino, texto)
                continue
            # Atributo INVISÍVEL (ou INSERT cujo layout não é alcançável,
            # dentro de uma definição de bloco) não pode virar MTEXT: isso
            # exporia na prancha um dado que o arquivo escondia de
            # propósito. Segue ATTRIB, com as quebras viradas em espaço —
            # que num campo que nunca é desenhado não representam nada.
            #
            # Quebra é só "\n": o `splitlines()` trocaria também U+0085 e
            # companhia por espaço, alterando em silêncio um valor que o
            # cliente escreveu (ver `linhas_do_dxf` em dwg_bridge.py).
            conteudo = " ".join(conteudo.split("\n"))
        ponto = (texto.insertion_point.x, texto.insertion_point.y)
        dxfattribs = {
            "layer": texto.layer,
            "height": max(texto.height, 1e-3),
            "rotation": math.degrees(texto.rotation),
            "style": texto.style,
            "width": max(texto.width_factor, 0.01),
        }
        if local.invisible:
            # Bit 1 do group code 70: o AutoCAD guarda o valor e não desenha.
            dxfattribs["flags"] = 1
        _apply_color_attribs(dxfattribs, texto)
        escrito = insert.add_attrib(tag=local.attrib_tag, text=conteudo, insert=ponto, dxfattribs=dxfattribs)
        alinhamento = _JUSTIFY_TO_ALIGN.get(texto.justify)
        if alinhamento is not None and alinhamento is not TextEntityAlignment.LEFT:
            escrito.set_placement(ponto, align=alinhamento)


def _to_dxf_entity(
    msp,
    entity: Entity,
    block_names: dict[str, str] | None = None,
    dim_style: DimStyle | None = None,
    document: Document | None = None,
) -> None:
    """`block_names`: nome interno -> nome gravado (ver save_dxf; None =
    mesmo nome). `dim_style`: tamanho de texto/seta das cotas (None =
    padrão DimStyle()). `document`: necessário para regravar uma anotação
    importada como anotação (ver `_escreve_dimension_preservada`)."""
    attribs = {"layer": entity.layer}
    _apply_color_attribs(attribs, entity)
    _apply_traco_attribs(attribs, entity, msp)

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
        if entity.bulges:
            bulges = list(entity.bulges) + [0.0] * (len(entity.points) - len(entity.bulges))
            points = [(p.x, p.y, b) for p, b in zip(entity.points, bulges)]
            polyline = msp.add_lwpolyline(points, format="xyb", dxfattribs=attribs)
        else:
            points = [(p.x, p.y) for p in entity.points]
            polyline = msp.add_lwpolyline(points, dxfattribs=attribs)
        polyline.closed = entity.closed
        if entity.width > 0:
            polyline.dxf.const_width = float(entity.width)
        return

    if isinstance(entity, Spline):
        # Pontos de ajuste COINCIDENTES quebram a interpolação de quem lê o
        # arquivo: o cálculo do espaçamento entre os dois primeiros pontos
        # vira zero e o leitor divide por zero (ezdxf
        # `cad_fit_point_interpolation`). Arquivos reais de arquiteto têm
        # ponto repetido com frequência — achado na varredura da base
        # (01/10/2026, Casa Sanchez e Academia Pegasus). O ponto repetido
        # não muda a curva, então some aqui em vez de virar um .dxf que o
        # programa do cliente não consegue abrir.
        points: list[tuple[float, float]] = []
        for p in entity.points:
            atual = (p.x, p.y)
            if points and abs(points[-1][0] - atual[0]) < 1e-9 and abs(points[-1][1] - atual[1]) < 1e-9:
                continue
            points.append(atual)
        if len(points) < 2:
            # Uma spline que virou um ponto só não é desenho — gravá-la
            # produziria uma entidade degenerada no arquivo do cliente.
            return
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
        fonte = (document.annotation_source.get(entity.block_name) if document else None)
        if fonte is not None and fonte.get("tipo") == "DIMENSION":
            atual = impressao_do_bloco(document.get_block_definition(entity.block_name))
            if tuple(fonte.get("impressao") or ()) == tuple(atual):
                if _escreve_dimension_preservada(msp, entity, fonte, dxf_name, attribs):
                    return
        insert = msp.add_blockref(
            dxf_name, (entity.insertion_point.x, entity.insertion_point.y), dxfattribs=insert_attribs
        )
        if entity.attributes:
            _write_attribs(insert, entity)
        return

    # OleFrame é uma ImageReference: o teste dele TEM de vir antes.
    if isinstance(entity, OleFrame):
        _escreve_ole(msp, entity, attribs, document)
        return

    if isinstance(entity, ImageReference):
        _escreve_imagem(msp, entity, attribs)
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
        msp.add_mtext(escapa_mtext(entity.content), dxfattribs=text_attribs)
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
    # Cota com tamanho PRÓPRIO (ajustado no painel de Propriedades) grava o
    # tamanho dela; sem override, o do desenho — ver dim_text_height.
    style_override = {
        "dimtxt": float(dim_text_height(entity, dim_style)),
        "dimasz": float(dim_arrow_size(entity, dim_style)),
    }
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
    # -1 = "sem tamanho próprio", pra reabrir voltando ao tamanho do desenho.
    tags.append((1040, -1.0 if entity.text_height is None else float(entity.text_height)))
    tags.append((1040, -1.0 if entity.arrow_size is None else float(entity.arrow_size)))
    tags.append((1000, entity.text_style or ""))
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
        wipeout = msp.add_wipeout([(p.x, p.y) for p in entity.boundary_points], dxfattribs=dict(attribs))
        # `add_wipeout` chama `set_masking_area`, que aplica DEFAULT_ATTRIBS
        # DEPOIS do que passamos — e esses defaults trazem `layer="0"`. Sem
        # reaplicar aqui, todo wipeout ia parar na camada "0" ao gravar e
        # deixava de obedecer o liga/desliga da camada de origem: ~1.150
        # entidades por gravação na planta NEWSI-CASA PAU BRASIL-R01
        # (auditoria de 2026-09-07).
        wipeout.update_dxf_attribs(dict(attribs))
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
    if pattern in _known_pattern_names():
        hatch.set_pattern_fill(pattern, color=attribs.get("color", 256), scale=max(entity.spacing, 0.1), angle=math.degrees(entity.angle))
    else:
        # Padrão de biblioteca de terceiro (veio num .dxf de fora, com nome
        # que a tabela do ezdxf não conhece). Antes o nome era trocado por
        # "ANSI31" e a hachura voltava com outro nome e outro desenho pra
        # quem abrisse o arquivo (auditoria de 2026-09-07). O nome original
        # fica, e junto vai uma definição própria — as mesmas linhas
        # paralelas que o NewSIcad de fato desenha (`angle`/`spacing`, ver
        # Hatch em core/entities.py) — pra não gravar um HATCH sem definição
        # nenhuma, que abre vazio no AutoCAD.
        hatch.set_pattern_fill(
            pattern,
            color=attribs.get("color", 256),
            scale=1.0,
            angle=0.0,
            definition=[[math.degrees(entity.angle), (0.0, 0.0), (0.0, max(entity.spacing, 0.1)), []]],
        )
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
