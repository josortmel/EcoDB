"""#1332 (pieza A de #1200): claves de SOLO LECTURA. Una clave con api_keys.read_only solo pasa por una lista
explícita de rutas de lectura (GET y los POST que solo leen, como /search); lo demás da 403, venga la clave tal cual
o cambiada por un JWT en /auth/token. Rotarla da otra de solo lectura. Las claves normales no cambian."""
import asyncio
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
PREFIX = "pytest-sololect-"


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


@pytest.fixture(autouse=True)
def _embed(monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    monkeypatch.setattr(search, "embed_text", _fake_embed)


def _clave(read_only: bool) -> tuple[str, int]:
    plain, h = generate_api_key()
    kid = _sql("INSERT INTO api_keys (key_hash, name, user_id, active, read_only) VALUES ($1, $2, 1, true, $3)"
               " RETURNING id", h, PREFIX + uuid.uuid4().hex[:6], read_only)[0]["id"]
    return plain, kid


@pytest.fixture(scope="module")
def claves(client):
    normal, k1 = _clave(False)
    lectura, k2 = _clave(True)
    jwt_lectura = client.post("/auth/token", json={"api_key": lectura}).json()["access_token"]
    yield {"normal": normal, "lectura": lectura, "jwt_lectura": jwt_lectura}
    _sql("DELETE FROM api_keys WHERE name LIKE $1 OR id = ANY($2::int[])", PREFIX + "%", [k1, k2])
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _memoria(client, tok):
    r = client.post("/memories", headers=_h(tok), json={"type": "observacion", "content": PREFIX + uuid.uuid4().hex,
                                                        "workspace_id": 1, "project_id": 1, "visibility": "public"})
    return r


@pytest.mark.parametrize("quien", ["lectura", "jwt_lectura"])
def test_lee(client, claves, quien):
    mid = _memoria(client, claves["normal"]).json()["id"]
    assert client.get(f"/memories/{mid}", headers=_h(claves[quien])).status_code == 200
    assert client.post("/search", headers=_h(claves[quien]), json={"query_text": "prueba de lectura"}).status_code == 200
    assert client.get("/auth/me", headers=_h(claves[quien])).status_code == 200


@pytest.mark.parametrize("quien", ["lectura", "jwt_lectura"])
def test_no_escribe(client, claves, quien):
    mid = _memoria(client, claves["normal"]).json()["id"]
    tok = claves[quien]
    assert _memoria(client, tok).status_code == 403
    assert client.put(f"/memories/{mid}", headers=_h(tok), json={"content": PREFIX + "cambiada"}).status_code == 403
    assert client.delete(f"/memories/{mid}", headers=_h(tok)).status_code == 403
    assert client.post("/graph/triples", headers=_h(tok),
                       json={"subject": "a", "predicate": "related_to", "object": "b"}).status_code == 403
    assert client.post("/auth/api-keys", headers=_h(tok), json={"user_id": 1, "name": PREFIX + "x"}).status_code == 403
    assert client.get("/admin/graph-vocabulary", headers=_h(tok)).status_code == 403   # admin: fuera aunque sea GET
    assert client.get(f"/memories/{mid}", headers=_h(claves["normal"])).json()["content"].startswith(PREFIX)


def test_la_clave_normal_no_cambia(client, claves):
    r = _memoria(client, claves["normal"])
    assert r.status_code == 201
    assert client.delete(f"/memories/{r.json()['id']}", headers=_h(claves["normal"])).status_code in (200, 204)


def test_rotar_una_de_lectura_da_otra_de_lectura(client, claves):
    """Se rota la clave de un usuario de usar y tirar (rotar desactiva la más antigua si hay más de 3)."""
    uid = _sql("INSERT INTO users (name, is_super, is_ceo, active) VALUES ($1, false, false, true) RETURNING id",
               PREFIX + uuid.uuid4().hex[:6])[0]["id"]
    try:
        plain, h = generate_api_key()
        kid = _sql("INSERT INTO api_keys (key_hash, name, user_id, active, read_only) VALUES ($1, $2, $3, true, true)"
                   " RETURNING id", h, PREFIX + "rotar", uid)[0]["id"]
        r = client.post(f"/auth/api-keys/{kid}/rotate", headers=_h(claves["normal"]), json={})
        assert r.status_code == 201, r.text
        assert _sql("SELECT read_only FROM api_keys WHERE id = $1", r.json()["new_key_id"])[0]["read_only"] is True
        assert _memoria(client, r.json()["new_api_key"]).status_code == 403
    finally:
        _sql("DELETE FROM api_keys WHERE user_id = $1", uid)
        _sql("DELETE FROM users WHERE id = $1", uid)
