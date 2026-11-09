"""#919 H2: search avisa de que una memoria está superada (o caducada) y NO cambia su puntuación.

Pepe, 16-oct: se avisa, no se esconde. Contra la Postgres de pruebas (5436); embeddings sustituidos
(todas las memorias con el mismo vector) y reranker apagado, para que la comparación sea limpia.
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
import search  # noqa: E402
from auth import generate_api_key  # noqa: E402
from main import create_app  # noqa: E402

FAKE_VEC = "[" + ",".join(["0.01"] * 512) + "]"
PREFIX = "pytest-vigencia-"


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
                  "VALUES ($1, 'pytest-vigencia', 1, true) RETURNING id", key_hash)[0]["id"]
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _sql("DELETE FROM api_keys WHERE id = $1", key_id)
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")


@pytest.fixture(autouse=True)
def _embed(monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    monkeypatch.setattr(search, "embed_text", _fake_embed)


def _post(client, jwt, tag, **extra):
    body = {"type": "decision", "content": PREFIX + uuid.uuid4().hex, "workspace_id": 1,
            "project_id": 1, "tags": [tag], **extra}
    r = client.post("/memories", headers={"Authorization": f"Bearer {jwt}"}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _buscar(client, jwt, tag):
    r = client.post("/search", headers={"Authorization": f"Bearer {jwt}"}, json={
        "query_text": "decisión de prueba de vigencia", "tags": [tag], "limit": 10,
        "rerank_mode": "off", "include_documents": False})
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()["results"]}


def test_la_superada_sale_con_su_aviso_y_la_misma_puntuacion(client, jwt):
    tag = "pytest-vig-" + uuid.uuid4().hex[:8]
    vieja = _post(client, jwt, tag)
    nueva = _post(client, jwt, tag, supersedes=[vieja])

    con_marca = _buscar(client, jwt, tag)
    assert vieja in con_marca, "la superada no se esconde"
    assert f"superada por {nueva}" in con_marca[vieja]["trust_warnings"]
    assert not any(w.startswith("superada") for w in con_marca[nueva]["trust_warnings"])

    _sql("UPDATE memories SET metadata = metadata - 'superseded_by' - 'supersede_kind' - 'marked_by' "
         "WHERE id = $1", uuid.UUID(vieja))
    sin_marca = _buscar(client, jwt, tag)
    assert not any(w.startswith("superada") for w in sin_marca[vieja]["trust_warnings"])
    assert con_marca[vieja]["score"] == pytest.approx(sin_marca[vieja]["score"], abs=1e-6)


def test_una_caducada_lleva_aviso(client, jwt):
    tag = "pytest-vig-" + uuid.uuid4().hex[:8]
    mid = _post(client, jwt, tag, valid_until="2026-01-01")
    assert "caducada el 2026-01-01" in _buscar(client, jwt, tag)[mid]["trust_warnings"]


def test_el_tipo_parcial_se_nombra(client, jwt):
    tag = "pytest-vig-" + uuid.uuid4().hex[:8]
    vieja = _post(client, jwt, tag)
    nueva = _post(client, jwt, tag, supersedes=[vieja], supersede_kind="parcial")
    assert f"superada por {nueva} (parcial)" in _buscar(client, jwt, tag)[vieja]["trust_warnings"]
