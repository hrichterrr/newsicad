"""Cache do Document já lido, por arquivo aberto.

Abrir um .dwg grande custa dezenas de segundos e quase tudo é o parser DXF
puro-Python do ezdxf (medido em 2026-09-02: 24 s dos ~32 s de abertura da
planta Casa Pau Brasil só no `ezdxf.readfile`; DXF binário do dwg2dxf não
ajuda — 12% mais rápido). Os testers abrem o MESMO arquivo várias vezes por
dia, então o ganho real está em não reparsear: o Document (dataclasses puras,
sem nada do Qt) e o SkippedCount vão pra um pickle em %LOCALAPPDATA%/NewSIcad/
cache, chaveado por caminho + tamanho + mtime + CACHE_VERSION (esquema). Qualquer
mudança no arquivo ou no esquema invalida a entrada; qualquer erro de
leitura/escrita do cache é ignorado silenciosamente (o pior caso é só
reparsear). Mantém as 20 entradas mais recentes."""

from __future__ import annotations

import hashlib
import os
import pickle
from pathlib import Path
from typing import Any

# Versao do ESQUEMA do cache: bumpar sempre que o formato pickled mudar
# (campo novo/renomeado em Document ou nas entidades de core/entities.py).
# A chave nao inclui mais a versao do app: chavear por versao fazia cada
# release "esfriar" o cache de todos os arquivos (90 s de parser por planta
# grande na primeira abertura de cada versao, medicao de 2026-09-05).
# "3": Document ganhou `text_height` (2026-09-06); uma entrada gravada antes
# disso volta sem o atributo e quebraria quem o lê.
# "6": Document ganhou `layouts` (pranchas de paper space, 09/09/2026) — mesmo
# risco: uma entrada antiga voltaria sem o atributo e quebraria
# `_populate_session_from_loaded`/`_show_layouts_dialog`. Bônus: a mesma leva
# corrigiu o bug dos blocos dinâmicos empilhados (ver dxf_io._is_invisible) —
# sem este bump, quem já tinha aberto um arquivo problemático continuaria
# vendo os ícones "explodidos" do cache até o arquivo mudar de novo.
# "7": Document ganhou `block_attdefs` (moldes de atributo por bloco,
# 22/09/2026) e Text ganhou `attrib_tag`/`attrib_owner` — sem o bump, uma
# entrada antiga volta sem os moldes e gravar o arquivo perderia os campos
# preenchíveis do bloco, que é justamente o que essa leva veio consertar.
CACHE_VERSION = "7"
MAX_ENTRIES = 20


def cache_dir() -> Path:
    base = os.environ.get("NEWSICAD_CACHE_DIR") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "NewSIcad" / "cache"


def cache_key(path: Path, app_version: str) -> str:
    stat = path.stat()
    del app_version  # mantido na assinatura pelos chamadores; ver CACHE_VERSION
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{CACHE_VERSION}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_cached(path: Path, app_version: str) -> Any | None:
    """Devolve o payload guardado para `path` ou None (ausente/inválido)."""
    try:
        entry = cache_dir() / f"{cache_key(path, app_version)}.pickle"
        if not entry.is_file():
            return None
        with open(entry, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def store_cached(path: Path, app_version: str, payload: Any) -> bool:
    """Grava `payload` para `path`; devolve False (sem levantar) em erro."""
    try:
        directory = cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        entry = directory / f"{cache_key(path, app_version)}.pickle"
        tmp = entry.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, entry)
        _prune(directory)
        return True
    except Exception:
        return False


def _prune(directory: Path) -> None:
    entries = sorted(directory.glob("*.pickle"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in entries[MAX_ENTRIES:]:
        try:
            stale.unlink()
        except OSError:
            pass
