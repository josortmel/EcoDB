"""#919: save_memory del MCP reenvía supersedes y compañía a la API solo cuando vienen."""
import os
import sys
from pathlib import Path

os.environ.setdefault("ECODB_API_URL", "http://localhost:8080")
os.environ.setdefault("ECODB_API_KEY", "clave-de-prueba")
os.environ.setdefault("MCP_TRANSPORT", "stdio")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


def _captura(monkeypatch):
    enviados = []

    def falso(method, path, **kw):
        enviados.append((method, path, kw.get("json")))
        return {"id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(server, "_api_call", falso)
    return enviados


def _fn(tool):
    return getattr(tool, "fn", tool)


def test_supersedes_y_compania_llegan_a_la_api(monkeypatch):
    enviados = _captura(monkeypatch)
    _fn(server.save_memory)(content="nueva", type="decision", supersedes=["a", "b"],
                            supersede_kind="parcial", supersede_reason="cambia el horario",
                            valid_until="2026-12-31", decidido_por={"tipo": "humano", "quien": "Pepe"})
    payload = [p for m, path, p in enviados if path == "/memories"][-1]
    assert payload["supersedes"] == ["a", "b"]
    assert payload["supersede_kind"] == "parcial"
    assert payload["supersede_reason"] == "cambia el horario"
    assert payload["valid_until"] == "2026-12-31"
    assert payload["decidido_por"] == {"tipo": "humano", "quien": "Pepe"}


def test_sin_ellos_el_payload_no_cambia(monkeypatch):
    enviados = _captura(monkeypatch)
    _fn(server.save_memory)(content="sola", type="observacion")
    payload = [p for m, path, p in enviados if path == "/memories"][-1]
    for k in ("supersedes", "supersede_kind", "supersede_reason", "valid_until", "decidido_por"):
        assert k not in payload
