"""#393: una semana cuyo JSON falla se parte en dos mitades; si las DOS mitades terminan, la semana
entera tiene que contar como hecha para el catch-up. Antes, _check_idempotency buscaba el periodo exacto de
la semana entera, no lo encontraba nunca y la relanzaba en cada arranque (~8 min de LLM; 10 veces con Eco).
Corre contra la base de PRUEBAS (conftest)."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402

W0, MID, W1 = date(2026, 9, 14), date(2026, 9, 17), date(2026, 9, 20)


async def _with_agent(fn):
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
        if agent_id is None:
            pytest.skip("la base de pruebas no tiene agentes")
        await conn.execute("DELETE FROM cell_runs WHERE agent_id=$1 AND cell_type='consolidation' "
                           "AND metrics->>'period_start' IN ($2,$3,$4)", agent_id, str(W0), str(MID), "2026-09-18")
        try:
            return await fn(conn, agent_id)
        finally:
            await conn.execute("DELETE FROM cell_runs WHERE agent_id=$1 AND cell_type='consolidation' "
                               "AND metrics->>'period_start' IN ($2,$3,$4)", agent_id, str(W0), str(MID), "2026-09-18")
    finally:
        await conn.close()


async def _done(conn, agent_id, a, b):
    rid = await cw._create_run(conn, "consolidation", agent_id, a, b)
    await cw._complete_run(conn, rid, 1)


def test_both_halves_done_marks_whole_week():
    async def body(conn, agent_id):
        await _done(conn, agent_id, W0, MID)
        await _done(conn, agent_id, date(2026, 9, 18), W1)
        assert not await cw._check_idempotency(conn, agent_id, "consolidation", W0, W1)  # el fallo de antes
        assert await cw._mark_split_complete(conn, agent_id, W0, MID, W1) is True
        assert await cw._check_idempotency(conn, agent_id, "consolidation", W0, W1)       # ya no se relanza
        n = await conn.fetchval("SELECT count(*) FROM cell_runs WHERE agent_id=$1 AND status='completed' "
                                "AND metrics->>'period_start'=$2 AND metrics->>'period_end'=$3 "
                                "AND metrics ? 'split_into'", agent_id, str(W0), str(W1))
        assert n == 1
        # idempotente: llamarlo otra vez no crea otro marcador
        await cw._mark_split_complete(conn, agent_id, W0, MID, W1)
        assert await conn.fetchval("SELECT count(*) FROM cell_runs WHERE agent_id=$1 AND metrics ? 'split_into' "
                                   "AND metrics->>'period_start'=$2", agent_id, str(W0)) == 1
    asyncio.run(_with_agent(body))


def test_one_half_missing_does_not_mark():
    async def body(conn, agent_id):
        await _done(conn, agent_id, W0, MID)          # la segunda mitad NO se completó
        assert await cw._mark_split_complete(conn, agent_id, W0, MID, W1) is False
        assert not await cw._check_idempotency(conn, agent_id, "consolidation", W0, W1)
    asyncio.run(_with_agent(body))
