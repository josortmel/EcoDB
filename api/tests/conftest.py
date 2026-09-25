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
from urllib.parse import parse_qs, urlparse

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


def _resolve_targets(dsn=None, host=None, port=None) -> list[tuple[str, int]]:
    """(host, port) pairs asyncpg would try, libpq-style: explicit kwargs, then the
    DSN netloc (comma-separated multi-host allowed), then ?host=/?port= in the DSN,
    then PGHOST/PGPORT, then localhost:5432."""
    dsn_hosts: list[str] = []
    dsn_ports: list[str] = []
    query: dict = {}
    if dsn:
        parsed = urlparse(dsn)
        query = parse_qs(parsed.query)
        netloc = parsed.netloc.rsplit("@", 1)[-1]
        for part in filter(None, netloc.split(",")):
            if part.startswith("["):  # bracketed IPv6: [::1]:5435
                h, _, rest = part[1:].partition("]")
                p = rest[1:] if rest.startswith(":") else ""
            elif part.count(":") == 1:
                h, _, p = part.partition(":")
            else:
                h, p = part, ""
            dsn_hosts.append(h)
            dsn_ports.append(p)
    hosts = ([host] if host else None) or [h for h in dsn_hosts if h] or query.get("host") \
        or [os.environ.get("PGHOST") or "localhost"]
    ports = ([str(port)] if port else None) or [p for p in dsn_ports if p] or query.get("port") \
        or [os.environ.get("PGPORT") or "5432"]
    if len(ports) == 1:
        ports = ports * len(hosts)
    return [(h, int(p)) for h, p in zip(hosts, ports)]


def _targets_live_db(dsn=None, host=None, port=None) -> bool:
    return any(p in LIVE_DB_PORTS or h in LIVE_DB_HOSTS for h, p in _resolve_targets(dsn, host, port))


def _refuse_live(dsn=None, **kwargs) -> None:
    if os.environ.get("ECODB_ALLOW_LIVE_TESTS") == "1":
        return
    if _targets_live_db(dsn, kwargs.get("host"), kwargs.get("port")):
        pytest.exit(
            "REFUSED: test tried to connect to the live family DB "
            f"({_resolve_targets(dsn, kwargs.get('host'), kwargs.get('port'))}). "
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
