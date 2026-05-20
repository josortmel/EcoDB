"""Tests integración — POST /admin/redistribute/memories.

Cubre el endpoint de redistribución: validaciones de target, dry_run, atomic
UPDATE+audit, filtros (agent_identifier, type), 422 cuando filter==target.
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

from main import create_app
from auth import generate_api_key


@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


async def _aconn():
    return await asyncpg.connect(dsn=os.environ["DATABASE_URL"])


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def super_jwt(client):
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-admin-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            # audit_log entries pytest-admin (resource = 'memories_batch' o cualquier de tests).
            await conn.execute(
                """
                DELETE FROM audit_log
                WHERE (action = 'redistribute' OR resource IN ('project','workspace'))
                  AND (user_id = 1 OR user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-admin-%'))
                """
            )
            # Memorias creadas en tests por project_id de pytest-admin projects.
            await conn.execute(
                "DELETE FROM memories WHERE project_id IN (SELECT id FROM projects WHERE name LIKE 'pytest-admin-%')"
            )
            await conn.execute("DELETE FROM memories WHERE content LIKE 'pytest-admin-%'")
            await conn.execute("DELETE FROM project_members WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-admin-%')")
            await conn.execute("DELETE FROM projects WHERE name LIKE 'pytest-admin-%'")
            await conn.execute("DELETE FROM workspaces WHERE name LIKE 'pytest-admin-%'")
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-admin-%'")
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-admin-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-admin-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


@pytest.fixture(scope="module")
def world(client, super_jwt):
    """Setup: 2 workspaces + 1 project no-común en cada + 3 memorias en source.

    Devuelve dict con IDs y count para tests de redistribución."""
    # Crear ws_origen.
    r1 = client.post(
        "/workspaces", headers={"Authorization": f"Bearer {super_jwt}"},
        json={"name": "pytest-admin-ws-origen"},
    )
    ws_origen = r1.json()["id"]
    # Crear project no-común en origen.
    r2 = client.post(
        f"/workspaces/{ws_origen}/projects",
        headers={"Authorization": f"Bearer {super_jwt}"},
        json={"name": "pytest-admin-proj-source", "is_common": False},
    )
    proj_origen = r2.json()["id"]

    # Crear ws_destino + project no-común.
    r3 = client.post(
        "/workspaces", headers={"Authorization": f"Bearer {super_jwt}"},
        json={"name": "pytest-admin-ws-destino"},
    )
    ws_destino = r3.json()["id"]
    r4 = client.post(
        f"/workspaces/{ws_destino}/projects",
        headers={"Authorization": f"Bearer {super_jwt}"},
        json={"name": "pytest-admin-proj-target", "is_common": False},
    )
    proj_destino = r4.json()["id"]

    # Crear 3 memorias en proj_origen — 2 'tecnico' + 1 'decision'.
    headers = {"Authorization": f"Bearer {super_jwt}"}
    for i, mtype in enumerate(["tecnico", "tecnico", "decision"]):
        r = client.post(
            "/memories", headers=headers,
            json={
                "type": mtype,
                "content": f"pytest-admin-content-{i}-{mtype}",
                "workspace_id": ws_origen,
                "project_id": proj_origen,
                "visibility": "public",
            },
        )
        assert r.status_code == 201

    return {
        "ws_origen": ws_origen, "proj_origen": proj_origen,
        "ws_destino": ws_destino, "proj_destino": proj_destino,
    }


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# Validaciones de body
# ===========================================================================

def test_redistribute_extra_field_returns_422(client, super_jwt, world):
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
            "rogue": "x",
        },
    )
    assert r.status_code == 422


def test_redistribute_filter_equals_target_returns_422(client, super_jwt, world):
    """Filter == target → no-op disfrazado. Rechazar."""
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
        },
    )
    assert r.status_code == 422
    assert "identical" in r.json()["detail"].lower()


def test_redistribute_target_workspace_unknown_returns_422(client, super_jwt, world):
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": 999999, "project_id": 999999},
        },
    )
    assert r.status_code == 422


def test_redistribute_target_project_not_in_workspace_returns_422(client, super_jwt, world):
    """target.project_id no pertenece a target.workspace_id → 422."""
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_origen"]},
        },
    )
    assert r.status_code == 422


def test_redistribute_filter_unknown_agent_returns_422(client, super_jwt, world):
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": world["ws_origen"], "project_id": world["proj_origen"],
                "agent_identifier": "NoExisto",
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 422


# ===========================================================================
# Permisos
# ===========================================================================

def test_redistribute_non_super_returns_403(client, world):
    """Crear user simple non-super → POST → 403."""
    async def _make_user():
        conn = await _aconn()
        try:
            u = await conn.fetchrow(
                "INSERT INTO users (name, active) VALUES ('pytest-admin-non-super', true) RETURNING id"
            )
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, 'pytest-admin-non-super@local', true)",
                u["id"],
            )
            key_plain, key_hash = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-admin-non-super-key', $2, true)",
                key_hash, u["id"],
            )
            return key_plain
        finally:
            await conn.close()

    key_plain = _run(_make_user())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(token),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 403


# ===========================================================================
# Funcionalidad
# ===========================================================================

def test_redistribute_dry_run_does_not_change_db(client, super_jwt, world):
    """dry_run=true: matched_count + sample, moved_count=0, audit_id=null,
    BD sin cambios."""
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {"workspace_id": world["ws_origen"], "project_id": world["proj_origen"]},
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["matched_count"] >= 3  # 3 memorias creadas en setup
    assert body["moved_count"] == 0
    assert body["audit_id"] is None
    assert len(body["sample_memory_ids"]) >= 3

    # Verificar BD: las memorias siguen en origen.
    async def _count():
        conn = await _aconn()
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM memories WHERE workspace_id = $1 AND project_id = $2",
                world["ws_origen"], world["proj_origen"],
            )
        finally:
            await conn.close()

    count_origen = _run(_count())
    assert count_origen >= 3  # nada se movió


def test_redistribute_with_type_filter_moves_only_matching(client, super_jwt, world):
    """filter.type='decision' → solo la 1 memoria 'decision' se mueve, las 2 'tecnico' se quedan."""
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": world["ws_origen"], "project_id": world["proj_origen"],
                "type": "decision",
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_count"] == 1
    assert body["moved_count"] == 1
    assert body["audit_id"] is not None

    # Verificar en BD: la decision está en target, las tecnico siguen en source.
    async def _check():
        conn = await _aconn()
        try:
            decision_target = await conn.fetchval(
                "SELECT count(*) FROM memories WHERE workspace_id = $1 AND project_id = $2 AND type = 'decision'",
                world["ws_destino"], world["proj_destino"],
            )
            tecnico_source = await conn.fetchval(
                "SELECT count(*) FROM memories WHERE workspace_id = $1 AND project_id = $2 AND type = 'tecnico'",
                world["ws_origen"], world["proj_origen"],
            )
            return decision_target, tecnico_source
        finally:
            await conn.close()

    dt, ts = _run(_check())
    assert dt >= 1
    assert ts >= 2


def test_redistribute_writes_audit_log(client, super_jwt, world):
    """Verificar audit_log batch row con resource_id=UUID + filter + target + count."""
    # Crear memoria nueva en source para tener algo concreto que mover.
    r0 = client.post(
        "/memories", headers=auth(super_jwt),
        json={
            "type": "observacion",
            "content": "pytest-admin-audit-marker",
            "workspace_id": world["ws_origen"],
            "project_id": world["proj_origen"],
            "visibility": "public",
        },
    )
    assert r0.status_code == 201

    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": world["ws_origen"], "project_id": world["proj_origen"],
                "type": "observacion",
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 200
    audit_id = r.json()["audit_id"]
    assert audit_id is not None

    async def _check_audit():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT user_id, action, resource, resource_id, details
                FROM audit_log WHERE resource_id = $1
                """,
                audit_id,
            )
        finally:
            await conn.close()

    audit = _run(_check_audit())
    assert audit is not None
    assert audit["action"] == "redistribute"
    assert audit["resource"] == "memories_batch"
    assert audit["user_id"] == 1
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["filter"]["workspace_id"] == world["ws_origen"]
    assert details["target"]["project_id"] == world["proj_destino"]
    assert details["matched_count"] >= 1


def test_redistribute_with_agent_identifier_filter(client, super_jwt, world):
    """Filter by agent_identifier: moves only memories of the specified agent."""
    # Crear 1 memoria con agent_identifier='SIN_AUTOR' en source.
    r0 = client.post(
        "/memories", headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-admin-sinautor-agent-content",
            "workspace_id": world["ws_origen"],
            "project_id": world["proj_origen"],
            "agent_identifier": "SIN_AUTOR",
            "visibility": "public",
        },
    )
    assert r0.status_code == 201

    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": world["ws_origen"], "project_id": world["proj_origen"],
                "agent_identifier": "SIN_AUTOR",
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_count"] >= 1
    assert body["moved_count"] >= 1
    assert body["audit_id"] is not None


def test_redistribute_with_combined_filter_agent_and_type(client, super_jwt, world):
    """SOFT gap adv-code: combined filter agent+type."""
    # Memoria 'tecnico' de SIN_AUTOR.
    r0 = client.post(
        "/memories", headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-admin-combo-sin-autor",
            "workspace_id": world["ws_origen"],
            "project_id": world["proj_origen"],
            "agent_identifier": "SIN_AUTOR",
            "visibility": "public",
        },
    )
    assert r0.status_code == 201
    # Memoria 'decision' de SIN_AUTOR (no debería moverse).
    r1 = client.post(
        "/memories", headers=auth(super_jwt),
        json={
            "type": "decision",
            "content": "pytest-admin-combo-sin-autor-decision",
            "workspace_id": world["ws_origen"],
            "project_id": world["proj_origen"],
            "agent_identifier": "SIN_AUTOR",
            "visibility": "public",
        },
    )
    assert r1.status_code == 201

    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": world["ws_origen"], "project_id": world["proj_origen"],
                "agent_identifier": "SIN_AUTOR",
                "type": "tecnico",
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_count"] >= 1
    # La 'decision' de SIN_AUTOR sigue en source.
    async def _check_decision_in_source():
        conn = await _aconn()
        try:
            return await conn.fetchval(
                """
                SELECT count(*) FROM memories m
                JOIN agents a ON a.id = m.agent_id
                WHERE m.workspace_id = $1 AND m.project_id = $2
                  AND a.identifier = 'SIN_AUTOR' AND m.type = 'decision'
                """,
                world["ws_origen"], world["proj_origen"],
            )
        finally:
            await conn.close()

    assert _run(_check_decision_in_source()) >= 1


def test_redistribute_no_match_audit_logs_zero(client, super_jwt, world):
    """Filter sin matches: matched=0, moved=0, audit_id NO null (intento documentado)."""
    r = client.post(
        "/admin/redistribute/memories",
        headers=auth(super_jwt),
        json={
            "filter": {
                "workspace_id": 999999, "project_id": 999999,  # no existe
            },
            "target": {"workspace_id": world["ws_destino"], "project_id": world["proj_destino"]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_count"] == 0
    assert body["moved_count"] == 0
    assert body["audit_id"] is not None  # documentado el intento
