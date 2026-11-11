"""#919 H1 (decisiones vigentes): save_memory(supersedes=[…]) marca las memorias que sustituye.

La marca va en metadata de la memoria VIEJA (superseded_by, supersede_kind, supersede_reason,
marked_by) y la escribe la API con el usuario que guarda. La nueva lleva valid_until y decidido_por.
Contra la Postgres de pruebas (5436); embeddings sustituidos.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

import memories  # noqa: E402
from auth import generate_api_key  # noqa: E402
from main import create_app  # noqa: E402

FAKE_VEC = "[" + ",".join(["0.01"] * 512) + "]"
PREFIX = "pytest-supersede-"


async def _fake_embed(*_a, **_k):
    return FAKE_VEC


def _sql(q, *args):
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetch(q, *args)
        finally:
            await conn.close()
    return asyncio.run(run())


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app("development")) as c:
        yield c


@pytest.fixture(scope="module")
def jwt(client):
    key_plain, key_hash = generate_api_key()
    key_id = _sql("INSERT INTO api_keys (key_hash, name, user_id, active) "
                  "VALUES ($1, 'pytest-supersede', 1, true) RETURNING id", key_hash)[0]["id"]
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _sql("DELETE FROM api_keys WHERE id = $1", key_id)
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")


@pytest.fixture(scope="module")
def agentes():
    """Dos agentes de la base de pruebas, para autora y no autora."""
    filas = _sql("SELECT identifier FROM agents ORDER BY id LIMIT 2")
    if len(filas) < 2:
        pytest.skip("la base de pruebas necesita al menos dos agentes")
    return filas[0]["identifier"], filas[1]["identifier"]


@pytest.fixture(autouse=True)
def _embed(monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)


def _post(client, jwt, **extra):
    body = {"type": "decision", "content": PREFIX + uuid.uuid4().hex,
            "workspace_id": 1, "project_id": 1, **extra}
    return client.post("/memories", headers={"Authorization": f"Bearer {jwt}"}, json=body)


def _meta(mem_id):
    raw = _sql("SELECT metadata FROM memories WHERE id = $1", uuid.UUID(str(mem_id)))[0]["metadata"]
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _cuenta_prefijo():
    return _sql("SELECT count(*) AS n FROM memories WHERE content LIKE $1", PREFIX + "%")[0]["n"]


def test_supersedes_marca_la_vieja_con_quien_y_cuando(client, jwt, agentes):
    a, _ = agentes
    vieja = _post(client, jwt, agent_identifier=a).json()["id"]
    r = _post(client, jwt, agent_identifier=a, supersedes=[vieja], supersede_reason="la cambió Pepe")
    assert r.status_code == 201, r.text
    nueva = r.json()["id"]
    m = _meta(vieja)
    assert m["superseded_by"] == nueva
    assert m["supersede_kind"] == "total"
    assert m["supersede_reason"] == "la cambió Pepe"
    assert m["marked_by"]["user_id"] == 1 and m["marked_by"]["agent"] == a and m["marked_by"]["at"]


def test_la_nueva_guarda_valid_until_y_decidido_por(client, jwt):
    r = _post(client, jwt, valid_until="2026-12-31",
              decidido_por={"tipo": "humano", "quien": "Pepe"})
    assert r.status_code == 201, r.text
    m = _meta(r.json()["id"])
    assert m["valid_until"] == "2026-12-31"
    assert m["decidido_por"] == {"tipo": "humano", "quien": "Pepe"}


def test_supersedes_a_una_que_no_existe_no_crea_nada(client, jwt):
    antes = _cuenta_prefijo()
    r = _post(client, jwt, supersedes=[str(uuid.uuid4())])
    assert r.status_code == 422
    assert "does not exist or is not yours" in r.text
    assert _cuenta_prefijo() == antes


def test_supersedes_a_una_ya_superada_es_409_y_no_crea_nada(client, jwt):
    vieja = _post(client, jwt).json()["id"]
    assert _post(client, jwt, supersedes=[vieja]).status_code == 201
    antes = _cuenta_prefijo()
    r = _post(client, jwt, supersedes=[vieja])
    assert r.status_code == 409
    assert _cuenta_prefijo() == antes


def test_nunca_valida_solo_la_autora(client, jwt, agentes):
    autora, otra = agentes
    vieja = _post(client, jwt, agent_identifier=autora).json()["id"]
    r = _post(client, jwt, agent_identifier=otra, supersedes=[vieja], supersede_kind="nunca_valida")
    assert r.status_code == 403
    assert "superseded_by" not in _meta(vieja)
    r = _post(client, jwt, agent_identifier=autora, supersedes=[vieja], supersede_kind="nunca_valida")
    assert r.status_code == 201, r.text
    assert _meta(vieja)["supersede_kind"] == "nunca_valida"


@pytest.mark.parametrize("extra", [{"supersede_kind": "total"}, {"supersede_reason": "x"}])
def test_tipo_o_motivo_sin_supersedes_es_422(client, jwt, extra):
    r = _post(client, jwt, **extra)
    assert r.status_code == 422
    assert "need supersedes" in r.text


def test_no_se_puede_sustituir_a_si_misma_ni_repetir(client, jwt):
    vieja = _post(client, jwt).json()["id"]
    r = _post(client, jwt, supersedes=[vieja, vieja])
    assert r.status_code == 422
    assert "repeats an id" in r.text
