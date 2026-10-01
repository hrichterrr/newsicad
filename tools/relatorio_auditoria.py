"""Transforma o JSON de `tools/auditoria_projeto.py` na fila de trabalho.

A ordenação é por QUANTOS PROJETOS REAIS cada defeito atinge, não pela
gravidade que a gente imagina nem por quem reclamou mais alto. É o que
responde "o que consertar primeiro" sem depender do vai e vem com a equipe.

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


def barra(fracao: float, largura: int = 24) -> str:
    cheio = int(round(fracao * largura))
    return "█" * cheio + "·" * (largura - cheio)


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
    print(f"  auditados: {len(ok)}   |   não auditados: {len(falhou)}")

    if ok:
        limpos = [r for r in ok if not r.get("alertas")]
        print(f"  SEM NENHUM ALERTA: {len(limpos)} de {len(ok)} ({100*len(limpos)/len(ok):.0f}%)")
        cob = sorted(r.get("cobertura", 0) for r in ok)
        print(f"  cobertura: mediana {cob[len(cob)//2]*100:.1f}% | pior {cob[0]*100:.1f}%")

    # ---------------------------------------------------------------- #
    if falhou:
        print("\n" + "-" * 78)
        print(f"1) NÃO AUDITARAM — {len(falhou)}")
        print("-" * 78)
        por = collections.Counter(
            (r.get("erro") or "?").split(":")[0][:60] for r in falhou
        )
        for erro, n in por.most_common():
            print(f"  {n:4d}x  {erro}")
        for r in falhou[:6]:
            print(f"        · {r.get('pasta')} / {r.get('arquivo')}")

    # ---------------------------------------------------------------- #
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
    if atinge:
        print("\n" + "-" * 78)
        print("2) O QUE O CLIENTE PERDE — por quantos projetos atinge")
        print("-" * 78)
        for tipo, n_arq in atinge.most_common(args.top):
            print(f"  {barra(n_arq / max(len(ok), 1))}  {tipo:<14} {n_arq:>3} projetos, {total[tipo]:>6} entidades")
            print(f"  {' ' * 24}  {consequencia.get(tipo, '')}")

    # ---------------------------------------------------------------- #
    com_perda_de_desenho = sorted(
        [r for r in ok if r.get("cobertura", 1) < 0.99], key=lambda r: r.get("cobertura", 1)
    )
    if com_perda_de_desenho:
        print("\n" + "-" * 78)
        print(f"3) SOME DESENHO — {len(com_perda_de_desenho)} de {len(ok)} arquivos abaixo de 99% de cobertura")
        print("-" * 78)
        for r in com_perda_de_desenho[: args.top]:
            print(f"  {r['cobertura']*100:5.1f}%  {r['pasta']} / {r['arquivo']}")
            if r.get("camadas_sumidas"):
                print(f"          camadas sumidas: {r['camadas_sumidas'][:4]}")

    # ---------------------------------------------------------------- #
    fora = sorted(
        [r for r in ok if r.get("desvio_extensao_rel", 0) > 0.01],
        key=lambda r: -r.get("desvio_extensao_rel", 0),
    )
    if fora:
        print("\n" + "-" * 78)
        print(f"4) ALGO SAIU DO LUGAR — {len(fora)} arquivos com extensão diferente do original")
        print("-" * 78)
        for r in fora[: args.top]:
            pior = (r.get("camadas_fora_do_lugar") or [{}])[0]
            print(f"  {r['desvio_extensao_rel']*100:5.1f}%  {r['pasta']} / {r['arquivo']}"
                  + (f"   (camada '{pior.get('camada')}')" if pior.get("camada") else ""))

    # ---------------------------------------------------------------- #
    etiquetas = sorted(
        [r for r in ok if (r.get("textos") or {}).get("sem_correspondente")],
        key=lambda r: -(r["textos"]["sem_correspondente"]),
    )
    if etiquetas:
        print("\n" + "-" * 78)
        print(f"5) ETIQUETA SEM CORRESPONDENTE — {len(etiquetas)} arquivos")
        print("-" * 78)
        for r in etiquetas[: args.top]:
            t = r["textos"]
            print(f"  {t['sem_correspondente']:>4} de {t['no_original']:<5} {r['pasta']} / {r['arquivo']}")
            if t.get("conteudo_que_sumiu"):
                print(f"          sumiu: {t['conteudo_que_sumiu'][:3]}")

    # ---------------------------------------------------------------- #
    lentos = sorted(ok, key=lambda r: -r.get("segundos", 0))[: args.top]
    print("\n" + "-" * 78)
    print("6) MAIS DEMORADOS (abertura + gravação + medição)")
    print("-" * 78)
    for r in lentos:
        print(f"  {r.get('segundos', 0):6.1f}s  {r.get('mb', 0):6.1f} MB  {r['pasta']} / {r['arquivo']}")

    print("\n" + "=" * 78)
    print("ONDE OLHAR PRIMEIRO: o bloco 1 (não abre) e o 3 (some desenho) são os")
    print("que impedem o projetista de trabalhar. O 2 é o que o cliente perde no")
    print("arquivo que recebe. O 4 e o 5 costumam ser ruído de medição — conferir")
    print("um caso antes de tratar como defeito.")


if __name__ == "__main__":
    main()
