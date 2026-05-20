"""Tests integración — CRUD grafo SQL+AGE contra postgres real."""
import asyncio
import os
import sys
from pathlib import Path

import pytest
import asyncpg
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app
from auth import generate_api_key


@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def super_jwt(client):
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-graph', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(key_id):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)
            # Cleanup grafo: AGE + SQL
            await conn.execute(
                "SELECT * FROM cypher('ecodb_graph', $$ MATCH (n:Entity) WHERE n.name STARTS WITH 'pytest-' DETACH DELETE n RETURN 1 $$) AS (ok agtype)"
            )
            await conn.execute("DELETE FROM triples WHERE author = 'pytest-graph'")
            await conn.execute("DELETE FROM nodes WHERE name LIKE 'pytest-%'")
        finally:
            await conn.close()

    key_id = asyncio.run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    asyncio.run(_cleanup(key_id))


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ---------------------------------------------------------------------------
# POST /graph/triples
# ---------------------------------------------------------------------------

def test_create_triple_creates_nodes_and_edge(client, super_jwt):
    r = client.post(
        "/graph/triples",
        headers=auth(super_jwt),
        json={"subject": "pytest-A", "predicate": "rel1", "object": "pytest-B", "author": "pytest-graph"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["subject_name"] == "pytest-A"
    assert body["object_name"] == "pytest-B"
    assert body["predicate"] == "rel1"


def test_create_duplicate_triple_returns_409(client, super_jwt):
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-X", "predicate": "rel-dup", "object": "pytest-Y", "author": "pytest-graph"})
    r = client.post("/graph/triples", headers=auth(super_jwt),
                    json={"subject": "pytest-X", "predicate": "rel-dup", "object": "pytest-Y", "author": "pytest-graph"})
    assert r.status_code == 409


def test_create_triple_with_null_byte_returns_422(client, super_jwt):
    r = client.post(
        "/graph/triples",
        headers=auth(super_jwt),
        json={"subject": "pytest-NB\x00", "predicate": "x", "object": "y"},
    )
    assert r.status_code == 422


def test_create_triple_without_auth_returns_401(client):
    r = client.post("/graph/triples", json={"subject": "x", "predicate": "y", "object": "z"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /graph/triples/batch
# ---------------------------------------------------------------------------

def test_batch_creates_multiple_triples(client, super_jwt):
    r = client.post(
        "/graph/triples/batch",
        headers=auth(super_jwt),
        json={"triples": [
            {"subject": "pytest-batch-1", "predicate": "p1", "object": "pytest-batch-2", "author": "pytest-graph"},
            {"subject": "pytest-batch-2", "predicate": "p2", "object": "pytest-batch-3", "author": "pytest-graph"},
        ]},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["created"]) == 2
    assert body["skipped_duplicates"] == 0


def test_batch_skips_duplicates(client, super_jwt):
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-D1", "predicate": "p", "object": "pytest-D2", "author": "pytest-graph"})
    r = client.post(
        "/graph/triples/batch",
        headers=auth(super_jwt),
        json={"triples": [
            {"subject": "pytest-D1", "predicate": "p", "object": "pytest-D2", "author": "pytest-graph"},
            {"subject": "pytest-D1", "predicate": "p", "object": "pytest-D3", "author": "pytest-graph"},
        ]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["skipped_duplicates"] == 1
    assert len(body["created"]) == 1


def test_batch_too_large_returns_422(client, super_jwt):
    too_many = [{"subject": f"pytest-x-{i}", "predicate": "r", "object": f"pytest-y-{i}"} for i in range(150)]
    r = client.post("/graph/triples/batch", headers=auth(super_jwt), json={"triples": too_many})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /graph/neighbors
# ---------------------------------------------------------------------------

def test_neighbors_depth_1(client, super_jwt):
    # Crear pytest-N1 → pytest-N2 → pytest-N3
    client.post("/graph/triples/batch", headers=auth(super_jwt), json={"triples": [
        {"subject": "pytest-N1", "predicate": "p", "object": "pytest-N2", "author": "pytest-graph"},
        {"subject": "pytest-N2", "predicate": "p", "object": "pytest-N3", "author": "pytest-graph"},
    ]})
    r = client.get("/graph/neighbors/pytest-N1?depth=1", headers=auth(super_jwt))
    assert r.status_code == 200
    assert "pytest-N2" in r.json()["neighbors"]
    assert "pytest-N3" not in r.json()["neighbors"]  # depth=1 no llega


def test_neighbors_depth_2(client, super_jwt):
    r = client.get("/graph/neighbors/pytest-N1?depth=2", headers=auth(super_jwt))
    assert r.status_code == 200
    neighbors = r.json()["neighbors"]
    assert "pytest-N2" in neighbors
    assert "pytest-N3" in neighbors


def test_neighbors_max_depth(client, super_jwt):
    r = client.get("/graph/neighbors/pytest-N1?depth=10", headers=auth(super_jwt))
    assert r.status_code == 422  # le=5


# ---------------------------------------------------------------------------
# GET /graph/path
# ---------------------------------------------------------------------------

def test_path_finds_route(client, super_jwt):
    client.post("/graph/triples/batch", headers=auth(super_jwt), json={"triples": [
        {"subject": "pytest-P1", "predicate": "r", "object": "pytest-P2", "author": "pytest-graph"},
        {"subject": "pytest-P2", "predicate": "r", "object": "pytest-P3", "author": "pytest-graph"},
    ]})
    r = client.get("/graph/path?source=pytest-P1&target=pytest-P3", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == ["pytest-P1", "pytest-P2", "pytest-P3"]
    assert body["length"] == 2


def test_path_unreachable_returns_404(client, super_jwt):
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-isolated-1", "predicate": "r", "object": "pytest-isolated-2", "author": "pytest-graph"})
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-island-A", "predicate": "r", "object": "pytest-island-B", "author": "pytest-graph"})
    r = client.get("/graph/path?source=pytest-isolated-1&target=pytest-island-A", headers=auth(super_jwt))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /graph/search (pg_trgm)
# ---------------------------------------------------------------------------

def test_search_finds_similar_node(client, super_jwt):
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-Cervantes", "predicate": "r", "object": "pytest-Quijote", "author": "pytest-graph"})
    r = client.get("/graph/search?q=Cerv", headers=auth(super_jwt))
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert any("pytest-Cervantes" in m["name"] for m in matches)


def test_search_min_3_chars(client, super_jwt):
    """VS2 (adv-seg): q < 3 chars rechazado para evitar seq scan sobre nodes."""
    r = client.get("/graph/search?q=a", headers=auth(super_jwt))
    assert r.status_code == 422


def test_neighbors_inexistent_node_returns_404(client, super_jwt):
    """OBS-2 (verificador): nodo inexistente → 404, no 200 con lista vacía."""
    r = client.get("/graph/neighbors/pytest-NOEXISTE-123", headers=auth(super_jwt))
    assert r.status_code == 404


def test_path_self_returns_zero_length(client, super_jwt):
    """OBS-1 (verificador): path A→A es trivial length=0, no 404."""
    client.post("/graph/triples", headers=auth(super_jwt),
                json={"subject": "pytest-SELF-1", "predicate": "r", "object": "pytest-other", "author": "pytest-graph"})
    r = client.get("/graph/path?source=pytest-SELF-1&target=pytest-SELF-1", headers=auth(super_jwt))
    assert r.status_code == 200
    assert r.json() == {"source": "pytest-SELF-1", "target": "pytest-SELF-1", "path": ["pytest-SELF-1"], "length": 0}


# ---------------------------------------------------------------------------
# DELETE /graph/triples/{id}
# ---------------------------------------------------------------------------

def test_delete_triple_removes_from_sql_and_age(client, super_jwt):
    created = client.post("/graph/triples", headers=auth(super_jwt),
                          json={"subject": "pytest-DEL-S", "predicate": "todelete", "object": "pytest-DEL-O", "author": "pytest-graph"}).json()
    r = client.delete(f"/graph/triples/{created['id']}", headers=auth(super_jwt))
    assert r.status_code == 204
    # Re-DELETE → 404
    r2 = client.delete(f"/graph/triples/{created['id']}", headers=auth(super_jwt))
    assert r2.status_code == 404


def test_delete_inexistent_triple_returns_404(client, super_jwt):
    r = client.delete("/graph/triples/999999999", headers=auth(super_jwt))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /graph/stats
# ---------------------------------------------------------------------------

def test_stats_returns_counts(client, super_jwt):
    r = client.get("/graph/stats", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] >= 1
    assert body["triples"] >= 1
    assert body["distinct_predicates"] >= 1
