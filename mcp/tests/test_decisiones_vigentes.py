"""#919: la herramienta decisiones_vigentes del MCP solo llama a GET /api/v1/decisiones/vigentes.

La lógica vive en la API (api/vigentes.py). El MCP no se queda con una copia: si volviera a
existir mcp/vigentes.py, este test lo dice.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ECODB_API_URL", "http://localhost:8080")
os.environ.setdefault("ECODB_API_KEY", "clave-de-prueba")
os.environ.setdefault("MCP_TRANSPORT", "stdio")

import server  # noqa: E402

MCP = Path(__file__).resolve().parent.parent


def _llamar(monkeypatch, **kw):
    llamadas = []

    def falsa(method, path, **k):
        llamadas.append((method, path, k.get("params")))
        return {"vigentes": [{"id": "C", "sustituye_a": ["A", "B"]}], "errores": [], "avisos": []}

    monkeypatch.setattr(server, "_api_call", falsa)
    fn = getattr(server.decisiones_vigentes, "fn", server.decisiones_vigentes)
    r = fn(**kw)
    return r.get("data", r), llamadas


def test_llama_al_endpoint_con_sus_parametros(monkeypatch):
    datos, llamadas = _llamar(monkeypatch, tema="horario de la tienda", agente="Hilo",
                              incluir_superadas=True, limit=7)
    assert llamadas == [("GET", "/api/v1/decisiones/vigentes",
                         {"tema": "horario de la tienda", "incluir_superadas": "true", "limit": 7,
                          "agente": "Hilo"})]
    assert datos["vigentes"][0]["id"] == "C"


def test_sin_agente_no_manda_agente_y_el_limit_se_ajusta(monkeypatch):
    _, llamadas = _llamar(monkeypatch, tema="horario de la tienda", limit=500)
    assert llamadas[0][2] == {"tema": "horario de la tienda", "incluir_superadas": "false", "limit": 50}


def test_el_mcp_no_tiene_copia_de_la_logica():
    assert not (MCP / "vigentes.py").exists()
