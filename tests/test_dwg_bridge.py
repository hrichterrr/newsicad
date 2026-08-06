"""Testes de newsicad/io/dwg_bridge.py.

`dwg2dxf` (LibreDWG) só está empacotado para macOS/Windows (ver
`resources/libredwg/`) e, fora isso, precisa estar no PATH. Em ambientes que
não têm nenhum dos dois (ex.: a maioria dos runners Linux de CI), os testes
que dependem dele são pulados via `pytest.skip`, cobrindo tanto "ferramenta
não encontrada" quanto "plataforma sem binário empacotado".

Não geramos aqui um .dwg de teste com o `dxf2dwg` do próprio LibreDWG: como
documentado em `dwg_bridge.py`, essa ferramenta (v0.13.3) é conhecida por
produzir arquivos com handles de entidade duplicados/inválidos mesmo para
conteúdo mínimo (uma única linha) — reproduzido manualmente durante o
desenvolvimento destes testes: o .dwg gerado pelo `dxf2dwg` falha ao ser
relido, com `ValueError: Invalid handle 0.` vazando de dentro do ezdxf. Por
isso o teste de "arquivo .dwg inválido" abaixo usa bytes arbitrários em vez
de depender do gravador não confiável.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from newsicad.io.dwg_bridge import DwgBridgeError, _tool_path, dwg_to_document, sanitize_dxf_text


def _require_dwg2dxf() -> str:
    try:
        return _tool_path("dwg2dxf")
    except DwgBridgeError as exc:
        pytest.skip(str(exc))


def test_tool_path_resolves_or_skips():
    tool = _require_dwg2dxf()
    assert Path(tool).name.startswith("dwg2dxf")


def test_dwg_to_document_raises_clean_error_for_invalid_file():
    _require_dwg2dxf()

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_dwg = Path(tmp_dir) / "not_really_a_dwg.dwg"
        fake_dwg.write_bytes(b"this is not a valid dwg file")

        with pytest.raises(DwgBridgeError):
            dwg_to_document(fake_dwg)


def test_dwg_to_document_raises_for_missing_file():
    _require_dwg2dxf()

    with tempfile.TemporaryDirectory() as tmp_dir:
        missing = Path(tmp_dir) / "does_not_exist.dwg"
        with pytest.raises(DwgBridgeError):
            dwg_to_document(missing)


# ---------------------------------------------------------------------- #
# sanitize_dxf_text: função pura, roda em qualquer ambiente (não depende
# do binário dwg2dxf) — cobre a corrupção real encontrada em .dwg reais de
# clientes, onde o dwg2dxf quebra uma string de MTEXT longa (com códigos de
# formatação embutidos) no meio de uma palavra em vez de encadear várias
# linhas de código 3 como o formato DXF exige.
# ---------------------------------------------------------------------- #
def test_sanitize_dxf_text_rejoins_word_broken_by_stray_newline():
    # Reprodução mínima do padrão real: o valor do código 1 (texto do MTEXT)
    # tem uma quebra de linha crua bem no meio de "ISOCPEUR".
    broken = "  0\nMTEXT\n  1\n\\fISOC\nPEUR|b0;texto\n  7\nGENERATED_STYLE_1\n"
    fixed, merged = sanitize_dxf_text(broken)

    assert merged == 1
    assert "\\fISOCPEUR|b0;texto" in fixed
    assert "ISOC\nPEUR" not in fixed


def test_sanitize_dxf_text_is_noop_for_well_formed_dxf():
    well_formed = "  0\nLINE\n  8\n0\n 10\n0.0\n 20\n0.0\n"
    fixed, merged = sanitize_dxf_text(well_formed)

    assert merged == 0
    assert fixed == well_formed


def test_sanitize_dxf_text_handles_multiple_consecutive_wraps():
    # Uma string tão longa que quebra em 3 linhas físicas, não só 2.
    broken = "  1\nAAA\nBBB\nCCC\n  0\nENDSEC\n"
    fixed, merged = sanitize_dxf_text(broken)

    assert merged == 2
    assert "AAABBBCCC" in fixed
