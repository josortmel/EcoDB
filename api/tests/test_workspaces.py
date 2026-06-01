"""Tests integracion — CRUD workspaces contra postgres real.

Cubre los 5 endpoints + cascada CEO/Lead/Worker + casos anti-IDOR + 409 hard
delete con memorias dentro.
"""
import asyncio
import json
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---- super_jwt: superuser (is_super=true, user_id=1) ------------------------------

@pytest.fixture(scope="module")
def super_jwt(client):
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-ws-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            # audit_log entries de los tests — incluir users temporales pytest-ws-*
            # (CEO temporal que ejecuta DELETE deja audit con su user_id, FK
            # bloquearía el DELETE FROM users si no se purga primero).
            await conn.execute(
                """
                DELETE FROM audit_log
                WHERE resource IN ('workspace', 'project')
                  AND (
                       user_id = 1
                    OR user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-ws-%')
                  )
                """
            )
            # Borrar artefactos creados por los tests.
            await conn.execute("DELETE FROM project_members WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-ws-%')")
            await conn.execute("DELETE FROM workspace_leads WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-ws-%')")
            # Workspaces nuevos creados durante los tests.
            await conn.execute("DELETE FROM workspaces WHERE name LIKE 'pytest-ws-%'")
            # Organizations creadas por los tests (sin CEO ya borrado).
            await conn.execute("DELETE FROM organizations WHERE name LIKE 'pytest-ws-%'")
            # API keys de pytest.
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-ws-%'")
            # Users temporales.
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-ws-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-ws-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


# ---- Helper para crear user temp con rol especifico --------------------------

async def _create_ceo(name: str, org_name: str) -> tuple[int, int, str]:
    """Crea user CEO + organization. Devuelve (user_id, org_id, api_key_plain)."""
    conn = await _aconn()
    try:
        # User
        u = await conn.fetchrow(
            "INSERT INTO users (name, is_ceo, active) VALUES ($1, true, true) RETURNING id",
            name,
        )
        user_id = u["id"]
        # Email
        await conn.execute(
            "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, $2, true)",
            user_id, f"{name}@pytest.local",
        )
        # Org
        o = await conn.fetchrow(
            "INSERT INTO organizations (name, ceo_user_id) VALUES ($1, $2) RETURNING id",
            org_name, user_id,
        )
        org_id = o["id"]
        await conn.execute(
            "UPDATE users SET organization_id = $1 WHERE id = $2", org_id, user_id
        )
        # API key
        key_plain, key_hash = generate_api_key()
        await conn.execute(
            "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, $2, $3, true)",
            key_hash, f"pytest-ws-ceo-{name}", user_id,
        )
        return user_id, org_id, key_plain
    finally:
        await conn.close()


async def _create_user_simple(name: str) -> tuple[int, str]:
    """Crea user no-super no-CEO. Devuelve (user_id, api_key_plain)."""
    conn = await _aconn()
    try:
        u = await conn.fetchrow(
            "INSERT INTO users (name, active) VALUES ($1, true) RETURNING id", name
        )
        user_id = u["id"]
        await conn.execute(
            "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, $2, true)",
            user_id, f"{name}@pytest.local",
        )
        key_plain, key_hash = generate_api_key()
        await conn.execute(
            "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, $2, $3, true)",
            key_hash, f"pytest-ws-user-{name}", user_id,
        )
        return user_id, key_plain
    finally:
        await conn.close()


# ---- ceo_jwt: usuario CEO con su organization --------------------------------

@pytest.fixture(scope="module")
def ceo_setup(client, super_jwt):
    user_id, org_id, key_plain = _run(_create_ceo("pytest-ws-ceo-alfa", "pytest-ws-org-alfa"))
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "org_id": org_id, "jwt": token}


# ---- worker_jwt: usuario simple sin lead ni org -------------------------------

@pytest.fixture(scope="module")
def worker_setup(client):
    user_id, key_plain = _run(_create_user_simple("pytest-ws-worker"))
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "jwt": token}


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# POST /workspaces
# ===========================================================================

def test_super_creates_workspace_with_org(client, super_jwt, ceo_setup):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-super-in-org", "organization_id": ceo_setup["org_id"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "pytest-ws-super-in-org"
    assert body["organization_id"] == ceo_setup["org_id"]


def test_super_creates_system_workspace_org_null(client, super_jwt):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-system-1"},
    )
    assert r.status_code == 201
    assert r.json()["organization_id"] is None


def test_ceo_creates_in_own_org(client, ceo_setup):
    r = client.post(
        "/workspaces",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-ws-ceo-own", "organization_id": ceo_setup["org_id"]},
    )
    assert r.status_code == 201


def test_ceo_cannot_create_system_workspace(client, ceo_setup):
    r = client.post(
        "/workspaces",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-ws-ceo-system-fail"},
    )
    assert r.status_code == 403
    assert "system" in r.json()["detail"].lower()


def test_ceo_cannot_create_in_foreign_org(client, ceo_setup):
    # Crear segunda org con otro CEO temporal solo para el ID.
    other_user, other_org, _ = _run(_create_ceo("pytest-ws-ceo-beta", "pytest-ws-org-beta"))
    r = client.post(
        "/workspaces",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-ws-ceo-foreign", "organization_id": other_org},
    )
    assert r.status_code == 403


def test_worker_cannot_create(client, worker_setup, ceo_setup):
    r = client.post(
        "/workspaces",
        headers=auth(worker_setup["jwt"]),
        json={"name": "pytest-ws-worker-fail", "organization_id": ceo_setup["org_id"]},
    )
    assert r.status_code == 403


def test_duplicate_name_in_org_returns_409(client, super_jwt, ceo_setup):
    name = "pytest-ws-dup"
    r1 = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": name, "organization_id": ceo_setup["org_id"]},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": name, "organization_id": ceo_setup["org_id"]},
    )
    assert r2.status_code == 409


def test_duplicate_name_in_system_returns_409(client, super_jwt):
    """Partial unique idx WHERE org_id IS NULL — deuda ."""
    name = "pytest-ws-system-dup"
    client.post("/workspaces", headers=auth(super_jwt), json={"name": name})
    r = client.post("/workspaces", headers=auth(super_jwt), json={"name": name})
    assert r.status_code == 409


def test_extra_field_returns_422(client, super_jwt):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-extra", "rogue_field": "x"},
    )
    assert r.status_code == 422


def test_empty_name_returns_422(client, super_jwt):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": ""},
    )
    assert r.status_code == 422


def test_null_byte_in_name_returns_422(client, super_jwt):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-\x00bad"},
    )
    assert r.status_code == 422


def test_whitespace_only_name_returns_422(client, super_jwt):
    """OBS-WS1 fix: name=' ' (solo espacio) pasa min_length=1 pero no debe
    crear workspaces con nombre invisible."""
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "   "},
    )
    assert r.status_code == 422


def test_name_with_padding_is_trimmed(client, super_jwt):
    """OBS-WS1 fix: '  foo  ' se almacena como 'foo' — UNIQUE consistente +
    queries LIKE no quedan ciegas."""
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "  pytest-ws-padded  "},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "pytest-ws-padded"


def test_unknown_organization_id_returns_422(client, super_jwt):
    r = client.post(
        "/workspaces",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-bad-org", "organization_id": 999999},
    )
    assert r.status_code == 422


# ===========================================================================
# GET /workspaces
# ===========================================================================

def test_super_lists_all_workspaces(client, super_jwt):
    r = client.get("/workspaces", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    # workspace_id=1 (default Fase 1 con 939 memorias) debe estar.
    ids = [w["id"] for w in body["items"]]
    assert 1 in ids


def test_ceo_lists_only_own_org(client, ceo_setup, super_jwt):
    # Crear dos workspaces — uno en org del CEO, otro en sistema.
    client.post("/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-list-system"})

    r = client.get("/workspaces", headers=auth(ceo_setup["jwt"]))
    assert r.status_code == 200
    items = r.json()["items"]
    # Todos deben pertenecer a la org del CEO.
    for w in items:
        assert w["organization_id"] == ceo_setup["org_id"]


def test_worker_without_assignments_lists_empty(client, worker_setup):
    r = client.get("/workspaces", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 200
    assert r.json()["items"] == []


# ===========================================================================
# GET /workspaces/{id}
# ===========================================================================

def test_super_can_read_any_workspace(client, super_jwt):
    r = client.get("/workspaces/1", headers=auth(super_jwt))
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_get_unknown_id_returns_403_not_404(client, super_jwt):
    """Anti-IDOR: super tampoco recibe 404 — coherencia. Aunque super tendría
    derecho a saber, devolvemos 403 igual para mantener invariante simple."""
    r = client.get("/workspaces/999999", headers=auth(super_jwt))
    assert r.status_code == 403


def test_worker_cannot_read_foreign_workspace(client, worker_setup):
    r = client.get("/workspaces/1", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 403


# ===========================================================================
# PUT /workspaces/{id}
# ===========================================================================

def test_super_updates_workspace_name(client, super_jwt):
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-put-orig"}
    )
    ws_id = r1.json()["id"]
    r2 = client.put(
        f"/workspaces/{ws_id}",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-put-renamed"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "pytest-ws-put-renamed"


def test_worker_cannot_update(client, worker_setup, super_jwt):
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-put-worker"}
    )
    ws_id = r1.json()["id"]
    r = client.put(
        f"/workspaces/{ws_id}",
        headers=auth(worker_setup["jwt"]),
        json={"name": "pytest-ws-hacked"},
    )
    assert r.status_code == 403


def test_put_unknown_id_returns_403(client, super_jwt):
    r = client.put(
        "/workspaces/999999", headers=auth(super_jwt), json={"name": "pytest-ws-x"}
    )
    assert r.status_code == 403


def test_put_unique_collision_returns_409(client, super_jwt):
    client.post("/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-collision-a"})
    r2 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-collision-b"}
    )
    ws_id = r2.json()["id"]
    r = client.put(
        f"/workspaces/{ws_id}",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-collision-a"},
    )
    assert r.status_code == 409


def test_put_extra_field_returns_422(client, super_jwt):
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-put-extra"}
    )
    ws_id = r1.json()["id"]
    r = client.put(
        f"/workspaces/{ws_id}",
        headers=auth(super_jwt),
        json={"name": "pytest-ws-put-renamed", "rogue": 1},
    )
    assert r.status_code == 422


# ===========================================================================
# DELETE /workspaces/{id}
# ===========================================================================

def test_super_deletes_empty_workspace(client, super_jwt):
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-del-empty"}
    )
    ws_id = r1.json()["id"]
    r2 = client.delete(f"/workspaces/{ws_id}", headers=auth(super_jwt))
    assert r2.status_code == 204
    # Verificacion: GET ahora 403 (workspace no existe).
    r3 = client.get(f"/workspaces/{ws_id}", headers=auth(super_jwt))
    assert r3.status_code == 403


def test_delete_workspace_with_memories_returns_409(client, super_jwt):
    """Workspace 1 tiene 939 memorias migradas — DELETE debe devolver 409."""
    r = client.delete("/workspaces/1", headers=auth(super_jwt))
    assert r.status_code == 409
    detail = r.json()["detail"]
    # Debe mencionar el count y "empty" o equivalente.
    assert "memories" in detail.lower()


def test_worker_cannot_delete(client, worker_setup, super_jwt):
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-del-worker"}
    )
    ws_id = r1.json()["id"]
    r = client.delete(f"/workspaces/{ws_id}", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 403


def test_lead_cannot_delete(client, super_jwt):
    """Lead puede leer y modificar pero NO borrar."""
    # Crear user + workspace + asignarlo como lead.
    user_id, key_plain = _run(_create_user_simple("pytest-ws-lead-del"))

    async def _make_lead():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-ws-lead-target",
            )
            await conn.execute(
                "INSERT INTO workspace_leads (workspace_id, user_id) VALUES ($1, $2)",
                ws["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_make_lead())
    lead_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.delete(f"/workspaces/{ws_id}", headers=auth(lead_jwt))
    assert r.status_code == 403


def test_delete_unknown_id_returns_403(client, super_jwt):
    r = client.delete("/workspaces/999999", headers=auth(super_jwt))
    assert r.status_code == 403


# ===========================================================================
# UA1 (adv-code Loop 1): tests positivos lead + worker — sin esto, los helpers
# `_user_can_read/modify_workspace` para esos roles son blind spots reales.
# ===========================================================================

def test_lead_can_read_own_workspace(client, super_jwt):
    """Lead asignado a un workspace lo puede leer (200)."""
    user_id, key_plain = _run(_create_user_simple("pytest-ws-lead-read"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-ws-lead-read-target",
            )
            await conn.execute(
                "INSERT INTO workspace_leads (workspace_id, user_id) VALUES ($1, $2)",
                ws["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    lead_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.get(f"/workspaces/{ws_id}", headers=auth(lead_jwt))
    assert r.status_code == 200
    assert r.json()["id"] == ws_id


def test_lead_can_update_own_workspace(client, super_jwt):
    """Lead asignado a un workspace puede actualizar su name (200)."""
    user_id, key_plain = _run(_create_user_simple("pytest-ws-lead-update"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-ws-lead-update-orig",
            )
            await conn.execute(
                "INSERT INTO workspace_leads (workspace_id, user_id) VALUES ($1, $2)",
                ws["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    lead_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.put(
        f"/workspaces/{ws_id}",
        headers=auth(lead_jwt),
        json={"name": "pytest-ws-lead-update-renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "pytest-ws-lead-update-renamed"


def test_worker_via_project_member_can_read_workspace(client):
    """Worker miembro de un project del workspace puede leer el workspace (200)."""
    user_id, key_plain = _run(_create_user_simple("pytest-ws-worker-read"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-ws-worker-read-target",
            )
            proj = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name) VALUES ($1, $2) RETURNING id",
                ws["id"], "pytest-ws-worker-read-proj",
            )
            await conn.execute(
                "INSERT INTO project_members (project_id, user_id) VALUES ($1, $2)",
                proj["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    worker_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.get(f"/workspaces/{ws_id}", headers=auth(worker_jwt))
    assert r.status_code == 200
    assert r.json()["id"] == ws_id


def test_worker_via_project_member_workspace_in_list(client):
    """Worker miembro de project ve su workspace en GET /workspaces."""
    user_id, key_plain = _run(_create_user_simple("pytest-ws-worker-list"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-ws-worker-list-target",
            )
            proj = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name) VALUES ($1, $2) RETURNING id",
                ws["id"], "pytest-ws-worker-list-proj",
            )
            await conn.execute(
                "INSERT INTO project_members (project_id, user_id) VALUES ($1, $2)",
                proj["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    worker_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.get("/workspaces", headers=auth(worker_jwt))
    assert r.status_code == 200
    ids = [w["id"] for w in r.json()["items"]]
    assert ws_id in ids


# ===========================================================================
# UA3 (adv-code Loop 1): CEO no puede leer/borrar workspace de otra org.
# ===========================================================================

def test_ceo_cannot_read_foreign_org_workspace(client, ceo_setup):
    """CEO de org-alfa NO puede leer workspace creado en org-beta."""
    other_user, other_org, other_key = _run(_create_ceo("pytest-ws-ceo-gamma", "pytest-ws-org-gamma"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (organization_id, name) VALUES ($1, $2) RETURNING id",
                other_org, "pytest-ws-foreign-read",
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    r = client.get(f"/workspaces/{ws_id}", headers=auth(ceo_setup["jwt"]))
    assert r.status_code == 403


def test_delete_workspace_writes_audit_log(client, super_jwt):
    """DELETE workspace exitoso escribe audit_log row con action='delete' resource='workspace' atómico."""
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-audit-target"}
    )
    ws_id = r1.json()["id"]
    r2 = client.delete(f"/workspaces/{ws_id}", headers=auth(super_jwt))
    assert r2.status_code == 204

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT user_id, action, resource, resource_id, details
                FROM audit_log
                WHERE resource = 'workspace' AND resource_id = $1
                ORDER BY created_at DESC LIMIT 1
                """,
                str(ws_id),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    assert audit["action"] == "delete"
    assert audit["resource"] == "workspace"
    assert audit["user_id"] == 1
    # `details` es JSONB — asyncpg lo devuelve como string en este path.
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["name"] == "pytest-ws-audit-target"


# ===========================================================================
# 
# ===========================================================================

def test_new_workspace_has_auto_project_common(client, super_jwt):
    """
    is_common=true. Workspace nuevo es usable desde día 0."""
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt), json={"name": "pytest-ws-auto-common"}
    )
    assert r1.status_code == 201
    ws_id = r1.json()["id"]

    # Listar projects del ws — debe contener 'general' is_common=true.
    r2 = client.get(f"/workspaces/{ws_id}/projects", headers=auth(super_jwt))
    assert r2.status_code == 200
    items = r2.json()["items"]
    common_projects = [p for p in items if p["is_common"]]
    assert len(common_projects) == 1, f"esperado exactamente 1 project_common, got {items}"
    assert common_projects[0]["name"] == "general"


def test_workspace_creation_atomic_rollback_on_collision(client, super_jwt, ceo_setup):
    """Si POST /workspaces colisiona en UNIQUE, la transacción rollback no
    deja ni workspace ni project huérfano. adv-code Loop 1 mejora: assert DB
    state explícito post-rollback (no solo el HTTP code)."""
    name = "pytest-ws-atomic-test"
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt),
        json={"name": name, "organization_id": ceo_setup["org_id"]},
    )
    assert r1.status_code == 201

    # Segundo create con mismo name+org → 409.
    r2 = client.post(
        "/workspaces", headers=auth(super_jwt),
        json={"name": name, "organization_id": ceo_setup["org_id"]},
    )
    assert r2.status_code == 409

    # Verificar en DB: solo UN workspace con ese name+org y solo UN project
    # 'general' asociado al ws (el del primer INSERT). Si la transacción
    # hubiera dejado un project huérfano del segundo intento, habría 2.
    async def _count():
        conn = await _aconn()
        try:
            ws_count = await conn.fetchval(
                "SELECT count(*) FROM workspaces WHERE name = $1 AND organization_id = $2",
                name, ceo_setup["org_id"],
            )
            ws_id = await conn.fetchval(
                "SELECT id FROM workspaces WHERE name = $1 AND organization_id = $2",
                name, ceo_setup["org_id"],
            )
            general_count = await conn.fetchval(
                "SELECT count(*) FROM projects WHERE workspace_id = $1 AND name = 'general'",
                ws_id,
            )
            return ws_count, general_count
        finally:
            await conn.close()

    ws_count, general_count = _run(_count())
    assert ws_count == 1, f"esperaba 1 workspace tras rollback, hay {ws_count}"
    assert general_count == 1, f"esperaba 1 project 'general' tras rollback, hay {general_count}"


def test_worker_in_new_workspace_can_use_common_project(client, super_jwt):
    """Workflow end-to-end 
    project_member en el general) puede leer/escribir memorias inmediatamente
    sin Lead que cree projects custom."""
    # Crear workspace nuevo (auto-creará 'general').
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt),
        json={"name": "pytest-ws-2.6-flow"},
    )
    ws_id = r1.json()["id"]

    # Encontrar el project_common 'general'.
    r2 = client.get(f"/workspaces/{ws_id}/projects", headers=auth(super_jwt))
    common = next(p for p in r2.json()["items"] if p["is_common"])
    common_pid = common["id"]

    # Crear user worker + asignarlo como member del project común.
    user_id, key_plain = _run(_create_user_simple("pytest-ws-2.6-worker"))

    async def _add_member():
        conn = await _aconn()
        try:
            await conn.execute(
                "INSERT INTO project_members (project_id, user_id) VALUES ($1, $2)",
                common_pid, user_id,
            )
        finally:
            await conn.close()

    _run(_add_member())
    worker_jwt = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]

    # Worker GET workspace → 200 (cascada via project_members).
    r3 = client.get(f"/workspaces/{ws_id}", headers=auth(worker_jwt))
    assert r3.status_code == 200


def test_ceo_cannot_delete_foreign_org_workspace(client, ceo_setup):
    """CEO de org-alfa NO puede borrar workspace creado en org-delta."""
    other_user, other_org, other_key = _run(_create_ceo("pytest-ws-ceo-delta", "pytest-ws-org-delta"))

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (organization_id, name) VALUES ($1, $2) RETURNING id",
                other_org, "pytest-ws-foreign-delete",
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_setup())
    r = client.delete(f"/workspaces/{ws_id}", headers=auth(ceo_setup["jwt"]))
    assert r.status_code == 403
