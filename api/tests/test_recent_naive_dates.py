"""C13: /memories/recent with one naive and one aware date used to compare
naive vs aware datetimes -> TypeError -> 500. Naive values are read as UTC
(same rule as SearchRequest). The date validation runs before any DB access,
so a router-only app with the auth dependency overridden is enough — no DB.
"""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import memories  # noqa: E402
from auth import get_current_user  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(memories.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}
    return TestClient(app, raise_server_exceptions=False)


def test_mixed_naive_aware_inverted_window_is_422_not_500():
    r = _client().get("/memories/recent",
                      params={"fecha_desde": "2026-09-17", "fecha_hasta": "2026-09-16T10:00:00Z"})
    assert r.status_code == 422, r.text


def test_as_utc_helper():
    from datetime import datetime, timezone
    assert memories._as_utc(datetime(2026, 9, 16)) == datetime(2026, 9, 16, tzinfo=timezone.utc)
    aware = datetime(2026, 9, 16, 2, tzinfo=timezone.utc)
    assert memories._as_utc(aware) is aware
    assert memories._as_utc(None) is None


def test_recent_rejects_unknown_type_before_db():
    """C13: `type` filter is validated against MemoryType (API-side, not client-side)."""
    r = _client().get("/memories/recent", params={"type": "not-a-type"})
    assert r.status_code == 422
