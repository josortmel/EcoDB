"""C16b: POST /documents/upload validates everything BEFORE a byte hits the media
store — size cap, extension denylist, permission. Now that the MCP routes every
agent document through it, it is the only gate. No DB: router-only app, fake pool.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import documents  # noqa: E402
from auth import get_current_user  # noqa: E402


class _FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield object()


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setattr(documents, "_MEDIA_STORE", str(store))
    monkeypatch.setattr(documents, "_MAX_UPLOAD_BYTES", 10)

    async def _pool():
        return _FakePool()

    async def _no_projects(conn, actor):
        return set()

    monkeypatch.setattr(documents, "get_pool", _pool)
    monkeypatch.setattr(documents, "visible_project_ids", _no_projects)
    app = FastAPI()
    app.include_router(documents.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "5", "is_super": False}
    return TestClient(app, raise_server_exceptions=False), store


def _up(client, name, data=b"hola"):
    return client.post("/documents/upload", params={"project_id": 1}, files={"file": (name, data)})


def test_no_permission_is_403_and_nothing_written(ctx):
    client, store = ctx
    r = _up(client, "x.md")
    assert r.status_code == 403
    assert not store.exists() or not any(store.iterdir())


def test_oversize_is_413_and_nothing_written(ctx):
    client, store = ctx
    r = _up(client, "x.md", b"x" * 11)
    assert r.status_code == 413
    assert not store.exists() or not any(store.iterdir())


@pytest.mark.parametrize("name", ["secrets.env", "id_rsa.pem", "run.ps1", "tool.exe", "noext", "a.m/d"])
def test_denied_or_malformed_extension_is_rejected_before_write(ctx, name):
    client, store = ctx
    r = _up(client, name)
    assert r.status_code in (400, 422), r.text
    assert not store.exists() or not any(store.iterdir())
