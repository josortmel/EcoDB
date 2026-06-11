"""Integration tests for Memory Agent v1.3 endpoints (D1).

Covers the v1.3 surface:
- cell_configs CRUD (/api/v1/cells/configs): create/list/update/delete, 409 dup,
  422 invalid cron, 422 cron-too-frequent (15-min floor), cell_type regex reject,
  super-only write.
- cell_templates (/api/v1/cells/templates): super-only GET (403), in-use DELETE 409,
  unique-default 409.
- providers (/api/v1/providers): encrypt round-trip + masked GET, dup 409, super-only.
- clusters/search (/api/v1/clusters/search): status pattern 422, short-query 422,
  "mesa" ownership rule (embeddings-guarded).
- clusters/telescopic (/api/v1/clusters/telescopic): structure, invalid level 422,
  unknown agent 404.
- search cluster_mode (/search): include -> related_clusters, mixed -> merged_results
  (embeddings-guarded).

SAFETY: only ephemeral pytest-ma-* agents/users/templates/providers are created and
cleaned up. Real data is never touched.

Requires a live postgres at TEST_DB_URL. Embeddings/LLM-dependent tests skip when the
backend returns 5xx (service not up).
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL

# crypto reads ENCRYPTION_KEY at import — set it BEFORE importing main.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app
from auth import generate_api_key, hash_api_key
import crypto

# Guarantee a usable Fernet regardless of import order across the test session.
if not crypto.encryption_key_ok():
    crypto._FERNET = Fernet(os.environ["ENCRYPTION_KEY"].encode())

TEST_AGENT = "pytest-ma-agent"


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


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def ma_env(client):
    """Super token + non-super token + ephemeral test agent. Cleans everything up."""
    super_plain, _ = generate_api_key()
    nonsuper_plain, _ = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-ma-super', 1, true)",
                hash_api_key(super_plain))
            u = await conn.fetchrow(
                "INSERT INTO users (name, is_super, is_ceo, active) "
                "VALUES ('pytest-ma-nonsuper', false, false, true) RETURNING id")
            uid = u["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) "
                "VALUES ($1, 'pytest-ma-nonsuper@test', true)", uid)
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-ma-nonsuper', $2, true)",
                hash_api_key(nonsuper_plain), uid)
            ag = await conn.fetchrow(
                "INSERT INTO agents (identifier, user_id, active) VALUES ($1, 1, true) "
                "ON CONFLICT (identifier) DO UPDATE SET active=true RETURNING id",
                TEST_AGENT)
            return uid, ag["id"]
        finally:
            await conn.close()

    async def _cleanup(agent_id):
        conn = await _aconn()
        try:
            await conn.execute(
                "DELETE FROM cell_task_configs WHERE agent_id = $1", agent_id)
            await conn.execute(
                "DELETE FROM cell_prompt_templates WHERE name LIKE 'pytest-ma-%'")
            await conn.execute(
                "DELETE FROM llm_provider_keys WHERE provider LIKE 'pytest_ma_%'")
            await conn.execute(
                "DELETE FROM agents WHERE identifier = $1", TEST_AGENT)
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-ma-%'")
            await conn.execute(
                "DELETE FROM user_emails WHERE user_id IN "
                "(SELECT id FROM users WHERE name LIKE 'pytest-ma-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-ma-%'")
        finally:
            await conn.close()

    uid, agent_id = _run(_setup())
    super_tok = client.post("/auth/token", json={"api_key": super_plain}).json()["access_token"]
    nonsuper_tok = client.post("/auth/token", json={"api_key": nonsuper_plain}).json()["access_token"]
    yield {"super": super_tok, "nonsuper": nonsuper_tok,
           "user_id": uid, "agent_id": agent_id}
    _run(_cleanup(agent_id))


# ---------------------------------------------------------------------------
# cell_configs CRUD
# ---------------------------------------------------------------------------

CONFIGS = "/api/v1/cells/configs"


def test_config_crud(client, ma_env):
    s = _h(ma_env["super"])
    # create
    r = client.post(CONFIGS, headers=s, json={
        "agent_identifier": TEST_AGENT, "cell_type": "pytest_custom",
        "model": "deepseek-chat", "provider": "deepseek"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # list (filtered by agent)
    r = client.get(f"{CONFIGS}?agent_identifier={TEST_AGENT}", headers=s)
    assert r.status_code == 200
    assert any(c["id"] == cid for c in r.json()["items"])
    # update
    r = client.put(f"{CONFIGS}/{cid}", headers=s, json={"enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    # delete
    assert client.delete(f"{CONFIGS}/{cid}", headers=s).status_code == 204
    r = client.get(f"{CONFIGS}?agent_identifier={TEST_AGENT}", headers=s)
    assert not any(c["id"] == cid for c in r.json()["items"])


def test_config_duplicate_409(client, ma_env):
    s = _h(ma_env["super"])
    body = {"agent_identifier": TEST_AGENT, "cell_type": "pytest_dup", "level": "weekly"}
    r1 = client.post(CONFIGS, headers=s, json=body)
    assert r1.status_code == 201, r1.text
    r2 = client.post(CONFIGS, headers=s, json=body)
    assert r2.status_code == 409
    client.delete(f"{CONFIGS}/{r1.json()['id']}", headers=s)


def test_config_invalid_cron_422(client, ma_env):
    r = client.post(CONFIGS, headers=_h(ma_env["super"]), json={
        "agent_identifier": TEST_AGENT, "cell_type": "pytest_badcron",
        "schedule_cron": "not a cron"})
    assert r.status_code == 422
    assert "cron" in r.text.lower()


def test_config_cron_too_frequent_422(client, ma_env):
    # _MIN_CRON_INTERVAL_MINUTES floor (VS_L4_4): every-minute cron rejected.
    r = client.post(CONFIGS, headers=_h(ma_env["super"]), json={
        "agent_identifier": TEST_AGENT, "cell_type": "pytest_freq",
        "schedule_cron": "* * * * *"})
    assert r.status_code == 422
    assert "frequent" in r.text.lower() or "minutes" in r.text.lower()


def test_config_cell_type_regex_reject_422(client, ma_env):
    # cell_type pattern ^[a-z0-9_]+$ rejects path-traversal-ish input.
    r = client.post(CONFIGS, headers=_h(ma_env["super"]), json={
        "agent_identifier": TEST_AGENT, "cell_type": "../x"})
    assert r.status_code == 422


def test_config_non_super_write_403(client, ma_env):
    r = client.post(CONFIGS, headers=_h(ma_env["nonsuper"]), json={
        "agent_identifier": TEST_AGENT, "cell_type": "pytest_nope"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# cell_templates
# ---------------------------------------------------------------------------

TEMPLATES = "/api/v1/cells/templates"


def test_templates_list_super_only_403(client, ma_env):
    assert client.get(TEMPLATES, headers=_h(ma_env["nonsuper"])).status_code == 403
    assert client.get(TEMPLATES, headers=_h(ma_env["super"])).status_code == 200


def test_template_in_use_delete_409(client, ma_env):
    s = _h(ma_env["super"])
    t = client.post(TEMPLATES, headers=s, json={
        "name": "pytest-ma-inuse", "cell_type": "pytest_iu", "content": "x"})
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    c = client.post(CONFIGS, headers=s, json={
        "agent_identifier": TEST_AGENT, "cell_type": "pytest_iu_cfg",
        "prompt_template_id": tid})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    # in-use -> 409
    r = client.delete(f"{TEMPLATES}/{tid}", headers=s)
    assert r.status_code == 409
    assert "config" in r.text.lower()
    # free it, then delete succeeds
    client.delete(f"{CONFIGS}/{cid}", headers=s)
    assert client.delete(f"{TEMPLATES}/{tid}", headers=s).status_code == 204


def test_template_unique_default_409(client, ma_env):
    s = _h(ma_env["super"])
    a = client.post(TEMPLATES, headers=s, json={
        "name": "pytest-ma-def-a", "cell_type": "pytest_def",
        "content": "x", "is_default": True})
    assert a.status_code == 201, a.text
    b = client.post(TEMPLATES, headers=s, json={
        "name": "pytest-ma-def-b", "cell_type": "pytest_def",
        "content": "y", "is_default": True})
    assert b.status_code == 409
    assert "default" in b.text.lower()
    client.delete(f"{TEMPLATES}/{a.json()['id']}", headers=s)


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

PROVIDERS = "/api/v1/providers"


def test_provider_roundtrip_and_mask(client, ma_env):
    s = _h(ma_env["super"])
    r = client.post(PROVIDERS, headers=s, json={
        "provider": "pytest_ma_ds", "api_key": "sk-test-12345",
        "model_default": "deepseek-chat"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_key_masked"] == "sk-****...2345"
    assert "12345" not in body["api_key_masked"][:-4] or body["api_key_masked"].count("12345") == 0
    # GET masks too, never returns plaintext
    g = client.get(PROVIDERS, headers=s)
    assert g.status_code == 200
    row = next(p for p in g.json()["items"] if p["provider"] == "pytest_ma_ds")
    assert row["api_key_masked"] == "sk-****...2345"
    assert "sk-test-12345" not in g.text
    client.delete(f"{PROVIDERS}/{body['id']}", headers=s)


def test_provider_duplicate_409(client, ma_env):
    s = _h(ma_env["super"])
    r1 = client.post(PROVIDERS, headers=s, json={
        "provider": "pytest_ma_dup", "api_key": "sk-aaaa-1111"})
    assert r1.status_code == 201, r1.text
    r2 = client.post(PROVIDERS, headers=s, json={
        "provider": "pytest_ma_dup", "api_key": "sk-bbbb-2222"})
    assert r2.status_code == 409
    client.delete(f"{PROVIDERS}/{r1.json()['id']}", headers=s)


def test_provider_super_only_403(client, ma_env):
    assert client.get(PROVIDERS, headers=_h(ma_env["nonsuper"])).status_code == 403


# ---------------------------------------------------------------------------
# clusters/search
# ---------------------------------------------------------------------------

CSEARCH = "/api/v1/clusters/search"


def test_cluster_search_status_pattern_422(client, ma_env):
    r = client.post(CSEARCH, headers=_h(ma_env["super"]), json={
        "query_text": "workflow design", "status": "bogus"})
    assert r.status_code == 422


def test_cluster_search_short_query_422(client, ma_env):
    r = client.post(CSEARCH, headers=_h(ma_env["super"]), json={"query_text": "ab"})
    assert r.status_code == 422


def test_cluster_search_mesa_rule_non_super(client, ma_env):
    # Without agent_identifier, a non-super actor must only ever see SIN_AUTOR
    # clusters (contamination prevention). Embeddings-guarded.
    r = client.post(CSEARCH, headers=_h(ma_env["nonsuper"]),
                    json={"query_text": "workflow design", "limit": 10})
    if r.status_code >= 500:
        pytest.skip("embeddings/search backend not available")
    assert r.status_code == 200, r.text
    for res in r.json()["results"]:
        assert res["agent_identifier"] == "SIN_AUTOR"


# ---------------------------------------------------------------------------
# clusters/telescopic
# ---------------------------------------------------------------------------

TELE = "/api/v1/clusters/telescopic"


def test_telescopic_structure(client, ma_env):
    r = client.get(f"{TELE}?agent_identifier={TEST_AGENT}", headers=_h(ma_env["super"]))
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("weekly", "monthly", "quarterly", "yearly"):
        assert k in data and isinstance(data[k], list)


def test_telescopic_invalid_level_422(client, ma_env):
    r = client.get(f"{TELE}?agent_identifier={TEST_AGENT}&levels=bogus",
                   headers=_h(ma_env["super"]))
    assert r.status_code == 422


def test_telescopic_unknown_agent_404(client, ma_env):
    r = client.get(f"{TELE}?agent_identifier=pytest-ma-nope", headers=_h(ma_env["super"]))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# search cluster_mode (root /search)
# ---------------------------------------------------------------------------

def test_search_cluster_mode_include(client, ma_env):
    r = client.post("/search", headers=_h(ma_env["super"]),
                    json={"query_text": "workflow design", "cluster_mode": "include"})
    if r.status_code >= 500:
        pytest.skip("embeddings/search backend not available")
    assert r.status_code == 200, r.text
    assert "related_clusters" in r.json()


def test_search_cluster_mode_mixed(client, ma_env):
    r = client.post("/search", headers=_h(ma_env["super"]),
                    json={"query_text": "workflow design", "cluster_mode": "mixed"})
    if r.status_code >= 500:
        pytest.skip("embeddings/search backend not available")
    assert r.status_code == 200, r.text
    assert "merged_results" in r.json()
