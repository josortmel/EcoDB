"""#337 — AGE is the canonical projection of SQL triples. Integration against a real postgres+AGE.

Run ONLY against a throwaway DB: TEST_DB_PORT=5436 (never the live family DB on 5435).
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

from conftest import TEST_DB_URL

sys.path.insert(0, str(Path(__file__).parent.parent))

import graph  # noqa: E402

TAG = f"pytest-age-{uuid.uuid4().hex[:6]}"


async def _age_edges(conn, *sids):
    rows = await conn.fetch("""
        SELECT * FROM cypher('ecodb_graph', $$
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.sql_id, r.predicate, b.sql_id
        $$) AS (s agtype, p agtype, o agtype)""")
    out = [(int(str(r["s"])), json.loads(str(r["p"])), int(str(r["o"]))) for r in rows]
    return sorted(e for e in out if e[0] in sids or e[2] in sids)


async def _vertices(conn, sid):
    return await conn.fetchval(
        "SELECT count(*) FROM cypher('ecodb_graph', $$ MATCH (n:Entity {sql_id: $sid}) RETURN id(n) $$, $1::agtype) AS (v agtype)",
        json.dumps({"sid": sid}))


async def _scenario():
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                a = await graph._ensure_node(conn, f"{TAG}-A")
                b = await graph._ensure_node(conn, f"{TAG}-B")
                c = await graph._ensure_node(conn, f"{TAG}-C")
                for s, o in ((b, c), (a, b)):
                    await conn.execute(
                        "INSERT INTO triples (subject_id, predicate, object_id, author) VALUES ($1,'rel',$2,$3)",
                        s, o, TAG)
                    await graph._create_age_edge(conn, s, "rel", o)
            res = {"initial": await _age_edges(conn, a, b, c)}

        # merge B into A: B's edge to C must be projected onto A; A-B becomes a self-loop (dropped)
        await graph.merge_entities(b, a, 1, TAG, pool)
        async with pool.acquire() as conn:
            res["after_merge"] = await _age_edges(conn, a, b, c)
            res["b_vertices_after_merge"] = await _vertices(conn, b)
            # a name that was merged away resolves to the canonical, and does not resurrect B's vertex
            async with conn.transaction():
                res["ensure_merged_name"] = await graph._ensure_node(conn, f"{TAG}-B")
            res["b_vertices_after_ensure"] = await _vertices(conn, b)
            async with conn.transaction():
                res["drift_after_merge"] = (await graph.age_drift(conn))["age_drift"]

        # undo: B gets its own edges back, A loses the projected copy
        await graph.undo_merge(b, pool)
        async with pool.acquire() as conn:
            res["after_undo"] = await _age_edges(conn, a, b, c)

            # fail loud: an edge to a vertex that doesn't exist raises and rolls back
            ghost = await conn.fetchval(
                "INSERT INTO nodes (name, status) VALUES ($1, 'active') RETURNING id", f"{TAG}-ghost")
            await conn.execute(
                "SELECT * FROM cypher('ecodb_graph', $$ MATCH (n:Entity {sql_id: $sid}) DETACH DELETE n $$, $1::agtype) AS (d agtype)",
                json.dumps({"sid": ghost}))
            try:
                async with conn.transaction():
                    await graph._create_age_edge(conn, a, "rel", ghost)
                res["fail_loud"] = "no-raise"
            except graph.GraphSyncError:
                res["fail_loud"] = "raised"

            # reconcile repairs the missing vertex and a manually deleted edge
            await conn.execute("""SELECT * FROM cypher('ecodb_graph', $$
                MATCH (x:Entity {sql_id: $s})-[r:RELATES_TO]->(y:Entity {sql_id: $o}) DELETE r $$, $1::agtype) AS (d agtype)""",
                json.dumps({"s": b, "o": c}))
            async with conn.transaction():
                res["dry"] = await graph.reconcile_age(conn, {a, b, c, ghost}, dry_run=True)
                res["fix"] = await graph.reconcile_age(conn, {a, b, c, ghost})
            res["after_reconcile"] = await _age_edges(conn, a, b, c)
            res["ghost_vertices"] = await _vertices(conn, ghost)
            res["ids"] = (a, b, c)

            # cleanup
            ids = [a, b, c, ghost]
            await conn.execute("DELETE FROM entity_merge_log WHERE reason = $1", TAG)
            await conn.execute("DELETE FROM triples WHERE author = $1", TAG)
            for sid in ids:
                await conn.execute("SELECT * FROM cypher('ecodb_graph', $$ MATCH (n:Entity {sql_id: $sid}) DETACH DELETE n $$, $1::agtype) AS (d agtype)",
                                   json.dumps({"sid": sid}))
            await conn.execute("DELETE FROM nodes WHERE id = ANY($1::int[])", ids)
        return res
    finally:
        await pool.close()


@pytest.fixture(scope="module")
def res():
    if os.environ.get("TEST_DB_PORT", "5435") == "5435":
        pytest.skip("integration test: run with TEST_DB_PORT pointing at a throwaway DB, never the live one")
    return asyncio.run(_scenario())


def test_initial_edges_projected(res):
    a, b, c = res["ids"]
    assert res["initial"] == sorted([(a, "rel", b), (b, "rel", c)])


def test_merge_projects_source_edges_onto_canonical(res):
    a, b, c = res["ids"]
    assert res["after_merge"] == [(a, "rel", c)]  # B->C moved to A->C; A->B is a self-loop now
    assert res["b_vertices_after_merge"] == 0


def test_merged_name_resolves_to_canonical_without_resurrecting_vertex(res):
    a, b, c = res["ids"]
    assert res["ensure_merged_name"] == a
    assert res["b_vertices_after_ensure"] == 0


def test_undo_merge_restores_source_edges(res):
    a, b, c = res["ids"]
    assert res["after_undo"] == sorted([(a, "rel", b), (b, "rel", c)])


def test_create_age_edge_fails_loud(res):
    assert res["fail_loud"] == "raised"


def test_reconcile_repairs(res):
    a, b, c = res["ids"]
    assert res["dry"]["missing_edges_created"] == 1 and res["dry"]["missing_vertices_created"] == 1
    assert res["after_reconcile"] == sorted([(a, "rel", b), (b, "rel", c)])
    assert res["ghost_vertices"] == 1
