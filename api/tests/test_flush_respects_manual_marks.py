"""C28 (#365): flush_accessed_buffer wakes stale/dormant memories that were found and
returned — but NOT one whose LAST manual staleness action (PUT /memories/{id}/staleness ->
audit_log action='update_staleness', details.staleness) set it to stale/dormant. Only
decay-set dormancy wakes. last_accessed is updated either way (the access is real).

Integration part runs on the THROWAWAY DB (conftest default 5436; the live DB is refused
by the conftest guard) inside a transaction that is rolled back.
"""
import asyncio
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest

from conftest import TEST_DB_URL

sys.path.insert(0, str(Path(__file__).parent.parent))

import search  # noqa: E402


def test_flush_sql_consults_last_manual_mark():
    sql = search._FLUSH_ACCESSED_SQL
    assert "update_staleness" in sql and "DISTINCT ON" in sql
    assert "ORDER BY" in sql and "created_at DESC" in sql


async def _scenario():
    conn = await asyncpg.connect(TEST_DB_URL)
    tx = conn.transaction()
    await tx.start()
    try:
        async def mem(staleness):
            return await conn.fetchval(
                "INSERT INTO memories (workspace_id, project_id, user_id, type, content, staleness) "
                "VALUES (1, 1, 1, 'observacion', 'pytest-c28', $1) RETURNING id", staleness)

        async def mark(mid, staleness, ts):
            await conn.execute(
                "INSERT INTO audit_log (user_id, action, resource, resource_id, details, created_at) "
                "VALUES (1, 'update_staleness', 'memory', $1, jsonb_build_object('staleness', $2::text), $3)",
                str(mid), staleness, datetime.fromisoformat(ts).replace(tzinfo=timezone.utc))

        decayed = await mem("dormant")                      # no manual mark -> wakes
        manual_dormant = await mem("dormant")
        await mark(manual_dormant, "dormant", "2026-09-01")  # last manual = dormant -> stays
        re_activated = await mem("stale")
        await mark(re_activated, "dormant", "2026-09-01")
        await mark(re_activated, "active", "2026-09-02")     # last manual = active -> wakes
        re_staled = await mem("stale")
        await mark(re_staled, "active", "2026-09-01")
        await mark(re_staled, "stale", "2026-09-02")          # last manual = stale -> stays
        archived = await mem("archived")                     # never woken

        ids = [decayed, manual_dormant, re_activated, re_staled, archived]
        search._accessed_buffer.clear()
        search._accessed_buffer.extend(str(i) for i in ids)

        class _Pool:
            @asynccontextmanager
            async def acquire(self):
                yield conn

        await search.flush_accessed_buffer(_Pool())
        rows = await conn.fetch("SELECT id, staleness, last_accessed IS NOT NULL AS touched "
                                "FROM memories WHERE id = ANY($1::uuid[])", ids)
        got = {r["id"]: (r["staleness"], r["touched"]) for r in rows}
        return {name: got[i] for name, i in [("decayed", decayed), ("manual_dormant", manual_dormant),
                                             ("re_activated", re_activated), ("re_staled", re_staled),
                                             ("archived", archived)]}
    finally:
        await tx.rollback()
        await conn.close()


def test_flush_wakes_only_decay_set_dormancy():
    try:
        res = asyncio.run(_scenario())
    except OSError as e:  # only an unreachable DB skips; SQL errors must fail
        pytest.skip(f"throwaway DB not reachable: {e}")
    assert res["decayed"] == ("active", True)
    assert res["manual_dormant"] == ("dormant", True)
    assert res["re_activated"] == ("active", True)
    assert res["re_staled"] == ("stale", True)
    assert res["archived"] == ("archived", True)
