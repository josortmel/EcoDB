"""#569: save_triple(s) tells the agent what it asked for and what was stored,
and always sends the requested predicate to the API (also when it is unchanged).

Prima's cases (16-oct and 22-oct): the dictionary swapped the predicate without
saying so ("was_investigated_on" -> "supervisa"). Choosing a better predicate is
NOT in scope (that goes to the EcoDB redesign); this only makes the swap visible
and recorded. Offline: httpx mocked with respx, no API, no DB.
"""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
import respx

SERVER = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
API = "http://localhost:8080"

# pedido -> (lo que devuelve el diccionario, confianza)
MAPPING = {
    "was_investigated_on": ("supervisa", 0.72),
    "has_hypothesis": ("habilita", 0.74),
    "removed": ("reemplaza", 0.71),
    "archived_in_faro_session": ("lidera", 0.70),
    "proposes_next_workflow": ("itera_de", 0.73),
    "depende_de": ("depende_de", 1.0),  # sin cambio: también se guarda el pedido
}


@pytest.fixture
def mod(monkeypatch):
    monkeypatch.setenv("ECODB_API_URL", API)
    monkeypatch.setenv("ECODB_API_KEY", "ecodb_test")
    spec = importlib.util.spec_from_file_location("ecodb_mcp_server_569", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._jwt = None
    return m


def _resolve(request):
    pred = request.url.params["predicate"]
    canonical, conf = MAPPING[pred]
    return httpx.Response(200, json={"canonical": canonical, "confidence": conf, "method": "embedding"})


def _mock_common():
    respx.post(f"{API}/auth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "jwt", "expires_in": 3600}))
    respx.get(f"{API}/graph/predicates/aliases").mock(return_value=httpx.Response(200, json={"aliases": []}))
    respx.get(f"{API}/graph/predicates/resolve").mock(side_effect=_resolve)


@respx.mock
@pytest.mark.parametrize("requested", list(MAPPING))
def test_save_triple_reports_and_sends_requested_predicate(mod, requested):
    _mock_common()
    stored = MAPPING[requested][0]
    post = respx.post(f"{API}/graph/triples").mock(return_value=httpx.Response(201, json={
        "id": 7, "subject_id": 1, "subject_name": "A", "predicate": stored,
        "object_id": 2, "object_name": "B", "author": None}))

    out = mod.save_triple("A", requested, "B")

    sent = json.loads(post.calls.last.request.content)
    assert sent["predicate"] == stored
    assert sent["original_predicate"] == requested          # (2) siempre, también si no cambia
    assert out["requested_predicate"] == requested          # (1) el agente ve lo que pidió...
    assert out["stored_predicate"] == stored                # ...y lo que se guardó


@respx.mock
def test_save_triples_batch_reports_each_triple(mod):
    _mock_common()
    cases = list(MAPPING)
    created = [{"id": i, "subject_id": 1, "subject_name": f"S{i}", "predicate": MAPPING[req][0],
                "object_id": 2, "object_name": f"O{i}", "author": None, "original_predicate": req}
               for i, req in enumerate(cases)]
    post = respx.post(f"{API}/graph/triples/batch").mock(
        return_value=httpx.Response(201, json={"created": created, "skipped_duplicates": 0}))

    out = mod.save_triples_batch([{"subject": f"S{i}", "predicate": req, "object": f"O{i}"}
                                  for i, req in enumerate(cases)])

    sent = json.loads(post.calls.last.request.content)["triples"]
    assert [t["original_predicate"] for t in sent] == cases
    assert out["count"] == len(cases)
    assert [(t["requested_predicate"], t["stored_predicate"]) for t in out["triples"]] == \
        [(req, MAPPING[req][0]) for req in cases]
