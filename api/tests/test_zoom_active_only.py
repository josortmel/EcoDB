"""C25 (N1): superseded twins must not appear as children/sources/parents. A
superseded cluster's content lives in its kept (active) twin, but it stays in
the parent's source_ids — so every child/source/parent lookup filters
status='active'. Router-only, fake conn recording SQL — no DB.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import clusters  # noqa: E402
from auth import get_current_user  # noqa: E402

CID = "11111111-1111-1111-1111-111111111111"
SRC = "22222222-2222-2222-2222-222222222222"


class _Conn:
    def __init__(self):
        self.sql = []

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        return []

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        return None


def _client(monkeypatch, conn):
    class _Pool:
        @asynccontextmanager
        async def acquire(self):
            yield conn

    async def _pool():
        return _Pool()

    async def _agent(c, actor, ident):
        return {"id": 1}

    async def _cluster(c, actor, cid):
        return {"id": cid, "agent_id": 1, "level": "monthly", "label": "m", "member_ids": [],
                "source_ids": [SRC], "status": "active", "period_start": "2026-09-01", "period_end": "2026-09-30",
                "created_at": "2026-09-01T00:00:00", "metadata": {}, "workspace_id": 1}

    monkeypatch.setattr(clusters, "get_pool", _pool)
    monkeypatch.setattr(clusters, "resolve_agent_for_actor", _agent)
    monkeypatch.setattr(clusters, "resolve_cluster_for_actor", _cluster)
    app = FastAPI()
    app.include_router(clusters.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}
    return TestClient(app)


def _cluster_selects(conn):
    return [s for s in conn.sql if "FROM memory_clusters" in s]


def test_zoom_drilldown_children_are_active_only(monkeypatch):
    conn = _Conn()
    r = _client(monkeypatch, conn).post("/clusters/zoom", json={"agent_identifier": "Eco", "cluster_id": CID})
    assert r.status_code == 200, r.text
    child_sql = [s for s in _cluster_selects(conn) if "ANY($1::uuid[])" in s]
    assert child_sql and all("status = 'active'" in s for s in child_sql), child_sql


def test_sources_and_parents_are_active_only(monkeypatch):
    conn = _Conn()
    r = _client(monkeypatch, conn).get(f"/clusters/{CID}/sources")
    assert r.status_code == 200, r.text
    sel = _cluster_selects(conn)
    assert len(sel) == 2, sel
    assert all("status = 'active'" in s for s in sel), sel
