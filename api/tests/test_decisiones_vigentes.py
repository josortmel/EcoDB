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
    assert del_worker["errores"] == [{"sustituta_no_legible": True, "de": publica}]

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


# ---- #919, Prima 10-nov: el id de la sustituta solo sale si quien llama puede leerla, en las cuatro salidas ----

def _par_publica_privada(client, entorno, agente):
    publica = _guardar(client, entorno["super"], agente)
    privada = _guardar(client, entorno["super"], agente, visibility="private", supersedes=[publica])
    return publica, privada


def test_endpoint_no_dice_el_id_de_la_privada_ni_con_superadas(client, entorno, agente):
    publica, privada = _par_publica_privada(client, entorno, agente)
    r = client.get(URL, headers={"Authorization": f"Bearer {entorno['worker']}"},
                   params={"tema": "decisión de prueba", "agente": agente, "incluir_superadas": "true"})
    assert r.status_code == 200 and privada not in r.text
    assert r.json()["superadas"] == []


def test_get_memories_tapa_la_sustituta_que_no_se_puede_leer(client, entorno, agente):
    publica, privada = _par_publica_privada(client, entorno, agente)
    h_w = {"Authorization": f"Bearer {entorno['worker']}"}
    r = client.get(f"/memories/{publica}", headers=h_w)
    assert r.status_code == 200 and privada not in r.text
    assert r.json()["metadata"]["superseded_by"] is None and r.json()["metadata"]["sustituta_no_legible"] is True
    lista = client.get("/memories/recent", headers=h_w, params={"agent_identifier": agente})
    assert lista.status_code == 200 and privada not in lista.text
    en_lista = {m["id"]: m for m in lista.json()["items"]}
    assert en_lista[publica]["metadata"]["sustituta_no_legible"] is True
    # Quien sí la puede leer ve el id.
    r_s = client.get(f"/memories/{publica}", headers={"Authorization": f"Bearer {entorno['super']}"})
    assert r_s.json()["metadata"]["superseded_by"] == privada and "sustituta_no_legible" not in r_s.json()["metadata"]


def test_search_avisa_sin_el_id(client, entorno, agente):
    publica, privada = _par_publica_privada(client, entorno, agente)
    body = {"query_text": "decisión de prueba", "agent_identifier": agente, "limit": 10,
            "rerank_mode": "off", "include_documents": False}
    r = client.post("/search", headers={"Authorization": f"Bearer {entorno['worker']}"}, json=body)
    assert r.status_code == 200 and privada not in r.text
    fila = {x["id"]: x for x in r.json()["results"]}[publica]
    assert "superada por una memoria que no puedes leer" in fila["trust_warnings"]
    r_s = client.post("/search", headers={"Authorization": f"Bearer {entorno['super']}"}, json=body)
    assert f"superada por {privada}" in {x["id"]: x for x in r_s.json()["results"]}[publica]["trust_warnings"]


def test_un_put_de_metadata_no_pone_ni_quita_la_marca(client, entorno, agente):
    publica, privada = _par_publica_privada(client, entorno, agente)
    r = client.put(f"/memories/{publica}", headers={"Authorization": f"Bearer {entorno['super']}"},
                   json={"metadata": {"nota": "x", "superseded_by": None, "sustituta_no_legible": True}})
    assert r.status_code == 200, r.text
    guardada = _sql("SELECT metadata FROM memories WHERE id = $1", uuid.UUID(publica))[0]["metadata"]
    import json as _json
    guardada = _json.loads(guardada) if isinstance(guardada, str) else guardada
    assert guardada["superseded_by"] == privada and guardada["nota"] == "x"
    assert "sustituta_no_legible" not in guardada


# #1118 (caso de Eco, c8269119 → 9fb038e2): una observación superada por una decisión.

def test_1118_observacion_superada_por_decision_sale_en_sustituye_a_y_en_superadas(client, entorno, agente):
    obs = _guardar(client, entorno["super"], agente, tipo="observacion")
    dec = _guardar(client, entorno["super"], agente, supersedes=[obs], supersede_reason="se decidió")
    sin = _vigentes(client, entorno["super"], agente)
    assert [f["id"] for f in sin["vigentes"]] == [dec] and sin["vigentes"][0]["sustituye_a"] == [obs]
    con = _vigentes(client, entorno["super"], agente, incluir_superadas="true")
    assert [(s["id"], s["superada_por"], s["tipo"]) for s in con["superadas"]] == [(obs, dec, "observacion")]


def test_1118_la_cadena_hacia_atras_pasa_por_una_decision_ya_vista(client, entorno, agente):
    obs = _guardar(client, entorno["super"], agente, tipo="observacion")
    d1 = _guardar(client, entorno["super"], agente, supersedes=[obs])
    d2 = _guardar(client, entorno["super"], agente, supersedes=[d1])
    r = _vigentes(client, entorno["super"], agente)
    assert [f["id"] for f in r["vigentes"]] == [d2] and set(r["vigentes"][0]["sustituye_a"]) == {d1, obs}


def test_1118_el_trabajador_no_ve_el_id_de_la_observacion_privada(client, entorno, agente):
    obs = _guardar(client, entorno["super"], agente, tipo="observacion", visibility="private")
    dec = _guardar(client, entorno["super"], agente, supersedes=[obs])
    r = client.get(URL, headers={"Authorization": f"Bearer {entorno['worker']}"},
                   params={"tema": "decisión de prueba", "agente": agente, "incluir_superadas": "true"})
    assert r.status_code == 200 and obs not in r.text
    assert [f["id"] for f in r.json()["vigentes"]] == [dec] and "sustituye_a" not in r.json()["vigentes"][0]
    assert r.json()["superadas"] == []
