"""Tests de integracion — auth endpoints contra postgres real.

Pre-requisitos:
- Container `ecodb-postgres` corriendo en localhost:5435 con init.sql aplicado.
- Variables de entorno DATABASE_URL apuntando ahi.

Los tests crean su propio user de prueba (ademas del seed inicial) con sus propias
api_keys, asi no contaminan el seed. Cleanup en teardown.

Si el postgres no esta accesible, los tests fallan con error claro (no skip
silencioso — porque la auth de verdad necesita DB).
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import create_app  # noqa: E402
from auth import generate_api_key, hash_api_key  # noqa: E402
import asyncpg  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def super_api_key():
    """Creates an API key for the superuser (user_id=1) and returns the plain key.
    Cleanup tras los tests."""
    import asyncio
    key_plain, key_hash = generate_api_key()

    async def _setup():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO api_keys (key_hash, name, user_id, active)
                VALUES ($1, 'pytest-super-key', 1, true)
                RETURNING id
                """,
                key_hash,
            )
            return row["id"]
        finally:
            await conn.close()

    async def _cleanup(key_id):
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)
        finally:
            await conn.close()

    key_id = asyncio.run(_setup())
    yield key_plain
    asyncio.run(_cleanup(key_id))


# ---------------------------------------------------------------------------
# POST /auth/token
# ---------------------------------------------------------------------------

def test_token_with_valid_api_key_returns_jwt(client, super_api_key):
    response = client.post("/auth/token", json={"api_key": super_api_key})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_token_with_invalid_api_key_returns_401(client):
    response = client.post("/auth/token", json={"api_key": "ecodb_invalid_key_42"})
    assert response.status_code == 401


def test_token_with_missing_api_key_returns_422(client):
    response = client.post("/auth/token", json={})
    # 422 — Pydantic validation error (api_key requerido)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

def test_me_without_auth_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_valid_jwt_returns_user(client, super_api_key):
    token_resp = client.post("/auth/token", json={"api_key": super_api_key})
    jwt_token = token_resp.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert response.status_code == 200
    me = response.json()
    assert me["user_id"] == 1
    assert me["name"] == "admin"
    assert me["is_super"] is True
    assert me["is_ceo"] is False
    assert me["organization_id"] is None
    assert me["email"] == "admin@example.com"


def test_me_with_api_key_as_bearer_returns_user(client, super_api_key):
    """Compat: clientes MCP que solo soportan Bearer pueden mandar la API key
    directamente con scheme Bearer (no necesariamente JWT)."""
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {super_api_key}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == 1


def test_me_with_api_key_as_apikey_scheme_returns_user(client, super_api_key):
    response = client.get("/auth/me", headers={"Authorization": f"ApiKey {super_api_key}"})
    assert response.status_code == 200


def test_me_with_invalid_jwt_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer eyJhbGc.invalid.signature"})
    assert response.status_code == 401


def test_me_with_malformed_authorization_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "NoSchemeOnlyToken"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/api-keys (super-only)
# ---------------------------------------------------------------------------

def test_create_api_key_as_super_returns_new_key(client, super_api_key):
    token = client.post("/auth/token", json={"api_key": super_api_key}).json()["access_token"]
    response = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": 1, "name": "pytest-created-key"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["api_key"].startswith("ecodb_")
    assert body["user_id"] == 1
    assert body["name"] == "pytest-created-key"
    # Cleanup la key recien creada
    import asyncio
    async def _cleanup():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            await conn.execute("DELETE FROM api_keys WHERE id = $1", body["id"])
        finally:
            await conn.close()
    asyncio.run(_cleanup())


def test_create_api_key_without_auth_returns_401(client):
    response = client.post(
        "/auth/api-keys",
        json={"user_id": 1, "name": "no-auth"},
    )
    assert response.status_code == 401


def test_create_api_key_for_inexistent_user_returns_404(client, super_api_key):
    token = client.post("/auth/token", json={"api_key": super_api_key}).json()["access_token"]
    response = client.post(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": 99999, "name": "ghost"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Security headers present on auth endpoints (VS5 + NV1 ASGI)
# ---------------------------------------------------------------------------

def test_security_headers_on_auth_endpoint(client, super_api_key):
    token = client.post("/auth/token", json={"api_key": super_api_key}).json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"


def test_security_headers_on_error_response(client):
    """Confirma que los headers se aplican en respuestas 401 (la migración a
    ASGI puro de NV1 garantiza esto)."""
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"
