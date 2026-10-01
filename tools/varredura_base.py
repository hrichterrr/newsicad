"""Varredura de fidelidade sobre a base inteira de projetos da New SI.

Existe para o defeito ser encontrado AQUI, e não pelo projetista no meio de
um projeto. Abre todo `.dwg` de uma pasta, mede o que entra e o que se perde,
e devolve uma fila de trabalho ordenada por quantos projetos reais cada
defeito atinge — não por quem reclamou mais alto.

Uso:

    python tools/varredura_base.py <pasta com .dwg> [--saida relatorio.json]
                                   [--limite N] [--so-novos]

Grava o resultado incrementalmente: pode ser interrompida e retomada (quem já
foi medido é pulado com `--so-novos`). O relatório em JSON alimenta
`tools/relatorio_varredura.py`, que imprime a fila priorizada.

Não mede desempenho de interação (mouse, zoom): isso é `tools/bench_perf.py`,
que precisa de janela real. Aqui é fidelidade e tempo de abertura, que é o que
dá para rodar em lote.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsicad.core.entities import (  # noqa: E402
    BlockReference,
    Dimension,
    Hatch,
    Text,
)
from newsicad.io.dwg_bridge import dwg_to_document  # noqa: E402
from newsicad.io.dxf_io import load_dxf  # noqa: E402

#: Acima disto a abertura é considerada lenta o bastante para o usuário
#: reclamar (o relato do grupo em 22/09/2026 era sobre arquivos que levavam
#: dezenas de segundos).
LIMITE_ABERTURA_S = 20.0


def mede(caminho: Path) -> dict:
    """Abre um arquivo e devolve tudo que dá para medir sobre ele."""
    reg: dict = {
        "arquivo": caminho.name,
        "pasta": caminho.parent.name,
        "mb": round(caminho.stat().st_size / 1024 / 1024, 2),
    }
    t0 = time.perf_counter()
    try:
        if caminho.suffix.lower() == ".dwg":
            doc, skipped = dwg_to_document(caminho)
        else:
            doc, skipped = load_dxf(caminho)
    except Exception as exc:
        reg["status"] = "FALHOU"
        reg["erro"] = f"{type(exc).__name__}: {exc}"
        reg["traceback"] = traceback.format_exc()[-1200:]
        reg["segundos"] = round(time.perf_counter() - t0, 1)
        return reg
    reg["segundos"] = round(time.perf_counter() - t0, 1)
    reg["status"] = "ok"

    ents = list(doc.entities.values())
    reg["entidades"] = len(ents)
    reg["por_tipo"] = dict(collections.Counter(type(e).__name__ for e in ents).most_common())

    # O que a leitura DESCARTOU — o coração da varredura.
    reg["descartadas"] = int(skipped)
    reg["descartadas_por_tipo"] = dict(getattr(skipped, "by_type", {}) or {})
    reg["notas"] = list(getattr(skipped, "notes", []) or [])

    refs = [e for e in ents if isinstance(e, BlockReference)]
    reg["blocos_defs"] = len(doc.block_definitions)
    reg["blocos_entidades"] = sum(len(v) for v in doc.block_definitions.values())
    reg["blocos_instancias"] = len(refs)
    reg["blocos_vazios"] = sum(
        1 for r in refs if not doc.block_definitions.get(r.block_name)
    )
    reg["anotacoes_importadas"] = sum(
        1 for n in doc.block_definitions if n.startswith(("*ML_", "*LD_", "*D_", "*T_"))
    )
    reg["atributos"] = sum(len(r.attributes) for r in refs)
    reg["atributos_moldes"] = sum(len(v) for v in doc.block_attdefs.values())
    reg["textos"] = sum(1 for e in ents if isinstance(e, Text))
    reg["cotas_nativas"] = sum(1 for e in ents if isinstance(e, Dimension))
    reg["hachuras"] = sum(1 for e in ents if isinstance(e, Hatch))
    reg["camadas"] = len(doc.layers)
    reg["unidades"] = doc.units
    reg["pranchas"] = {k: len(v) for k, v in doc.layouts.items()}
    reg["altura_texto"] = doc.text_height

    # Sinais de alerta legíveis, que viram a fila de trabalho.
    alertas = []
    if reg["segundos"] > LIMITE_ABERTURA_S:
        alertas.append(f"abertura lenta ({reg['segundos']:.0f}s)")
    if reg["descartadas"]:
        tipos = ", ".join(f"{t} x{n}" for t, n in reg["descartadas_por_tipo"].items())
        alertas.append(f"{reg['descartadas']} entidades descartadas ({tipos})")
    if reg["blocos_vazios"]:
        alertas.append(f"{reg['blocos_vazios']} instancias de bloco sem definicao")
    if reg["entidades"] == 0:
        alertas.append("ABRIU VAZIO")
    if reg["textos"] == 0 and reg["entidades"] > 200:
        alertas.append("nenhum texto num desenho grande")
    reg["alertas"] = alertas
    return reg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("varredura.json"))
    ap.add_argument("--limite", type=int, default=0, help="só os N primeiros")
    ap.add_argument("--so-novos", action="store_true", help="pula o que já está no relatório")
    args = ap.parse_args()

    arquivos = sorted(
        [p for p in args.pasta.rglob("*") if p.suffix.lower() in (".dwg", ".dxf")],
        key=lambda p: p.stat().st_size,
    )
    if args.limite:
        arquivos = arquivos[: args.limite]

    feitos: dict[str, dict] = {}
    if args.saida.exists():
        try:
            feitos = {r["arquivo"] + "|" + r.get("pasta", ""): r for r in json.loads(args.saida.read_text(encoding="utf-8"))}
        except Exception:
            feitos = {}

    print(f"{len(arquivos)} arquivos | {len(feitos)} já medidos", flush=True)
    for i, caminho in enumerate(arquivos, 1):
        chave = caminho.name + "|" + caminho.parent.name
        if args.so_novos and chave in feitos:
            continue
        print(f"[{i}/{len(arquivos)}] {caminho.parent.name} / {caminho.name} ({caminho.stat().st_size/1024/1024:.1f} MB)", flush=True)
        reg = mede(caminho)
        feitos[chave] = reg
        if reg["status"] == "FALHOU":
            print(f"    FALHOU: {reg['erro'][:160]}", flush=True)
        else:
            resumo = f"    {reg['segundos']}s | {reg['entidades']} ent"
            if reg["alertas"]:
                resumo += " | " + "; ".join(reg["alertas"])
            print(resumo, flush=True)
        args.saida.write_text(
            json.dumps(list(feitos.values()), ensure_ascii=False, indent=1), encoding="utf-8"
        )

    print(f"\nrelatório: {args.saida.resolve()}")


if __name__ == "__main__":
    main()
