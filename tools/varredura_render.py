"""Segunda passada da varredura: DESENHA cada arquivo e mede se apareceu algo.

A passada de fidelidade (`tools/varredura_base.py`) responde "o que entrou no
modelo". Ela não pega a falha mais cara de todas: o arquivo entra inteiro e
mesmo assim a tela fica em branco ou quase. Foi o que aconteceu com a planta
João e Brenda, onde todo arco saía espelhado e a prancha abria vazia — o
modelo estava cheio, o desenho não aparecia.

Aqui cada arquivo é renderizado de verdade (mesmo canvas do programa), salvo
em PNG e medido: quanta TINTA tem na tela e o quanto ela se espalha. Pouca
tinta com muita entidade é o sinal de "explodiu" ou "sumiu".

Uso:

    python tools/varredura_render.py <pasta com .dwg> [--saida render.json]
                                     [--pngs pasta] [--limite N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from newsicad.io.dwg_bridge import dwg_to_document  # noqa: E402
from newsicad.io.dxf_io import load_dxf  # noqa: E402
from newsicad.ui.main_window import MainWindow  # noqa: E402

#: Abaixo desta fração de pixels com tinta, num desenho que tem entidades, a
#: tela está praticamente vazia — é o sinal de alarme.
TINTA_MINIMA = 0.004


def fracao_de_tinta(imagem) -> float:
    """Fração de pixels que não são a cor de fundo. Amostra de 4 em 4 pixels:
    a precisão não importa, o sinal sim."""
    fundo = imagem.pixel(2, 2)
    total = pintados = 0
    for y in range(0, imagem.height(), 4):
        for x in range(0, imagem.width(), 4):
            total += 1
            if imagem.pixel(x, y) != fundo:
                pintados += 1
    return pintados / max(total, 1)


def mede(caminho: Path, pasta_png: Path | None) -> dict:
    reg = {"arquivo": caminho.name, "pasta": caminho.parent.name}
    try:
        t0 = time.perf_counter()
        if caminho.suffix.lower() == ".dwg":
            loaded, skipped = dwg_to_document(caminho)
        else:
            loaded, skipped = load_dxf(caminho)
        reg["segundos_leitura"] = round(time.perf_counter() - t0, 1)

        win = MainWindow()
        win.resize(1400, 900)
        sessao = win._make_untitled_session()
        t1 = time.perf_counter()
        win._populate_session_from_loaded(sessao, loaded, caminho, skipped)
        win._add_session_tab(sessao)
        win.show()
        app.processEvents()
        canvas = win.canvas
        canvas.zoom_extents()
        app.processEvents()
        canvas.viewport().repaint()
        app.processEvents()
        reg["segundos_montagem"] = round(time.perf_counter() - t1, 1)

        reg["entidades"] = len(sessao.document.entities)
        reg["itens_na_cena"] = len(canvas._scene.items())
        imagem = canvas.viewport().grab().toImage()
        reg["tinta"] = round(fracao_de_tinta(imagem), 5)
        if pasta_png is not None:
            pasta_png.mkdir(parents=True, exist_ok=True)
            destino = pasta_png / f"{caminho.parent.name}__{caminho.stem}.png"
            imagem.save(str(destino))
            reg["png"] = str(destino)

        alertas = []
        if reg["entidades"] > 50 and reg["tinta"] < TINTA_MINIMA:
            alertas.append(f"TELA QUASE VAZIA (tinta {reg['tinta']:.4f})")
        if reg["itens_na_cena"] == 0 and reg["entidades"] > 0:
            alertas.append("nenhum item montado na cena")
        reg["alertas"] = alertas
        reg["status"] = "ok"
        win.close()
    except Exception as exc:
        reg["status"] = "FALHOU"
        reg["erro"] = f"{type(exc).__name__}: {exc}"
        reg["alertas"] = ["FALHOU AO DESENHAR"]
    app.processEvents()
    return reg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("render.json"))
    ap.add_argument("--pngs", type=Path, default=None)
    ap.add_argument("--limite", type=int, default=0)
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
            feitos = {r["arquivo"] + "|" + r["pasta"]: r for r in json.loads(args.saida.read_text(encoding="utf-8"))}
        except Exception:
            feitos = {}

    print(f"{len(arquivos)} arquivos | {len(feitos)} já renderizados", flush=True)
    for i, caminho in enumerate(arquivos, 1):
        chave = caminho.name + "|" + caminho.parent.name
        if chave in feitos:
            continue
        print(f"[{i}/{len(arquivos)}] {caminho.parent.name} / {caminho.name}", flush=True)
        reg = mede(caminho, args.pngs)
        feitos[chave] = reg
        marca = "; ".join(reg.get("alertas") or []) or "ok"
        print(f"    {reg.get('entidades', '?')} ent | tinta {reg.get('tinta', '?')} | {marca}", flush=True)
        args.saida.write_text(json.dumps(list(feitos.values()), ensure_ascii=False, indent=1), encoding="utf-8")

    suspeitos = [r for r in feitos.values() if r.get("alertas")]
    print(f"\n{len(suspeitos)} arquivo(s) com sinal de alarme:")
    for r in suspeitos:
        print(f"  · {r['pasta']} / {r['arquivo']} — {'; '.join(r['alertas'])}")
    print(f"relatório: {args.saida.resolve()}")


if __name__ == "__main__":
    main()
