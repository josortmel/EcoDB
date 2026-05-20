"""Tests integración — pre-filtro project-level en /search.

Cubre el cambio clave de 2.4: worker con project_member en P_a NO ve memorias
de P_b dentro del mismo workspace (a menos que P_b sea is_common). El filtro
ahora usa visible_project_ids (granular) en lugar de visible_workspace_ids.

Mantiene compatibilidad con filtros opcionales workspace_id y project_id (403
unificado anti-IDOR).
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


@pytest.fixture(scope="module")
def super_jwt(client):
    """Super para crear setup + cleanup."""
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-search-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            # Borrar memorias creadas por los tests (matching content prefix).
            await conn.execute("DELETE FROM memories WHERE content LIKE 'pytest-search-%'")
            await conn.execute("DELETE FROM project_members WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-search-%')")
            await conn.execute("DELETE FROM projects WHERE name LIKE 'pytest-search-%'")
            await conn.execute("DELETE FROM workspaces WHERE name LIKE 'pytest-search-%'")
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-search-%'")
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-search-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-search-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


@pytest.fixture(scope="module")
def worker_world(client, super_jwt):
    """Setup completo: workspace + 3 projects (A miembro, B non-member, C common)
    + worker user + super crea memorias en cada uno con prefix identificable.

    Devuelve dict con jwt del worker y los IDs para asserts."""
    async def _setup():
        conn = await _aconn()
        try:
            # User worker
            user = await conn.fetchrow(
                "INSERT INTO users (name, active) VALUES ('pytest-search-worker', true) RETURNING id"
            )
            user_id = user["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, 'pytest-search-worker@local', true)",
                user_id,
            )
            key_plain, key_hash = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-search-worker-key', $2, true)",
                key_hash, user_id,
            )

            # Workspace
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ('pytest-search-ws') RETURNING id"
            )
            ws_id = ws["id"]

            # Otro workspace (worker NO debería ver nada de aquí)
            ws_foreign = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ('pytest-search-ws-foreign') RETURNING id"
            )
            ws_foreign_id = ws_foreign["id"]

            # Project A (worker es member)
            pa = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, 'pytest-search-pa', false) RETURNING id",
                ws_id,
            )
            pa_id = pa["id"]
            await conn.execute(
                "INSERT INTO project_members (project_id, user_id) VALUES ($1, $2)",
                pa_id, user_id,
            )

            # Project B (worker NO es member, NO is_common)
            pb = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, 'pytest-search-pb', false) RETURNING id",
                ws_id,
            )
            pb_id = pb["id"]

            # Project C (is_common del mismo ws)
            pc = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, 'pytest-search-pc-common', true) RETURNING id",
                ws_id,
            )
            pc_id = pc["id"]

            # Project D en ws_foreign (is_common pero el worker NO tiene project_member en ws_foreign,
            # asi que NO debe verlo)
            pd = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, 'pytest-search-pd-common-foreign', true) RETURNING id",
                ws_foreign_id,
            )
            pd_id = pd["id"]

            return {
                "user_id": user_id,
                "key_plain": key_plain,
                "ws_id": ws_id,
                "ws_foreign_id": ws_foreign_id,
                "pa_id": pa_id, "pb_id": pb_id, "pc_id": pc_id, "pd_id": pd_id,
            }
        finally:
            await conn.close()

    state = _run(_setup())

    # Crear 1 memoria pública por project usando super (obtiene embedding via API).
    for pid_key, label in [("pa_id", "pa"), ("pb_id", "pb"), ("pc_id", "pc"), ("pd_id", "pd")]:
        ws_used = state["ws_foreign_id"] if pid_key == "pd_id" else state["ws_id"]
        r = client.post(
            "/memories",
            headers={"Authorization": f"Bearer {super_jwt}"},
            json={
                "type": "tecnico",
                "content": f"pytest-search-marker-{label} unique semantic content for retrieval",
                "workspace_id": ws_used,
                "project_id": state[pid_key],
                "visibility": "public",
            },
        )
        assert r.status_code == 201, f"setup memory {label} failed: {r.status_code} {r.text}"

    state["worker_jwt"] = client.post(
        "/auth/token", json={"api_key": state["key_plain"]}
    ).json()["access_token"]
    return state


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# Pre-filtro project-level — el cambio clave de # ===========================================================================

def test_worker_search_only_returns_member_and_common_projects(client, worker_world):
    """
    P_a (member) + P_c (is_common del ws), pero NO P_b (mismo ws, sin acceso)
    ni P_d (otro ws, aunque sea is_common).

    Antes (
    porque tenía acceso al ws — viola granularidad.
    """
    r = client.post(
        "/search",
        headers=auth(worker_world["worker_jwt"]),
        json={"query_text": "pytest-search-marker semantic content for retrieval", "limit": 20},
    )
    assert r.status_code == 200
    project_ids_seen = {result["project_id"] for result in r.json()["results"]}

    # P_a (member): visible
    assert worker_world["pa_id"] in project_ids_seen
    # P_c (is_common del ws con assignment): visible
    assert worker_world["pc_id"] in project_ids_seen
    # P_b (mismo ws, sin acceso, NO common): INVISIBLE — invariante de 2.4
    assert worker_world["pb_id"] not in project_ids_seen
    # P_d (otro ws, aunque is_common): INVISIBLE — worker no tiene member en ese ws
    assert worker_world["pd_id"] not in project_ids_seen


def test_worker_search_explicit_project_id_foreign_returns_403(client, worker_world):
    """Filtro project_id ajeno → 403 unificado anti-IDOR."""
    r = client.post(
        "/search",
        headers=auth(worker_world["worker_jwt"]),
        json={"query_text": "pytest", "project_id": worker_world["pb_id"], "limit": 5},
    )
    assert r.status_code == 403


def test_worker_search_explicit_project_id_unknown_returns_403(client, worker_world):
    """project_id inexistente → 403 igual que project ajeno (no 404 — anti-IDOR)."""
    r = client.post(
        "/search",
        headers=auth(worker_world["worker_jwt"]),
        json={"query_text": "pytest", "project_id": 999999, "limit": 5},
    )
    assert r.status_code == 403


def test_worker_search_explicit_workspace_id_foreign_returns_403(client, worker_world):
    """Filtro workspace_id ajeno → 403."""
    r = client.post(
        "/search",
        headers=auth(worker_world["worker_jwt"]),
        json={"query_text": "pytest", "workspace_id": worker_world["ws_foreign_id"], "limit": 5},
    )
    assert r.status_code == 403


def test_worker_search_explicit_project_member_works(client, worker_world):
    """Filtro project_id explícito en P_a (worker es member) → 200 con resultados."""
    r = client.post(
        "/search",
        headers=auth(worker_world["worker_jwt"]),
        json={"query_text": "pytest-search-marker-pa", "project_id": worker_world["pa_id"], "limit": 5},
    )
    assert r.status_code == 200
    # Todos los resultados deben pertenecer al project P_a.
    for res in r.json()["results"]:
        assert res["project_id"] == worker_world["pa_id"]


def test_super_search_sees_all_test_projects(client, super_jwt, worker_world):
    """Super sin filtros: debe ver memorias de los 4 projects de test."""
    r = client.post(
        "/search",
        headers=auth(super_jwt),
        json={"query_text": "pytest-search-marker semantic content", "limit": 50},
    )
    assert r.status_code == 200
    project_ids_seen = {res["project_id"] for res in r.json()["results"]}
    # Los 4 projects de pytest deberían aparecer.
    for pid_key in ["pa_id", "pb_id", "pc_id", "pd_id"]:
        assert worker_world[pid_key] in project_ids_seen


def test_team_member_can_search_team_resource_project(client, super_jwt):
    """
    Si user es team_member de team T y T tiene team_resource project P,
    /search devuelve memorias de P aunque user NO sea project_member directo
    de P y P NO sea is_common.

    Setup:
    - Crear user "team-only" sin project_members, sin lead_workspaces.
    - Crear workspace + project P (no is_common).
    - Crear memoria pública en P.
    - Crear team T → añadir team_resource P → añadir user a team T.
    - Search por marker → user-team-only ve memorias de P vía team_resources.
    """
    async def _setup():
        conn = await _aconn()
        try:
            u = await conn.fetchrow(
                "INSERT INTO users (name, active) VALUES ('pytest-search-team-only', true) RETURNING id"
            )
            user_id = u["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, 'pytest-search-team-only@local', true)",
                user_id,
            )
            key_plain, key_hash = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-search-team-only-key', $2, true)",
                key_hash, user_id,
            )
            ws = await conn.fetchrow(
                "INSERT INTO workspaces (name) VALUES ('pytest-search-team-ws') RETURNING id"
            )
            proj = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, is_common) VALUES ($1, 'pytest-search-team-proj', false) RETURNING id",
                ws["id"],
            )
            return user_id, key_plain, ws["id"], proj["id"]
        finally:
            await conn.close()

    user_id, key_plain, ws_id, proj_id = _run(_setup())

    # Crear memoria en proj_id usando super (necesita embedding via API).
    r_mem = client.post(
        "/memories",
        headers=auth(super_jwt),
        json={
            "type": "tecnico",
            "content": "pytest-search-team-marker semantic content for retrieval",
            "workspace_id": ws_id,
            "project_id": proj_id,
            "visibility": "public",
        },
    )
    assert r_mem.status_code == 201

    # Crear team + añadir user + añadir resource.
    r_team = client.post(
        "/teams", headers=auth(super_jwt),
        json={"name": "pytest-search-team"},
    )
    team_id = r_team.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": user_id},
    )
    client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": proj_id},
    )

    # Token del user. Debe re-emitirse despues de las asignaciones de team
    # porque visible_project_ids se evalua per-request, no en el token.
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]

    # Search por marker — user debe ver la memoria via team_resources.
    r_search = client.post(
        "/search",
        headers=auth(token),
        json={"query_text": "pytest-search-team-marker semantic", "limit": 5},
    )
    assert r_search.status_code == 200
    proj_ids_seen = {res["project_id"] for res in r_search.json()["results"]}
    assert proj_id in proj_ids_seen, (
        f"team_member should see project via team_resources but didn't. "
        f"results={r_search.json()['results']}"
    )

    # Cleanup adicional para que el fixture super_jwt._cleanup pueda
    # borrar el user despues (FK audit_log si team del DELETE durante el test).
    async def _post_cleanup():
        conn = await _aconn()
        try:
            await conn.execute("DELETE FROM team_resources WHERE team_id = $1", team_id)
            await conn.execute("DELETE FROM team_members WHERE team_id = $1", team_id)
            await conn.execute("DELETE FROM teams WHERE id = $1", team_id)
            await conn.execute("DELETE FROM memories WHERE project_id = $1", proj_id)
            await conn.execute("DELETE FROM projects WHERE id = $1", proj_id)
            await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
            await conn.execute("DELETE FROM api_keys WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM user_emails WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        finally:
            await conn.close()

    _run(_post_cleanup())


def test_isolated_user_with_no_assignments_returns_empty(client, super_jwt):
    """User no-super sin lead_workspaces ni project_members → search devuelve [] sin tocar GPU."""
    async def _setup():
        conn = await _aconn()
        try:
            u = await conn.fetchrow(
                "INSERT INTO users (name, active) VALUES ('pytest-search-isolated', true) RETURNING id"
            )
            user_id = u["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, 'pytest-search-isolated@local', true)",
                user_id,
            )
            key_plain, key_hash = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-search-isolated-key', $2, true)",
                key_hash, user_id,
            )
            return key_plain
        finally:
            await conn.close()

    key_plain = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    r = client.post(
        "/search",
        headers=auth(token),
        json={"query_text": "pytest-search-marker semantic content", "limit": 5},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 0
    assert r.json()["results"] == []
