"""C23 (#221): after an owner rewrites a cluster narrative (PUT /clusters/{id}/narrate),
the cluster must stop claiming the cell's model. metadata.cell_model is removed (readers
then report model=None, model_source=None), kept as cell_model_before_owner, and
narrated_by="owner" is set. Router-only, fake conn — no DB.
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


class _Conn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchval(self, sql, *args):
        return 1


def _client(monkeypatch, conn):
    class _Pool:
        @asynccontextmanager
        async def acquire(self):
            yield conn

    async def _pool():
        return _Pool()

    async def _resolve(c, actor, cid):
        return {"agent_id": 1, "workspace_id": 1, "agent_identifier": "Eco"}

    async def _broadcast(*a, **k):
        return None

    monkeypatch.setattr(clusters, "get_pool", _pool)
    monkeypatch.setattr(clusters, "resolve_cluster_for_actor", _resolve)
    monkeypatch.setattr(clusters, "broadcast_event", _broadcast)
    app = FastAPI()
    app.include_router(clusters.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}
    return TestClient(app, raise_server_exceptions=False)


def test_owner_narrate_drops_cell_model_claim(monkeypatch):
    conn = _Conn()
    r = _client(monkeypatch, conn).put(f"/api/v1/clusters/{CID}/narrate", json={"narrative": "mi versión"})
    assert r.status_code == 200, r.text
    sql, args = conn.executed[0]
    assert "UPDATE memory_clusters" in sql
    assert "- 'cell_model'" in sql
    assert "'narrated_by', 'owner'" in sql
    assert "cell_model_before_owner" in sql
    assert args[0] == "mi versión"


def test_model_fields_without_cell_model_is_no_measurement():
    assert clusters._model_fields(None) == {"model": None, "model_source": None}
