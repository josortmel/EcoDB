"""#892: a save of ~2,000 chars took 64 s on 1-nov, ~55 s of it the LLM classifier (qwen 3B on CPU)
awaited before the response. The MCP gave up at 60 s and its queue re-sent the save as a twin.
The classifier now runs after the response: the save returns at once and the tag lands later.
Against the throwaway Postgres (5436); embeddings and the classifier are stubbed."""
import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

import classifier  # noqa: E402
import memories  # noqa: E402
from auth import generate_api_key  # noqa: E402
from main import create_app  # noqa: E402

FAKE_VEC = "[" + ",".join(["0.01"] * 512) + "]"
PREFIX = "pytest-892-"
SLOW = 10.0


async def _fake_embed(*_a, **_k):
    return FAKE_VEC


async def _slow_classify(_content):
    await asyncio.sleep(SLOW)
    return {"template_type": "learning", "confidence": 0.9, "fields": {}}


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
                  "VALUES ($1, 'pytest-892', 1, true) RETURNING id", key_hash)[0]["id"]
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _sql("DELETE FROM api_keys WHERE id = $1", key_id)
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")


def test_save_does_not_wait_for_the_llm_classifier(client, jwt, monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    monkeypatch.setattr(memories, "ENABLE_POST_HOC_CLASSIFIER", True)
    monkeypatch.setattr(classifier, "classify_with_llm", _slow_classify)
    # No heuristic tag, so Pass 2 (the LLM) is the one that decides.
    body = {"type": "observacion", "content": PREFIX + uuid.uuid4().hex,
            "workspace_id": 1, "project_id": 1, "client_id": str(uuid.uuid4())}
    t0 = time.monotonic()
    r = client.post("/memories", headers={"Authorization": f"Bearer {jwt}"}, json=body)
    took = time.monotonic() - t0
    assert r.status_code == 201, r.text
    assert took < SLOW, f"the save waited {took:.1f}s for the classifier"
    # The tag still arrives, after the response.
    deadline = time.monotonic() + SLOW + 5
    tags = []
    while time.monotonic() < deadline:
        tags = _sql("SELECT tags FROM memories WHERE id = $1", uuid.UUID(body["client_id"]))[0]["tags"]
        if "classified:learning" in tags:
            break
        time.sleep(0.3)
    assert "classified:learning" in tags
