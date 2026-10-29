"""#547: a save_memory queued by the MCP during an embeddings outage is re-sent later with
the id it already gave the agent (client_id) and the time it really happened (occurred_at).
Against the throwaway Postgres (5436); embeddings stubbed so the outage is controllable."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

import memories  # noqa: E402
from auth import generate_api_key  # noqa: E402
from main import create_app  # noqa: E402

FAKE_VEC = "[" + ",".join(["0.01"] * 512) + "]"
PREFIX = "pytest-replay-"


async def _fake_embed(*_a, **_k):
    return FAKE_VEC


async def _down_embed(*_a, **_k):
    raise HTTPException(503, "embeddings service unavailable: ConnectError")


def _sql(q, *args):
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetch(q, *args)
        finally:
            await conn.close()
    return asyncio.run(run())


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app("development")) as c:
        yield c


@pytest.fixture(scope="module")
def jwt(client):
    key_plain, key_hash = generate_api_key()
    key_id = _sql("INSERT INTO api_keys (key_hash, name, user_id, active) "
                  "VALUES ($1, 'pytest-replay', 1, true) RETURNING id", key_hash)[0]["id"]
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _sql("DELETE FROM api_keys WHERE id = $1", key_id)
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")


def _post(client, jwt, **extra):
    body = {"type": "observacion", "content": PREFIX + uuid.uuid4().hex,
            "workspace_id": 1, "project_id": 1, **extra}
    return client.post("/memories", headers={"Authorization": f"Bearer {jwt}"}, json=body)


def test_client_id_and_occurred_at_are_kept(client, jwt, monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    mid = uuid.uuid4()
    when = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0)
    r = _post(client, jwt, client_id=str(mid), occurred_at=when.isoformat())
    assert r.status_code == 201, r.text
    assert r.json()["id"] == str(mid)
    row = _sql("SELECT created_at FROM memories WHERE id = $1", mid)[0]
    assert row["created_at"] == when


def test_resend_returns_the_same_memory_without_embedding_again(client, jwt, monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    mid = uuid.uuid4()
    first = _post(client, jwt, client_id=str(mid))
    assert first.status_code == 201
    # embeddings down: a replay must not need it, and must not create a second row
    monkeypatch.setattr(memories, "embed_text", _down_embed)
    again = client.post("/memories", headers={"Authorization": f"Bearer {jwt}"},
                        json={"type": "observacion", "content": first.json()["content"],
                              "workspace_id": 1, "project_id": 1, "client_id": str(mid)})
    assert again.status_code == 201, again.text
    assert again.json()["id"] == str(mid)
    assert _sql("SELECT count(*) AS n FROM memories WHERE id = $1", mid)[0]["n"] == 1


def test_outage_without_client_id_is_still_503(client, jwt, monkeypatch):
    """The API keeps its invariant: no embedding, no memory. The queue lives in the MCP."""
    monkeypatch.setattr(memories, "embed_text", _down_embed)
    assert _post(client, jwt).status_code == 503


@pytest.mark.parametrize("delta", [timedelta(hours=1), -timedelta(days=8)])
def test_occurred_at_out_of_range_is_rejected(client, jwt, monkeypatch, delta):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    when = datetime.now(timezone.utc) + delta
    assert _post(client, jwt, occurred_at=when.isoformat()).status_code == 422


def test_client_id_of_another_owner_is_409(client, jwt, monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    mid = uuid.uuid4()
    _sql("INSERT INTO memories (id, user_id, workspace_id, project_id, type, content, embedding) "
         "VALUES ($1, 30, 1, 1, 'observacion', $2, $3::vector)", mid, PREFIX + "other", FAKE_VEC)
    assert _post(client, jwt, client_id=str(mid)).status_code == 409
