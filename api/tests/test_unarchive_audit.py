"""C29: PUT /memories/{id}/unarchive records an update_staleness audit row
{"staleness": "active"} (same shape as PUT /memories/{id}/staleness), so the manual
history read by the access wake-up (C28) is right after an unarchive. Integration on
the THROWAWAY DB (conftest default 5436; live refused) in a rolled-back transaction.
"""
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL

sys.path.insert(0, str(Path(__file__).parent.parent))

import memories  # noqa: E402
from auth import get_current_user  # noqa: E402


async def _scenario(monkeypatch):
    conn = await asyncpg.connect(TEST_DB_URL)
    tx = conn.transaction()
    await tx.start()
    try:
        archived = await conn.fetchval(
            "INSERT INTO memories (workspace_id, project_id, user_id, type, content, staleness) "
            "VALUES (1, 1, 1, 'observacion', 'pytest-c29', 'archived') RETURNING id")
        active = await conn.fetchval(
            "INSERT INTO memories (workspace_id, project_id, user_id, type, content, staleness) "
            "VALUES (1, 1, 1, 'observacion', 'pytest-c29', 'active') RETURNING id")

        class _Pool:
            @asynccontextmanager
            async def acquire(self):
                yield conn

        async def _pool():
            return _Pool()

        monkeypatch.setattr(memories, "get_pool", _pool)
        app = FastAPI()
        app.include_router(memories.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}

        async def _call(mid):
            import httpx
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                return await c.put(f"/memories/{mid}/unarchive")

        r_ok = await _call(archived)
        r_404 = await _call(active)
        rows = await conn.fetch(
            "SELECT resource_id, details FROM audit_log WHERE action = 'update_staleness' "
            "AND resource = 'memory' AND resource_id = ANY($1::text[])", [str(archived), str(active)])
        staleness = await conn.fetchval("SELECT staleness FROM memories WHERE id = $1", archived)
        return r_ok.status_code, r_404.status_code, [(r["resource_id"], r["details"]) for r in rows], \
            str(archived), staleness
    finally:
        await tx.rollback()
        await conn.close()


def test_unarchive_writes_update_staleness_audit(monkeypatch):
    try:
        ok, not_archived, rows, archived_id, staleness = asyncio.run(_scenario(monkeypatch))
    except OSError as e:  # only an unreachable DB skips
        pytest.skip(f"throwaway DB not reachable: {e}")
    assert ok == 200 and not_archived == 404
    assert staleness == "active"
    assert len(rows) == 1, rows                      # none for the 404 (nothing changed)
    rid, details = rows[0]
    assert rid == archived_id
    assert (details if isinstance(details, dict) else __import__("json").loads(details)) == {"staleness": "active"}
