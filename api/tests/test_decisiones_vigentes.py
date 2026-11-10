"""#919: GET /api/v1/decisiones/vigentes contra la Postgres de pruebas (5436).

Embeddings sustituidos (todas las memorias con el mismo vector) y un agente propio del módulo, para
que las candidatas sean solo las de cada test. Comprueba la cadena, las caducadas, las superadas, que
una clave sin rol elevado solo ve lo que ya veía (y no escribe nada), y que los topes avisan sin 500.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DB_URL
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("ENVIRONMENT", "development")

sys.path.insert(0, str(Path(__file__).parent.parent))

import decisiones  # noqa: E402
import memories  # noqa: E402
import search  # noqa: E402
import vigentes  # noqa: E402
from auth import generate_api_key  # noqa: E402
from main import create_app  # noqa: E402

FAKE_VEC = "[" + ",".join(["0.01"] * 512) + "]"
PREFIX = "pytest-decvig-"
URL = "/api/v1/decisiones/vigentes"


async def _fake_embed(*_a, **_k):
    return FAKE_VEC


def _sql(q, *args):
    async def run():
        conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        try:
            return await conn.fetch(q, *args)
        finally:
            await conn.close()
    return asyncio.run(run())


def _token(client, user_id, nombre):
    key_plain, key_hash = generate_api_key()
    key_id = _sql("INSERT INTO api_keys (key_hash, name, user_id, active) VALUES ($1, $2, $3, true) RETURNING id",
                  key_hash, nombre, user_id)[0]["id"]
    return client.post("/auth/token", json={"api_key": key_plain}).json()["access_token"], key_id


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app("development")) as c:
        yield c


@pytest.fixture(scope="module")
def entorno(client):
    """Super (user 1) y un trabajador sin rol elevado, miembro del proyecto 1."""
    sufijo = uuid.uuid4().hex[:8]
    worker = _sql("INSERT INTO users (name, is_super, is_ceo, active) VALUES ($1, false, false, true) RETURNING id",
                  PREFIX + sufijo)[0]["id"]
    _sql("INSERT INTO user_emails (user_id, email, is_primary) VALUES ($1, $2, true)", worker, f"{PREFIX}{sufijo}@test")
    _sql("INSERT INTO project_members (project_id, user_id) VALUES (1, $1)", worker)
    jwt_super, k1 = _token(client, 1, "pytest-decvig-super")
    jwt_worker, k2 = _token(client, worker, "pytest-decvig-worker")
    yield {"super": jwt_super, "worker": jwt_worker}
    _sql("DELETE FROM api_keys WHERE id = ANY($1::int[])", [k1, k2])
    _sql("DELETE FROM memories WHERE content LIKE $1", PREFIX + "%")
    _sql("DELETE FROM agents WHERE identifier LIKE $1", PREFIX + "%")
    _sql("DELETE FROM project_members WHERE user_id = $1", worker)
    _sql("DELETE FROM user_emails WHERE user_id = $1", worker)
    _sql("DELETE FROM users WHERE id = $1", worker)


@pytest.fixture(autouse=True)
def _embed(monkeypatch):
    monkeypatch.setattr(memories, "embed_text", _fake_embed)
    monkeypatch.setattr(search, "embed_text", _fake_embed)


@pytest.fixture
def agente():
    nombre = PREFIX + uuid.uuid4().hex[:8]
    _sql("INSERT INTO agents (identifier, user_id, active) VALUES ($1, 1, true)", nombre)
    return nombre


def _guardar(client, jwt, agente, tipo="decision", **extra):
    body = {"type": tipo, "content": PREFIX + uuid.uuid4().hex, "workspace_id": 1, "project_id": 1,
            "agent_identifier": agente, "visibility": "public", **extra}
    r = client.post("/memories", headers={"Authorization": f"Bearer {jwt}"}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _vigentes(client, jwt, agente, **params):
    r = client.get(URL, headers={"Authorization": f"Bearer {jwt}"},
                   params={"tema": "decisión de prueba", "agente": agente, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_cadena_a_b_c_devuelve_c(client, entorno, agente):
    a = _guardar(client, entorno["super"], agente)
    b = _guardar(client, entorno["super"], agente, supersedes=[a])
    c = _guardar(client, entorno["super"], agente, tipo="acuerdo", supersedes=[b])
    r = _vigentes(client, entorno["super"], agente)
    assert [f["id"] for f in r["vigentes"]] == [c]
    assert r["vigentes"][0]["sustituye_a"][-1] == b and r["errores"] == [] and r["avisos"] == []


def test_caducada_fuera_y_superada_solo_con_incluir_superadas(client, entorno, agente):
    vieja = _guardar(client, entorno["super"], agente)
    nueva = _guardar(client, entorno["super"], agente, supersedes=[vieja], supersede_reason="cambió")
    _guardar(client, entorno["super"], agente, valid_until="2026-01-01")
    sin = _vigentes(client, entorno["super"], agente)
    assert [f["id"] for f in sin["vigentes"]] == [nueva] and "superadas" not in sin
    con = _vigentes(client, entorno["super"], agente, incluir_superadas="true")
    assert [s["id"] for s in con["superadas"]] == [vieja] and con["superadas"][0]["motivo"] == "cambió"


def test_clave_sin_rol_elevado_ve_lo_que_ya_veia_y_no_escribe(client, entorno, agente):
    publica = _guardar(client, entorno["super"], agente)
    privada = _guardar(client, entorno["super"], agente, visibility="private", supersedes=[publica])
    antes = _sql("SELECT id, metadata, content FROM memories WHERE content LIKE $1 ORDER BY id", PREFIX + "%")
    auditoria = _sql("SELECT count(*) AS n FROM audit_log")[0]["n"]

    del_super = _vigentes(client, entorno["super"], agente)
    assert [f["id"] for f in del_super["vigentes"]] == [privada]

    del_worker = _vigentes(client, entorno["worker"], agente)
    # La sustituta es privada de otro: el trabajador no la lee, se le avisa y se queda con la que ve.
    assert [f["id"] for f in del_worker["vigentes"]] == [publica]
    assert del_worker["errores"] == [{"sustituta_no_legible": privada, "de": publica}]

    despues = _sql("SELECT id, metadata, content FROM memories WHERE content LIKE $1 ORDER BY id", PREFIX + "%")
    assert [dict(r) for r in antes] == [dict(r) for r in despues]
    assert _sql("SELECT count(*) AS n FROM audit_log")[0]["n"] == auditoria


def test_sin_credencial_401(client):
    assert client.get(URL, params={"tema": "decisión de prueba"}).status_code == 401


def test_limit_fuera_de_rango_avisa_y_no_falla(client, entorno, agente):
    _guardar(client, entorno["super"], agente)
    r = _vigentes(client, entorno["super"], agente, limit=500)
    assert r["avisos"] == ["limit 500 fuera de 1-50: se usa 50"] and len(r["vigentes"]) == 1


def test_tope_de_memorias_leidas_avisa(client, entorno, agente, monkeypatch):
    a = _guardar(client, entorno["super"], agente)
    b = _guardar(client, entorno["super"], agente, supersedes=[a])
    c = _guardar(client, entorno["super"], agente, supersedes=[b])
    _guardar(client, entorno["super"], agente, supersedes=[c])
    monkeypatch.setattr(decisiones, "MAX_LEIDAS", 2)
    r = _vigentes(client, entorno["super"], agente)
    assert any(a.startswith("más de 2 memorias") for a in r["avisos"])


def test_cadena_mas_larga_que_el_tope_de_saltos_avisa(client, entorno, agente, monkeypatch):
    ids = [_guardar(client, entorno["super"], agente)]
    for _ in range(4):
        ids.append(_guardar(client, entorno["super"], agente, supersedes=[ids[-1]]))
    monkeypatch.setattr(vigentes, "MAX_SALTOS", 2)
    r = _vigentes(client, entorno["super"], agente)
    assert any("pasa de 2 saltos" in a for a in r["avisos"])
    assert r["errores"], "la cadena cortada no se esconde"
