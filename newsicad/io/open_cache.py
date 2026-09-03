"""Cache do Document já lido, por arquivo aberto.

Abrir um .dwg grande custa dezenas de segundos e quase tudo é o parser DXF
puro-Python do ezdxf (medido em 2026-09-02: 24 s dos ~32 s de abertura da
planta Casa Pau Brasil só no `ezdxf.readfile`; DXF binário do dwg2dxf não
ajuda — 12% mais rápido). Os testers abrem o MESMO arquivo várias vezes por
dia, então o ganho real está em não reparsear: o Document (dataclasses puras,
sem nada do Qt) e o SkippedCount vão pra um pickle em %LOCALAPPDATA%/NewSIcad/
cache, chaveado por caminho + tamanho + mtime + versão do app. Qualquer
mudança no arquivo ou no NewSIcad invalida a entrada; qualquer erro de
leitura/escrita do cache é ignorado silenciosamente (o pior caso é só
reparsear). Mantém as 20 entradas mais recentes."""

from __future__ import annotations

import hashlib
import os
import pickle
from pathlib import Path
from typing import Any

CACHE_VERSION = "1"
MAX_ENTRIES = 20


def cache_dir() -> Path:
    base = os.environ.get("NEWSICAD_CACHE_DIR") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "NewSIcad" / "cache"


def cache_key(path: Path, app_version: str) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{app_version}|{CACHE_VERSION}"
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
