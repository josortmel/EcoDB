"""#701: every weekly cluster feeds exactly one monthly — the month of the Thursday of
its ISO week. Before, the monthly took weeklies by containment (period_start >= month
start AND period_end <= month end), so a week crossing a month boundary fitted in no
month and was orphaned forever (49 orphan weeklies in production, 22-oct).
Runs against the TEST database (conftest)."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402

LABEL = "pytest-701"

# (period_start, period_end) -> month it must feed (first day)
WEEKS = {
    (date(2026, 8, 31), date(2026, 9, 6)): date(2026, 9, 1),    # crosses Aug/Sep, Thu 3-sep
    (date(2026, 9, 21), date(2026, 9, 27)): date(2026, 9, 1),   # inside September
    (date(2026, 9, 28), date(2026, 10, 4)): date(2026, 10, 1),  # crosses Sep/Oct, Thu 1-oct
    (date(2026, 9, 14), date(2026, 9, 17)): date(2026, 9, 1),   # #393 first half
    (date(2026, 9, 18), date(2026, 9, 20)): date(2026, 9, 1),   # #393 second half (Fri-Sun)
    (date(2026, 10, 26), date(2026, 11, 1)): date(2026, 10, 1), # crosses Oct/Nov, Thu 29-oct
    (date(2026, 12, 28), date(2027, 1, 3)): date(2026, 12, 1),  # crosses the YEAR, Thu 31-dec
}
MONTHS = [(date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30)),
          (date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 30)),
          (date(2026, 12, 1), date(2026, 12, 31)), (date(2027, 1, 1), date(2027, 1, 31))]


async def _scenario():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
        ws_id = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
        if agent_id is None or ws_id is None:
            pytest.skip("la base de pruebas no tiene agentes o workspaces")
        await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
        ids = {}
        try:
            for (ps, pe) in WEEKS:
                ids[(ps, pe)] = await conn.fetchval("""
                    INSERT INTO memory_clusters (agent_id, workspace_id, level, label, member_ids,
                                                 period_start, period_end, status)
                    VALUES ($1, $2, 'weekly', $3, $4, $5, $6, 'active') RETURNING id
                """, agent_id, ws_id, f"{LABEL} {ps}", [uuid.uuid4()], ps, pe)
            picked = {}
            for ms, me in MONTHS:
                rows = await cw._select_higher_sources(conn, agent_id, 'weekly', ms, me)
                picked[ms] = {r["id"] for r in rows if r["label"].startswith(LABEL)}
            return ids, picked
        finally:
            await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
    finally:
        await conn.close()


def test_each_week_feeds_exactly_one_month_the_one_of_its_thursday():
    ids, picked = asyncio.run(_scenario())
    for week, want_month in WEEKS.items():
        months = [m for m, chosen in picked.items() if ids[week] in chosen]
        assert months == [want_month], f"week {week[0]}..{week[1]} fed {months}, want [{want_month}]"


# --- guard: a monthly is not sealed before its last week has been consolidated ---

@pytest.mark.parametrize("p_end,want", [
    (date(2026, 10, 31), (date(2026, 10, 26), date(2026, 11, 1))),  # month ends Sat: week ends 1-nov
    (date(2026, 9, 30), (date(2026, 9, 21), date(2026, 9, 27))),    # ends Wed: 28-sep week is October's
    (date(2026, 12, 31), (date(2026, 12, 28), date(2027, 1, 3))),   # ends Thu: week ends on the 3rd
    (date(2026, 5, 31), (date(2026, 5, 25), date(2026, 5, 31))),    # ends Sun
])
def test_last_week_of_period(p_end, want):
    assert cw._last_week_of_period(p_end) == want


async def _guard(with_completed_run):
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
    agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
    if agent_id is None:
        pytest.skip("la base de pruebas no tiene agentes")
    ms, me = date(2031, 10, 1), date(2031, 10, 31)  # far future: nothing else lives there
    ws, we = cw._last_week_of_period(me)
    clean = ("DELETE FROM cell_runs WHERE agent_id=$1 AND cell_type='consolidation' "
             "AND metrics->>'period_start' IN ($2, $3)")
    try:
        await conn.execute(clean, agent_id, str(ws), str(ms))
        if with_completed_run:
            await conn.execute("""INSERT INTO cell_runs (cell_type, agent_id, model, status, metrics)
                VALUES ('consolidation', $1, 'pytest-701', 'completed', $2::jsonb)""",
                agent_id, f'{{"period_start": "{ws}", "period_end": "{we}"}}')
        out = await cw._run_higher_consolidation(pool, agent_id, 'monthly', ms, me, 'weekly')
        sealed = await conn.fetchval("SELECT count(*) FROM cell_runs WHERE agent_id=$1 "
                                     "AND metrics->>'period_start'=$2", agent_id, str(ms))
        return out, sealed
    finally:
        await conn.execute(clean, agent_id, str(ws), str(ms))
        await pool.close()
        await conn.close()


def test_monthly_waits_for_its_last_week(caplog):
    with caplog.at_level("WARNING"):
        out, sealed = asyncio.run(_guard(with_completed_run=False))
    assert out is None and sealed == 0
    assert "not consolidated yet" in caplog.text


def test_monthly_goes_on_once_last_week_is_done(caplog):
    with caplog.at_level("WARNING"):
        out, sealed = asyncio.run(_guard(with_completed_run=True))
    assert out is None and sealed == 0          # no sources in 2031 -> min_sources stops it
    assert "not consolidated yet" not in caplog.text   # ...but the guard let it through


# --- coverage invariant: memories of the week that no weekly cluster took ---

async def _coverage():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
    ws_id = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
    pj_id = await conn.fetchval("SELECT id FROM projects ORDER BY id LIMIT 1")
    if None in (agent_id, ws_id, pj_id):
        pytest.skip("la base de pruebas no tiene agentes, workspaces o proyectos")
    ws, we = date(2031, 10, 27), date(2031, 11, 2)
    try:
        ids = [await conn.fetchval("""
            INSERT INTO memories (workspace_id, project_id, agent_id, type, content, created_at)
            VALUES ($1, $2, $3, 'momento', $4, $5) RETURNING id""",
            ws_id, pj_id, agent_id, f"{LABEL} memoria {i}", datetime(2031, 10, 28 + i, 12, tzinfo=timezone.utc))
            for i in range(2)]
        await conn.execute("""
            INSERT INTO memory_clusters (agent_id, workspace_id, level, label, member_ids,
                                         period_start, period_end, status)
            VALUES ($1, $2, 'weekly', $3, $4, $5, $6, 'active')""",
            agent_id, ws_id, f"{LABEL} cobertura", [ids[0]], ws, we)
        return ids, await cw._week_uncovered(conn, agent_id, ws_id, ws, we)
    finally:
        await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
        await conn.execute("DELETE FROM memories WHERE content LIKE $1", LABEL + "%")
        await conn.close()


def test_week_uncovered_lists_only_the_memory_no_cluster_took():
    ids, uncovered = asyncio.run(_coverage())
    assert uncovered == [ids[1]]
