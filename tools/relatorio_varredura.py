"""Lê o JSON de `tools/varredura_base.py` e imprime a fila de trabalho.

A ordenação é por QUANTOS PROJETOS REAIS cada defeito atinge, não pela
gravidade que a gente imagina nem por quem reclamou. É isso que responde
"o que consertar primeiro" sem depender do vai e vem com a equipe.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("relatorio", type=Path, nargs="?", default=Path("varredura.json"))
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    regs = json.loads(args.relatorio.read_text(encoding="utf-8"))
    ok = [r for r in regs if r.get("status") == "ok"]
    falhou = [r for r in regs if r.get("status") == "FALHOU"]

    print("=" * 74)
    print(f"VARREDURA DA BASE — {len(regs)} arquivos")
    print("=" * 74)
    print(f"  abriram: {len(ok)}   |   NÃO abriram: {len(falhou)}")
    if ok:
        tempos = sorted(r["segundos"] for r in ok)
        ents = sorted(r["entidades"] for r in ok)
        print(f"  tempo de abertura: mediana {tempos[len(tempos)//2]:.1f}s | pior {tempos[-1]:.1f}s")
        print(f"  tamanho: mediana {ents[len(ents)//2]} entidades | maior {ents[-1]}")

    if falhou:
        print("\n" + "-" * 74)
        print(f"1) NÃO ABREM — {len(falhou)} arquivo(s). É o defeito mais caro: o projetista não começa.")
        print("-" * 74)
        por_erro = collections.Counter(r["erro"].split(":")[0] for r in falhou)
        for erro, n in por_erro.most_common():
            print(f"  {n:4d}x  {erro}")
        for r in falhou[:8]:
            print(f"        · {r['pasta']} / {r['arquivo']} — {r['erro'][:110]}")

    # entidades descartadas: quantos ARQUIVOS cada tipo atinge, e o total
    atinge = collections.Counter()
    total = collections.Counter()
    for r in ok:
        for tipo, n in (r.get("descartadas_por_tipo") or {}).items():
            atinge[tipo] += 1
            total[tipo] += n
    if atinge:
        print("\n" + "-" * 74)
        print("2) O QUE SOME NA IMPORTAÇÃO — ordenado por quantos projetos atinge")
        print("-" * 74)
        print(f"  {'tipo':<34} {'projetos':>9} {'entidades':>11}")
        for tipo, n_arq in atinge.most_common(args.top):
            print(f"  {tipo:<34} {n_arq:>9} {total[tipo]:>11}")

    lentos = sorted([r for r in ok if r.get("alertas")], key=lambda r: -r["segundos"])
    lentos = [r for r in lentos if any("lenta" in a for a in r["alertas"])]
    if lentos:
        print("\n" + "-" * 74)
        print(f"3) ABERTURA LENTA — {len(lentos)} de {len(ok)} arquivos")
        print("-" * 74)
        for r in lentos[: args.top]:
            print(f"  {r['segundos']:>6.1f}s  {r['entidades']:>7} ent  {r['pasta']} / {r['arquivo']}")

    vazios = [r for r in ok if "ABRIU VAZIO" in r.get("alertas", [])]
    sem_texto = [r for r in ok if any("nenhum texto" in a for a in r.get("alertas", []))]
    sem_def = [r for r in ok if r.get("blocos_vazios")]
    if vazios or sem_texto or sem_def:
        print("\n" + "-" * 74)
        print("4) SINAIS DE IMPORTAÇÃO QUEBRADA")
        print("-" * 74)
        if vazios:
            print(f"  abriram VAZIOS: {len(vazios)}")
            for r in vazios[:6]:
                print(f"        · {r['pasta']} / {r['arquivo']}")
        if sem_texto:
            print(f"  desenho grande sem nenhum texto: {len(sem_texto)}")
            for r in sem_texto[:6]:
                print(f"        · {r['pasta']} / {r['arquivo']} ({r['entidades']} ent)")
        if sem_def:
            total_vazios = sum(r["blocos_vazios"] for r in sem_def)
            print(f"  instâncias de bloco sem definição: {total_vazios} em {len(sem_def)} arquivos")
            for r in sorted(sem_def, key=lambda x: -x["blocos_vazios"])[:6]:
                print(f"        · {r['blocos_vazios']:>5} em {r['pasta']} / {r['arquivo']}")

    print("\n" + "-" * 74)
    print("5) O QUE A BASE TEM (para saber onde vale investir)")
    print("-" * 74)
    somas = collections.Counter()
    com = collections.Counter()
    for r in ok:
        for campo in ("anotacoes_importadas", "atributos", "cotas_nativas", "hachuras", "textos"):
            v = r.get(campo) or 0
            somas[campo] += v
            if v:
                com[campo] += 1
    for campo, v in somas.most_common():
        print(f"  {campo:<24} {v:>9} no total, presente em {com[campo]} de {len(ok)} arquivos")
    unidades = collections.Counter(r.get("unidades") for r in ok)
    print(f"  unidades: {dict(unidades)}")
    com_prancha = [r for r in ok if r.get("pranchas")]
    print(f"  arquivos com prancha em paper space: {len(com_prancha)} de {len(ok)}")


if __name__ == "__main__":
    main()
