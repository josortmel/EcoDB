"""ECODB_API_URL con http:// solo vale para hosts internos; ECODB_INTERNAL_HOSTS añade los de una red propia.

La comprobación se hace al importar server.py, así que cada caso importa el módulo en un proceso aparte.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parent.parent


def _importar(api_url: str, extra_hosts: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "ECODB_INTERNAL_HOSTS"}
    env.update(ECODB_API_URL=api_url, ECODB_API_KEY="clave-de-prueba", MCP_TRANSPORT="stdio")
    if extra_hosts is not None:
        env["ECODB_INTERNAL_HOSTS"] = extra_hosts
    return subprocess.run([sys.executable, "-c", "import server"], cwd=MCP_DIR, env=env,
                          capture_output=True, text=True, timeout=120)


def test_http_a_un_host_no_interno_se_rechaza():
    r = _importar("http://dind:8080", None)
    assert r.returncode != 0
    assert "solo permitido a hosts internos" in r.stderr


def test_ecodb_internal_hosts_admite_el_host_listado():
    r = _importar("http://dind:8080", "dind")
    assert r.returncode == 0, r.stderr[-500:]


@pytest.mark.parametrize("lista", ["otro", "otro, mas", ""])
def test_un_host_no_listado_sigue_rechazado(lista):
    r = _importar("http://dind:8080", lista)
    assert r.returncode != 0
    assert "solo permitido a hosts internos" in r.stderr


def test_la_lista_ignora_espacios_y_mayusculas():
    r = _importar("http://dind:8080", " otro , DIND ")
    assert r.returncode == 0, r.stderr[-500:]


def test_los_internos_de_siempre_siguen_valiendo():
    r = _importar("http://localhost:8080", None)
    assert r.returncode == 0, r.stderr[-500:]
