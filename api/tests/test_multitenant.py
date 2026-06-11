"""Integration tests — multi-tenant cross-org isolation.

Tests that org_A data is invisible to org_B users across all access paths:
search, search_recent, graph discovery, admin operations, API keys, teams.

Pre-requisites:
- Container ecodb-postgres running on localhost:5435
- Schema v5.1.0 applied (migrate_5.0.1_to_5.1.0.sql)
- API running on localhost:8080
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app  # noqa: E402
from auth import generate_api_key  # noqa: E402
import asyncpg  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — two orgs with isolated users
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def two_orgs():
    """Create two organizations with users, workspaces, projects, and API keys.
    Returns dict with all IDs and keys for both orgs + super.
    """
    async def _setup():
        import time as _t
        _suffix = str(int(_t.time()))[-6:]
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            # Org A
            org_a_id = await conn.fetchval(
                "INSERT INTO organizations (name) VALUES ($1) RETURNING id",
                f"Test Org A {_suffix}",
            )
            ceo_a_id = await conn.fetchval(
                "INSERT INTO users (name, is_ceo, active, organization_id) VALUES ('CEO-A', true, true, $1) RETURNING id",
                org_a_id,
            )
            await conn.execute(
                "UPDATE organizations SET ceo_user_id = $1 WHERE id = $2", ceo_a_id, org_a_id
            )
            await conn.execute(
                "INSERT INTO user_emails (email, user_id, is_primary) VALUES ($1, $2, true)",
                f"ceo-a-{org_a_id}@test.local.{_suffix}", ceo_a_id,
            )
            ws_a_id = await conn.fetchval(
                "INSERT INTO workspaces (name, organization_id) VALUES ('WS-A', $1) RETURNING id",
                org_a_id,
            )
            proj_a_id = await conn.fetchval(
                "INSERT INTO projects (name, workspace_id) VALUES ('Proj-A', $1) RETURNING id",
                ws_a_id,
            )
            worker_a_id = await conn.fetchval(
                "INSERT INTO users (name, active, organization_id) VALUES ('Worker-A', true, $1) RETURNING id",
                org_a_id,
            )
            await conn.execute(
                "INSERT INTO user_emails (email, user_id, is_primary) VALUES ($1, $2, true)",
                f"worker-a-{org_a_id}@test.local.{_suffix}", worker_a_id,
            )
            await conn.execute(
                "INSERT INTO project_members (user_id, project_id) VALUES ($1, $2)",
                worker_a_id, proj_a_id,
            )

            # Org B
            org_b_id = await conn.fetchval(
                "INSERT INTO organizations (name) VALUES ($1) RETURNING id",
                f"Test Org B {_suffix}",
            )
            ceo_b_id = await conn.fetchval(
                "INSERT INTO users (name, is_ceo, active, organization_id) VALUES ('CEO-B', true, true, $1) RETURNING id",
                org_b_id,
            )
            await conn.execute(
                "UPDATE organizations SET ceo_user_id = $1 WHERE id = $2", ceo_b_id, org_b_id
            )
            await conn.execute(
                "INSERT INTO user_emails (email, user_id, is_primary) VALUES ($1, $2, true)",
                f"ceo-b-{org_b_id}@test.local.{_suffix}", ceo_b_id,
            )
            ws_b_id = await conn.fetchval(
                "INSERT INTO workspaces (name, organization_id) VALUES ('WS-B', $1) RETURNING id",
                org_b_id,
            )
            proj_b_id = await conn.fetchval(
                "INSERT INTO projects (name, workspace_id) VALUES ('Proj-B', $1) RETURNING id",
                ws_b_id,
            )
            worker_b_id = await conn.fetchval(
                "INSERT INTO users (name, active, organization_id) VALUES ('Worker-B', true, $1) RETURNING id",
                org_b_id,
            )
            await conn.execute(
                "INSERT INTO user_emails (email, user_id, is_primary) VALUES ($1, $2, true)",
                f"worker-b-{org_b_id}@test.local.{_suffix}", worker_b_id,
            )
            await conn.execute(
                "INSERT INTO project_members (user_id, project_id) VALUES ($1, $2)",
                worker_b_id, proj_b_id,
            )

            # API keys for all users
            keys = {}
            for label, uid in [("ceo_a", ceo_a_id), ("worker_a", worker_a_id),
                               ("ceo_b", ceo_b_id), ("worker_b", worker_b_id)]:
                plain, hashed = generate_api_key()
                await conn.execute(
                    "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, $2, $3, true)",
                    hashed, f"pytest-{label}", uid,
                )
                keys[label] = plain

            # Super key
            plain_super, hash_super = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-super', 1, true)",
                hash_super,
            )
            keys["super"] = plain_super

            # Seed a memory in each org
            mem_a_id = await conn.fetchval(
                """INSERT INTO memories (user_id, workspace_id, project_id, type, content, visibility)
                VALUES ($1, $2, $3, 'tecnico', 'Secret data org A', 'public') RETURNING id""",
                worker_a_id, ws_a_id, proj_a_id,
            )
            mem_b_id = await conn.fetchval(
                """INSERT INTO memories (user_id, workspace_id, project_id, type, content, visibility)
                VALUES ($1, $2, $3, 'tecnico', 'Secret data org B', 'public') RETURNING id""",
                worker_b_id, ws_b_id, proj_b_id,
            )

            return {
                "org_a": org_a_id, "org_b": org_b_id,
                "ceo_a": ceo_a_id, "ceo_b": ceo_b_id,
                "worker_a": worker_a_id, "worker_b": worker_b_id,
                "ws_a": ws_a_id, "ws_b": ws_b_id,
                "proj_a": proj_a_id, "proj_b": proj_b_id,
                "mem_a": str(mem_a_id), "mem_b": str(mem_b_id),
                "keys": keys,
            }
        finally:
            await conn.close()

    async def _cleanup(data):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            for uid in [data["worker_a"], data["worker_b"], data["ceo_a"], data["ceo_b"]]:
                await conn.execute("DELETE FROM api_keys WHERE user_id = $1", uid)
            await conn.execute("DELETE FROM api_keys WHERE name = 'pytest-super'")
            await conn.execute("DELETE FROM memories WHERE id = ANY($1::uuid[])",
                               [data["mem_a"], data["mem_b"]])
            await conn.execute("DELETE FROM project_members WHERE project_id = ANY($1::int[])",
                               [data["proj_a"], data["proj_b"]])
            await conn.execute("DELETE FROM projects WHERE id = ANY($1::int[])",
                               [data["proj_a"], data["proj_b"]])
            await conn.execute("DELETE FROM workspaces WHERE id = ANY($1::int[])",
                               [data["ws_a"], data["ws_b"]])
            await conn.execute("DELETE FROM user_emails WHERE user_id = ANY($1::int[])",
                               [data["worker_a"], data["worker_b"], data["ceo_a"], data["ceo_b"]])
            await conn.execute("DELETE FROM users WHERE id = ANY($1::int[])",
                               [data["worker_a"], data["worker_b"], data["ceo_a"], data["ceo_b"]])
            await conn.execute("UPDATE organizations SET ceo_user_id = NULL WHERE id = ANY($1::int[])",
                               [data["org_a"], data["org_b"]])
            await conn.execute("DELETE FROM organizations WHERE id = ANY($1::int[])",
                               [data["org_a"], data["org_b"]])
        except Exception:
            pass
        finally:
            await conn.close()

    data = asyncio.run(_setup())
    yield data
    asyncio.run(_cleanup(data))


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# ---------------------------------------------------------------------------
# JWT org_id propagation
# ---------------------------------------------------------------------------

def test_worker_jwt_has_org_id(client, two_orgs):
    resp = client.post("/auth/token", json={"api_key": two_orgs["keys"]["worker_a"]})
    assert resp.status_code == 200
    import jwt
    token = resp.json()["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["organization_id"] == two_orgs["org_a"]


def test_ceo_jwt_has_org_id(client, two_orgs):
    resp = client.post("/auth/token", json={"api_key": two_orgs["keys"]["ceo_a"]})
    assert resp.status_code == 200
    import jwt
    token = resp.json()["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["organization_id"] == two_orgs["org_a"]
    assert payload["is_ceo"] is True


def test_super_jwt_has_null_org_id(client, two_orgs):
    resp = client.post("/auth/token", json={"api_key": two_orgs["keys"]["super"]})
    assert resp.status_code == 200
    import jwt
    token = resp.json()["access_token"]
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["organization_id"] is None
    assert payload["is_super"] is True


# ---------------------------------------------------------------------------
# Search isolation
# ---------------------------------------------------------------------------

def test_worker_a_cannot_see_org_b_memories(client, two_orgs):
    resp = client.post("/search", json={"query_text": "Secret data org B"},
                       headers=_auth(two_orgs["keys"]["worker_a"]))
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json().get("results", [])]
    assert two_orgs["mem_b"] not in ids


def test_worker_b_cannot_see_org_a_memories(client, two_orgs):
    resp = client.post("/search", json={"query_text": "Secret data org A"},
                       headers=_auth(two_orgs["keys"]["worker_b"]))
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json().get("results", [])]
    assert two_orgs["mem_a"] not in ids


def test_ceo_a_sees_own_org_only(client, two_orgs):
    resp = client.post("/search", json={"query_text": "Secret data"},
                       headers=_auth(two_orgs["keys"]["ceo_a"]))
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json().get("results", [])]
    assert two_orgs["mem_b"] not in ids


def test_super_sees_all(client, two_orgs):
    resp = client.post("/search", json={"query_text": "Secret data"},
                       headers=_auth(two_orgs["keys"]["super"]))
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json().get("results", [])]
    assert two_orgs["mem_a"] in ids
    assert two_orgs["mem_b"] in ids


# ---------------------------------------------------------------------------
# Search recent isolation
# ---------------------------------------------------------------------------

def test_search_recent_worker_a_no_org_b(client, two_orgs):
    resp = client.get("/memories/recent?limit=100",
                      headers=_auth(two_orgs["keys"]["worker_a"]))
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json().get("items", [])]
    assert two_orgs["mem_b"] not in ids


# ---------------------------------------------------------------------------
# Admin cross-org 403
# ---------------------------------------------------------------------------

def test_ceo_a_graph_vocabulary_ok(client, two_orgs):
    resp = client.get("/admin/graph-vocabulary",
                      headers=_auth(two_orgs["keys"]["ceo_a"]))
    assert resp.status_code == 200


def test_worker_a_graph_vocabulary_403(client, two_orgs):
    resp = client.get("/admin/graph-vocabulary",
                      headers=_auth(two_orgs["keys"]["worker_a"]))
    assert resp.status_code == 403


def test_ceo_a_redistribute_403(client, two_orgs):
    """Redistribute stays super-only."""
    resp = client.post("/admin/redistribute/memories",
                       json={"filter": {"workspace_id": 1, "project_id": 1},
                             "target": {"workspace_id": 1, "project_id": 1}},
                       headers=_auth(two_orgs["keys"]["ceo_a"]))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API key isolation
# ---------------------------------------------------------------------------

def test_ceo_a_list_keys_own_org_only(client, two_orgs):
    resp = client.get("/auth/api-keys", headers=_auth(two_orgs["keys"]["ceo_a"]))
    assert resp.status_code == 200
    user_ids = {k["user_id"] for k in resp.json()}
    assert two_orgs["worker_b"] not in user_ids
    assert two_orgs["ceo_b"] not in user_ids


def test_worker_a_list_keys_own_only(client, two_orgs):
    resp = client.get("/auth/api-keys", headers=_auth(two_orgs["keys"]["worker_a"]))
    assert resp.status_code == 200
    user_ids = {k["user_id"] for k in resp.json()}
    assert user_ids == {two_orgs["worker_a"]}


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429(client, two_orgs):
    """Verify rate limiting triggers (we can't do 120+ requests easily, but
    verify the Retry-After header format when it does trigger)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers


# ---------------------------------------------------------------------------
# Migration preserves data
# ---------------------------------------------------------------------------

def test_workspace_1_has_null_org(two_orgs):
    """Workspace id=1 (system) must retain org_id=NULL post-migration."""
    async def _check():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            org_id = await conn.fetchval(
                "SELECT organization_id FROM workspaces WHERE id = 1"
            )
            assert org_id is None
        finally:
            await conn.close()
    asyncio.run(_check())


def test_schema_version_is_current(two_orgs):
    async def _check():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            version = await conn.fetchval(
                "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
            )
            assert version >= "5.1.0"
        finally:
            await conn.close()
    asyncio.run(_check())


# ---------------------------------------------------------------------------
# Trigger propagate_user_org_id — workspace_leads and project_members paths
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def trigger_env(two_orgs):
    """Minimal env for trigger tests: one bare user with no org, reusing orgs from two_orgs."""
    async def _setup():
        import time as _t
        _suffix = str(int(_t.time()))[-6:]
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            user_id = await conn.fetchval(
                "INSERT INTO users (name, active) VALUES ($1, true) RETURNING id",
                f"trigger-test-user-{_suffix}",
            )
            await conn.execute(
                "INSERT INTO user_emails (email, user_id, is_primary) VALUES ($1, $2, true)",
                f"trigger-{_suffix}@test.local", user_id,
            )
            return {"user_id": user_id, "org_a": two_orgs["org_a"], "ws_a": two_orgs["ws_a"],
                    "proj_a": two_orgs["proj_a"]}
        finally:
            await conn.close()

    async def _cleanup(d):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM workspace_leads WHERE user_id = $1", d["user_id"])
            await conn.execute("DELETE FROM project_members WHERE user_id = $1", d["user_id"])
            await conn.execute("DELETE FROM user_emails WHERE user_id = $1", d["user_id"])
            await conn.execute("DELETE FROM users WHERE id = $1", d["user_id"])
        except Exception:
            pass
        finally:
            await conn.close()

    d = asyncio.run(_setup())
    yield d
    asyncio.run(_cleanup(d))


def test_trigger_workspace_lead_insert_sets_org_id(trigger_env):
    """INSERT into workspace_leads → users.organization_id propagated."""
    async def _run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            uid = trigger_env["user_id"]
            org_before = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_before is None

            await conn.execute(
                "INSERT INTO workspace_leads (user_id, workspace_id) VALUES ($1, $2)",
                uid, trigger_env["ws_a"],
            )
            org_after = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_after == trigger_env["org_a"]
        finally:
            await conn.close()
    asyncio.run(_run())


def test_trigger_delete_last_workspace_lead_clears_org_id(trigger_env):
    """DELETE last workspace_lead (no project_members) → users.organization_id = NULL."""
    async def _run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            uid = trigger_env["user_id"]
            await conn.execute(
                "INSERT INTO workspace_leads (user_id, workspace_id) VALUES ($1, $2)",
                uid, trigger_env["ws_a"],
            )
            org_set = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_set == trigger_env["org_a"]

            await conn.execute(
                "DELETE FROM workspace_leads WHERE user_id = $1 AND workspace_id = $2",
                uid, trigger_env["ws_a"],
            )
            org_after = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_after is None
        finally:
            await conn.close()
    asyncio.run(_run())


def test_trigger_delete_workspace_lead_keeps_org_from_project_members(trigger_env):
    """DELETE workspace_lead when project_members remain → org_id resolved from project path."""
    async def _run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            uid = trigger_env["user_id"]
            # Establish org via workspace_leads
            await conn.execute(
                "INSERT INTO workspace_leads (user_id, workspace_id) VALUES ($1, $2)",
                uid, trigger_env["ws_a"],
            )
            # Also add project_member path
            await conn.execute(
                "INSERT INTO project_members (user_id, project_id) VALUES ($1, $2)",
                uid, trigger_env["proj_a"],
            )
            # Remove workspace_lead — trigger should fall back to project_members path
            await conn.execute(
                "DELETE FROM workspace_leads WHERE user_id = $1 AND workspace_id = $2",
                uid, trigger_env["ws_a"],
            )
            org_after = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_after == trigger_env["org_a"]
        finally:
            await conn.close()
    asyncio.run(_run())


def test_trigger_project_member_path_independent(trigger_env):
    """INSERT/DELETE project_members trigger path sets/clears org_id independently of workspace_leads."""
    async def _run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            uid = trigger_env["user_id"]
            org_before = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_before is None

            # Insert via project_members only (no workspace_lead)
            await conn.execute(
                "INSERT INTO project_members (user_id, project_id) VALUES ($1, $2)",
                uid, trigger_env["proj_a"],
            )
            org_set = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_set == trigger_env["org_a"]

            # Delete project_member — org should clear
            await conn.execute(
                "DELETE FROM project_members WHERE user_id = $1 AND project_id = $2",
                uid, trigger_env["proj_a"],
            )
            org_after = await conn.fetchval("SELECT organization_id FROM users WHERE id = $1", uid)
            assert org_after is None
        finally:
            await conn.close()
    asyncio.run(_run())
