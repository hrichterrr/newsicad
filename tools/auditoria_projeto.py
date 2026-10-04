"""Auditoria GEOMÉTRICA de um projeto: o que o NewSIcad mostra bate com o
que o arquivo manda?

A varredura de fidelidade (`varredura_base.py`) responde "quantas entidades
entraram". A de render (`varredura_render.py`) responde "apareceu alguma
coisa na tela". Nenhuma das duas responde a pergunta que importa de verdade:

    os itens estão NO LUGAR CERTO? a legenda explodiu? as extremidades
    saíram do lugar? os círculos estão onde deviam? sumiu alguma linha?

Aqui a resposta é medida. O método:

1. O arquivo do cliente vira DXF (o mesmo caminho que o programa usa). Esse
   DXF é a VERDADE: é o que o AutoCAD diz que existe.
2. O NewSIcad lê esse DXF e grava de volta. Esse é o NOSSO resultado.
3. Os dois são achatados em segmentos de reta pelo MESMO código do ezdxf
   (blocos explodidos, arcos tesselados, tudo em coordenadas do mundo) —
   comparação maçã com maçã, sem favorecer ninguém.
4. Compara-se:
   - a extensão total do desenho (se mudou, algo saiu do lugar);
   - a extensão POR CAMADA (pega "a legenda explodiu": a camada dela cresce);
   - a contagem de segmentos por camada (pega "sumiu linha");
   - uma GRADE DE OCUPAÇÃO de 256x256 sobre a prancha, dizendo exatamente
     QUE REGIÃO ficou vazia no nosso e cheia no original — e o contrário,
     que é geometria aparecendo onde não devia.

O relatório sai por arquivo e some num ranking.

Uso:

    python tools/auditoria_projeto.py <arquivo.dwg | pasta> [--saida auditoria.json]
                                      [--mapas pasta] [--limite N]
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import subprocess
import json
import math
import sys
import threading
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # console do Windows em cp1252 não aceita acento/seta
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import ezdxf  # noqa: E402
import ezdxf.disassemble as dis  # noqa: E402

from newsicad.io import dwg_bridge
from newsicad.io.dxf_annotations import remonta_acento  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402

GRADE = 256
#: Diferença relativa de extensão acima da qual se considera que algo saiu
#: do lugar (1% da diagonal do desenho).
TOL_EXTENSAO = 0.01


# --------------------------------------------------------------------- #
# achatamento: tudo vira segmento de reta em coordenadas do mundo
# --------------------------------------------------------------------- #
#: Camadas que o AutoCAD NÃO plota e que não entram na comparação. Defpoints
#: guarda os pontos de definição das cotas; é invisível no papel por
#: definição do próprio AutoCAD.
CAMADAS_NAO_PLOTADAS = {"defpoints"}

#: Tipos que nunca são desenho da prancha. VIEWPORT é a JANELA do layout,
#: não conteúdo — e o nome da camada dela varia por escritório
#: (`_NEWSI_VIEWPORTS` no padrão da New SI), então filtrar por nome de
#: camada não pega. A moldura de um único viewport cobre 3,4% da grade e
#: aparecia como "some desenho".
_NAO_SAO_DESENHO = {"VIEWPORT"}

_MAX_ANINHAMENTO = 6

#: Tipos que viram geometria ao serem desenhados — a mesma lista que o
#: importador expande (ver newsicad/io/dxf_annotations.py).
_EXPANDIR = {"INSERT", "DIMENSION", "LEADER", "MULTILEADER", "ACAD_TABLE"}

#: Texto fica FORA da comparação geométrica e é comparado à parte, por
#: posição e conteúdo. Motivo: o ezdxf achata um texto como a CAIXA
#: delimitadora dele, e a nossa gravação (sempre MTEXT) produz caixa de
#: largura diferente da do TEXT original — a caixa não é desenho, mas
#: entrava na grade como se fosse e acusava "geometria que o original não
#: tem" em cima de cada etiqueta.
_TIPOS_DE_TEXTO = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}


def _invisivel(e) -> bool:
    """Group code 60: o AutoCAD nunca desenha. É assim que um bloco dinâmico
    com parâmetro de visibilidade guarda as variantes inativas — as dez
    molduras A0..A4 empilhadas dentro de `_Prancha-Margem` do padrão da New
    SI são exatamente isso. O `recursive_decompose` do ezdxf IGNORA esse
    sinalizador e desenha todas; sem este filtro a referência mostra dez
    molduras que o AutoCAD não mostra, e a auditoria acusa o NewSIcad de
    perder desenho que ele acertou em não desenhar."""
    try:
        return bool(e.dxf.get("invisible", 0))
    except Exception:
        return False


def _visiveis(entidades, profundidade: int = 0, camada_pai: str = ""):
    """(entidade, camada efetiva) do que o AutoCAD de fato desenha.

    Honra invisibilidade, pula camada não-plotada e aplica a HERANÇA DE
    CAMADA: conteúdo de bloco na camada "0" assume a camada do INSERT — a
    regra do AutoCAD, que o importador do NewSIcad aplica e o
    `virtual_entities` do ezdxf não. Sem isto a camada "0" da referência
    fica com tudo que no nosso modelo foi para a camada do símbolo, e a
    comparação por camada acusa 44,9% de deslocamento num arquivo com 100%
    de cobertura."""
    for e in entidades:
        if _invisivel(e):
            continue
        try:
            propria = (e.dxf.get("layer", "0") or "0").strip()
        except Exception:
            propria = "0"
        camada = camada_pai if (propria == "0" and camada_pai) else propria
        if camada.lower() in CAMADAS_NAO_PLOTADAS:
            continue
        if e.dxftype() in _NAO_SAO_DESENHO:
            continue
        if e.dxftype() in _TIPOS_DE_TEXTO:
            # Texto sai da travessia junto com o desenho (quem mede geometria
            # filtra depois): era a mesma expansão de bloco feita duas vezes,
            # e expandir bloco é o que custa caro aqui.
            yield e, camada
            continue
        if e.dxftype() in _EXPANDIR and profundidade < _MAX_ANINHAMENTO:
            # INSERT e ANOTAÇÃO (cota, chamada, tabela) são expandidos na
            # geometria que o AutoCAD já calculou e gravou. É o mesmo que o
            # importador do NewSIcad faz — sem isto, o achatador genérico do
            # ezdxf não materializa a seta nem a linha da chamada, e a
            # auditoria acusa o NewSIcad de INVENTAR geometria que na
            # verdade existe nos dois lados (67 LEADER num layout do Joe
            # Lee davam 4.501 células de "sobra" inexistente).
            try:
                filhos = list(e.virtual_entities())
            except Exception:
                continue
            yield from _visiveis(filhos, profundidade + 1, camada)
            continue
        yield e, camada


#: (arquivo, espaço) -> lista de (entidade, camada efetiva) já achatada.
#: Achatar é o passo caro da auditoria: no 2412_AP_101_LAY (3.782 entidades,
#: 142 blocos) uma travessia do modelspace custa 110 s, e ela era refeita
#: para medir segmento, para medir texto e para contar tipo — em cada um dos
#: dois arquivos comparados. É o que estourava o limite de 1.500 s num
#: arquivo de 0,69 MB que o PROGRAMA abre em 3,6 s.
_ACHATADO: dict[tuple[str, str], list] = {}


def achatado(caminho: Path, espaco: str = "Model") -> list:
    chave = (str(caminho), espaco)
    pronto = _ACHATADO.get(chave)
    if pronto is None:
        pronto = list(_visiveis(_entidades_do_espaco(abre(caminho), espaco)))
        if len(_ACHATADO) >= 4:   # Model + prancha, dos dois lados
            _ACHATADO.pop(next(iter(_ACHATADO)))
        _ACHATADO[chave] = pronto
    return pronto


def textos(caminho: Path, espaco: str = "Model") -> list[tuple[str, float, float]]:
    """(conteúdo, x, y) de cada texto desenhável, com blocos e anotações já
    expandidos — para comparar etiqueta por etiqueta, por posição."""
    out: list[tuple[str, float, float]] = []
    for e, _camada in achatado(caminho, espaco):
        if e.dxftype() not in _TIPOS_DE_TEXTO:
            continue
        if e.dxftype() == "ATTDEF":
            # ATTDEF SOLTO no espaco de desenho: o AutoCAD mostra a TAG, nao
            # o valor padrao. Comparar `plain_text()` (o valor) punia o
            # importador por fazer a coisa certa — 413 etiquetas "X" num
            # arquivo do Fernando Labes, que na verdade sao "1P/01" e afins.
            conteudo = " ".join(str(e.dxf.get("tag", "") or "").split())
        else:
            try:
                conteudo = " ".join(e.plain_text().split())
            except Exception:
                conteudo = str(e.dxf.get("text", "") or "")
        # O mesmo remendo de acento que o importador aplica (o dwg2dxf parte
        # a string no meio de um caractere de dois bytes). Sem aplicar nos
        # DOIS lados, a auditoria punia o importador por fazer a coisa certa:
        # a referencia ficava com os bytes soltos e o nosso lado, remontado.
        conteudo = remonta_acento(conteudo)
        if not conteudo.strip():
            continue
        # ÂNCORA, não o ponto 10. Num TEXT centralizado ou à direita o ponto
        # 10 é a esquerda-baseline e a âncora de verdade é o ponto 11
        # (`align_point`) — é o que `get_placement()` devolve e o que o
        # importador do NewSIcad guarda. Comparar o ponto 10 do TEXT original
        # contra o `insert` do nosso MTEXT acusava deslocamento de 0,7 em cada
        # cabeçalho de legenda (22 etiquetas no NEWSI-LEG_R07 da Casa Sanchez)
        # que não existe.
        try:
            _al, ancora, _p2 = e.get_placement()
        except Exception:
            ancora = None
        if ancora is None:
            ancora = e.dxf.get("insert", (0, 0, 0))
        try:
            out.append((conteudo, round(float(ancora[0]), 1), round(float(ancora[1]), 1)))
        except Exception:
            pass
    return out


def compara_textos(ref: list, nosso: list) -> dict:
    """Quantas etiquetas do original têm correspondente no nosso, pelo
    conteúdo e pela posição (tolerância de 0,1 unidade de desenho)."""
    falta = collections.Counter(ref)
    falta.subtract(collections.Counter(nosso))
    sumidos = [(c, n) for c, n in falta.items() if n > 0]
    # mesmo conteúdo, posição diferente = saiu do lugar
    pos_ref = collections.Counter(c for c, _x, _y in ref)
    pos_nos = collections.Counter(c for c, _x, _y in nosso)
    conteudo_sumido = [c for c, n in (pos_ref - pos_nos).items()]
    return {
        "no_original": len(ref),
        "no_nosso": len(nosso),
        "sem_correspondente": sum(n for _c, n in sumidos),
        "conteudo_que_sumiu": conteudo_sumido[:15],
        "exemplos_fora_do_lugar": [c for (c, _x, _y), _n in sumidos[:10] if c not in conteudo_sumido][:10],
    }


#: Os dois arquivos em comparação, já abertos. Reler o DXF a cada medição
#: era o que fazia a auditoria estourar 1.500 s em arquivo de 0,6 MB: com 11
#: pranchas, o mesmo arquivo era desmontado mais de vinte vezes (duas
#: medições de segmento, duas de texto e uma de tipos por espaço). São só
#: dois documentos — a referência e o nosso —, então o cache tem tamanho 2.
_ABERTOS: dict[str, object] = {}


def abre(caminho: Path):
    chave = str(caminho)
    doc = _ABERTOS.get(chave)
    if doc is None:
        doc = ezdxf.readfile(Path(chave))
        if len(_ABERTOS) >= 2:
            _ABERTOS.pop(next(iter(_ABERTOS)))
        _ABERTOS[chave] = doc
    return doc


def espacos(caminho: Path) -> list[str]:
    """Nomes dos espaços de desenho do arquivo: "Model" e cada prancha.

    Auditar só o Model deixa de fora um desenho inteiro: no luminotécnico
    da Mauro e Marcia o modelspace está VAZIO e as 1.432 entidades vivem
    todas na prancha. A auditoria reportava "0% de cobertura" — alarme
    falso e ponto cego ao mesmo tempo."""
    doc = abre(caminho)
    nomes = ["Model"]
    for nome in doc.layout_names():
        if nome != "Model" and len(list(doc.layouts.get(nome))):
            nomes.append(nome)
    return nomes


def _entidades_do_espaco(doc, espaco: str):
    """As entidades de um espaço, ou lista vazia se ele não existe nesse
    arquivo. Prancha que existe no original e não no nosso é achado — some
    o selo, a legenda e o enquadramento —, então vira medição de cobertura
    zero naquele espaço, não exceção."""
    if espaco == "Model":
        return doc.modelspace()
    try:
        return doc.layouts.get(espaco)
    except Exception:
        return []


#: Quantos lados um círculo inteiro ganha ao ser achatado. 400 dá ~44 lados,
#: muito acima do que uma grade de 256 células consegue distinguir.
_LADOS_DE_CIRCULO = 400.0


def _tolerancia(e) -> float | None:
    """Distância de achatamento PROPORCIONAL ao tamanho da entidade.

    A do ezdxf é absoluta (0,01 unidade de desenho), o que num arco de raio
    grande vira um número absurdo de pontos: o `2412_AP_102_DEM` da Ricardo e
    Gabriela tem 1.287 arcos na camada "Painéis cortina" com MÉDIA de 30.625
    pontos cada — oito deles com quase um milhão — e o arquivo inteiro gerava
    39,4 milhões de pontos. Era isso que fazia cada processo da varredura
    chegar a 7 GB de RAM e 95 s só para achatar um arquivo de 0,57 MB (e não
    o programa: o NewSIcad abre esse mesmo arquivo em 5,2 s).

    Precisão fina aqui não compra nada: a comparação é numa grade de 256x256
    sobre a prancha, e os dois lados são achatados pela MESMA regra, então a
    medida continua maçã com maçã. `None` deixa o padrão do ezdxf para os
    tipos sem tamanho óbvio.
    """
    tipo = e.dxftype()
    try:
        if tipo in ("ARC", "CIRCLE"):
            return max(float(e.dxf.radius) / _LADOS_DE_CIRCULO, 1e-9)
        if tipo == "ELLIPSE":
            eixo = e.dxf.major_axis
            raio = math.hypot(float(eixo[0]), float(eixo[1]))
            return max(raio / _LADOS_DE_CIRCULO, 1e-9)
    except Exception:
        pass
    return None


def segmentos(caminho: Path, espaco: str = "Model") -> tuple[list[tuple[str, list[tuple[float, float]]]], tuple]:
    """[(camada, [(x, y), ...]), ...] + extensão (minx, miny, maxx, maxy).

    Explode blocos honrando invisibilidade (ver `_visiveis`) e tessela arco,
    círculo, elipse e spline — o mesmo tratamento para os dois lados da
    comparação."""
    saida: list[tuple[str, list[tuple[float, float]]]] = []
    minx = miny = math.inf
    maxx = maxy = -math.inf
    # Uma entidade defeituosa não pode derrubar a medição do arquivo
    # inteiro: o `dwg2dxf` grava spline com contagem de nós errada em
    # alguns arquivos reais, e o achatador do ezdxf levanta no meio.
    for entidade, camada_efetiva in achatado(caminho, espaco):
        if entidade.dxftype() in _TIPOS_DE_TEXTO:
            # Texto entra na travessia (ver `achatado`) mas não na geometria:
            # achatá-lo vira a CAIXA dele, e a nossa, sempre MTEXT, tem
            # largura diferente — acusava "geometria que o original não tem"
            # em toda etiqueta.
            continue
        try:
            primitivas = list(dis.to_primitives([entidade], _tolerancia(entidade)))
        except Exception:
            continue
        for prim in primitivas:
            # `is_empty` e `vertices()` ficam no MESMO try: o ezdxf calcula o
            # caminho da primitiva SOB DEMANDA, então a exceção da spline
            # defeituosa ("15 knot values required, got 13", gravada assim
            # pelo dwg2dxf) estourava na linha do `is_empty`, fora da guarda
            # que protegia só a criação da lista — e derrubava a auditoria do
            # arquivo INTEIRO. Três arquivos da base (Helena & Pedro,
            # Houssein e Fabi) apareciam como "não abre" e abrem sem
            # reclamar no programa.
            try:
                if prim.is_empty:
                    continue
                pontos = [(float(v.x), float(v.y)) for v in prim.vertices()]
            except Exception:
                continue
            if len(pontos) < 1:
                continue
            saida.append((camada_efetiva, pontos))
            for x, y in pontos:
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
    if not math.isfinite(minx):
        return saida, (0.0, 0.0, 0.0, 0.0)
    return saida, (minx, miny, maxx, maxy)


#: Conversões de tipo que são DECISÃO do NewSIcad e não perda: a geometria
#: e a posição continuam as mesmas, só muda como o tipo é gravado.
CONVERSOES_BENIGNAS = {
    "POLYLINE": "LWPOLYLINE",   # polilinha "clássica" vira LWPolyline
    "SOLID": "HATCH",           # SOLID/TRACE vira hachura sólida
    "TRACE": "HATCH",
    "TEXT": "MTEXT",            # a gravação é sempre MTEXT
}

#: Tipos cuja perda SIGNIFICA alguma coisa para o cliente: ele deixa de
#: poder editar/remedir no AutoCAD dele.
PERDA_QUE_IMPORTA = {
    "DIMENSION": "cota vira linha solta — o cliente perde a cota editável",
    "MULTILEADER": "chamada vira geometria solta",
    "ACAD_TABLE": "tabela vira linhas e textos",
    "ATTDEF": "campo preenchível do bloco",
    "ATTRIB": "valor de atributo",
    "LEADER": "chamada vira geometria solta",
    "WIPEOUT": "máscara",
    "IMAGE": "imagem de fundo",
    "VIEWPORT": "janela da prancha",
}


def tipos_desenhaveis(caminho: Path, espaco: str = "Model") -> collections.Counter:
    return collections.Counter(
        e.dxftype() for e, _camada in achatado(caminho, espaco)
        if e.dxftype() not in _TIPOS_DE_TEXTO
    )


def degradacao(ref: collections.Counter, nosso: collections.Counter) -> list[dict]:
    """Tipos que existiam no original e sumiram do nosso, separando o que é
    conversão nossa do que é perda que o cliente sente."""
    out = []
    for tipo, n in ref.items():
        restam = nosso.get(tipo, 0)
        if restam >= n:
            continue
        destino = CONVERSOES_BENIGNAS.get(tipo)
        if destino and nosso.get(destino, 0) >= ref.get(destino, 0):
            continue  # virou o outro tipo, como era de se esperar
        out.append({
            "tipo": tipo,
            "no_original": n,
            "restaram": restam,
            "consequencia": PERDA_QUE_IMPORTA.get(tipo, "tipo não preservado na gravação"),
            "importa": tipo in PERDA_QUE_IMPORTA,
        })
    return sorted(out, key=lambda x: (not x["importa"], -x["no_original"]))


def extensao_por_camada(segs) -> dict[str, tuple]:
    caixas: dict[str, list] = {}
    for camada, pontos in segs:
        c = caixas.setdefault(camada, [math.inf, math.inf, -math.inf, -math.inf])
        for x, y in pontos:
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            c[0], c[1] = min(c[0], x), min(c[1], y)
            c[2], c[3] = max(c[2], x), max(c[3], y)
    return {k: tuple(v) for k, v in caixas.items() if math.isfinite(v[0])}


def ocupacao(segs, caixa, n: int = GRADE) -> set[tuple[int, int]]:
    """Células da grade tocadas por algum segmento. Rasteriza o segmento
    inteiro (não só os vértices), senão uma linha longa marcaria só as
    pontas."""
    minx, miny, maxx, maxy = caixa
    largura = max(maxx - minx, 1e-9)
    altura = max(maxy - miny, 1e-9)
    celulas: set[tuple[int, int]] = set()

    def celula(x, y):
        return (
            min(n - 1, max(0, int((x - minx) / largura * n))),
            min(n - 1, max(0, int((y - miny) / altura * n))),
        )

    # A célula de cada vértice é calculada UMA vez (cada ponto é fim de um
    # trecho e começo do seguinte), e trecho que começa e termina na mesma
    # célula não é interpolado. Sem as duas coisas, uma planta com curva
    # tesselada vira milhões de passos de interpolação para marcar sempre a
    # mesma célula: era o que fazia a auditoria passar de 1.500 s no
    # 2412_AP_101_LAY (12.519 polilinhas achatadas).
    for _camada, pontos in segs:
        limpos = [(x, y) for x, y in pontos if math.isfinite(x) and math.isfinite(y)]
        if not limpos:
            continue
        cells = [celula(x, y) for x, y in limpos]
        if len(cells) == 1:
            celulas.add(cells[0])
            continue
        for indice, (c1, c2) in enumerate(zip(cells, cells[1:])):
            if c1 == c2:
                celulas.add(c1)
                continue
            passos = max(abs(c2[0] - c1[0]), abs(c2[1] - c1[1]))
            if passos > 4 * n:  # segmento absurdo: marca só as pontas
                celulas.add(c1)
                celulas.add(c2)
                continue
            x1, y1 = limpos[indice]
            x2, y2 = limpos[indice + 1]
            for i in range(passos + 1):
                t = i / passos
                celulas.add(celula(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return celulas


def salva_mapa(ref: set, nosso: set, destino: Path, n: int = GRADE) -> None:
    """PNG do diff: branco = igual, VERMELHO = só no original (sumiu),
    AZUL = só no nosso (apareceu onde não devia)."""
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.new("RGB", (n, n), (20, 20, 20))
    px = img.load()
    for (cx, cy) in ref & nosso:
        px[cx, n - 1 - cy] = (210, 210, 210)
    for (cx, cy) in ref - nosso:
        px[cx, n - 1 - cy] = (220, 40, 40)
    for (cx, cy) in nosso - ref:
        px[cx, n - 1 - cy] = (60, 120, 255)
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.resize((n * 3, n * 3), Image.NEAREST).save(destino)


# --------------------------------------------------------------------- #
def audita(caminho: Path, pasta_mapas: Path | None) -> dict:
    reg: dict = {"arquivo": caminho.name, "pasta": caminho.parent.name,
                 "mb": round(caminho.stat().st_size / 1024 / 1024, 2)}
    t0 = time.perf_counter()
    try:
        # `ignore_cleanup_errors`: no Windows a pasta temporaria as vezes
        # nao pode ser apagada na hora (antivirus ou o proprio leitor ainda
        # com o arquivo aberto), e o erro de LIMPEZA derrubava a operacao
        # INTEIRA depois dela ja ter dado certo — o projetista via
        # "Acesso negado" num .dwg que abriu sem problema. O temporario e
        # do sistema: sobrar uma pasta la e inofensivo perto disso.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            # 1) verdade: o arquivo do cliente como DXF
            if caminho.suffix.lower() == ".dwg":
                ferramenta = dwg_bridge._tool_path("dwg2dxf")
                tmp = dwg_bridge.pasta_que_a_ferramenta_enxerga(tmp)
                ref_dxf = tmp / "ref.dxf"
                # Mesmo desvio do programa: nome com acento (28 arquivos da
                # base) chega truncado na ferramenta e "nao existe".
                entrada = dwg_bridge.entrada_que_a_ferramenta_abre(caminho, tmp)
                dwg_bridge._run([ferramenta, "-o", str(ref_dxf), "-y", str(entrada)])
                dwg_bridge._sanitize_dxf_file(ref_dxf)
            else:
                ref_dxf = caminho

            # 2) nosso: lido e gravado de volta pelo NewSIcad
            doc, skipped = load_dxf(ref_dxf)
            reg["entidades"] = len(doc.entities)
            reg["descartadas"] = dict(getattr(skipped, "by_type", {}) or {})
            nosso_dxf = tmp / "nosso.dxf"
            save_dxf(doc, nosso_dxf)

            # 3) mede CADA espaço de desenho (Model e cada prancha),
            #    porque há arquivo cujo desenho inteiro vive na prancha.
            por_espaco = []
            pranchas_perdidas: list[str] = []
            deg_total: list[dict] = []
            for espaco in espacos(ref_dxf):
                segs_ref, caixa_ref = segmentos(ref_dxf, espaco)
                if not segs_ref:
                    continue
                if espaco != "Model" and espaco not in espacos(nosso_dxf):
                    pranchas_perdidas.append(espaco)
                segs_nos, _caixa_nos = segmentos(nosso_dxf, espaco)
                diag_e = math.hypot(caixa_ref[2] - caixa_ref[0], caixa_ref[3] - caixa_ref[1]) or 1.0
                oc_r = ocupacao(segs_ref, caixa_ref)
                oc_n = ocupacao(segs_nos, caixa_ref)
                t = compara_textos(textos(ref_dxf, espaco), textos(nosso_dxf, espaco))
                deg_total.extend(
                    degradacao(tipos_desenhaveis(ref_dxf, espaco), tipos_desenhaveis(nosso_dxf, espaco))
                )
                cx_r = extensao_por_camada(segs_ref)
                cx_n = extensao_por_camada(segs_nos)
                sumidas = [c for c in cx_r if c not in cx_n]
                fora = []
                for camada, cref in cx_r.items():
                    cnos = cx_n.get(camada)
                    if cnos is None:
                        continue
                    d = max(abs(a - b) for a, b in zip(cref, cnos))
                    if d / diag_e > TOL_EXTENSAO:
                        fora.append({"camada": camada, "desvio_rel": round(d / diag_e, 4)})
                por_espaco.append({
                    "espaco": espaco,
                    "segmentos_ref": len(segs_ref),
                    "segmentos_nosso": len(segs_nos),
                    "cobertura": round(len(oc_r & oc_n) / max(len(oc_r), 1), 4),
                    "celulas_ref": len(oc_r),
                    "celulas_sobraram": len(oc_n - oc_r),
                    "camadas_sumidas": sumidas[:10],
                    "camadas_fora_do_lugar": sorted(fora, key=lambda x: -x["desvio_rel"])[:10],
                    "textos": t,
                })
                if pasta_mapas is not None and espaco == por_espaco[0]["espaco"]:
                    salva_mapa(oc_r, oc_n, pasta_mapas / f"{caminho.parent.name}__{caminho.stem}.png")
            deg = {d["tipo"]: d for d in deg_total}
            deg = sorted(deg.values(), key=lambda x: (not x["importa"], -x["no_original"]))

        if not por_espaco:
            reg["status"] = "ok"
            reg["alertas"] = ["arquivo sem geometria desenhável"]
            reg["espacos"] = []
            reg["segundos"] = round(time.perf_counter() - t0, 1)
            return reg

        reg["espacos"] = por_espaco
        pior = min(por_espaco, key=lambda x: x["cobertura"])
        reg["cobertura"] = pior["cobertura"]
        reg["espaco_pior"] = pior["espaco"]
        reg["segmentos_ref"] = sum(x["segmentos_ref"] for x in por_espaco)
        reg["segmentos_nosso"] = sum(x["segmentos_nosso"] for x in por_espaco)
        reg["camadas_sumidas"] = pior["camadas_sumidas"]
        reg["camadas_fora_do_lugar"] = pior["camadas_fora_do_lugar"]
        reg["textos"] = {
            "no_original": sum(x["textos"]["no_original"] for x in por_espaco),
            "no_nosso": sum(x["textos"]["no_nosso"] for x in por_espaco),
            "sem_correspondente": sum(x["textos"]["sem_correspondente"] for x in por_espaco),
            "conteudo_que_sumiu": [c for x in por_espaco for c in x["textos"]["conteudo_que_sumiu"]][:15],
        }
        reg["degradacao_de_tipo"] = deg
        reg["pranchas_perdidas"] = pranchas_perdidas
        alertas = []
        if pranchas_perdidas:
            alertas.append(f"PRANCHA PERDIDA AO GRAVAR: {pranchas_perdidas}")
        txt = reg["textos"]
        if txt["sem_correspondente"]:
            alertas.append(
                f"{txt['sem_correspondente']} de {txt['no_original']} etiquetas sem correspondente"
                + (f" (ex.: {txt['conteudo_que_sumiu'][:3]})" if txt["conteudo_que_sumiu"] else " — mesmas palavras, posição diferente")
            )
        for d in deg:
            if d["importa"]:
                alertas.append(f"{d['no_original']}x {d['tipo']}: {d['consequencia']}")
        if reg["cobertura"] < 0.97:
            alertas.append(
                f"cobertura {reg['cobertura']*100:.1f}% em '{reg['espaco_pior']}' — some desenho"
            )
        sobrou = sum(x["celulas_sobraram"] for x in por_espaco)
        celulas = sum(x["celulas_ref"] for x in por_espaco)
        reg["celulas_ref"] = celulas
        reg["celulas_sobraram"] = sobrou
        if sobrou > 0.02 * max(celulas, 1):
            alertas.append(f"{sobrou} células com geometria que o original não tem")
        if reg["camadas_sumidas"]:
            alertas.append(
                f"{len(reg['camadas_sumidas'])} camada(s) sumiram em '{reg['espaco_pior']}': "
                f"{reg['camadas_sumidas'][:3]}"
            )
        if reg["camadas_fora_do_lugar"]:
            pc = reg["camadas_fora_do_lugar"][0]
            alertas.append(f"camada '{pc['camada']}' fora do lugar ({pc['desvio_rel']*100:.1f}%)")
        reg["alertas"] = alertas
        reg["status"] = "ok"
    except Exception as exc:
        reg["status"] = "FALHOU"
        reg["erro"] = f"{type(exc).__name__}: {exc}"
        reg["traceback"] = traceback.format_exc()[-800:]
        reg["alertas"] = ["FALHOU NA AUDITORIA"]
    reg["segundos"] = round(time.perf_counter() - t0, 1)
    return reg


def audita_isolado(caminho: Path, pasta_mapas: Path | None, tempo_limite: int) -> dict:
    """Audita o arquivo num processo separado. Travamento duro ou demora
    viram um registro de falha em vez de interromper a varredura."""
    cmd = [sys.executable, str(Path(__file__).resolve()), str(caminho), "--um-arquivo"]
    if pasta_mapas is not None:
        cmd += ["--mapas", str(pasta_mapas)]
    base = {"arquivo": caminho.name, "pasta": caminho.parent.name,
            "mb": round(caminho.stat().st_size / 1024 / 1024, 2)}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=tempo_limite)
    except subprocess.TimeoutExpired:
        return {**base, "status": "FALHOU", "erro": f"passou de {tempo_limite}s",
                "alertas": [f"NAO TERMINOU EM {tempo_limite}s"]}
    marca = "<<<JSON>>>"
    for linha in (r.stdout or "").splitlines():
        if linha.startswith(marca):
            try:
                return json.loads(linha[len(marca):])
            except Exception:
                break
    erro = (r.stderr or "").strip().splitlines()
    return {**base, "status": "FALHOU",
            "erro": f"processo encerrou com codigo {r.returncode}: " + (erro[-1] if erro else "sem saida"),
            "alertas": ["O PROCESSO MORREU AUDITANDO ESTE ARQUIVO"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("alvo", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("auditoria.json"))
    ap.add_argument("--mapas", type=Path, default=None)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--um-arquivo", action="store_true",
                    help="uso interno: audita um arquivo e imprime o JSON")
    ap.add_argument("--trabalhadores", type=int, default=1,
                    help="quantos arquivos auditar ao mesmo tempo")
    ap.add_argument("--tempo-limite", type=int, default=600,
                    help="segundos por arquivo antes de desistir dele")
    args = ap.parse_args()

    if args.um_arquivo:
        # Modo filho: um arquivo, resultado no stdout. É assim que a
        # varredura sobrevive a um travamento duro — ezdxf e o achatador
        # derrubaram o processo inteiro no arquivo 70 de 218 na primeira
        # tentativa, sem nem deixar traceback.
        print("<<<JSON>>>" + json.dumps(audita(args.alvo, args.mapas), ensure_ascii=False))
        return

    if args.alvo.is_file():
        arquivos = [args.alvo]
    else:
        arquivos = sorted(
            [p for p in args.alvo.rglob("*") if p.suffix.lower() in (".dwg", ".dxf")],
            key=lambda p: p.stat().st_size,
        )
    if args.limite:
        arquivos = arquivos[: args.limite]

    feitos: dict[str, dict] = {}
    if args.saida.exists():
        try:
            feitos = {r["arquivo"] + "|" + r["pasta"]: r for r in json.loads(args.saida.read_text(encoding="utf-8"))}
        except Exception:
            feitos = {}

    pendentes = [p for p in arquivos if p.name + "|" + p.parent.name not in feitos]
    print(f"{len(arquivos)} arquivos | {len(feitos)} auditados antes |"
          f" {len(pendentes)} na fila | {args.trabalhadores} por vez", flush=True)

    trava = threading.Lock()
    total = len(arquivos)
    pronto = len(feitos)

    def conta(caminho: Path, reg: dict) -> None:
        # So quem tem a trava imprime e grava: um JSON pego no meio da
        # escrita e o que da "Expecting value" quando a gente le o
        # relatorio com a varredura ainda rodando.
        nonlocal pronto
        with trava:
            pronto += 1
            feitos[caminho.name + "|" + caminho.parent.name] = reg
            mb = caminho.stat().st_size / 1024 / 1024
            print(f"[{pronto}/{total}] {caminho.parent.name} / {caminho.name} ({mb:.1f} MB)", flush=True)
            if reg["status"] == "FALHOU":
                print(f"    FALHOU: {reg['erro'][:140]}", flush=True)
            else:
                print(f"    cobertura {reg['cobertura']*100:.1f}% | {reg['segmentos_ref']}"
                      f" -> {reg['segmentos_nosso']} seg | {reg['segundos']}s", flush=True)
                for a in reg["alertas"]:
                    print(f"       ! {a}", flush=True)
            temp = args.saida.with_suffix(".parcial")
            temp.write_text(json.dumps(list(feitos.values()), ensure_ascii=False, indent=1),
                            encoding="utf-8")
            temp.replace(args.saida)

    if args.trabalhadores <= 1:
        for caminho in pendentes:
            conta(caminho, audita_isolado(caminho, args.mapas, args.tempo_limite))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.trabalhadores) as pool:
            futuros = {pool.submit(audita_isolado, c, args.mapas, args.tempo_limite): c
                       for c in pendentes}
            for f in concurrent.futures.as_completed(futuros):
                caminho = futuros[f]
                try:
                    conta(caminho, f.result())
                except Exception as exc:  # o pool nao pode morrer por um arquivo
                    conta(caminho, {"arquivo": caminho.name, "pasta": caminho.parent.name,
                                    "status": "FALHOU", "erro": f"{type(exc).__name__}: {exc}",
                                    "alertas": ["ERRO NO PROPRIO AUDITOR"]})

    print(f"\nrelatório: {args.saida.resolve()}")


if __name__ == "__main__":
    main()
