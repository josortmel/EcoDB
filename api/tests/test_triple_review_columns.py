"""#569: the API stores what the predicate mapper decided, not just its output.

The MCP sends original_predicate / mapper_confidence / needs_review with every
triple, but TripleCreate did not declare them, so pydantic dropped them and the
INSERT never wrote them: no triple saved through the MCP ever kept the predicate
the agent asked for, and list_needs_review could never fill up. The columns
existed only in production (added by scripts/, no migration), so the test DB
could not catch it either. Cases are Prima's from 16-oct and 22-oct.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app
from auth import generate_api_key

AUTHOR = "pytest-569"

# (pedido por el agente, guardado por el diccionario) — casos reales de Prima.
PRIMA_CASES = [
    ("was_investigated_on", "supervisa"),
    ("has_hypothesis", "habilita"),
    ("removed", "reemplaza"),
    ("archived_in_faro_session", "lidera"),
    ("proposes_next_workflow", "itera_de"),
]


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app("development")) as c:
        yield c


@pytest.fixture(scope="module")
def jwt(client):
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetchval(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-569', 1, true) RETURNING id", key_hash)
        finally:
            await conn.close()

    async def _cleanup(key_id):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)
            await conn.execute(
                "SELECT * FROM cypher('ecodb_graph', $$ MATCH (n:Entity) WHERE n.name STARTS WITH "
                "'pytest-569-' DETACH DELETE n RETURN 1 $$) AS (ok agtype)")
            await conn.execute("DELETE FROM triples WHERE author = $1", AUTHOR)
            await conn.execute("DELETE FROM nodes WHERE name LIKE 'pytest-569-%'")
        finally:
            await conn.close()

    key_id = asyncio.run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}
    asyncio.run(_cleanup(key_id))


def _row(triple_id):
    async def _q():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetchrow(
                "SELECT predicate, original_predicate, mapper_confidence, needs_review "
                "FROM triples WHERE id = $1", triple_id)
        finally:
            await conn.close()
    return asyncio.run(_q())


@pytest.mark.parametrize("requested,stored", PRIMA_CASES)
def test_single_triple_keeps_requested_predicate(client, jwt, requested, stored):
    r = client.post("/graph/triples", headers=jwt, json={
        "subject": f"pytest-569-s-{requested}", "predicate": stored,
        "object": f"pytest-569-o-{requested}", "author": AUTHOR,
        "original_predicate": requested, "mapper_confidence": 0.71, "needs_review": False,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["predicate"] == stored
    assert body["original_predicate"] == requested
    row = _row(body["id"])
    assert row["predicate"] == stored
    assert row["original_predicate"] == requested
    assert row["mapper_confidence"] == pytest.approx(0.71)
    assert row["needs_review"] is False


def test_needs_review_is_stored(client, jwt):
    r = client.post("/graph/triples", headers=jwt, json={
        "subject": "pytest-569-rev-s", "predicate": "rel_desconocida", "object": "pytest-569-rev-o",
        "author": AUTHOR, "original_predicate": "rel desconocida", "mapper_confidence": 0.0,
        "needs_review": True,
    })
    assert r.status_code == 201, r.text
    assert _row(r.json()["id"])["needs_review"] is True


def test_batch_keeps_requested_predicate_per_triple(client, jwt):
    triples = [{
        "subject": f"pytest-569-b-s-{req}", "predicate": st, "object": f"pytest-569-b-o-{req}",
        "author": AUTHOR, "original_predicate": req, "mapper_confidence": 0.7,
    } for req, st in PRIMA_CASES]
    r = client.post("/graph/triples/batch", headers=jwt, json={"triples": triples})
    assert r.status_code == 201, r.text
    created = r.json()["created"]
    assert [(t["original_predicate"], t["predicate"]) for t in created] == PRIMA_CASES
    for t in created:
        assert _row(t["id"])["original_predicate"] == t["original_predicate"]


def test_old_clients_without_the_fields_still_work(client, jwt):
    r = client.post("/graph/triples", headers=jwt, json={
        "subject": "pytest-569-old-s", "predicate": "rel_vieja", "object": "pytest-569-old-o",
        "author": AUTHOR})
    assert r.status_code == 201, r.text
    row = _row(r.json()["id"])
    assert row["original_predicate"] is None
    assert row["needs_review"] is False
