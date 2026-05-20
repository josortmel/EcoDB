"""Integration tests for agent_identity REST endpoints.

Covers:
- GET /agents/{id}/identity (default max version + ?version=N + 404).
- POST /agents/{id}/identity (full snapshot, auto-increment version, validation).
- Permissions: super | owner (agent.user_id == jwt.sub). Others → 404 anti-discovery.
- Validations: MAX_FRAGMENT_SIZE, null bytes, ConfigDict extra="forbid", min_length=1.

SAFETY: Tests never touch real agents. Fixtures create and clean up a dedicated
ephemeral test agent (`pytest-agent-3-0e` linked to user_id=1).
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app
from auth import generate_api_key, hash_api_key


# Identifier del agent test efímero — único, prefijo `pytest-` para no chocar
# con agents reales del seed.
TEST_AGENT_IDENTIFIER = "pytest-agent-3-0e"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


async def _aconn():
    return await asyncpg.connect(dsn=os.environ["DATABASE_URL"])


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def test_agent_id():
    """Crea agent test dedicado al inicio del módulo. Borra al cierre.

    SAFETY: this is the only agent tests can touch; only ephemeral pytest-* agents should be created and cleaned up by tests.
    """
    async def _create():
        conn = await _aconn()
        try:
            # ON CONFLICT por si quedó residuo de un run interrumpido.
            row = await conn.fetchrow(
                "INSERT INTO agents (identifier, user_id, active) "
                "VALUES ($1, 1, true) "
                "ON CONFLICT (identifier) DO UPDATE SET active=true RETURNING id",
                TEST_AGENT_IDENTIFIER,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(agent_id: int):
        conn = await _aconn()
        try:
            # Borrar fragments del agent test (cascade desde agents.id no existe;
            # agent_identity tiene ON DELETE CASCADE, pero borramos explícito por
            # seguridad — y nunca tocamos otros agents).
            await conn.execute(
                "DELETE FROM agent_identity WHERE agent_id = $1",
                agent_id,
            )
            await conn.execute(
                "DELETE FROM agents WHERE id = $1 AND identifier = $2",
                agent_id, TEST_AGENT_IDENTIFIER,
            )
        finally:
            await conn.close()

    agent_id = _run(_create())
    yield agent_id
    _run(_cleanup(agent_id))


@pytest.fixture(scope="module")
def super_jwt(client):
    """Token for the superuser (user_id=1, is_super=true)."""
    key_plain, _ = generate_api_key()
    key_hash = hash_api_key(key_plain)

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-agents-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup():
        conn = await _aconn()
        try:
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-agents-%'")
            await conn.execute(
                "DELETE FROM user_emails WHERE user_id IN "
                "(SELECT id FROM users WHERE name LIKE 'pytest-agents-%')"
            )
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-agents-%'")
        finally:
            await conn.close()

    _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup())


@pytest.fixture(scope="module")
def owner_setup(client):
    """User no-super que es dueño de un agent test dedicado.
    Fix BC2 (adv-code Loop 1): ejercita branch propio (agent.user_id == jwt.sub)
    que super_jwt nunca toca (super bypasea siempre).
    """
    owner_key_plain, _ = generate_api_key()
    owner_key_hash = hash_api_key(owner_key_plain)
    owner_agent_id = "pytest-agent-owner"

    async def _setup():
        conn = await _aconn()
        try:
            user_row = await conn.fetchrow(
                "INSERT INTO users (name, is_super, is_ceo, active) "
                "VALUES ('pytest-agents-owner', false, false, true) RETURNING id",
            )
            user_id = user_row["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) "
                "VALUES ($1, 'pytest-agents-owner@test', true)",
                user_id,
            )
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-agents-owner', $2, true)",
                owner_key_hash, user_id,
            )
            agent_row = await conn.fetchrow(
                "INSERT INTO agents (identifier, user_id, active) "
                "VALUES ($1, $2, true) "
                "ON CONFLICT (identifier) DO UPDATE SET user_id=$2, active=true RETURNING id",
                owner_agent_id, user_id,
            )
            return user_id, agent_row["id"]
        finally:
            await conn.close()

    async def _cleanup(user_id, agent_db_id):
        conn = await _aconn()
        try:
            await conn.execute("DELETE FROM agent_identity WHERE agent_id = $1", agent_db_id)
            await conn.execute("DELETE FROM agents WHERE identifier = $1", owner_agent_id)
        finally:
            await conn.close()

    user_id, agent_db_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": owner_key_plain}).json()["access_token"]
    yield {"token": token, "user_id": user_id, "agent_id": agent_db_id, "identifier": owner_agent_id}
    _run(_cleanup(user_id, agent_db_id))


@pytest.fixture(scope="module")
def other_user_jwt(client):
    """Token de un user secundario (NO super, NO dueño de ningún agent test).
    Usado para verificar isolation: GET → 404 anti-discovery.
    """
    key_plain, _ = generate_api_key()
    key_hash = hash_api_key(key_plain)

    async def _setup():
        conn = await _aconn()
        try:
            user_row = await conn.fetchrow(
                "INSERT INTO users (name, is_super, is_ceo, active) "
                "VALUES ('pytest-agents-other', false, false, true) RETURNING id",
            )
            user_id = user_row["id"]
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) "
                "VALUES ($1, 'pytest-agents-other@test', true)",
                user_id,
            )
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) "
                "VALUES ($1, 'pytest-agents-other', $2, true)",
                key_hash, user_id,
            )
            return user_id
        finally:
            await conn.close()

    _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _path() -> str:
    """Path del endpoint para el agent test."""
    return f"/agents/{TEST_AGENT_IDENTIFIER}/identity"


# ---------------------------------------------------------------------------
# GET — sin fragmentos / version máxima default / ?version=N
# ---------------------------------------------------------------------------

def test_get_identity_empty_returns_version_0(client, super_jwt, test_agent_id):
    """Agent existe pero sin fragmentos → version=0, fragments=[]."""
    r = client.get(_path(), headers=_h(super_jwt))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_identifier"] == TEST_AGENT_IDENTIFIER
    assert data["agent_id"] == test_agent_id
    assert data["version"] == 0
    assert data["fragments"] == []


def test_post_creates_version_1_then_get_returns_it(client, super_jwt, test_agent_id):
    """POST crea version 1, GET devuelve fragments en orden por fragment_idx."""
    body = {"fragments": ["soy test", "vivo en pytest", "trabajo con coverage"]}
    r = client.post(_path(), headers=_h(super_jwt), json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["version"] == 1
    assert data["fragments_count"] == 3

    r = client.get(_path(), headers=_h(super_jwt))
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert len(data["fragments"]) == 3
    # ORDER BY fragment_idx ASC enforced.
    assert [f["fragment_idx"] for f in data["fragments"]] == [0, 1, 2]
    assert data["fragments"][0]["content"] == "soy test"
    assert data["fragments"][1]["content"] == "vivo en pytest"
    assert data["fragments"][2]["content"] == "trabajo con coverage"


def test_post_again_increments_version(client, super_jwt):
    """Segundo POST → version 2 (auto-increment)."""
    body = {"fragments": ["soy test v2", "actualizado"]}
    r = client.post(_path(), headers=_h(super_jwt), json=body)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2

    r = client.get(_path(), headers=_h(super_jwt))
    assert r.status_code == 200
    assert r.json()["version"] == 2


def test_get_with_version_param_returns_historic(client, super_jwt):
    """?version=1 devuelve la versión histórica concreta, no la máxima."""
    r = client.get(_path() + "?version=1", headers=_h(super_jwt))
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert len(data["fragments"]) == 3  # los 3 originales del test_post_creates_version_1


def test_get_inexistent_version_returns_404(client, super_jwt):
    """?version=999 → 404."""
    r = client.get(_path() + "?version=999", headers=_h(super_jwt))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Permisos — super, propio, anti-discovery
# ---------------------------------------------------------------------------

def test_get_inexistent_agent_returns_404(client, super_jwt):
    r = client.get("/agents/NoExisteEsteAgente/identity", headers=_h(super_jwt))
    assert r.status_code == 404


def test_owner_can_get_own_agent(client, owner_setup):
    """Fix BC2 (adv-code REQUIRED): user no-super dueño del agent → 200 via branch propio."""
    r = client.get(
        f"/agents/{owner_setup['identifier']}/identity",
        headers=_h(owner_setup["token"]),
    )
    assert r.status_code == 200


def test_owner_can_post_own_agent(client, owner_setup):
    """Fix BC2: user no-super dueño puede POST → 201 via branch propio."""
    r = client.post(
        f"/agents/{owner_setup['identifier']}/identity",
        headers=_h(owner_setup["token"]),
        json={"fragments": ["soy owner test"]},
    )
    assert r.status_code == 201


def test_owner_cannot_see_other_agent(client, owner_setup, test_agent_id):
    """Owner cannot see another user's agent (anti-discovery → 404)."""
    r = client.get(_path(), headers=_h(owner_setup["token"]))
    assert r.status_code == 404


def test_other_user_gets_404_anti_discovery(client, other_user_jwt, test_agent_id):
    """User que NO es dueño del agent test (ni super) → 404 anti-discovery, no 403."""
    r = client.get(_path(), headers=_h(other_user_jwt))
    assert r.status_code == 404


def test_other_user_post_returns_404(client, other_user_jwt, test_agent_id):
    """User que NO es dueño NO puede POST → 404 anti-discovery."""
    r = client.post(
        _path(),
        headers=_h(other_user_jwt),
        json={"fragments": ["intento robar"]},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Validaciones — size, null bytes, extra fields, empty
# ---------------------------------------------------------------------------

def test_post_fragment_too_large_422(client, super_jwt, test_agent_id):
    """Fragmento > MAX_FRAGMENT_SIZE → 422."""
    huge = "x" * 33_000  # > 32KB
    r = client.post(
        _path(),
        headers=_h(super_jwt),
        json={"fragments": ["ok", huge]},
    )
    assert r.status_code == 422
    assert "exceeds" in r.text.lower()


def test_post_null_bytes_rejected_422(client, super_jwt, test_agent_id):
    """Null bytes en content → 422."""
    r = client.post(
        _path(),
        headers=_h(super_jwt),
        json={"fragments": ["normal", "con\x00null"]},
    )
    assert r.status_code == 422
    assert "null" in r.text.lower()


def test_post_empty_list_422(client, super_jwt, test_agent_id):
    """Lista vacía → 422 (Pydantic min_length=1)."""
    r = client.post(_path(), headers=_h(super_jwt), json={"fragments": []})
    assert r.status_code == 422


def test_post_extra_field_422(client, super_jwt, test_agent_id):
    """ConfigDict(extra='forbid') rechaza campos desconocidos."""
    r = client.post(
        _path(),
        headers=_h(super_jwt),
        json={"fragments": ["ok"], "unknown_field": "test"},
    )
    assert r.status_code == 422


def test_post_too_many_fragments_422(client, super_jwt, test_agent_id):
    """Más de MAX_FRAGMENTS_PER_VERSION → 422 (Pydantic max_length=100)."""
    r = client.post(
        _path(),
        headers=_h(super_jwt),
        json={"fragments": ["x"] * 101},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Auth — sin token
# ---------------------------------------------------------------------------

def test_get_without_auth_401(client):
    r = client.get(_path())
    assert r.status_code == 401


def test_post_without_auth_401(client):
    r = client.post(_path(), json={"fragments": ["test"]})
    assert r.status_code == 401

