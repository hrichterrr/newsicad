"""Ponte de ESCRITA Document → .dwg via CloudConvert (API em nuvem).

LibreDWG (gravador `dxf2dwg`, usado só para leitura em dwg_bridge.py) tem um
bug de handle duplicado ainda aberto upstream (libredwg#192, aberto desde
2020) que o torna inviável para escrita — ver dwg_bridge.py e a seção
"Arquivos .dwg" do README para o histórico completo. O ODA File Converter
resolveria a escrita, mas seu EULA proíbe embutir o binário em outro
software distribuído, mesmo pra uso interno (é uma restrição de
redistribuição, separada da de uso comercial). QCAD (open source) não tem
suporte a .dwg na edição livre. Aspose.CAD resolveria mas é uma licença paga
recorrente.

Este módulo usa o CloudConvert (cloudconvert.com) em vez disso: nenhum
binário pra empacotar ou instalar, só chamadas HTTP (upload do .dxf →
conversão → download do .dwg). Ao contrário da ODA, os termos do
CloudConvert permitem explicitamente esse uso embutido. Troca real:
precisa de internet no momento da exportação, e o desenho sai da máquina
até o servidor deles — aceito conscientemente (ver conversa/plano do
projeto), já que o uso é interno/arquivo.

A versão de saída do .dwg não é configurável aqui: o engine do CloudConvert
usado pra dxf→dwg ("cadconverter") não expõe um parâmetro documentado de
versão de destino. Testado empiricamente: produz DWG assinatura "AC1018"
(AutoCAD 2004), uma versão amplamente compatível com qualquer AutoCAD/
BricsCAD atual.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import requests

from newsicad.core.document import Document
from newsicad.io.dxf_io import save_dxf

API_BASE = "https://api.cloudconvert.com/v2"
_POLL_INTERVAL_SECONDS = 2
_POLL_MAX_ATTEMPTS = 60  # ~2 minutos de espera no total
_REQUEST_TIMEOUT_SECONDS = 30
_UPLOAD_TIMEOUT_SECONDS = 120
_DOWNLOAD_TIMEOUT_SECONDS = 120

_API_KEY_ENV_VAR = "NEWSICAD_CLOUDCONVERT_API_KEY"
_API_KEY_FILENAME = "cloudconvert_api_key.txt"


class DwgExportError(RuntimeError):
    pass


def _api_key_file() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Empacotado: ao lado do NewSIcad.exe, pra Hamilton poder colocar a
        # key sem precisar reconstruir o .exe (mesma pasta dist/NewSIcad/).
        base = Path(sys.executable).resolve().parent
    else:
        # newsicad/io/dwg_export.py -> parent.parent.parent = raiz do repo
        base = Path(__file__).resolve().parent.parent.parent
    return base / _API_KEY_FILENAME


def _api_key() -> str:
    env_key = os.environ.get(_API_KEY_ENV_VAR)
    if env_key and env_key.strip():
        return env_key.strip()

    key_file = _api_key_file()
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key

    raise DwgExportError(
        "Exportação .dwg precisa de uma API key do CloudConvert. Configure a "
        f"variável de ambiente {_API_KEY_ENV_VAR} ou crie o arquivo "
        f"'{_API_KEY_FILENAME}' em {key_file.parent} com a key (gerada em "
        "cloudconvert.com > Dashboard > API v2 > Keys)."
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}"}


def document_to_dwg(document: Document, path: str | Path) -> None:
    """Exporta o Document pra um .dwg real via CloudConvert. Precisa de
    internet — levanta DwgExportError com uma mensagem clara pra qualquer
    falha (sem internet, API key inválida, limite do plano, timeout etc.)."""
    path = Path(path)
    headers = _headers()

    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "export.dxf"
        save_dxf(document, dxf_path)

        job = _create_job(headers)
        _upload_file(job, dxf_path)
        result = _wait_for_completion(job["id"], headers)
        _download_result(result, path)


def _create_job(headers: dict[str, str]) -> dict:
    payload = {
        "tasks": {
            "upload-dxf": {"operation": "import/upload"},
            "convert-to-dwg": {
                "operation": "convert",
                "input": "upload-dxf",
                "input_format": "dxf",
                "output_format": "dwg",
            },
            "export-dwg": {"operation": "export/url", "input": "convert-to-dwg"},
        }
    }
    try:
        response = requests.post(
            f"{API_BASE}/jobs", headers=headers, json=payload, timeout=_REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise DwgExportError(f"Não foi possível conectar ao CloudConvert: {exc}") from exc

    if response.status_code == 401:
        raise DwgExportError("API key do CloudConvert inválida ou expirada.")
    if response.status_code >= 400:
        raise DwgExportError(f"CloudConvert recusou o pedido de exportação: {response.text}")

    return response.json()["data"]


def _upload_file(job: dict, dxf_path: Path) -> None:
    upload_task = next(t for t in job["tasks"] if t["name"] == "upload-dxf")
    form = upload_task["result"]["form"]
    try:
        with open(dxf_path, "rb") as f:
            response = requests.post(
                form["url"],
                data=form["parameters"],
                files={"file": (dxf_path.name, f)},
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            )
    except requests.RequestException as exc:
        raise DwgExportError(f"Falha no upload do desenho pro CloudConvert: {exc}") from exc

    if response.status_code >= 400:
        raise DwgExportError(
            f"CloudConvert recusou o upload do arquivo (HTTP {response.status_code})."
        )


def _wait_for_completion(job_id: str, headers: dict[str, str]) -> dict:
    url = f"{API_BASE}/jobs/{job_id}"
    for _ in range(_POLL_MAX_ATTEMPTS):
        time.sleep(_POLL_INTERVAL_SECONDS)
        try:
            response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise DwgExportError(
                f"Não foi possível verificar o status da conversão: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise DwgExportError(
                f"CloudConvert recusou a consulta de status (HTTP {response.status_code})."
            )

        data = response.json()["data"]
        status = data["status"]
        if status == "finished":
            return data
        if status == "error":
            failed_task = next((t for t in data["tasks"] if t["status"] == "error"), None)
            message = failed_task["message"] if failed_task else "erro desconhecido"
            raise DwgExportError(f"A conversão falhou no CloudConvert: {message}")

    raise DwgExportError(
        "A conversão no CloudConvert demorou demais e não terminou a tempo (timeout)."
    )


def _download_result(job_data: dict, path: Path) -> None:
    export_task = next(t for t in job_data["tasks"] if t["name"] == "export-dwg")
    files = export_task["result"]["files"]
    if not files:
        raise DwgExportError("CloudConvert terminou a conversão mas não retornou nenhum arquivo.")

    try:
        response = requests.get(files[0]["url"], timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise DwgExportError(f"Falha ao baixar o .dwg convertido: {exc}") from exc

    if response.status_code >= 400:
        raise DwgExportError(
            f"Falha ao baixar o .dwg convertido (HTTP {response.status_code})."
        )

    try:
        path.write_bytes(response.content)
    except OSError as exc:
        # A conversão em si já tinha terminado com sucesso nesse ponto — só
        # a gravação local falhou (ex.: arquivo de destino aberto em outro
        # programa, disco cheio, permissão negada). Sem isso, esse erro
        # subia cru até a UI em vez do QMessageBox amigável que
        # `MainWindow._export_dwg` já mostra pra qualquer DwgExportError
        # (bug real de auditoria, 2026-08-22 — o único caminho de exceção
        # deste módulo que ainda não virava DwgExportError).
        raise DwgExportError(f"Conversão concluída, mas falhou ao salvar o .dwg em disco: {exc}") from exc
