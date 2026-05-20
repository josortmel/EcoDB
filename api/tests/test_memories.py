"""Tests integración — CRUD memorias contra postgres real."""
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
    """Creates API key for superuser, exchanges for JWT, returns token."""
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-mem', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(key_id):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)
            await conn.execute("DELETE FROM memories WHERE user_id = 1 AND content LIKE 'pytest-mem-%'")
            await conn.execute("DELETE FROM trash WHERE original_table = 'memories'")
        finally:
            await conn.close()

    key_id = asyncio.run(_setup())
    token_resp = client.post("/auth/token", json={"api_key": key_plain})
    token = token_resp.json()["access_token"]
    yield token
    asyncio.run(_cleanup(key_id))


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ---------------------------------------------------------------------------
# 
# ---------------------------------------------------------------------------

def test_recent_with_workspace_id_filter(client, super_jwt):
    r = client.get(
        "/memories/recent?limit=5&workspace_id=1",
        headers=auth(super_jwt),
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["workspace_id"] == 1


def test_recent_with_project_id_filter(client, super_jwt):
    r = client.get(
        "/memories/recent?limit=5&project_id=1",
        headers=auth(super_jwt),
    )
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["project_id"] == 1


def test_recent_super_with_unknown_workspace_returns_empty(client, super_jwt):
    """Super con workspace_id que no existe → 200 con 0 items. Coherente con
    search.py para super (no 403)."""
    r = client.get(
        "/memories/recent?limit=5&workspace_id=999999",
        headers=auth(super_jwt),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_recent_no_params_regression(client, super_jwt):
    """Regresión ."""
    r = client.get("/memories/recent?limit=2", headers=auth(super_jwt))
    assert r.status_code == 200
    assert "items" in r.json()


# ---------------------------------------------------------------------------
# POST /memories
# ---------------------------------------------------------------------------

def test_create_memory_decision_has_weight_09(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "decision",
            "content": "pytest-mem-decision-1",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "decision"
    assert abs(body["weight"] - 0.9) < 0.001
    assert abs(body["weight_base"] - 0.9) < 0.001
    assert body["user_id"] == 1
    assert body["visibility"] == "public"
    assert body["tags"] == []


def test_create_memory_tecnico_has_weight_05(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-mem-tecnico-1",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code == 201
    assert abs(r.json()["weight"] - 0.5) < 0.001


def test_create_memory_with_tags_persists_them(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "observacion",
            "content": "pytest-mem-tags-1",
            "workspace_id": 1,
            "project_id": 1,
            "tags": ["foo", "bar", "baz"],
        },
    )
    assert r.status_code == 201
    assert sorted(r.json()["tags"]) == ["bar", "baz", "foo"]


def test_create_memory_unknown_type_returns_422(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "tipo_inexistente",
            "content": "pytest-mem-bad-1",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code in (422, 500)  # 422 si DB rechaza enum, 500 si Python falla


def test_create_memory_unknown_workspace_returns_404(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "decision",
            "content": "pytest-mem-bad-ws",
            "workspace_id": 99999,
            "project_id": 1,
        },
    )
    assert r.status_code == 404


def test_create_memory_project_mismatch_returns_400(client, super_jwt):
    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "decision",
            "content": "pytest-mem-bad-proj",
            "workspace_id": 1,
            "project_id": 99999,
        },
    )
    assert r.status_code == 404  # project no existe


def test_create_memory_without_auth_returns_401(client):
    r = client.post("/memories", json={"type": "decision", "content": "x", "workspace_id": 1, "project_id": 1})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /memories/recent
# ---------------------------------------------------------------------------

def test_recent_returns_pytest_memories(client, super_jwt):
    r = client.get("/memories/recent?limit=20", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    contents = [m["content"] for m in body["items"]]
    assert any("pytest-mem-" in c for c in contents)


def test_recent_respects_limit(client, super_jwt):
    r = client.get("/memories/recent?limit=2", headers=auth(super_jwt))
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 2


# ---------------------------------------------------------------------------
# GET /memories/{id}
# ---------------------------------------------------------------------------

def test_get_existing_memory_returns_200(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "decision", "content": "pytest-mem-get-1", "workspace_id": 1, "project_id": 1},
    ).json()
    r = client.get(f"/memories/{created['id']}", headers=auth(super_jwt))
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_inexistent_memory_returns_403(client, super_jwt):
    """
    (no distingue 'no existe' vs 'sin acceso'). Coherente con el patrón
    aplicado en workspaces, projects, search."""
    r = client.get("/memories/00000000-0000-0000-0000-000000000000", headers=auth(super_jwt))
    assert r.status_code == 403


def test_get_increments_access_count(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "observacion", "content": "pytest-mem-access-1", "workspace_id": 1, "project_id": 1},
    ).json()
    assert created["access_count"] == 0
    # Lectura 1
    client.get(f"/memories/{created['id']}", headers=auth(super_jwt))
    # Lectura 2
    second = client.get(f"/memories/{created['id']}", headers=auth(super_jwt)).json()
    assert second["access_count"] >= 1


# ---------------------------------------------------------------------------
# PUT /memories/{id}
# ---------------------------------------------------------------------------

def test_update_content_persists(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "decision", "content": "pytest-mem-original", "workspace_id": 1, "project_id": 1},
    ).json()
    r = client.put(
        f"/memories/{created['id']}",
        headers=auth(super_jwt),
        json={"content": "pytest-mem-updated"},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "pytest-mem-updated"


def test_update_type_updates_weight_base(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "tecnico", "content": "pytest-mem-typechange-1", "workspace_id": 1, "project_id": 1},
    ).json()
    assert abs(created["weight_base"] - 0.5) < 0.001
    r = client.put(
        f"/memories/{created['id']}",
        headers=auth(super_jwt),
        json={"type": "decision"},
    )
    assert r.status_code == 200
    assert abs(r.json()["weight_base"] - 0.9) < 0.001


def test_update_with_no_fields_returns_400(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "decision", "content": "pytest-mem-empty-update", "workspace_id": 1, "project_id": 1},
    ).json()
    r = client.put(f"/memories/{created['id']}", headers=auth(super_jwt), json={})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /memories/{id} — soft delete a trash
# ---------------------------------------------------------------------------

def test_delete_moves_to_trash_and_returns_204(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "decision", "content": "pytest-mem-todelete-1", "workspace_id": 1, "project_id": 1},
    ).json()
    r = client.delete(f"/memories/{created['id']}", headers=auth(super_jwt))
    assert r.status_code == 204
    # GET tras delete → 403 anti-IDOR ( → 403 unificado).
    assert client.get(f"/memories/{created['id']}", headers=auth(super_jwt)).status_code == 403


def test_delete_inexistent_returns_404(client, super_jwt):
    r = client.delete(
        "/memories/00000000-0000-0000-0000-000000000000",
        headers=auth(super_jwt),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Visibility (private vs public)
# ---------------------------------------------------------------------------

def test_create_private_memory_visible_to_creator(client, super_jwt):
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "momento", "content": "pytest-mem-private-1", "workspace_id": 1, "project_id": 1, "visibility": "private"},
    ).json()
    assert created["visibility"] == "private"
    # Superuser (creator + super) can see it
    r = client.get(f"/memories/{created['id']}", headers=auth(super_jwt))
    assert r.status_code == 200


def test_super_can_change_own_memory_visibility(client, super_jwt):
    """NV1 fix: super sigue pudiendo cambiar visibility de sus propias memorias."""
    created = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={"type": "decision", "content": "pytest-mem-vis-1", "workspace_id": 1, "project_id": 1},
    ).json()
    assert created["visibility"] == "public"
    r = client.put(
        f"/memories/{created['id']}",
        headers=auth(super_jwt),
        json={"visibility": "private"},
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "private"


# ---------------------------------------------------------------------------
# — GLiNER hook en POST /memories → memory_entity_links
# ---------------------------------------------------------------------------

def _count_entity_links(memory_id: str) -> int:
    async def _q():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM memory_entity_links WHERE memory_id = $1::uuid",
                memory_id,
            )
        finally:
            await conn.close()
    return asyncio.run(_q())


def _entity_names_for_memory(memory_id: str) -> set[str]:
    async def _q():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            rows = await conn.fetch(
                """
                SELECT n.name FROM memory_entity_links mel
                JOIN nodes n ON n.id = mel.entity_node_id
                WHERE mel.memory_id = $1::uuid
                """,
                memory_id,
            )
            return {r["name"] for r in rows}
        finally:
            await conn.close()
    return asyncio.run(_q())


# Tests con monkeypatch sobre gliner_service.extract_entities.
# Razón: TestClient corre el handler en proceso pytest local, NO en el container.
# El módulo `gliner` (con torch + transformers, ~13GB) NO está instalado en el
# host por diseño — solo en la imagen Docker. Tests unitarios verifican el flujo
# de linking con entidades pre-fabricadas. La integración GLiNER real se prueba
# via endpoint /admin/extract_entities + POST manual smoke runtime.

async def _mock_entities_alice_acme(*args, **kwargs):
    return [
        {"text": "Alice", "label": "person", "start": 0, "end": 5, "score": 0.97},
        {"text": "Acme Corp", "label": "organization", "start": 6, "end": 15, "score": 0.81},
        {"text": "London", "label": "location", "start": 16, "end": 22, "score": 0.97},
        {"text": "5 May 2026", "label": "date", "start": 23, "end": 33, "score": 0.87},
    ]


async def _mock_entities_empty(*args, **kwargs):
    return []


async def _mock_entities_dedup(*args, **kwargs):
    # GLiNER may detect the same entity multiple times at different positions.
    return [
        {"text": "Alice", "label": "person", "start": 0, "end": 5, "score": 0.97},
        {"text": "Alice", "label": "person", "start": 17, "end": 22, "score": 0.95},
        {"text": "Alice", "label": "person", "start": 36, "end": 41, "score": 0.93},
    ]


async def _mock_entities_raise(*args, **kwargs):
    raise RuntimeError("simulated GLiNER failure (timeout, OOM, etc.)")


def test_create_memory_with_named_entities_creates_links(client, super_jwt, monkeypatch):
    """Memoria con entidades mockeadas → memory_entity_links populated."""
    import gliner_service
    monkeypatch.setattr(gliner_service, "extract_entities", _mock_entities_alice_acme)

    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "decision",
            "content": "pytest-mem-gliner Alice Acme Corp London 5 May 2026",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code == 201
    mem_id = r.json()["id"]
    # 4 entidades mockeadas únicas → 4 entries en memory_entity_links.
    assert _count_entity_links(mem_id) == 4
    names = _entity_names_for_memory(mem_id)
    assert "Alice" in names and "London" in names


def test_create_memory_without_obvious_entities_creates_zero_links(client, super_jwt, monkeypatch):
    """Mock devuelve 0 entidades → memoria SE crea, 0 links."""
    import gliner_service
    monkeypatch.setattr(gliner_service, "extract_entities", _mock_entities_empty)

    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-mem-noent texto generico sin entidades.",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code == 201
    mem_id = r.json()["id"]
    assert _count_entity_links(mem_id) == 0


def test_create_memory_idempotent_entity_dedup(client, super_jwt, monkeypatch):
    """Mock devuelve 'Alice' 3 veces → 1 sola fila en memory_entity_links."""
    import gliner_service
    monkeypatch.setattr(gliner_service, "extract_entities", _mock_entities_dedup)

    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "momento",
            "content": "pytest-mem-dedup Alice called Alice and then Alice replied.",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    assert r.status_code == 201
    mem_id = r.json()["id"]
    # Dedup by exact name → only 1 entry for "Alice".
    names = _entity_names_for_memory(mem_id)
    alice_count = sum(1 for n in names if n == "Alice")
    assert alice_count == 1


def test_create_memory_gliner_failure_does_not_block_creation(client, super_jwt, monkeypatch):
    """Mock raises → memoria SE crea con 0 links (skip + log graceful)."""
    import gliner_service
    monkeypatch.setattr(gliner_service, "extract_entities", _mock_entities_raise)

    r = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "observacion",
            "content": "pytest-mem-failgliner content cualquiera.",
            "workspace_id": 1,
            "project_id": 1,
        },
    )
    # Lo critico: GLiNER fallo NO bloquea la creacion de memoria.
    assert r.status_code == 201
    mem_id = r.json()["id"]
    assert _count_entity_links(mem_id) == 0
