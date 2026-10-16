"""#447 (decisión #42 de Pepe, 15-oct: «Arreglar el trigger»): los triggers que sincronizan `nodes` con AGE
metían el nombre con format(%L), que es el escapado de SQL, dentro de un texto cypher. Cypher no entiende ''
como comilla escapada: un nodo «O'Brien» se creaba en SQL y se quedaba SIN vértice (solo un WARNING), hasta
el siguiente reconcile. Igual al renombrar y al reactivar. Ahora el valor viaja como parámetro agtype
(EXECUTE … USING), la forma de «Prepared Statements» del manual de AGE.

El test aplica sql/trigger_age_sync.sql a la base de PRUEBAS (como hace migrations.py al arrancar) y comprueba
los vértices. Solo contra ecodb-test-pg (5436).
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

import asyncpg

from conftest import TEST_DB_URL

SQL = Path(__file__).resolve().parents[2] / "sql" / "trigger_age_sync.sql"


async def _vertice(conn, sid):
    rows = await conn.fetch(
        "SELECT * FROM cypher('ecodb_graph', $$ MATCH (n:Entity {sql_id: $sid}) RETURN n.name $$, $1::agtype)"
        " AS (name agtype)", json.dumps({"sid": sid}))
    return [json.loads(str(r["name"])) for r in rows]


async def _escenario():
    tag = f"t447-{uuid.uuid4().hex[:6]}"
    nombres = {"apostrofo": f"O'Brien {tag}", "barra": f"C:\\ruta\\{tag}", "comillas": f'dijo "hola" {tag}',
               "inyeccion": f"x'}}) DETACH DELETE n //{tag}"}
    conn = await asyncpg.connect(TEST_DB_URL)
    res, ids = {}, []
    try:
        await conn.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")
        await conn.execute(SQL.read_text(encoding="utf-8"))
        avisos = []
        conn.add_log_listener(lambda c, m: avisos.append(m.message))
        for clave, nombre in nombres.items():
            sid = await conn.fetchval("INSERT INTO nodes (name, type) VALUES ($1, 'concepto') RETURNING id", nombre)
            ids.append(sid)
            res[clave] = await _vertice(conn, sid)
        sid = ids[0]
        await conn.execute("UPDATE nodes SET name = $1 WHERE id = $2", f"Ts'ui Pen {tag}", sid)
        res["rename"] = await _vertice(conn, sid)
        await conn.execute("UPDATE nodes SET status = 'merged' WHERE id = $1", sid)
        res["tras_desactivar"] = await _vertice(conn, sid)
        await conn.execute("UPDATE nodes SET status = 'active' WHERE id = $1", sid)
        res["reactivado"] = await _vertice(conn, sid)
        await asyncio.sleep(0.1)
        res["avisos"] = [a for a in avisos if "AGE sync" in a]
        res["nombres"], res["tag"] = nombres, tag
        return res
    finally:
        for sid in ids:
            await conn.execute("DELETE FROM nodes WHERE id = $1", sid)
        await conn.close()


def test_nombres_con_comillas_y_barras_tienen_su_vertice_con_el_nombre_exacto():
    r = asyncio.run(_escenario())
    for clave in ("apostrofo", "barra", "comillas", "inyeccion"):
        assert r[clave] == [r["nombres"][clave]], (clave, r[clave])
    assert r["rename"] == [f"Ts'ui Pen {r['tag']}"]
    assert r["tras_desactivar"] == []
    assert r["reactivado"] == [f"Ts'ui Pen {r['tag']}"]
    assert r["avisos"] == []
