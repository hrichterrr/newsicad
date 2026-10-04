"""Transforma o JSON de `tools/auditoria_projeto.py` na fila de trabalho.

A ordenação é por QUANTOS PROJETOS REAIS cada defeito atinge, não pela
gravidade que a gente imagina nem por quem reclamou mais alto. É o que
responde "o que consertar primeiro" sem depender do vai e vem com a equipe.

LEITURA DOS NÚMEROS — a lição de nove falsos positivos:

    Cobertura sozinha NÃO é veredito. Ela mede quantas células da grade de
    256x256 que o original ocupa o nosso desenho também ocupa, e a grade é
    normalizada pela extensão do ARQUIVO INTEIRO. Duas formas cheias longe
    do desenho esticam a caixa e fazem o desenho real caber num canto: o
    `BASE_XREF_LEE` do Joe Lee aparecia com "4% de cobertura" tendo 4.323
    dos 4.327 segmentos presentes. Por isso toda linha de cobertura aqui sai
    junto da RAZÃO DE SEGMENTOS, e os casos em que as duas discordam saem
    separados — são medição, não perda.

Uso:

    python tools/relatorio_auditoria.py auditoria.json [--top 15]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

#: Abaixo disto a cobertura merece olhar; acima é ruído de rasterização.
COBERTURA_SUSPEITA = 0.99
#: Se a razão de segmentos está acima disto, o desenho está todo lá e a
#: cobertura baixa é distorção da caixa de medição.
SEGMENTOS_INTACTOS = 0.98


def barra(fracao: float, largura: int = 22) -> str:
    cheio = max(0, min(largura, int(round(fracao * largura))))
    return "█" * cheio + "·" * (largura - cheio)


def razao_de_segmentos(r: dict) -> float:
    ref = r.get("segmentos_ref") or 0
    return (r.get("segmentos_nosso") or 0) / ref if ref else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("relatorio", type=Path, nargs="?", default=Path("auditoria.json"))
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    regs = json.loads(args.relatorio.read_text(encoding="utf-8"))
    ok = [r for r in regs if r.get("status") == "ok"]
    falhou = [r for r in regs if r.get("status") != "ok"]
    clientes = {r.get("pasta") for r in regs}

    print("=" * 78)
    print(f"AUDITORIA DA BASE — {len(regs)} arquivos de {len(clientes)} clientes")
    print("=" * 78)

    if ok:
        limpos = [r for r in ok if not r.get("alertas")]
        print(f"  auditados: {len(ok)}   |   não auditados: {len(falhou)}")
        print(f"  SEM NENHUM ALERTA: {len(limpos)} de {len(ok)} ({100*len(limpos)/len(ok):.0f}%)")
        cob = sorted(r.get("cobertura", 0) for r in ok)
        seg = sorted(razao_de_segmentos(r) for r in ok)
        print(f"  cobertura:  mediana {cob[len(cob)//2]*100:5.1f}%   pior {cob[0]*100:5.1f}%")
        print(f"  segmentos:  mediana {seg[len(seg)//2]*100:5.1f}%   pior {seg[0]*100:5.1f}%"
              "   <- é esta que diz se SUMIU desenho")

    # ------------------------------------------------------------------ #
    # 1) NÃO ABRE — a única classe que impede o projetista de trabalhar
    # ------------------------------------------------------------------ #
    print("\n" + "-" * 78)
    if falhou:
        print(f"1) NÃO ABRE — {len(falhou)} arquivo(s). É a classe mais grave.")
        print("-" * 78)
        por_erro = collections.defaultdict(list)
        for r in falhou:
            por_erro[(r.get("erro") or "?").split(":")[0][:58]].append(r)
        for erro, lista in sorted(por_erro.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(lista):4d}x  {erro}")
            for r in lista[:4]:
                print(f"          · {r.get('pasta')} / {r.get('arquivo')} ({r.get('mb')} MB)")
            if len(lista) > 4:
                print(f"          · (+{len(lista) - 4} outros)")
    else:
        print(f"1) NÃO ABRE — nenhum. Os {len(ok)} arquivos auditados abrem.")
        print("-" * 78)

    # ------------------------------------------------------------------ #
    # 2) O QUE O CLIENTE PERDE NO ARQUIVO QUE RECEBE
    # ------------------------------------------------------------------ #
    atinge = collections.Counter()
    total = collections.Counter()
    consequencia: dict[str, str] = {}
    for r in ok:
        for d in r.get("degradacao_de_tipo") or []:
            if not d.get("importa"):
                continue
            atinge[d["tipo"]] += 1
            total[d["tipo"]] += d["no_original"]
            consequencia[d["tipo"]] = d["consequencia"]
    print("\n" + "-" * 78)
    print("2) O QUE O CLIENTE PERDE NO ARQUIVO QUE RECEBE")
    print("-" * 78)
    if atinge:
        for tipo, n_arq in atinge.most_common(args.top):
            print(f"  {barra(n_arq / max(len(ok), 1))}  {tipo:<13} {n_arq:>3} projetos, "
                  f"{total[tipo]:>6} entidades")
            print(f"  {' ' * 22}  {consequencia.get(tipo, '')}")
    else:
        print("  Nada: todo tipo que entra volta como o mesmo tipo.")

    # ------------------------------------------------------------------ #
    # 3) ENTIDADE DESCARTADA NA LEITURA (some da tela E do arquivo)
    # ------------------------------------------------------------------ #
    descartes = collections.Counter()
    arquivos_com = collections.Counter()
    for r in ok:
        for tipo, n in (r.get("descartadas") or {}).items():
            descartes[tipo] += n
            arquivos_com[tipo] += 1
    print("\n" + "-" * 78)
    print("3) TIPO QUE O PROGRAMA NÃO LÊ — some da tela e do arquivo entregue")
    print("-" * 78)
    if descartes:
        for tipo, n in descartes.most_common(args.top):
            print(f"  {barra(arquivos_com[tipo] / max(len(ok), 1))}  {tipo:<28} "
                  f"{arquivos_com[tipo]:>3} projetos, {n:>6} entidades")
    else:
        print("  Nada descartado em nenhum arquivo.")

    # ------------------------------------------------------------------ #
    # 4) SOME DESENHO — cobertura SEMPRE junto da razão de segmentos
    # ------------------------------------------------------------------ #
    suspeitos = sorted(
        [r for r in ok if r.get("cobertura", 1) < COBERTURA_SUSPEITA],
        key=lambda r: r.get("cobertura", 1),
    )
    perda_real = [r for r in suspeitos if razao_de_segmentos(r) < SEGMENTOS_INTACTOS]
    so_medicao = [r for r in suspeitos if razao_de_segmentos(r) >= SEGMENTOS_INTACTOS]

    print("\n" + "-" * 78)
    print(f"4) SOME DESENHO — {len(perda_real)} arquivo(s) com perda REAL de segmento")
    print("-" * 78)
    if perda_real:
        for r in perda_real[: args.top]:
            print(f"  cobertura {r['cobertura']*100:5.1f}% | segmentos "
                  f"{razao_de_segmentos(r)*100:5.1f}% "
                  f"({r.get('segmentos_ref')} -> {r.get('segmentos_nosso')})")
            print(f"       {r['pasta']} / {r['arquivo']}  [pior espaço: {r.get('espaco_pior')}]")
            if r.get("descartadas"):
                print(f"       descartadas: {r['descartadas']}")
            if r.get("camadas_sumidas"):
                print(f"       camadas sumidas: {r['camadas_sumidas'][:4]}")
    else:
        print("  Nenhum arquivo perde segmento de forma significativa.")

    if so_medicao:
        print(f"\n  ({len(so_medicao)} arquivo(s) com cobertura baixa e segmentos INTACTOS —")
        print("   caixa de medição esticada por geometria distante, não perda de")
        print("   desenho. Ver o cabeçalho deste arquivo.)")
        for r in so_medicao[:5]:
            print(f"     {r['cobertura']*100:5.1f}% cob / {razao_de_segmentos(r)*100:5.1f}% seg  "
                  f"{r['pasta']} / {r['arquivo']}")

    # ------------------------------------------------------------------ #
    # 5) PRANCHA PERDIDA
    # ------------------------------------------------------------------ #
    sem_prancha = [r for r in ok if r.get("pranchas_perdidas")]
    if sem_prancha:
        print("\n" + "-" * 78)
        print(f"5) PRANCHA PERDIDA AO GRAVAR — {len(sem_prancha)} arquivo(s)")
        print("-" * 78)
        for r in sem_prancha[: args.top]:
            print(f"  {r['pasta']} / {r['arquivo']}: {r['pranchas_perdidas'][:4]}")

    # ------------------------------------------------------------------ #
    # 6) ETIQUETA SEM CORRESPONDENTE
    # ------------------------------------------------------------------ #
    etiquetas = sorted(
        [r for r in ok if (r.get("textos") or {}).get("sem_correspondente")],
        key=lambda r: -(r["textos"]["sem_correspondente"]),
    )
    if etiquetas:
        print("\n" + "-" * 78)
        print(f"6) ETIQUETA SEM CORRESPONDENTE — {len(etiquetas)} arquivo(s)")
        print("   (conferir UM caso antes de tratar como defeito: já houve etiqueta")
        print("    acusada em arquivo 100% íntegro, e etiqueta cujo defeito estava")
        print("    no ORIGINAL, não no nosso)")
        print("-" * 78)
        for r in etiquetas[: args.top]:
            t = r["textos"]
            print(f"  {t['sem_correspondente']:>4} de {t['no_original']:<5} "
                  f"{r['pasta']} / {r['arquivo']}")
            for c in (t.get("conteudo_que_sumiu") or [])[:1]:
                print(f"        sumiu: {c[:70]!r}")

    # ------------------------------------------------------------------ #
    # 7) POR CLIENTE — é assim que a base é pensada no dia a dia
    # ------------------------------------------------------------------ #
    por_cliente: dict[str, list] = collections.defaultdict(list)
    for r in regs:
        por_cliente[r.get("pasta", "?")].append(r)
    problematicos = sorted(
        ((c, l) for c, l in por_cliente.items()
         if any(x.get("status") != "ok" or x.get("alertas") for x in l)),
        key=lambda cl: -sum(1 for x in cl[1] if x.get("status") != "ok" or x.get("alertas")),
    )
    print("\n" + "-" * 78)
    print(f"7) POR CLIENTE — {len(problematicos)} de {len(por_cliente)} com algum alerta")
    print("-" * 78)
    for cliente, lista in problematicos[: args.top]:
        com_alerta = sum(1 for x in lista if x.get("status") != "ok" or x.get("alertas"))
        nao_abre = sum(1 for x in lista if x.get("status") != "ok")
        marca = f"   ({nao_abre} não abre)" if nao_abre else ""
        print(f"  {com_alerta:>2} de {len(lista):>2} arquivos   {cliente}{marca}")

    # ------------------------------------------------------------------ #
    lentos = sorted(ok, key=lambda r: -r.get("segundos", 0))[:5]
    print("\n" + "-" * 78)
    print("8) MAIS DEMORADOS NA AUDITORIA — NÃO é o tempo do programa: a")
    print("   auditoria abre, grava E mede os dois lados do arquivo")
    print("-" * 78)
    for r in lentos:
        print(f"  {r.get('segundos', 0):6.1f}s  {r.get('mb', 0):6.1f} MB  "
              f"{r['pasta']} / {r['arquivo']}")

    print("\n" + "=" * 78)
    print("ONDE OLHAR PRIMEIRO: o bloco 1 (não abre) e o 3 (tipo não lido) são os")
    print("que o projetista sente na tela. O 2 é o que o cliente perde no arquivo")
    print("que recebe. O 4 só conta como perda quando a razão de segmentos cai.")


if __name__ == "__main__":
    main()
