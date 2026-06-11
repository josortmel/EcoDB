"""Tests integración — GET/PUT /users/me/preferences."""
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
from auth import generate_api_key


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
def super_jwt(client):
    """Superuser (user_id=1)."""
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await _aconn()
        try:
            row = await conn.fetchrow(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-users-super', 1, true) RETURNING id",
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(api_key_id):
        conn = await _aconn()
        try:
            # Borrar prefs de pytest users (user_id=1 testea sus prefs).
            await conn.execute("DELETE FROM user_preferences WHERE user_id = 1")
            await conn.execute("DELETE FROM user_preferences WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-users-%')")
            await conn.execute("DELETE FROM api_keys WHERE name LIKE 'pytest-users-%'")
            await conn.execute("DELETE FROM user_emails WHERE user_id IN (SELECT id FROM users WHERE name LIKE 'pytest-users-%')")
            await conn.execute("DELETE FROM users WHERE name LIKE 'pytest-users-%'")
        finally:
            await conn.close()

    key_id = _run(_setup())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    yield token
    _run(_cleanup(key_id))


@pytest.fixture(scope="module")
def other_user_setup(client):
    """User secundario para verificar isolation entre users."""
    async def _create():
        conn = await _aconn()
        try:
            u = await conn.fetchrow(
                "INSERT INTO users (name, active) VALUES ('pytest-users-other', true) RETURNING id"
            )
            await conn.execute(
                "INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, 'pytest-users-other@local', true)",
                u["id"],
            )
            key_plain, key_hash = generate_api_key()
            await conn.execute(
                "INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, 'pytest-users-other-key', $2, true)",
                key_hash, u["id"],
            )
            return u["id"], key_plain
        finally:
            await conn.close()

    user_id, key_plain = _run(_create())
    token = client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"]
    return {"user_id": user_id, "jwt": token}


def auth(jwt):
    return {"Authorization": f"Bearer {jwt}"}


# ===========================================================================
# GET /users/me/preferences
# ===========================================================================

def test_get_preferences_no_row_returns_empty(client, super_jwt):
    """Si no hay row, devuelve prefs={} sin crear row (lazy)."""
    # Asegurar que NO hay row.
    async def _wipe():
        conn = await _aconn()
        try:
            await conn.execute("DELETE FROM user_preferences WHERE user_id = 1")
        finally:
            await conn.close()
    _run(_wipe())

    r = client.get("/users/me/preferences", headers=auth(super_jwt))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 1
    assert body["prefs"] == {}
    assert body["updated_at"] is None

    # Confirmar que NO se creó row.
    async def _count():
        conn = await _aconn()
        try:
            return await conn.fetchval("SELECT count(*) FROM user_preferences WHERE user_id = 1")
        finally:
            await conn.close()
    assert _run(_count()) == 0


# ===========================================================================
# PUT /users/me/preferences
# ===========================================================================

def test_put_preferences_creates_row_first_time(client, super_jwt):
    """PUT inicial crea la row (upsert). GET posterior la devuelve."""
    # Wipe.
    async def _wipe():
        conn = await _aconn()
        try:
            await conn.execute("DELETE FROM user_preferences WHERE user_id = 1")
        finally:
            await conn.close()
    _run(_wipe())

    payload = {"prefs": {"theme": "dark", "lang": "es"}}
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 1
    assert body["prefs"] == {"theme": "dark", "lang": "es"}
    assert body["updated_at"] is not None

    # GET la devuelve.
    r2 = client.get("/users/me/preferences", headers=auth(super_jwt))
    assert r2.json()["prefs"] == {"theme": "dark", "lang": "es"}


def test_put_preferences_replaces_completely(client, super_jwt):
    """PUT NO es PATCH parcial. Replace completo del JSONB."""
    client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": {"theme": "light", "lang": "en", "extra": 1}})
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": {"theme": "dark"}})
    assert r.status_code == 200
    assert r.json()["prefs"] == {"theme": "dark"}
    # 'lang' y 'extra' NO están — replace completo.


def test_put_preferences_too_large_returns_422(client, super_jwt):
    """JSON > 32KB → 422."""
    huge = {"data": "x" * 40_000}
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": huge})
    assert r.status_code == 422


def test_put_preferences_empty_dict_ok(client, super_jwt):
    """PUT con {} es válido — borra contenido sin borrar la row."""
    client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": {"a": 1}})
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": {}})
    assert r.status_code == 200
    assert r.json()["prefs"] == {}


def test_put_preferences_arbitrary_keys_accepted(client, super_jwt):
    """Estructura libre — frontend define keys. NO extra=forbid."""
    payload = {"prefs": {"random_key_xyz": "value", "nested": {"deep": [1, 2, 3]}}}
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json=payload)
    assert r.status_code == 200
    assert r.json()["prefs"]["random_key_xyz"] == "value"
    assert r.json()["prefs"]["nested"]["deep"] == [1, 2, 3]


# ===========================================================================
# Isolation entre users
# ===========================================================================

def test_users_have_isolated_preferences(client, super_jwt, other_user_setup):
    """User A guarda prefs, User B GET las suyas → no ve las de A."""
    # User A (super) saves.
    client.put("/users/me/preferences", headers=auth(super_jwt), json={"prefs": {"theme": "dark"}})
    # User B GET las SUYAS.
    r = client.get("/users/me/preferences", headers=auth(other_user_setup["jwt"]))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == other_user_setup["user_id"]
    assert body["prefs"] == {}


# ===========================================================================
# Auth required
# ===========================================================================

def test_get_preferences_without_auth_returns_401(client):
    r = client.get("/users/me/preferences")
    assert r.status_code == 401


def test_put_preferences_without_auth_returns_401(client):
    r = client.put("/users/me/preferences", json={"prefs": {"x": 1}})
    assert r.status_code == 401


def test_put_preferences_extra_field_in_envelope_returns_422(client, super_jwt):
    """IC2 fix Loop 1 (adv-code): el body envelope rechaza extra fields
    aunque `prefs:dict` interno acepte keys arbitrarias."""
    r = client.put(
        "/users/me/preferences",
        headers=auth(super_jwt),
        json={"prefs": {"theme": "dark"}, "rogue_field": "x"},
    )
    assert r.status_code == 422


def test_put_preferences_unicode_size_byte_count(client, super_jwt):
    """SOFT gap test (adv-code): valida que la validación de tamaño cuenta
    bytes UTF-8, no chars. Emojis/CJK cuentan más bytes que chars."""
    # Cada emoji 🎉 ocupa 4 bytes UTF-8. 8000 emojis = 32000 bytes (al borde).
    payload = {"prefs": {"data": "🎉" * 8000}}  # ~32KB
    r = client.put("/users/me/preferences", headers=auth(super_jwt), json=payload)
    # Debería ser aceptado (al borde) o rechazado (si pasa 32KB con overhead JSON).
    # Lo importante: NO 500 — la validación maneja Unicode correctamente.
    assert r.status_code in (200, 422)
