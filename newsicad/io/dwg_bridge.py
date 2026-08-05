"""Ponte de LEITURA .dwg → Document usando o `dwg2dxf` do LibreDWG (GPL, sem
restrição de uso comercial). O NewSIcad sempre trabalha internamente em DXF
(newsicad/io/dxf_io.py); este módulo converte .dwg para um .dxf temporário
de forma transparente — o usuário só vê "File > Open" de um .dwg, nunca roda
nada manualmente.

NÃO há gravação de .dwg aqui de propósito: o `dxf2dwg` do LibreDWG (testado
na versão 0.13.3) se mostrou não-confiável mesmo para DWG R2000 com conteúdo
mínimo — produz arquivos com handles de entidade duplicados que nem o
próprio `dwg2dxf` consegue reler direito. Os mantenedores do próprio
LibreDWG descrevem o `dxf2dwg` como "ainda altamente experimental"
(github.com/LibreDWG/libredwg/issues/195). Por enquanto, "Save"/"Save As"
só grava `.dxf` — ver o README para o status dessa limitação.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from newsicad.core.document import Document
from newsicad.io.dxf_io import load_dxf


class DwgBridgeError(RuntimeError):
    pass


def _platform_dir() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    raise DwgBridgeError(f"Conversão .dwg não tem binários do LibreDWG empacotados para '{system}'.")


def _bundled_bin_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Empacotado com PyInstaller: os dados extras (build_windows.spec)
        # ficam soltos na raiz do bundle (sys._MEIPASS), não dentro do pacote.
        base = Path(sys._MEIPASS) / "resources" / "libredwg"
    else:
        # newsicad/io/dwg_bridge.py -> parent.parent = pacote newsicad/ (raiz)
        base = Path(__file__).resolve().parent.parent / "resources" / "libredwg"
    return base / _platform_dir()


def _tool_path(name: str) -> str:
    exe_name = f"{name}.exe" if platform.system() == "Windows" else name
    bundled = _bundled_bin_dir() / exe_name
    if bundled.exists():
        return str(bundled)

    found = shutil.which(name)
    if found:
        return found

    raise DwgBridgeError(
        f"Ferramenta '{name}' do LibreDWG não encontrada (nem empacotada, nem no PATH). "
        "Instale o LibreDWG (ex.: `brew install libredwg` no macOS) para abrir .dwg."
    )


def _run(args: list[str]) -> None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except OSError as exc:
        raise DwgBridgeError(f"Falha ao executar '{args[0]}': {exc}") from exc
    if result.returncode != 0:
        raise DwgBridgeError((result.stderr or result.stdout or "erro desconhecido").strip())


def dwg_to_document(path: str | Path) -> tuple[Document, int]:
    """Lê um .dwg (via dwg2dxf) e retorna (Document, entidades ignoradas)."""
    tool = _tool_path("dwg2dxf")
    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "converted.dxf"
        _run([tool, "-o", str(dxf_path), "-y", str(path)])
        if not dxf_path.exists():
            raise DwgBridgeError(f"dwg2dxf não gerou o arquivo DXF esperado para '{path}'.")
        return load_dxf(dxf_path)
