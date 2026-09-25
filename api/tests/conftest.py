"""Shared test configuration and fixtures.

All test database credentials are centralized here.
Tests use the `db_url` and `api_url` fixtures instead of hardcoding.

NEVER RUN THE SUITE AGAINST THE LIVE FAMILY DB. DB-touching tests insert
fixtures, run migrations and delete rows (e.g. trash). Defaults point at a
throwaway Postgres on 5436. Any asyncpg connection to the live DB (host port
5435, or the in-compose host `postgres`/`ecodb-postgres`) aborts the whole
session via pytest.exit() unless ECODB_ALLOW_LIVE_TESTS=1 is set explicitly.
Pure tests (no DB) run anywhere. (C18, after the 2026-09-25 live-run incident.)
"""
import functools
import os
from urllib.parse import urlparse

import asyncpg
import pytest

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.environ.get("TEST_DB_PORT", "5436")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "ecodb")
TEST_DB_USER = os.environ.get("TEST_DB_USER", "ecodb")
TEST_DB_PASS = os.environ.get("TEST_DB_PASS", "ecodb_test_pass")

TEST_DB_URL = f"postgresql://{TEST_DB_USER}:{TEST_DB_PASS}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"

TEST_API_URL = os.environ.get("TEST_API_URL", "http://localhost:8080")

LIVE_DB_PORTS = {5435}
LIVE_DB_HOSTS = {"postgres", "ecodb-postgres"}
LIVE_API_PORTS = {8080}


def _targets_live_db(dsn=None, host=None, port=None) -> bool:
    if dsn:
        parsed = urlparse(dsn)
        host = host or parsed.hostname
        port = port or parsed.port
    return int(port or 5432) in LIVE_DB_PORTS or (host or "") in LIVE_DB_HOSTS


def _refuse_live(dsn=None, **kwargs) -> None:
    if os.environ.get("ECODB_ALLOW_LIVE_TESTS") == "1":
        return
    if _targets_live_db(dsn, kwargs.get("host"), kwargs.get("port")):
        pytest.exit(
            "REFUSED: test tried to connect to the live family DB "
            f"({urlparse(dsn).hostname if dsn else kwargs.get('host')}:"
            f"{urlparse(dsn).port if dsn else kwargs.get('port')}). "
            "Use the throwaway DB (TEST_DB_PORT=5436) or set ECODB_ALLOW_LIVE_TESTS=1 on purpose.",
            returncode=3,
        )


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(dsn=None, *args, **kwargs):
        _refuse_live(dsn, **kwargs)
        return fn(dsn, *args, **kwargs)
    return wrapper


# Installed at conftest import, i.e. before any test module (or api module) connects.
_ORIGINALS = {"connect": asyncpg.connect, "create_pool": asyncpg.create_pool}
asyncpg.connect = _guard(_ORIGINALS["connect"])
asyncpg.create_pool = _guard(_ORIGINALS["create_pool"])


@pytest.fixture
def db_url():
    return TEST_DB_URL


@pytest.fixture
def api_url():
    if os.environ.get("ECODB_ALLOW_LIVE_TESTS") != "1" and urlparse(TEST_API_URL).port in LIVE_API_PORTS:
        pytest.exit("REFUSED: api_url points at the live API (:8080). Set TEST_API_URL or ECODB_ALLOW_LIVE_TESTS=1.",
                    returncode=3)
    return TEST_API_URL
