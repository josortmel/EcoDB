"""#702 (28-oct, encargo de Pepe: «solucionemos de una vez el problema de la memoria… aunque implique rehacer todos
los semanales, mensuales y trimestrales»). Para poder rehacer una semana:
(1) la semana está hecha por lo que EXISTE (un semanal activo dentro de la semana, también las mitades de #393),
    no por un run viejo: antes cualquier run completado la bloqueaba para siempre;
(2) el contexto de la semana no lleva nada POSTERIOR a ella (narrativas, calibración y muestras de voz): al
    rehacer marzo entraban narrativas de octubre.
Corre contra la base de PRUEBAS (conftest), en semanas de 2031."""
import asyncio
import inspect
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402

LABEL = "pytest-702"
W0, W1 = date(2031, 3, 3), date(2031, 3, 9)


async def _ids(conn):
    agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
    ws_id = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
    if agent_id is None or ws_id is None:
        pytest.skip("la base de pruebas no tiene agentes o workspaces")
    return agent_id, ws_id


async def _run(conn, agent_id, status, items, ps=W0, pe=W1, extra=None):
    metrics = {"period_start": str(ps), "period_end": str(pe), "pytest": LABEL, **(extra or {})}
    await conn.execute("""INSERT INTO cell_runs (agent_id, cell_type, status, items_created, metrics, started_at, model)
                          VALUES ($1, 'consolidation', $2, $3, $4::jsonb, NOW(), 'pytest')""",
                       agent_id, status, items, json.dumps(metrics))


async def _cluster(conn, agent_id, ws_id, ps, pe, status="active"):
    await conn.execute("""INSERT INTO memory_clusters (agent_id, workspace_id, level, label, member_ids,
                                                       period_start, period_end, status)
                          VALUES ($1, $2, 'weekly', $3, $4, $5, $6, $7)""",
                       agent_id, ws_id, f"{LABEL} {ps}", [uuid.uuid4()], ps, pe, status)


async def _clean(conn):
    await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
    await conn.execute("DELETE FROM cell_runs WHERE metrics->>'pytest' = $1", LABEL)


def _case(setup):
    async def go():
        conn = await asyncpg.connect(dsn=TEST_DB_URL)
        try:
            agent_id, ws_id = await _ids(conn)
            await _clean(conn)
            await setup(conn, agent_id, ws_id)
            return await cw._weekly_done(conn, agent_id, W0, W1)
        finally:
            await _clean(conn)
            await conn.close()
    return asyncio.run(go())


def test_a_week_with_its_clusters_is_done():
    async def s(c, a, w):
        await _run(c, a, "completed", 5)
        await _cluster(c, a, w, W0, W1)
    assert _case(s) is True


def test_a_week_whose_clusters_were_superseded_can_be_rebuilt():
    async def s(c, a, w):
        await _run(c, a, "completed", 5)
        await _cluster(c, a, w, W0, W1, status="superseded")
    assert _case(s) is False


def test_the_halves_of_a_split_week_count_as_done():
    async def s(c, a, w):
        await _run(c, a, "completed", 0, extra={"split_into": [[str(W0), "2031-03-06"], ["2031-03-07", str(W1)]]})
        await _cluster(c, a, w, W0, date(2031, 3, 6))
    assert _case(s) is True


def test_a_split_week_whose_halves_were_superseded_can_be_rebuilt_whole():
    async def s(c, a, w):
        await _run(c, a, "completed", 0, extra={"split_into": [[str(W0), "2031-03-06"], ["2031-03-07", str(W1)]]})
        await _cluster(c, a, w, W0, date(2031, 3, 6), status="superseded")
        await _cluster(c, a, w, date(2031, 3, 7), W1, status="superseded")
    assert _case(s) is False


def test_an_empty_week_already_run_is_not_run_again():
    async def s(c, a, w):
        await _run(c, a, "completed", 0)
    assert _case(s) is True


def test_a_week_in_progress_is_done():
    async def s(c, a, w):
        await _run(c, a, "running", 0)
    assert _case(s) is True


def test_a_week_never_run_is_not_done():
    async def s(c, a, w):
        pass
    assert _case(s) is False


def test_the_week_context_has_no_future():
    src = inspect.getsource(cw.run_consolidation)
    for q in ("'calibration' = ANY(tags) AND created_at < $2",
              "length(content) > 200 AND created_at < $2",
              "AND period_end < $2"):
        assert q in src, q
