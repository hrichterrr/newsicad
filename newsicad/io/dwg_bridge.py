"""Ponte de LEITURA .dwg → Document usando o `dwg2dxf` do LibreDWG (GPL, sem
restrição de uso comercial). O NewSIcad sempre trabalha internamente em DXF
(newsicad/io/dxf_io.py); este módulo converte .dwg para um .dxf temporário
de forma transparente — o usuário só vê "File > Open" de um .dwg, nunca roda
nada manualmente.

NÃO há gravação de .dwg aqui de propósito: o `dxf2dwg` do LibreDWG (testado
nas versões 0.13.3 via Homebrew E 0.14 compilado localmente a partir do
código-fonte, github.com/LibreDWG/libredwg/releases/tag/0.14) se mostrou
não-confiável mesmo para DWG R2000 com conteúdo mínimo (ou mesmo com um
documento vazio, sem nenhuma entidade) — produz arquivos com handles de
entidade duplicados que nem o próprio `dwg2dxf` consegue reler direito
(`ERROR: Duplicate handle ... already points to object ...` na escrita;
`ValueError: Invalid handle 0.` no ezdxf ao reler). Chegamos a tentar um
fix pontual em `dwg_next_handle()` (src/dwg.c) — a função calculava o
"maior handle já usado" de forma incorreta (parava no primeiro handle
não-nulo varrendo o array de trás pra frente, em vez de calcular o máximo
real) — mas corrigir isso sozinho não resolveu as colisões, indicando que a
causa raiz está em outro lugar (provavelmente na forma como TABLE/CLASS
recebem handles fora do caminho normal de `dwg_add_handle`/`object_map`).
Isso é um bug conhecido e ainda aberto do próprio LibreDWG, não algo
específico do NewSIcad: veja github.com/LibreDWG/libredwg/issues/192
("check duplicate owner handles", aberto desde 2020) e
github.com/LibreDWG/libredwg/issues/1356 (mesma classe de bug, relatado
recentemente). Os mantenedores do próprio LibreDWG descrevem o `dxf2dwg`
como "ainda altamente experimental" (github.com/LibreDWG/libredwg/issues/195).
Por enquanto, "Save"/"Save As" só grava `.dxf` — ver o README para o status
dessa limitação.
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
        # errors="replace": o dwg2dxf às vezes escreve avisos no stderr com
        # bytes que não são UTF-8 válido (texto/nomes de camada do próprio
        # .dwg em latin-1/cp1252) — sem isso, subprocess.run derruba com
        # UnicodeDecodeError antes mesmo de chegarmos a olhar o resultado.
        result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=120)
    except OSError as exc:
        raise DwgBridgeError(f"Falha ao executar '{args[0]}': {exc}") from exc
    if result.returncode != 0:
        raise DwgBridgeError((result.stderr or result.stdout or "erro desconhecido").strip())


def _read_text_flexible(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def sanitize_dxf_text(text: str) -> tuple[str, int]:
    """Corrige uma corrupção específica e recorrente do `dwg2dxf` em textos
    MTEXT longos com muita formatação embutida (`\\fFONTE|b0|i0|c0|p0;...`):
    em vez de quebrar o valor em várias linhas de código 3 (como o formato
    DXF exige para strings compridas), o `dwg2dxf` às vezes insere uma quebra
    de linha crua NO MEIO da string de um único código de grupo — quebrando
    literalmente no meio de uma palavra (ex.: "...ISOC\nPEUR..." em vez de
    "...ISOCPEUR..."). Isso desalinha os pares código/valor do DXF a partir
    dali, e todo o resto do arquivo passa a ser lido errado (o típico erro é
    "Invalid group code" bem à frente no arquivo, sem relação óbvia com a
    causa real).

    Como todo código de grupo DXF válido é um inteiro não-negativo puro,
    detectamos a corrupção reaplicando a leitura em pares (código, valor): ao
    ler uma linha onde um código era esperado, se ela não for um inteiro,
    ela só pode ser a continuação quebrada do valor anterior — colamos de
    volta (sem separador, já que a quebra caiu no meio de uma palavra) e
    tentamos de novo a próxima linha como código."""
    lines = text.splitlines()
    out: list[str] = []
    merged = 0
    i, n = 0, len(lines)
    while i < n:
        code_line = lines[i]
        if not code_line.strip().isdigit():
            if out:
                out[-1] += code_line
                merged += 1
            i += 1
            continue
        out.append(code_line)
        i += 1
        if i < n:
            out.append(lines[i])
            i += 1
    return "\n".join(out) + "\n", merged


def _sanitize_dxf_file(path: Path) -> int:
    text = _read_text_flexible(path)
    sanitized, merged = sanitize_dxf_text(text)
    if merged:
        path.write_text(sanitized, encoding="utf-8")
    return merged


def dwg_to_document(path: str | Path) -> tuple[Document, int]:
    """Lê um .dwg (via dwg2dxf) e retorna (Document, entidades ignoradas)."""
    tool = _tool_path("dwg2dxf")
    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "converted.dxf"
        _run([tool, "-o", str(dxf_path), "-y", str(path)])
        if not dxf_path.exists():
            raise DwgBridgeError(f"dwg2dxf não gerou o arquivo DXF esperado para '{path}'.")
        _sanitize_dxf_file(dxf_path)
        try:
            return load_dxf(dxf_path)
        except Exception as exc:
            raise DwgBridgeError(
                f"O .dwg foi convertido, mas o DXF resultante não pôde ser lido: {exc}"
            ) from exc
