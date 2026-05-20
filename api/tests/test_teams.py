"""Tests integración — equipos ad-hoc.

Cubre los 9 endpoints + cascada (super only para gestión + member para read)
+ anti-IDOR + audit log atómico DELETE + idempotencia members/resources.
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
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-teams-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            await conn.execute(
                """
                DELETE FROM audit_log
                WHERE resource = 'team'
                  AND (user_id = 1 OR user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-teams-%'))
                """
            )
            await conn.execute("DELETE FROM team_resources WHERE team_id IN (SELECT id FROM teams WHERE name LIKE 'pytest-teams-%')")
            await conn.execute("DELETE FROM team_members WHERE team_id IN (SELECT id FROM teams WHERE name LIKE 'pytest-teams-%')")
            await conn.execute("DELETE FROM teams WHERE name LIKE 'pytest-teams-%'")
            await conn.execute("DELETE FROM project_members WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-teams-%')")
            await conn.execute("DELETE FROM projects WHERE name LIKE 'pytest-teams-%'")
            await conn.execute("DELETE FROM workspaces WHERE name LIKE 'pytest-teams-%'")
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-teams-%'")
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-teams-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-teams-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


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
            key_hash, f"pytest-teams-user-{name}", user_id,
        )
        return user_id, key_plain
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def member_setup(client):
    user_id, key_plain = _run(_create_user_simple("pytest-teams-member"))
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "jwt": token}


@pytest.fixture(scope="module")
def outsider_setup(client):
    user_id, key_plain = _run(_create_user_simple("pytest-teams-outsider"))
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "jwt": token}


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# POST /teams — solo super
# ===========================================================================

def test_super_creates_team(client, super_jwt):
    r = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-alfa"})
    assert r.status_code == 201
    assert r.json()["name"] == "pytest-teams-alfa"


def test_member_cannot_create_team(client, member_setup):
    r = client.post("/teams", headers=auth(member_setup["jwt"]), json={"name": "pytest-teams-fail"})
    assert r.status_code == 403


def test_duplicate_team_name_returns_409(client, super_jwt):
    name = "pytest-teams-dup"
    client.post("/teams", headers=auth(super_jwt), json={"name": name})
    r = client.post("/teams", headers=auth(super_jwt), json={"name": name})
    assert r.status_code == 409


def test_create_team_blank_name_returns_422(client, super_jwt):
    r = client.post("/teams", headers=auth(super_jwt), json={"name": "   "})
    assert r.status_code == 422


def test_create_team_extra_field_returns_422(client, super_jwt):
    r = client.post(
        "/teams", headers=auth(super_jwt),
        json={"name": "pytest-teams-extra", "rogue": 1},
    )
    assert r.status_code == 422


# ===========================================================================
# GET /teams — super ve todos, member ve los suyos, outsider ve [].
# ===========================================================================

def test_super_lists_all_teams(client, super_jwt):
    r = client.get("/teams", headers=auth(super_jwt))
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["items"]]
    assert "pytest-teams-alfa" in names


def test_outsider_sees_no_teams(client, outsider_setup):
    r = client.get("/teams", headers=auth(outsider_setup["jwt"]))
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_member_sees_only_own_teams(client, super_jwt, member_setup):
    """Crear team + añadir member → /teams del member lo ve."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-with-member"})
    team_id = r1.json()["id"]
    r2 = client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    assert r2.status_code == 201

    r3 = client.get("/teams", headers=auth(member_setup["jwt"]))
    assert r3.status_code == 200
    ids = [t["id"] for t in r3.json()["items"]]
    assert team_id in ids


# ===========================================================================
# GET /teams/{id}
# ===========================================================================

def test_super_reads_any_team_with_members_resources(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-detail"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r = client.get(f"/teams/{team_id}", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == team_id
    assert member_setup["user_id"] in body["member_user_ids"]
    assert body["resource_project_ids"] == []


def test_member_reads_own_team(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-member-read"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r = client.get(f"/teams/{team_id}", headers=auth(member_setup["jwt"]))
    assert r.status_code == 200


def test_outsider_cannot_read_team(client, super_jwt, outsider_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-outsider-blind"})
    team_id = r1.json()["id"]
    r = client.get(f"/teams/{team_id}", headers=auth(outsider_setup["jwt"]))
    assert r.status_code == 403


def test_get_unknown_team_returns_403(client, super_jwt):
    """Anti-IDOR: super tampoco recibe 404."""
    r = client.get("/teams/999999", headers=auth(super_jwt))
    assert r.status_code == 403


# ===========================================================================
# PUT /teams/{id} — solo super
# ===========================================================================

def test_super_renames_team(client, super_jwt):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-rename-orig"})
    team_id = r1.json()["id"]
    r2 = client.put(
        f"/teams/{team_id}", headers=auth(super_jwt),
        json={"name": "pytest-teams-rename-new"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "pytest-teams-rename-new"


def test_member_cannot_rename_team(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-no-rename"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r = client.put(
        f"/teams/{team_id}", headers=auth(member_setup["jwt"]),
        json={"name": "pytest-teams-hacked"},
    )
    assert r.status_code == 403


def test_put_unknown_team_returns_403(client, super_jwt):
    r = client.put(
        "/teams/999999", headers=auth(super_jwt),
        json={"name": "pytest-teams-x"},
    )
    assert r.status_code == 403


# ===========================================================================
# DELETE /teams/{id} — solo super + audit_log + CASCADE
# ===========================================================================

def test_super_deletes_team_with_audit_log(client, super_jwt, member_setup):
    """DELETE team CASCADE elimina team_members. Audit log atómico."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-delete-target"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r2 = client.delete(f"/teams/{team_id}", headers=auth(super_jwt))
    assert r2.status_code == 204

    # CASCADE: team_members eliminados.
    async def _check():
        conn = await _aconn()
        try:
            tm = await conn.fetchval(
                "SELECT count(*) FROM team_members WHERE team_id = $1", team_id
            )
            audit = await conn.fetchrow(
                """
                SELECT user_id, action, resource, resource_id, details
                FROM audit_log
                WHERE resource = 'team' AND resource_id = $1
                ORDER BY created_at DESC LIMIT 1
                """,
                str(team_id),
            )
            return tm, audit
        finally:
            await conn.close()

    tm_count, audit = _run(_check())
    assert tm_count == 0
    assert audit is not None
    assert audit["action"] == "delete"
    assert audit["user_id"] == 1
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["name"] == "pytest-teams-delete-target"


def test_member_cannot_delete_team(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-no-delete"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r = client.delete(f"/teams/{team_id}", headers=auth(member_setup["jwt"]))
    assert r.status_code == 403


def test_delete_unknown_team_returns_403(client, super_jwt):
    r = client.delete("/teams/999999", headers=auth(super_jwt))
    assert r.status_code == 403


# ===========================================================================
# POST /teams/{id}/members
# ===========================================================================

def test_add_member_idempotent(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-idempotent-m"})
    team_id = r1.json()["id"]
    r2 = client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    assert r2.status_code == 201
    # Mismo INSERT otra vez → 201, no 409 (ON CONFLICT DO NOTHING).
    r3 = client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    assert r3.status_code == 201


def test_add_member_unknown_user_returns_422(client, super_jwt):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-bad-user"})
    team_id = r1.json()["id"]
    r2 = client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": 999999},
    )
    assert r2.status_code == 422


def test_add_member_to_unknown_team_returns_403(client, super_jwt, member_setup):
    r = client.post(
        "/teams/999999/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    assert r.status_code == 403


def test_remove_member(client, super_jwt, member_setup):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-remove-m"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    r2 = client.delete(
        f"/teams/{team_id}/members/{member_setup['user_id']}",
        headers=auth(super_jwt),
    )
    assert r2.status_code == 204


# ===========================================================================
# POST /teams/{id}/resources
# ===========================================================================

def test_add_resource_idempotent(client, super_jwt):
    """Vincular project=1 (default) al team. Idempotente."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-res-team"})
    team_id = r1.json()["id"]
    r2 = client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 1},
    )
    assert r2.status_code == 201
    r3 = client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 1},
    )
    assert r3.status_code == 201


def test_add_resource_unknown_project_returns_422(client, super_jwt):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-bad-proj"})
    team_id = r1.json()["id"]
    r2 = client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 999999},
    )
    assert r2.status_code == 422


def test_remove_member_from_unknown_team_returns_403(client, super_jwt):
    """Anti-IDOR adv-code Loop 1 gap: DELETE /members/X en team inexistente → 403."""
    r = client.delete("/teams/999999/members/1", headers=auth(super_jwt))
    assert r.status_code == 403


def test_remove_non_member_user_idempotent(client, super_jwt):
    """Docstring promete idempotencia: DELETE de user que no es member → 204."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-idem-rm"})
    team_id = r1.json()["id"]
    # User existe pero NO es member del team.
    r = client.delete(f"/teams/{team_id}/members/1", headers=auth(super_jwt))
    assert r.status_code == 204


def test_remove_resource_from_unknown_team_returns_403(client, super_jwt):
    r = client.delete("/teams/999999/resources/1", headers=auth(super_jwt))
    assert r.status_code == 403


def test_put_team_duplicate_name_returns_409(client, super_jwt):
    client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-put-collision-a"})
    r2 = client.post(
        "/teams", headers=auth(super_jwt), json={"name": "pytest-teams-put-collision-b"}
    )
    team_id = r2.json()["id"]
    r3 = client.put(
        f"/teams/{team_id}", headers=auth(super_jwt),
        json={"name": "pytest-teams-put-collision-a"},
    )
    assert r3.status_code == 409


def test_audit_log_for_add_member(client, super_jwt, member_setup):
    """VS1 fix Loop 1: POST /teams/{id}/members deja entry en audit_log."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-audit-add-mem"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT user_id, action, resource, resource_id, details
                FROM audit_log
                WHERE resource = 'team' AND resource_id = $1 AND action = 'add_member'
                ORDER BY created_at DESC LIMIT 1
                """,
                str(team_id),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    assert audit["action"] == "add_member"
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["user_id"] == member_setup["user_id"]


def test_audit_log_for_remove_member(client, super_jwt, member_setup):
    """VS1 fix: DELETE /teams/{id}/members/{user_id} deja entry."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-audit-rm-mem"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/members", headers=auth(super_jwt),
        json={"user_id": member_setup["user_id"]},
    )
    client.delete(
        f"/teams/{team_id}/members/{member_setup['user_id']}",
        headers=auth(super_jwt),
    )

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT action, details FROM audit_log
                WHERE resource = 'team' AND resource_id = $1 AND action = 'remove_member'
                ORDER BY created_at DESC LIMIT 1
                """,
                str(team_id),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["user_id"] == member_setup["user_id"]


def test_audit_log_for_add_resource(client, super_jwt):
    """VS1 fix: POST /teams/{id}/resources deja entry."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-audit-add-res"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 1},
    )

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT action, details FROM audit_log
                WHERE resource = 'team' AND resource_id = $1 AND action = 'add_resource'
                ORDER BY created_at DESC LIMIT 1
                """,
                str(team_id),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["project_id"] == 1


def test_audit_log_for_remove_resource(client, super_jwt):
    """VS1 fix: DELETE /teams/{id}/resources/{pid} deja entry."""
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-audit-rm-res"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 1},
    )
    client.delete(f"/teams/{team_id}/resources/1", headers=auth(super_jwt))

    async def _check():
        conn = await _aconn()
        try:
            return await conn.fetchrow(
                """
                SELECT action, details FROM audit_log
                WHERE resource = 'team' AND resource_id = $1 AND action = 'remove_resource'
                ORDER BY created_at DESC LIMIT 1
                """,
                str(team_id),
            )
        finally:
            await conn.close()

    audit = _run(_check())
    assert audit is not None
    details = json.loads(audit["details"]) if isinstance(audit["details"], str) else audit["details"]
    assert details["project_id"] == 1


def test_remove_resource(client, super_jwt):
    r1 = client.post("/teams", headers=auth(super_jwt), json={"name": "pytest-teams-rem-res"})
    team_id = r1.json()["id"]
    client.post(
        f"/teams/{team_id}/resources", headers=auth(super_jwt),
        json={"project_id": 1},
    )
    r2 = client.delete(
        f"/teams/{team_id}/resources/1",
        headers=auth(super_jwt),
    )
    assert r2.status_code == 204
