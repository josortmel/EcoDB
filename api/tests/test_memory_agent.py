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
# clusters/telescopic/progressive + clusters/zoom (progressive-zoom v1.3.1)
# ---------------------------------------------------------------------------

PROG = "/api/v1/clusters/telescopic/progressive"
ZOOM = "/api/v1/clusters/zoom"

TEST_AGENT2 = "pytest-ma-agent2"


@pytest.fixture(scope="module")
def zoom_env(client, ma_env):
    """Seeds a small fractal for TEST_AGENT (relative dates, ephemeral):

      monthly  m_old  [today-75 .. today-50]  sources=[w_old1, w_old2]
      weekly   w_old1 [today-70 .. today-64]  members=[mem1]   (absorbed)
      weekly   w_old2 [today-63 .. today-57]  members=[mem2]   (absorbed)
      weekly   w_rec  [today-10 .. today-4]   members=[mem_w]  (loose week)
      memory   mem_loose  created today        (loose day)

    Plus one cluster for TEST_AGENT2 (cross-agent 404 check).
    Cleans memories before ma_env deletes the agent (FK has no cascade).
    """
    from datetime import date, datetime, time, timedelta, timezone as tz

    today = date.today()
    aid = ma_env["agent_id"]

    def _ts(d: date) -> datetime:
        return datetime.combine(d, time(10, 0), tzinfo=tz.utc)

    async def _setup():
        conn = await _aconn()
        try:
            ws = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
            pj = await conn.fetchval("SELECT id FROM projects ORDER BY id LIMIT 1")

            async def _mem(content, created):
                return await conn.fetchval(
                    "INSERT INTO memories (agent_id, workspace_id, project_id, "
                    "type, content, created_at) "
                    "VALUES ($1, $2, $3, 'tecnico', $4, $5) RETURNING id",
                    aid, ws, pj, content, created)

            mem1 = await _mem("pytest-ma zoom mem old week 1", _ts(today - timedelta(days=67)))
            mem2 = await _mem("pytest-ma zoom mem old week 2", _ts(today - timedelta(days=60)))
            mem_w = await _mem("pytest-ma zoom mem recent week", _ts(today - timedelta(days=7)))
            mem_loose = await _mem("pytest-ma zoom mem loose day", _ts(today))

            async def _cluster(agent, level, p_start, p_end, members, sources=None):
                return await conn.fetchval(
                    "INSERT INTO memory_clusters (agent_id, workspace_id, level, "
                    "label, member_ids, source_ids, period_start, period_end, status) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active') RETURNING id",
                    agent, ws, level, f"pytest-ma-{level}", members, sources,
                    p_start, p_end)

            w_old1 = await _cluster(aid, "weekly", today - timedelta(days=70),
                                    today - timedelta(days=64), [mem1])
            w_old2 = await _cluster(aid, "weekly", today - timedelta(days=63),
                                    today - timedelta(days=57), [mem2])
            w_rec = await _cluster(aid, "weekly", today - timedelta(days=10),
                                   today - timedelta(days=4), [mem_w])
            m_old = await _cluster(aid, "monthly", today - timedelta(days=75),
                                   today - timedelta(days=50), [mem1, mem2],
                                   [w_old1, w_old2])

            ag2 = await conn.fetchrow(
                "INSERT INTO agents (identifier, user_id, active) VALUES ($1, 1, true) "
                "ON CONFLICT (identifier) DO UPDATE SET active=true RETURNING id",
                TEST_AGENT2)
            mem_a2 = await _mem("pytest-ma zoom mem other agent", _ts(today))
            await conn.execute(
                "UPDATE memories SET agent_id = $1 WHERE id = $2", ag2["id"], mem_a2)
            c_other = await _cluster(ag2["id"], "weekly", today - timedelta(days=10),
                                     today - timedelta(days=4), [mem_a2])
            return {"w_old1": w_old1, "w_old2": w_old2, "w_rec": w_rec,
                    "m_old": m_old, "c_other": c_other,
                    "mem1": mem1, "mem_w": mem_w, "mem_loose": mem_loose}
        finally:
            await conn.close()

    async def _cleanup():
        conn = await _aconn()
        try:
            await conn.execute(
                "DELETE FROM memories WHERE content LIKE 'pytest-ma zoom mem%'")
            await conn.execute(
                "DELETE FROM agents WHERE identifier = $1", TEST_AGENT2)
        finally:
            await conn.close()

    ids = _run(_setup())
    yield ids
    _run(_cleanup())


def test_progressive_structure(client, ma_env, zoom_env):
    r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}", headers=_h(ma_env["super"]))
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("yearly", "quarterly", "monthly", "weekly", "recent_days"):
        assert k in data and isinstance(data[k], list)


def test_progressive_absorption(client, ma_env, zoom_env):
    """Closed periods are not re-read: weeklies covered by the monthly are
    hidden; only the loose week and the monthly itself appear."""
    r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}", headers=_h(ma_env["super"]))
    assert r.status_code == 200, r.text
    data = r.json()
    weekly_ids = {c["id"] for c in data["weekly"]}
    assert str(zoom_env["w_rec"]) in weekly_ids
    assert str(zoom_env["w_old1"]) not in weekly_ids
    assert str(zoom_env["w_old2"]) not in weekly_ids
    monthly_ids = {c["id"] for c in data["monthly"]}
    assert str(zoom_env["m_old"]) in monthly_ids


def test_progressive_recent_days_after_last_weekly(client, ma_env, zoom_env):
    """recent_days only carries memories newer than the last consolidated week."""
    r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}", headers=_h(ma_env["super"]))
    assert r.status_code == 200, r.text
    recent_ids = {m["id"] for m in r.json()["recent_days"]}
    assert str(zoom_env["mem_loose"]) in recent_ids
    assert str(zoom_env["mem_w"]) not in recent_ids  # inside w_rec period


def test_progressive_recent_days_hides_closed_week_outliers(client, ma_env, zoom_env):
    """A memory inside a consolidated week's period but NOT woven into any
    cluster (outlier) must still be hidden — closed weeks are never re-read."""
    from datetime import date, datetime, time, timedelta, timezone as tz
    today = date.today()
    created = datetime.combine(today - timedelta(days=6), time(12, 0), tzinfo=tz.utc)

    async def _ins():
        conn = await _aconn()
        try:
            ws = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
            pj = await conn.fetchval("SELECT id FROM projects ORDER BY id LIMIT 1")
            return await conn.fetchval(
                "INSERT INTO memories (agent_id, workspace_id, project_id, type, "
                "content, created_at) VALUES ($1,$2,$3,'tecnico',"
                "'pytest-ma zoom mem outlier in closed week',$4) RETURNING id",
                ma_env["agent_id"], ws, pj, created)
        finally:
            await conn.close()

    outlier_id = _run(_ins())
    try:
        r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}", headers=_h(ma_env["super"]))
        assert r.status_code == 200, r.text
        assert str(outlier_id) not in {m["id"] for m in r.json()["recent_days"]}
    finally:
        async def _del():
            conn = await _aconn()
            try:
                await conn.execute("DELETE FROM memories WHERE id=$1", outlier_id)
            finally:
                await conn.close()
        _run(_del())


def test_progressive_unknown_agent_404(client, ma_env):
    r = client.get(f"{PROG}?agent_identifier=pytest-ma-nope", headers=_h(ma_env["super"]))
    assert r.status_code == 404


def test_progressive_sections_filter(client, ma_env, zoom_env):
    """sections=monthly computes only that layer; the rest come back empty."""
    r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}&sections=monthly",
                   headers=_h(ma_env["super"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert str(zoom_env["m_old"]) in {c["id"] for c in data["monthly"]}
    assert data["weekly"] == [] and data["recent_days"] == []


def test_progressive_sections_invalid_422(client, ma_env):
    r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}&sections=bogus",
                   headers=_h(ma_env["super"]))
    assert r.status_code == 422


def test_zoom_entry_highest_level(client, ma_env, zoom_env):
    """Entry without cluster_id starts at the highest abstraction (monthly here)."""
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["parent"] is None
    assert data["child_type"] == "clusters"
    assert {c["level"] for c in data["clusters"]} == {"monthly"}
    assert str(zoom_env["m_old"]) in {c["id"] for c in data["clusters"]}


def test_zoom_explicit_level(client, ma_env, zoom_env):
    """Lineage-absorbed clusters (sources of an active parent) are hidden at
    entry — w_old1/w_old2 are read by zooming their monthly, not raw."""
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT, "level": "weekly"})
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()["clusters"]}
    assert str(zoom_env["w_rec"]) in ids
    assert str(zoom_env["w_old1"]) not in ids
    assert str(zoom_env["w_old2"]) not in ids


def test_week_rollup_absorbs_thematic_in_views(client, ma_env, zoom_env):
    """A week rollup (weekly cluster with source_ids) hides its thematic
    sources in progressive + zoom entry; zooming the rollup reveals them."""
    from datetime import date, timedelta

    today = date.today()

    async def _mk_rollup():
        conn = await _aconn()
        try:
            ws = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
            return await conn.fetchval(
                "INSERT INTO memory_clusters (agent_id, workspace_id, level, "
                "label, narrative, member_ids, source_ids, period_start, "
                "period_end, status) VALUES ($1,$2,'weekly','pytest-ma-rollup',"
                "'la semana tejida', $3, $4, $5, $6, 'active') RETURNING id",
                ma_env["agent_id"], ws,
                [zoom_env["mem_w"]], [zoom_env["w_rec"]],
                today - timedelta(days=10), today - timedelta(days=4))
        finally:
            await conn.close()

    rollup_id = _run(_mk_rollup())
    try:
        # progressive: rollup visible, thematic source hidden
        r = client.get(f"{PROG}?agent_identifier={TEST_AGENT}",
                       headers=_h(ma_env["super"]))
        weekly_ids = {c["id"] for c in r.json()["weekly"]}
        assert str(rollup_id) in weekly_ids
        assert str(zoom_env["w_rec"]) not in weekly_ids
        # zoom entry weekly: same
        z = client.post(ZOOM, headers=_h(ma_env["super"]),
                        json={"agent_identifier": TEST_AGENT, "level": "weekly"})
        entry_ids = {c["id"] for c in z.json()["clusters"]}
        assert str(rollup_id) in entry_ids
        assert str(zoom_env["w_rec"]) not in entry_ids
        # zoom INTO the rollup: thematic source revealed
        z2 = client.post(ZOOM, headers=_h(ma_env["super"]),
                         json={"agent_identifier": TEST_AGENT,
                               "cluster_id": str(rollup_id)})
        assert z2.json()["child_type"] == "clusters"
        assert {c["id"] for c in z2.json()["clusters"]} == {str(zoom_env["w_rec"])}
    finally:
        async def _del():
            conn = await _aconn()
            try:
                await conn.execute(
                    "DELETE FROM memory_clusters WHERE id=$1", rollup_id)
            finally:
                await conn.close()
        _run(_del())


def test_zoom_into_monthly_returns_source_weeklies(client, ma_env, zoom_env):
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT,
                          "cluster_id": str(zoom_env["m_old"])})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["parent"]["id"] == str(zoom_env["m_old"])
    assert data["child_type"] == "clusters"
    assert {c["id"] for c in data["clusters"]} == {
        str(zoom_env["w_old1"]), str(zoom_env["w_old2"])}


def test_zoom_into_weekly_returns_memories(client, ma_env, zoom_env):
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT,
                          "cluster_id": str(zoom_env["w_old1"])})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["child_type"] == "memories"
    assert {m["memory_id"] for m in data["memories"]} == {str(zoom_env["mem1"])}


def test_zoom_cross_agent_404(client, ma_env, zoom_env):
    """A cluster of another agent must 404 even for super when the
    agent_identifier doesn't match (anti cross-agent traversal)."""
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT,
                          "cluster_id": str(zoom_env["c_other"])})
    assert r.status_code == 404


def test_zoom_short_query_422(client, ma_env):
    r = client.post(ZOOM, headers=_h(ma_env["super"]),
                    json={"agent_identifier": TEST_AGENT, "query_text": "ab"})
    assert r.status_code == 422


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
