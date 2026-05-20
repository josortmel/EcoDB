"""Tests integracion — CRUD projects contra postgres real.

Cubre los 5 endpoints + cascada CEO/Lead/Worker (con is_common) + anti-IDOR
+ 409 hard delete con memorias/documentos + audit log atómico.
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


# ---- super_jwt ----------------------------------------------------------

@pytest.fixture(scope="module")
def super_jwt(client):
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-proj-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            # audit_log entries de los tests — 
            # test_cannot_delete_common_project crea workspaces y los borra,
            # dejando audit_log con resource='workspace' del user_id=1. También
            # audit_log de POST /workspaces no se registran (POST workspace no
            # tiene audit), pero los DELETEs sí.
            await conn.execute(
                """
                DELETE FROM audit_log
                WHERE resource IN ('project', 'workspace', 'team')
                  AND (
                       user_id = 1
                    OR user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-proj-%')
                  )
                """
            )
            # project_members y team_resources de pytest.
            await conn.execute("DELETE FROM project_members WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-proj-%')")
            # workspace_leads de pytest.
            await conn.execute("DELETE FROM workspace_leads WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-proj-%')")
            # Memorias en projects de pytest (por project_id, no por content —
            # el FK NO ACTION en memories.project_id bloquea el DELETE projects
            # si hay memorias en alguno, aunque sus content no matche LIKE).
            await conn.execute(
                "DELETE FROM memories WHERE project_id IN (SELECT id FROM projects WHERE name LIKE 'pytest-proj-%')"
            )
            # Projects creados por los tests.
            await conn.execute("DELETE FROM projects WHERE name LIKE 'pytest-proj-%'")
            # Workspaces creados por los tests.
            await conn.execute("DELETE FROM workspaces WHERE name LIKE 'pytest-proj-%'")
            # Organizations creadas por los tests.
            await conn.execute("DELETE FROM organizations WHERE name LIKE 'pytest-proj-%'")
            # API keys de pytest.
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-proj-%'")
            # Users temporales.
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-proj-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-proj-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


# ---- Helpers crear users ------------------------------------------------

async def _create_ceo(name: str, org_name: str) -> tuple[int, int, str]:
    conn = await _aconn()
    try:
        u = await conn.fetchrow(
            "INSERT INTO users (name, is_ceo, active) VALUES ($1, true, true) RETURNING id", name
        )
        user_id = u["id"]
        await conn.execute(
            "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, $2, true)",
            user_id, f"{name}@pytest.local",
        )
        o = await conn.fetchrow(
            "INSERT INTO organizations (name, ceo_user_id) VALUES ($1, $2) RETURNING id",
            org_name, user_id,
        )
        org_id = o["id"]
        key_plain, key_hash = generate_api_key()
        await conn.execute(
            "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, $2, $3, true)",
            key_hash, f"pytest-proj-ceo-{name}", user_id,
        )
        return user_id, org_id, key_plain
    finally:
        await conn.close()


async def _create_user_simple(name: str) -> tuple[int, str]:
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
            key_hash, f"pytest-proj-user-{name}", user_id,
        )
        return user_id, key_plain
    finally:
        await conn.close()


# ---- Setup compartido para tests ---------------------------------------

@pytest.fixture(scope="module")
def ceo_setup(client, super_jwt):
    user_id, org_id, key_plain = _run(_create_ceo("pytest-proj-ceo-alfa", "pytest-proj-org-alfa"))
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]

    async def _make_ws():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO workspaces (name, organization_id) VALUES ($1, $2) RETURNING id",
                "pytest-proj-ws-alfa", org_id,
            )
            return row["id"]
        finally:
            await conn.close()

    ws_id = _run(_make_ws())
    return {"user_id": user_id, "org_id": org_id, "jwt": token, "ws_id": ws_id}


@pytest.fixture(scope="module")
def lead_setup(client, super_jwt):
    """Crea user lead + workspace + asigna como lead."""
    user_id, key_plain = _run(_create_user_simple("pytest-proj-lead"))

    async def _make_ws_and_lead():
        conn = await _aconn()
        try:
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ($1) RETURNING id",
                "pytest-proj-ws-lead",
            )
            await conn.execute(
                "INSERT INTO workspace_leads (workspace_id, user_id) VALUES ($1, $2)",
                ws["id"], user_id,
            )
            return ws["id"]
        finally:
            await conn.close()

    ws_id = _run(_make_ws_and_lead())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "jwt": token, "ws_id": ws_id}


@pytest.fixture(scope="module")
def worker_setup(client, lead_setup):
    """Crea user worker en el ws de lead_setup como project_member del project A.
    Permite testear que worker ve project A (su asignación) + project_common pero no project B."""
    user_id, key_plain = _run(_create_user_simple("pytest-proj-worker"))

    async def _setup():
        conn = await _aconn()
        try:
            # Project A: el worker es member
            pa = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, $2, false) RETURNING id",
                lead_setup["ws_id"], "pytest-proj-worker-a",
            )
            await conn.execute(
                "INSERT INTO project_members (project_id, user_id) VALUES ($1, $2)",
                pa["id"], user_id,
            )
            # Project B: el worker NO es member
            pb = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, $2, false) RETURNING id",
                lead_setup["ws_id"], "pytest-proj-worker-b",
            )
            # Project C: is_common, worker debería ver
            pc = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, $2, true) RETURNING id",
                lead_setup["ws_id"], "pytest-proj-worker-common",
            )
            return pa["id"], pb["id"], pc["id"]
        finally:
            await conn.close()

    pa_id, pb_id, pc_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {
        "user_id": user_id, "jwt": token, "ws_id": lead_setup["ws_id"],
        "proj_a": pa_id, "proj_b": pb_id, "proj_common": pc_id,
    }


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# POST /workspaces/{ws_id}/projects
# ===========================================================================

def test_super_creates_project(client, super_jwt, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-super-create"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "pytest-proj-super-create"
    assert body["workspace_id"] == ceo_setup["ws_id"]
    assert body["is_common"] is False


def test_super_creates_common_project(client, super_jwt, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-super-common", "is_common": True},
    )
    assert r.status_code == 201
    assert r.json()["is_common"] is True


def test_ceo_creates_in_own_org_workspace(client, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-proj-ceo-own"},
    )
    assert r.status_code == 201


def test_ceo_cannot_create_in_foreign_workspace(client, ceo_setup, lead_setup):
    """ceo_setup es de org-alfa; lead_setup.ws_id es de sistema (org=null)."""
    r = client.post(
        f"/workspaces/{lead_setup['ws_id']}/projects",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-proj-ceo-foreign"},
    )
    assert r.status_code == 403


def test_lead_creates_in_own_workspace(client, lead_setup):
    r = client.post(
        f"/workspaces/{lead_setup['ws_id']}/projects",
        headers=auth(lead_setup["jwt"]),
        json={"name": "pytest-proj-lead-create"},
    )
    assert r.status_code == 201


def test_worker_cannot_create(client, worker_setup):
    r = client.post(
        f"/workspaces/{worker_setup['ws_id']}/projects",
        headers=auth(worker_setup["jwt"]),
        json={"name": "pytest-proj-worker-fail"},
    )
    assert r.status_code == 403


def test_create_in_unknown_workspace_returns_403(client, super_jwt):
    """Workspace inexistente → 403 (anti-IDOR), no 404."""
    r = client.post(
        "/workspaces/999999/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-bad-ws"},
    )
    assert r.status_code == 403


def test_duplicate_project_name_in_workspace_returns_409(client, super_jwt, ceo_setup):
    name = "pytest-proj-dup"
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": name},
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": name},
    )
    assert r2.status_code == 409


def test_create_extra_field_returns_422(client, super_jwt, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-extra", "rogue": "x"},
    )
    assert r.status_code == 422


def test_create_blank_name_returns_422(client, super_jwt, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "   "},
    )
    assert r.status_code == 422


def test_create_padded_name_is_trimmed(client, super_jwt, ceo_setup):
    r = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "  pytest-proj-padded  "},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "pytest-proj-padded"


# ===========================================================================
# GET /workspaces/{ws_id}/projects
# ===========================================================================

def test_super_lists_projects(client, super_jwt, ceo_setup):
    r = client.get(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
    )
    assert r.status_code == 200
    assert "items" in r.json()


def test_ceo_lists_projects_in_own_org(client, ceo_setup):
    r = client.get(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(ceo_setup["jwt"]),
    )
    assert r.status_code == 200


def test_lead_lists_projects_in_own_workspace(client, lead_setup):
    r = client.get(
        f"/workspaces/{lead_setup['ws_id']}/projects",
        headers=auth(lead_setup["jwt"]),
    )
    assert r.status_code == 200


def test_worker_sees_own_project_and_common(client, worker_setup):
    """Worker ve proj_a (member) + proj_common (is_common) pero no proj_b."""
    r = client.get(
        f"/workspaces/{worker_setup['ws_id']}/projects",
        headers=auth(worker_setup["jwt"]),
    )
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["items"]}
    assert worker_setup["proj_a"] in ids
    assert worker_setup["proj_common"] in ids
    assert worker_setup["proj_b"] not in ids


def test_unknown_workspace_list_returns_403(client, super_jwt):
    """Anti-IDOR: workspace inexistente → 403, no 404."""
    r = client.get("/workspaces/999999/projects", headers=auth(super_jwt))
    assert r.status_code == 403


# ===========================================================================
# GET /projects/{pid}
# ===========================================================================

def test_super_can_read_any_project(client, super_jwt, ceo_setup):
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-get-target"},
    )
    pid = r1.json()["id"]
    r2 = client.get(f"/projects/{pid}", headers=auth(super_jwt))
    assert r2.status_code == 200
    assert r2.json()["id"] == pid


def test_get_unknown_project_returns_403(client, super_jwt):
    """Anti-IDOR: super tampoco recibe 404."""
    r = client.get("/projects/999999", headers=auth(super_jwt))
    assert r.status_code == 403


def test_worker_member_can_read_own_project(client, worker_setup):
    r = client.get(f"/projects/{worker_setup['proj_a']}", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 200


def test_worker_can_read_common_project_in_workspace(client, worker_setup):
    """is_common: worker con assignment en cualquier project del ws ve el is_common."""
    r = client.get(f"/projects/{worker_setup['proj_common']}", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 200


def test_worker_cannot_read_foreign_project_in_same_workspace(client, worker_setup):
    """Worker NO ve project no-common al que no es member, aun en su propio ws."""
    r = client.get(f"/projects/{worker_setup['proj_b']}", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 403


# ===========================================================================
# PUT /projects/{pid}
# ===========================================================================

def test_super_updates_project_name(client, super_jwt, ceo_setup):
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-put-orig"},
    )
    pid = r1.json()["id"]
    r2 = client.put(
        f"/projects/{pid}",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-put-renamed"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "pytest-proj-put-renamed"


def test_lead_updates_project_in_own_workspace(client, lead_setup, super_jwt):
    r1 = client.post(
        f"/workspaces/{lead_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-lead-put-target"},
    )
    pid = r1.json()["id"]
    r2 = client.put(
        f"/projects/{pid}",
        headers=auth(lead_setup["jwt"]),
        json={"name": "pytest-proj-lead-put-renamed"},
    )
    assert r2.status_code == 200


def test_worker_cannot_update_project(client, worker_setup):
    r = client.put(
        f"/projects/{worker_setup['proj_a']}",
        headers=auth(worker_setup["jwt"]),
        json={"name": "pytest-proj-hacked"},
    )
    assert r.status_code == 403


def test_put_unknown_project_returns_403(client, super_jwt):
    r = client.put(
        "/projects/999999",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-x"},
    )
    assert r.status_code == 403


def test_put_unique_collision_returns_409(client, super_jwt, ceo_setup):
    client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-collision-a"},
    )
    r2 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-collision-b"},
    )
    pid = r2.json()["id"]
    r3 = client.put(
        f"/projects/{pid}",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-collision-a"},
    )
    assert r3.status_code == 409


# ===========================================================================
# DELETE /projects/{pid}
# ===========================================================================

def test_super_deletes_empty_project(client, super_jwt, ceo_setup):
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-del-empty"},
    )
    pid = r1.json()["id"]
    r2 = client.delete(f"/projects/{pid}", headers=auth(super_jwt))
    assert r2.status_code == 204
    r3 = client.get(f"/projects/{pid}", headers=auth(super_jwt))
    assert r3.status_code == 403


def test_lead_deletes_project_in_own_workspace(client, lead_setup, super_jwt):
    r1 = client.post(
        f"/workspaces/{lead_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-lead-del"},
    )
    pid = r1.json()["id"]
    r2 = client.delete(f"/projects/{pid}", headers=auth(lead_setup["jwt"]))
    assert r2.status_code == 204


def test_worker_cannot_delete(client, worker_setup):
    r = client.delete(f"/projects/{worker_setup['proj_a']}", headers=auth(worker_setup["jwt"]))
    assert r.status_code == 403


def test_delete_unknown_project_returns_403(client, super_jwt):
    r = client.delete("/projects/999999", headers=auth(super_jwt))
    assert r.status_code == 403


def test_delete_project_with_memories_returns_409(client, super_jwt, ceo_setup):
    """FK NO ACTION en memories.project_id bloquea DELETE de un project NO común
    que tenga memorias dentro. Anteriormente este test usaba project_id=1 (que
    tiene 940 memorias migradas) pero tras 
    is_common → entra al guard "cannot delete common" antes. Test re-escrito
    para crear un project no-común con memoria y verificar el guard FK."""
    # Crear project no-común en ws de ceo_setup.
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-mem-target", "is_common": False},
    )
    pid = r1.json()["id"]

    # Crear memoria pública en el project (necesita embedding via API).
    r2 = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-proj-mem-content for FK guard test",
            "workspace_id": ceo_setup["ws_id"],
            "project_id": pid,
            "visibility": "public",
        },
    )
    assert r2.status_code == 201, f"setup memory failed: {r2.text}"

    # DELETE project con memoria → 409 FK guard.
    r3 = client.delete(f"/projects/{pid}", headers=auth(super_jwt))
    assert r3.status_code == 409
    assert "memories" in r3.json()["detail"].lower()


def test_ceo_can_update_project_in_own_org(client, ceo_setup, super_jwt):
    """UA1 fix Loop 1: CEO branch en _user_can_modify_project (positivo)."""
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-ceo-put-target"},
    )
    pid = r1.json()["id"]
    r2 = client.put(
        f"/projects/{pid}",
        headers=auth(ceo_setup["jwt"]),
        json={"name": "pytest-proj-ceo-put-renamed"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "pytest-proj-ceo-put-renamed"


def test_ceo_can_delete_project_in_own_org(client, ceo_setup, super_jwt):
    """UA1 fix Loop 1: CEO branch en _user_can_delete_project (positivo)."""
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-ceo-del-target"},
    )
    pid = r1.json()["id"]
    r2 = client.delete(f"/projects/{pid}", headers=auth(ceo_setup["jwt"]))
    assert r2.status_code == 204


def test_cannot_delete_common_project(client, super_jwt):
    """VS1 fix  — rompería
    la invariante 'todo workspace nace con un common'. Devuelve 409 explícito."""
    # Crear ws nuevo (auto-creará un project_common 'general').
    r1 = client.post(
        "/workspaces", headers=auth(super_jwt),
        json={"name": "pytest-proj-common-protect"},
    )
    ws_id = r1.json()["id"]

    # Localizar el project common del ws.
    r2 = client.get(f"/workspaces/{ws_id}/projects", headers=auth(super_jwt))
    common = next(p for p in r2.json()["items"] if p["is_common"])
    common_id = common["id"]

    # Intentar borrar — debe 409.
    r3 = client.delete(f"/projects/{common_id}", headers=auth(super_jwt))
    assert r3.status_code == 409
    assert "common" in r3.json()["detail"].lower()

    # Cleanup workspace (CASCADE borrará el project común).
    client.delete(f"/workspaces/{ws_id}", headers=auth(super_jwt))


def test_delete_project_writes_audit_log(client, super_jwt, ceo_setup):
    """Mismo patrón VS2-WS de ."""
    r1 = client.post(
        f"/workspaces/{ceo_setup['ws_id']}/projects",
        headers=auth(super_jwt),
        json={"name": "pytest-proj-audit-target"},
    )
    pid = r1.json()["id"]
    r2 = client.delete(f"/projects/{pid}", headers=auth(super_jwt))
    assert r2.status_code == 204

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT user_id, action, resource, resource_id, details
                FROM audit_log
                WHERE resource = 'project' AND resource_id = $1
                ORDER BY created_at DESC LIMIT 1
                """,
                str(pid),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    assert audit["action"] == "delete"
    assert audit["resource"] == "project"
    assert audit["user_id"] == 1
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["name"] == "pytest-proj-audit-target"
    assert details["workspace_id"] == ceo_setup["ws_id"]
