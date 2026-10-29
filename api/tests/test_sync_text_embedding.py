"""#816: search reads memory_embeddings. Whatever gives a memory its embedding — the cell (raw SQL
under the ecodb_cell role, which has no grant on memory_embeddings), the backfill (UPDATE) or a PUT
that re-embeds — must leave the 'text' row there, without waiting for an api restart.
Against the throwaway Postgres (5436)."""
import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest

from conftest import TEST_DB_URL

SQL = Path(__file__).resolve().parents[2] / "sql" / "migrate_5.5.0_sync_text_embedding.sql"
VEC_A = "[" + ",".join(["0.01"] * 512) + "]"
VEC_B = "[" + ",".join(["0.02"] * 512) + "]"


def _run(coro_fn):
    async def go():
        conn = await asyncpg.connect(dsn=os.environ.get("DATABASE_URL", TEST_DB_URL))
        try:
            await conn.execute(SQL.read_text(encoding="utf-8"))
            return await coro_fn(conn)
        finally:
            await conn.execute("DELETE FROM memories WHERE content LIKE 'pytest-816-%'")
            await conn.close()
    return asyncio.run(go())


async def _text_row(conn, mid):
    return await conn.fetchval(
        "SELECT embedding::text FROM memory_embeddings WHERE memory_id=$1 AND modality='text'", mid)


def test_a_cell_insert_under_the_cell_role_lands_in_memory_embeddings():
    async def body(conn):
        async with conn.transaction():  # the same columns the cell inserts (cell_worker ~1320)
            await conn.execute("SET LOCAL ROLE ecodb_cell")
            await conn.execute(
                "INSERT INTO memories (user_id, agent_id, workspace_id, project_id, type, content, "
                "metadata, weight, weight_base, tags, embedding) VALUES ((SELECT 1), NULL, 1, 1, "
                "'observacion', 'pytest-816-cell', '{}'::jsonb, 0.6, 0.6, ARRAY['x'], $1::vector)", VEC_A)
        mid = await conn.fetchval("SELECT id FROM memories WHERE content='pytest-816-cell'")
        return await _text_row(conn, mid)
    assert _run(body) is not None


def test_a_backfilled_embedding_lands_and_a_new_one_replaces_it():
    async def body(conn):
        mid = uuid.uuid4()
        await conn.execute(
            "INSERT INTO memories (id, user_id, workspace_id, project_id, type, content) "
            "VALUES ($1, 1, 1, 1, 'observacion', 'pytest-816-backfill')", mid)
        before = await _text_row(conn, mid)
        await conn.execute("UPDATE memories SET embedding=$2::vector WHERE id=$1", mid, VEC_A)
        filled = await _text_row(conn, mid)
        await conn.execute("UPDATE memories SET embedding=$2::vector WHERE id=$1", mid, VEC_B)
        replaced = await _text_row(conn, mid)
        return before, filled, replaced
    before, filled, replaced = _run(body)
    assert before is None
    assert filled is not None and filled.startswith("[0.01")
    assert replaced.startswith("[0.02")


def test_setting_the_embedding_to_null_keeps_the_row():
    async def body(conn):
        mid = uuid.uuid4()
        await conn.execute(
            "INSERT INTO memories (id, user_id, workspace_id, project_id, type, content, embedding) "
            "VALUES ($1, 1, 1, 1, 'observacion', 'pytest-816-null', $2::vector)", mid, VEC_A)
        await conn.execute("UPDATE memories SET embedding=NULL WHERE id=$1", mid)
        return await _text_row(conn, mid)
    assert _run(body).startswith("[0.01")


def test_the_migration_can_run_twice():
    async def body(conn):
        await conn.execute(SQL.read_text(encoding="utf-8"))
        return await conn.fetchval(
            "SELECT count(*) FROM pg_trigger WHERE tgname='trg_sync_text_embedding'")
    assert _run(body) == 1
