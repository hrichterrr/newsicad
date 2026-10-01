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
import subprocess
import json
import math
import sys
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

from newsicad.io import dwg_bridge  # noqa: E402
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
CAMADAS_NAO_PLOTADAS = {"defpoints", "viewport"}

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


def _visiveis(entidades, profundidade: int = 0):
    """Expande blocos honrando invisibilidade e camada não-plotada — o que o
    AutoCAD de fato desenha, que é o único referencial honesto."""
    for e in entidades:
        if _invisivel(e):
            continue
        try:
            camada = (e.dxf.get("layer", "0") or "0").strip().lower()
        except Exception:
            camada = "0"
        if camada in CAMADAS_NAO_PLOTADAS:
            continue
        if e.dxftype() in _TIPOS_DE_TEXTO:
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
            yield from _visiveis(filhos, profundidade + 1)
            continue
        yield e


def textos(caminho: Path) -> list[tuple[str, float, float]]:
    """(conteúdo, x, y) de cada texto desenhável, com blocos e anotações já
    expandidos — para comparar etiqueta por etiqueta, por posição."""
    doc = ezdxf.readfile(caminho)
    out: list[tuple[str, float, float]] = []

    def anda(entidades, prof=0):
        for e in entidades:
            if _invisivel(e):
                continue
            try:
                camada = (e.dxf.get("layer", "0") or "0").strip().lower()
            except Exception:
                camada = "0"
            if camada in CAMADAS_NAO_PLOTADAS:
                continue
            t = e.dxftype()
            if t in _TIPOS_DE_TEXTO:
                try:
                    conteudo = " ".join(e.plain_text().split())
                except Exception:
                    conteudo = str(e.dxf.get("text", "") or "")
                if not conteudo.strip():
                    continue
                try:
                    p = e.dxf.get("insert", None) or e.dxf.get("align_point", (0, 0, 0))
                    out.append((conteudo, round(float(p[0]), 1), round(float(p[1]), 1)))
                except Exception:
                    pass
                continue
            if t in _EXPANDIR and prof < _MAX_ANINHAMENTO:
                try:
                    anda(list(e.virtual_entities()), prof + 1)
                except Exception:
                    pass
    anda(doc.modelspace())
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


def segmentos(caminho: Path) -> tuple[list[tuple[str, list[tuple[float, float]]]], tuple]:
    """[(camada, [(x, y), ...]), ...] + extensão (minx, miny, maxx, maxy).

    Explode blocos honrando invisibilidade (ver `_visiveis`) e tessela arco,
    círculo, elipse e spline — o mesmo tratamento para os dois lados da
    comparação."""
    doc = ezdxf.readfile(caminho)
    msp = doc.modelspace()
    saida: list[tuple[str, list[tuple[float, float]]]] = []
    minx = miny = math.inf
    maxx = maxy = -math.inf
    # Uma entidade defeituosa não pode derrubar a medição do arquivo
    # inteiro: o `dwg2dxf` grava spline com contagem de nós errada em
    # alguns arquivos reais, e o achatador do ezdxf levanta no meio.
    for entidade in _visiveis(msp):
        try:
            primitivas = list(dis.to_primitives([entidade]))
        except Exception:
            continue
        for prim in primitivas:
            if prim.is_empty:
                continue
            try:
                pontos = [(float(v.x), float(v.y)) for v in prim.vertices()]
            except Exception:
                continue
            if len(pontos) < 1:
                continue
            camada = getattr(prim.entity.dxf, "layer", "0") or "0"
            saida.append((camada, pontos))
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


def tipos_desenhaveis(caminho: Path) -> collections.Counter:
    doc = ezdxf.readfile(caminho)
    return collections.Counter(e.dxftype() for e in _visiveis(doc.modelspace()))


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

    for _camada, pontos in segs:
        if len(pontos) == 1:
            x, y = pontos[0]
            if math.isfinite(x) and math.isfinite(y):
                celulas.add(celula(x, y))
            continue
        for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                continue
            c1, c2 = celula(x1, y1), celula(x2, y2)
            passos = max(abs(c2[0] - c1[0]), abs(c2[1] - c1[1]), 1)
            if passos > 4 * n:  # segmento absurdo: marca só as pontas
                celulas.add(c1)
                celulas.add(c2)
                continue
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
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # 1) verdade: o arquivo do cliente como DXF
            if caminho.suffix.lower() == ".dwg":
                ferramenta = dwg_bridge._tool_path("dwg2dxf")
                ref_dxf = tmp / "ref.dxf"
                dwg_bridge._run([ferramenta, "-o", str(ref_dxf), "-y", str(caminho)])
                dwg_bridge._sanitize_dxf_file(ref_dxf)
            else:
                ref_dxf = caminho

            # 2) nosso: lido e gravado de volta pelo NewSIcad
            doc, skipped = load_dxf(ref_dxf)
            reg["entidades"] = len(doc.entities)
            reg["descartadas"] = dict(getattr(skipped, "by_type", {}) or {})
            nosso_dxf = tmp / "nosso.dxf"
            save_dxf(doc, nosso_dxf)

            # 3) achata os dois com o mesmo código
            segs_ref, caixa_ref = segmentos(ref_dxf)
            segs_nos, caixa_nos = segmentos(nosso_dxf)
            deg = degradacao(tipos_desenhaveis(ref_dxf), tipos_desenhaveis(nosso_dxf))
            txt = compara_textos(textos(ref_dxf), textos(nosso_dxf))

        reg["segmentos_ref"] = len(segs_ref)
        reg["segmentos_nosso"] = len(segs_nos)
        reg["extensao_ref"] = [round(v, 3) for v in caixa_ref]
        reg["extensao_nosso"] = [round(v, 3) for v in caixa_nos]

        diag = math.hypot(caixa_ref[2] - caixa_ref[0], caixa_ref[3] - caixa_ref[1]) or 1.0
        desloc = max(abs(a - b) for a, b in zip(caixa_ref, caixa_nos))
        reg["desvio_extensao_rel"] = round(desloc / diag, 5)

        # grade de ocupação sobre a extensão do ORIGINAL
        oc_ref = ocupacao(segs_ref, caixa_ref)
        oc_nos = ocupacao(segs_nos, caixa_ref)
        sumiu = oc_ref - oc_nos
        sobrou = oc_nos - oc_ref
        reg["celulas_ref"] = len(oc_ref)
        reg["celulas_sumiram"] = len(sumiu)
        reg["celulas_sobraram"] = len(sobrou)
        reg["cobertura"] = round(len(oc_ref & oc_nos) / max(len(oc_ref), 1), 4)
        if pasta_mapas is not None:
            destino = pasta_mapas / f"{caminho.parent.name}__{caminho.stem}.png"
            salva_mapa(oc_ref, oc_nos, destino)
            reg["mapa"] = str(destino)

        # extensão por camada: pega "a legenda explodiu"
        cx_ref = extensao_por_camada(segs_ref)
        cx_nos = extensao_por_camada(segs_nos)
        estouradas = []
        sumidas = []
        for camada, cref in cx_ref.items():
            cnos = cx_nos.get(camada)
            if cnos is None:
                sumidas.append(camada)
                continue
            d = max(abs(a - b) for a, b in zip(cref, cnos))
            if d / diag > TOL_EXTENSAO:
                estouradas.append({"camada": camada, "desvio_rel": round(d / diag, 4)})
        reg["camadas_sumidas"] = sumidas[:20]
        reg["camadas_fora_do_lugar"] = sorted(estouradas, key=lambda x: -x["desvio_rel"])[:20]

        # contagem de segmentos por camada: pega "sumiu linha"
        n_ref = collections.Counter(c for c, _ in segs_ref)
        n_nos = collections.Counter(c for c, _ in segs_nos)
        perdas = []
        for camada, n in n_ref.items():
            falta = n - n_nos.get(camada, 0)
            if falta > 0 and falta / n > 0.02:
                perdas.append({"camada": camada, "perdidos": falta, "de": n,
                               "pct": round(100 * falta / n, 1)})
        reg["camadas_com_perda"] = sorted(perdas, key=lambda x: -x["perdidos"])[:20]

        reg["degradacao_de_tipo"] = deg
        reg["textos"] = txt
        alertas = []
        if txt["sem_correspondente"]:
            alertas.append(
                f"{txt['sem_correspondente']} de {txt['no_original']} etiquetas sem correspondente"
                + (f" (ex.: {txt['conteudo_que_sumiu'][:3]})" if txt["conteudo_que_sumiu"] else " — mesmas palavras, posição diferente")
            )
        for d in deg:
            if d["importa"]:
                alertas.append(f"{d['no_original']}x {d['tipo']}: {d['consequencia']}")
        if reg["cobertura"] < 0.97:
            alertas.append(f"cobertura {reg['cobertura']*100:.1f}% — some desenho")
        if reg["desvio_extensao_rel"] > TOL_EXTENSAO:
            alertas.append(f"extensão mudou {reg['desvio_extensao_rel']*100:.1f}% — algo saiu do lugar")
        if reg["celulas_sobraram"] > 0.02 * max(reg["celulas_ref"], 1):
            alertas.append(f"{reg['celulas_sobraram']} células com geometria que o original não tem")
        if sumidas:
            alertas.append(f"{len(sumidas)} camada(s) sumiram inteiras")
        if reg["camadas_fora_do_lugar"]:
            pior = reg["camadas_fora_do_lugar"][0]
            alertas.append(f"camada '{pior['camada']}' fora do lugar ({pior['desvio_rel']*100:.1f}%)")
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

    print(f"{len(arquivos)} arquivos | {len(feitos)} já auditados", flush=True)
    for i, caminho in enumerate(arquivos, 1):
        chave = caminho.name + "|" + caminho.parent.name
        if chave in feitos:
            continue
        print(f"[{i}/{len(arquivos)}] {caminho.parent.name} / {caminho.name} ({caminho.stat().st_size/1024/1024:.1f} MB)", flush=True)
        reg = audita_isolado(caminho, args.mapas, args.tempo_limite)
        feitos[chave] = reg
        if reg["status"] == "FALHOU":
            print(f"    FALHOU: {reg['erro'][:140]}", flush=True)
        else:
            print(f"    cobertura {reg['cobertura']*100:.1f}% | {reg['segmentos_ref']} -> {reg['segmentos_nosso']} seg | {reg['segundos']}s", flush=True)
            for a in reg["alertas"]:
                print(f"       ! {a}", flush=True)
        args.saida.write_text(json.dumps(list(feitos.values()), ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nrelatório: {args.saida.resolve()}")


if __name__ == "__main__":
    main()
