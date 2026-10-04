"""Quanto tempo o NewSIcad leva para ABRIR cada projeto da base.

Responde "está com lentidão?" com número, não com impressão. Mede as três
etapas que o projetista espera quando dá File > Open num `.dwg`:

    1. converter   o `dwg2dxf` do LibreDWG transformando o .dwg em .dxf
    2. ler         `load_dxf` montando o Document
    3. gravar      `save_dxf` (não entra no File > Open, mas é o que ele
                   espera no Save — medido junto porque é o outro tempo que
                   aparece no dia a dia)

NÃO confundir com o tempo da auditoria (`tools/auditoria_projeto.py`), que
além disso mede os dois lados do arquivo e chega a ser dez vezes maior. Essa
confusão já custou caro: seis arquivos que a auditoria levava 1.500 s para
processar abrem no programa em 9,6 s e 15,8 s, e eu quase reportei "o
programa leva 25 minutos para abrir" (ver docs/VARREDURA.md).

A montagem da cena no Qt fica de fora: ela precisa de janela e é medida
pelas rotinas de `tools/bench_perf.py`.

Uso:

    python tools/tempo_de_abertura.py <pasta> [--saida tempos.json]
                                      [--trabalhadores 4]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from newsicad.io import dwg_bridge  # noqa: E402
from newsicad.io.dxf_io import load_dxf, save_dxf  # noqa: E402


def mede(caminho: Path) -> dict:
    reg = {"arquivo": caminho.name, "pasta": caminho.parent.name,
           "mb": round(caminho.stat().st_size / 1024 / 1024, 2)}
    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = dwg_bridge.pasta_que_a_ferramenta_enxerga(Path(tmp))
            dxf = tmp / "ref.dxf"
            if caminho.suffix.lower() == ".dwg":
                entrada = dwg_bridge.entrada_que_a_ferramenta_abre(caminho, tmp)
                dwg_bridge._run([dwg_bridge._tool_path("dwg2dxf"), "-o", str(dxf), "-y", str(entrada)])
                dwg_bridge._sanitize_dxf_file(dxf)
            else:
                dxf = caminho
            t1 = time.perf_counter()

            documento, descartadas = load_dxf(dxf)
            t2 = time.perf_counter()

            save_dxf(documento, tmp / "nosso.dxf")
            t3 = time.perf_counter()

        reg.update(
            status="ok",
            converter=round(t1 - t0, 2),
            ler=round(t2 - t1, 2),
            gravar=round(t3 - t2, 2),
            abrir=round(t2 - t0, 2),          # é isto que o File > Open custa
            entidades=len(documento.entities),
            blocos=len(documento.block_definitions),
            pranchas=len(documento.layouts),
            descartadas=int(descartadas),
        )
    except Exception as exc:
        reg.update(status="FALHOU", erro=f"{type(exc).__name__}: {exc}"[:200],
                   abrir=round(time.perf_counter() - t0, 2))
    return reg


def mede_isolado(caminho: Path, tempo_limite: int) -> dict:
    """Num processo separado: um arquivo que derruba o interpretador não
    pode levar a medição inteira junto."""
    cmd = [sys.executable, str(Path(__file__).resolve()), str(caminho), "--um-arquivo"]
    base = {"arquivo": caminho.name, "pasta": caminho.parent.name,
            "mb": round(caminho.stat().st_size / 1024 / 1024, 2)}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=tempo_limite)
    except subprocess.TimeoutExpired:
        return {**base, "status": "FALHOU", "erro": f"passou de {tempo_limite}s"}
    for linha in (r.stdout or "").splitlines():
        if linha.startswith("<<<JSON>>>"):
            try:
                return json.loads(linha[len("<<<JSON>>>"):])
            except Exception:
                break
    return {**base, "status": "FALHOU", "erro": "o processo morreu medindo este arquivo"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("alvo", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("tempos.json"))
    ap.add_argument("--trabalhadores", type=int, default=4)
    ap.add_argument("--tempo-limite", type=int, default=900)
    ap.add_argument("--um-arquivo", action="store_true", help="uso interno")
    args = ap.parse_args()

    if args.um_arquivo:
        print("<<<JSON>>>" + json.dumps(mede(args.alvo), ensure_ascii=False))
        return

    arquivos = ([args.alvo] if args.alvo.is_file() else
                sorted((p for p in args.alvo.rglob("*") if p.suffix.lower() in (".dwg", ".dxf")),
                       key=lambda p: p.stat().st_size))
    feitos: list[dict] = []
    trava = threading.Lock()
    print(f"{len(arquivos)} arquivos | {args.trabalhadores} por vez", flush=True)

    def guarda(reg: dict) -> None:
        with trava:
            feitos.append(reg)
            if reg["status"] == "ok":
                print(f"[{len(feitos)}/{len(arquivos)}] {reg['mb']:6.1f} MB  "
                      f"abrir {reg['abrir']:6.1f}s  (converter {reg['converter']:5.1f} + "
                      f"ler {reg['ler']:5.1f})  gravar {reg['gravar']:6.1f}s  "
                      f"{reg['entidades']:>7} ent  {reg['pasta'][:22]} / {reg['arquivo'][:30]}", flush=True)
            else:
                print(f"[{len(feitos)}/{len(arquivos)}] FALHOU {reg.get('erro','')[:80]}  "
                      f"{reg['pasta'][:22]} / {reg['arquivo'][:30]}", flush=True)
            temp = args.saida.with_suffix(".parcial")
            temp.write_text(json.dumps(feitos, ensure_ascii=False, indent=1), encoding="utf-8")
            temp.replace(args.saida)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.trabalhadores) as pool:
        futuros = {pool.submit(mede_isolado, c, args.tempo_limite): c for c in arquivos}
        for f in concurrent.futures.as_completed(futuros):
            try:
                guarda(f.result())
            except Exception as exc:
                caminho = futuros[f]
                guarda({"arquivo": caminho.name, "pasta": caminho.parent.name,
                        "status": "FALHOU", "erro": f"{type(exc).__name__}: {exc}"[:200]})

    ok = [r for r in feitos if r["status"] == "ok"]
    if not ok:
        return
    abrir = sorted(r["abrir"] for r in ok)
    print()
    print(f"ABRIR ({len(ok)} arquivos): mediana {abrir[len(abrir)//2]:.1f}s | "
          f"90% abaixo de {abrir[int(len(abrir)*0.9)]:.1f}s | pior {abrir[-1]:.1f}s")
    acima = [r for r in ok if r["abrir"] > 30]
    print(f"acima de 30 s: {len(acima)} de {len(ok)} ({100*len(acima)/len(ok):.0f}%)")
    for r in sorted(ok, key=lambda r: -r["abrir"])[:10]:
        print(f"   {r['abrir']:7.1f}s  {r['mb']:6.1f} MB  {r['entidades']:>7} ent  "
              f"{r['pasta'][:24]} / {r['arquivo'][:34]}")


if __name__ == "__main__":
    main()
