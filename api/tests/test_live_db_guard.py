"""C18: the test suite must never write to the live family DB (5435). The guard
wraps asyncpg.connect/create_pool in conftest, so it covers every path (direct
connects, module-level DATABASE_URL, the app's pool). Pure — no DB is reached:
the wrapped originals are replaced by stubs.
"""
import asyncpg
import pytest

import conftest

LIVE = "postgresql://ecodb:pw@localhost:5435/ecodb"
THROWAWAY = "postgresql://ecodb:pw@localhost:5436/ecodb"


def test_default_test_port_is_not_live():
    assert conftest.TEST_DB_PORT == "5436" or "TEST_DB_PORT" in __import__("os").environ
    assert asyncpg.connect is not conftest._ORIGINALS["connect"], "asyncpg.connect not guarded"
    assert asyncpg.create_pool is not conftest._ORIGINALS["create_pool"], "create_pool not guarded"


@pytest.mark.parametrize("kwargs", [
    {"dsn": LIVE},
    {"dsn": "postgresql://ecodb@postgres:5432/ecodb"},        # in-container live host
    {"dsn": None, "host": "localhost", "port": 5435},
])
def test_guard_refuses_live_without_opt_in(monkeypatch, kwargs):
    monkeypatch.delenv("ECODB_ALLOW_LIVE_TESTS", raising=False)
    with pytest.raises(pytest.exit.Exception, match="live"):
        conftest._refuse_live(kwargs.pop("dsn"), **kwargs)


def test_guard_allows_throwaway(monkeypatch):
    monkeypatch.delenv("ECODB_ALLOW_LIVE_TESTS", raising=False)
    conftest._refuse_live(THROWAWAY)  # no exit


def test_guard_allows_live_only_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ECODB_ALLOW_LIVE_TESTS", "1")
    conftest._refuse_live(LIVE)  # no exit


def test_wrapped_connect_never_reaches_asyncpg_for_live(monkeypatch):
    monkeypatch.delenv("ECODB_ALLOW_LIVE_TESTS", raising=False)
    calls = []
    guarded = conftest._guard(lambda dsn=None, *a, **kw: calls.append(dsn))
    with pytest.raises(pytest.exit.Exception):
        guarded(dsn=LIVE)
    guarded(THROWAWAY)
    assert calls == [THROWAWAY]
