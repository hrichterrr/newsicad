"""Testes de newsicad/io/dwg_export.py.

Ao contrário de test_dwg_bridge.py (que pula testes quando o binário do
LibreDWG não está disponível), aqui não dependemos de nenhuma ferramenta
externa nem de rede: todas as chamadas HTTP são mockadas via
unittest.mock.patch em `requests.post`/`requests.get`. Isso mantém os testes
rápidos, determinísticos, e sem consumir créditos reais da conta CloudConvert
da New SI a cada execução do pytest.

O fluxo real (upload -> conversão -> download, com uma API key de verdade)
já foi validado manualmente contra a API real durante o planejamento desta
feature: um .dxf com layer/linhas/círculo/texto foi convertido e o .dwg
resultante reabriu no próprio dwg_bridge.py com 6/6 entidades e a layer
preservada, 0 entidades perdidas.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from newsicad.core.document import Document
from newsicad.core.entities import Circle, Line, Point
from newsicad.io.dwg_export import (
    DwgExportError,
    _api_key,
    _api_key_file,
    document_to_dwg,
)


def _make_document() -> Document:
    document = Document()
    document.add_entity(Line(layer="0", start=Point(0, 0), end=Point(10, 5)))
    document.add_entity(Circle(layer="0", center=Point(3, 4), radius=2.5))
    return document


# ---------------------------------------------------------------------- #
# _api_key(): resolução da API key (env var > arquivo local > erro claro)
# ---------------------------------------------------------------------- #


def test_api_key_from_env_var(monkeypatch):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "  minha-key-de-teste  ")
    assert _api_key() == "minha-key-de-teste"


def test_api_key_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("NEWSICAD_CLOUDCONVERT_API_KEY", raising=False)
    key_file = tmp_path / "cloudconvert_api_key.txt"
    key_file.write_text("key-do-arquivo\n", encoding="utf-8")
    with patch("newsicad.io.dwg_export._api_key_file", return_value=key_file):
        assert _api_key() == "key-do-arquivo"


def test_api_key_missing_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv("NEWSICAD_CLOUDCONVERT_API_KEY", raising=False)
    missing_file = tmp_path / "does_not_exist.txt"
    with patch("newsicad.io.dwg_export._api_key_file", return_value=missing_file):
        with pytest.raises(DwgExportError, match="API key"):
            _api_key()


def test_api_key_file_resolves_next_to_repo_root_in_dev_mode():
    # newsicad/io/dwg_export.py -> raiz do repo é 3 níveis acima
    key_file = _api_key_file()
    assert key_file.name == "cloudconvert_api_key.txt"
    assert (key_file.parent / "pyproject.toml").exists()


# ---------------------------------------------------------------------- #
# document_to_dwg(): fluxo completo, com requests mockado
# ---------------------------------------------------------------------- #


def _mock_job_response(job_id="job-123"):
    return {
        "data": {
            "id": job_id,
            "tasks": [
                {
                    "name": "upload-dxf",
                    "result": {
                        "form": {
                            "url": "https://upload.example/put",
                            "parameters": {"key": "value"},
                        }
                    },
                }
            ],
        }
    }


def _mock_finished_status(job_id="job-123"):
    return {
        "data": {
            "id": job_id,
            "status": "finished",
            "tasks": [
                {
                    "name": "export-dwg",
                    "status": "finished",
                    "result": {"files": [{"url": "https://download.example/file.dwg"}]},
                }
            ],
        }
    }


def test_document_to_dwg_happy_path(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")
    out_path = tmp_path / "resultado.dwg"

    responses = {
        "post_job": Mock(status_code=201, json=lambda: _mock_job_response()),
        "post_upload": Mock(status_code=201),
        "get_status": Mock(status_code=200, json=lambda: _mock_finished_status()),
        "get_download": Mock(status_code=200, content=b"FAKE DWG BYTES"),
    }

    def fake_post(url, **kwargs):
        if url.endswith("/jobs"):
            return responses["post_job"]
        return responses["post_upload"]

    def fake_get(url, **kwargs):
        if url == "https://download.example/file.dwg":
            return responses["get_download"]
        return responses["get_status"]

    with patch("newsicad.io.dwg_export.requests.post", side_effect=fake_post), patch(
        "newsicad.io.dwg_export.requests.get", side_effect=fake_get
    ), patch("newsicad.io.dwg_export.time.sleep"):
        document_to_dwg(_make_document(), out_path)

    assert out_path.read_bytes() == b"FAKE DWG BYTES"


def test_document_to_dwg_raises_on_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("NEWSICAD_CLOUDCONVERT_API_KEY", raising=False)
    with patch("newsicad.io.dwg_export._api_key_file", return_value=tmp_path / "nope.txt"):
        with pytest.raises(DwgExportError, match="API key"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")


def test_document_to_dwg_raises_on_job_creation_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")
    bad_response = Mock(status_code=422, text="Invalid data")

    with patch("newsicad.io.dwg_export.requests.post", return_value=bad_response):
        with pytest.raises(DwgExportError, match="recusou o pedido"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")


def test_document_to_dwg_raises_on_invalid_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")
    unauthorized = Mock(status_code=401, text="Unauthorized")

    with patch("newsicad.io.dwg_export.requests.post", return_value=unauthorized):
        with pytest.raises(DwgExportError, match="inválida ou expirada"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")


def test_document_to_dwg_raises_on_network_error(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")
    import requests as requests_module

    with patch(
        "newsicad.io.dwg_export.requests.post",
        side_effect=requests_module.ConnectionError("sem internet"),
    ):
        with pytest.raises(DwgExportError, match="conectar ao CloudConvert"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")


def test_document_to_dwg_raises_on_conversion_error_status(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")

    job_response = Mock(status_code=201, json=lambda: _mock_job_response())
    upload_response = Mock(status_code=201)
    error_status = Mock(
        status_code=200,
        json=lambda: {
            "data": {
                "id": "job-123",
                "status": "error",
                "tasks": [
                    {"name": "convert-to-dwg", "status": "error", "message": "arquivo corrompido"}
                ],
            }
        },
    )

    def fake_post(url, **kwargs):
        return job_response if url.endswith("/jobs") else upload_response

    with patch("newsicad.io.dwg_export.requests.post", side_effect=fake_post), patch(
        "newsicad.io.dwg_export.requests.get", return_value=error_status
    ), patch("newsicad.io.dwg_export.time.sleep"):
        with pytest.raises(DwgExportError, match="arquivo corrompido"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")


def test_document_to_dwg_raises_on_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSICAD_CLOUDCONVERT_API_KEY", "fake-key")
    monkeypatch.setattr("newsicad.io.dwg_export._POLL_MAX_ATTEMPTS", 2)

    job_response = Mock(status_code=201, json=lambda: _mock_job_response())
    upload_response = Mock(status_code=201)
    waiting_status = Mock(
        status_code=200,
        json=lambda: {"data": {"id": "job-123", "status": "waiting", "tasks": []}},
    )

    def fake_post(url, **kwargs):
        return job_response if url.endswith("/jobs") else upload_response

    with patch("newsicad.io.dwg_export.requests.post", side_effect=fake_post), patch(
        "newsicad.io.dwg_export.requests.get", return_value=waiting_status
    ), patch("newsicad.io.dwg_export.time.sleep"):
        with pytest.raises(DwgExportError, match="timeout"):
            document_to_dwg(_make_document(), tmp_path / "out.dwg")
