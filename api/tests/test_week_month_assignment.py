"""#701, decisión 76 de Pepe (26-oct): el mensual coge las semanas COMPLETAS que tocan el mes.

Antes el mensual cogía semanales por contención (period_start >= inicio del mes AND period_end <= fin
del mes): una semana que cruza de mes no cabía en ninguno y se quedaba huérfana (49 en producción el
22-oct). La primera corrección (fe3170a) mandaba cada semana al mes de su jueves; Pepe la cambió: «los
resúmenes del mes cogen las semanas completas, incluidos los primeros y últimos días que caigan en
semanas que compartan días con ese mes» — una semana de borde entra en DOS mensuales, a propósito
(gradiente temporal). Y «secuenciarlos»: un nivel no se sella sin su fuente, y cuando una capa termina
dispara las de arriba que la esperaban.
Corre contra la base de PRUEBAS (conftest)."""
import asyncio
import json
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

# (period_start, period_end) -> meses que tiene que alimentar (primer día de cada uno)
WEEKS = {
    (date(2026, 8, 31), date(2026, 9, 6)): [date(2026, 8, 1), date(2026, 9, 1)],     # cruza ago/sep
    (date(2026, 9, 21), date(2026, 9, 27)): [date(2026, 9, 1)],                      # dentro de septiembre
    (date(2026, 9, 28), date(2026, 10, 4)): [date(2026, 9, 1), date(2026, 10, 1)],   # borde de octubre, que empieza en JUEVES
    (date(2026, 9, 14), date(2026, 9, 17)): [date(2026, 9, 1)],                      # #393 primera mitad
    (date(2026, 9, 18), date(2026, 9, 20)): [date(2026, 9, 1)],                      # #393 segunda mitad (vie-dom)
    (date(2026, 10, 26), date(2026, 11, 1)): [date(2026, 10, 1), date(2026, 11, 1)], # cruza oct/nov
    (date(2026, 6, 29), date(2026, 7, 5)): [date(2026, 6, 1), date(2026, 7, 1)],     # borde de junio, que acaba en MARTES
    (date(2026, 12, 28), date(2027, 1, 3)): [date(2026, 12, 1), date(2027, 1, 1)],   # cruza el AÑO
}
MONTHS = [(date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 7, 1), date(2026, 7, 31)),
          (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30)),
          (date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 30)),
          (date(2026, 12, 1), date(2026, 12, 31)), (date(2027, 1, 1), date(2027, 1, 31))]


async def _test_ids(conn):
    agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
    ws_id = await conn.fetchval("SELECT id FROM workspaces ORDER BY id LIMIT 1")
    if agent_id is None or ws_id is None:
        pytest.skip("la base de pruebas no tiene agentes o workspaces")
    return agent_id, ws_id


async def _insert_cluster(conn, agent_id, ws_id, level, ps, pe, tag=""):
    return await conn.fetchval("""
        INSERT INTO memory_clusters (agent_id, workspace_id, level, label, member_ids,
                                     period_start, period_end, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'active') RETURNING id
    """, agent_id, ws_id, level, f"{LABEL} {level} {ps}{tag}", [uuid.uuid4()], ps, pe)


async def _scenario():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        agent_id, ws_id = await _test_ids(conn)
        await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
        try:
            ids = {w: await _insert_cluster(conn, agent_id, ws_id, 'weekly', *w) for w in WEEKS}
            picked = {}
            for ms, me in MONTHS:
                rows = await cw._select_higher_sources(conn, agent_id, 'weekly', ms, me)
                picked[ms] = {r["id"] for r in rows if r["label"].startswith(LABEL)}
            return ids, picked
        finally:
            await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
    finally:
        await conn.close()


def test_each_month_takes_every_week_that_touches_it():
    ids, picked = asyncio.run(_scenario())
    for week, want in WEEKS.items():
        months = sorted(m for m, chosen in picked.items() if ids[week] in chosen)
        assert months == want, f"week {week[0]}..{week[1]} fed {months}, want {want}"


async def _quarter_sources():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        agent_id, ws_id = await _test_ids(conn)
        await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
        try:
            inside = [await _insert_cluster(conn, agent_id, ws_id, 'monthly', ms, me)
                      for ms, me in MONTHS if date(2026, 10, 1) <= ms <= date(2026, 12, 1)]
            outside = await _insert_cluster(conn, agent_id, ws_id, 'monthly', date(2026, 9, 1), date(2026, 9, 30))
            rows = await cw._select_higher_sources(conn, agent_id, 'monthly', date(2026, 10, 1), date(2026, 12, 31))
            return inside, outside, {r["id"] for r in rows if r["label"].startswith(LABEL)}
        finally:
            await conn.execute("DELETE FROM memory_clusters WHERE label LIKE $1", LABEL + "%")
    finally:
        await conn.close()


def test_quarterly_takes_its_three_monthlies_and_nothing_else():
    inside, outside, got = asyncio.run(_quarter_sources())
    assert got == set(inside) and len(inside) == 3 and outside not in got


# --- la última fuente: la semana que CONTIENE el último día del mes ---

@pytest.mark.parametrize("p_end,want", [
    (date(2026, 10, 31), (date(2026, 10, 26), date(2026, 11, 1))),  # acaba en sábado
    (date(2026, 9, 30), (date(2026, 9, 28), date(2026, 10, 4))),    # acaba en miércoles: su semana de borde
    (date(2026, 12, 31), (date(2026, 12, 28), date(2027, 1, 3))),   # acaba en jueves, la semana cruza el año
    (date(2026, 6, 30), (date(2026, 6, 29), date(2026, 7, 5))),     # acaba en martes
    (date(2026, 5, 31), (date(2026, 5, 25), date(2026, 5, 31))),    # acaba en domingo
])
def test_last_week_of_period_is_the_week_containing_the_last_day(p_end, want):
    assert cw._last_week_of_period(p_end) == want


# --- qué periodos de arriba cierra una fuente al terminar (la cadena) ---

@pytest.mark.parametrize("level,ps,pe,want", [
    ('weekly', date(2026, 10, 26), date(2026, 11, 1), [('monthly', date(2026, 10, 1), date(2026, 10, 31))]),
    ('weekly', date(2026, 10, 19), date(2026, 10, 25), []),
    ('weekly', date(2026, 5, 25), date(2026, 5, 31), [('monthly', date(2026, 5, 1), date(2026, 5, 31))]),
    ('weekly', date(2026, 12, 28), date(2027, 1, 3), [('monthly', date(2026, 12, 1), date(2026, 12, 31))]),
    ('weekly', date(2026, 9, 18), date(2026, 9, 20), []),                 # media semana #393 sin fin de mes
    ('monthly', date(2026, 11, 1), date(2026, 11, 30), []),
    ('monthly', date(2026, 12, 1), date(2026, 12, 31), [('quarterly', date(2026, 10, 1), date(2026, 12, 31))]),
    ('monthly', date(2026, 6, 1), date(2026, 6, 30), [('quarterly', date(2026, 4, 1), date(2026, 6, 30))]),
    ('quarterly', date(2026, 7, 1), date(2026, 9, 30), []),
    ('quarterly', date(2026, 10, 1), date(2026, 12, 31), [('yearly', date(2026, 1, 1), date(2026, 12, 31))]),
    ('yearly', date(2026, 1, 1), date(2026, 12, 31), []),
])
def test_periods_closed_by(level, ps, pe, want):
    assert cw._periods_closed_by(level, ps, pe) == want


# --- guarda: ningún nivel se sella sin su última fuente; con ella, sigue ---

FAR = {  # futuro lejano: ahí no vive nada más
    'monthly': (date(2031, 10, 1), date(2031, 10, 31), 'weekly', (date(2031, 10, 27), date(2031, 11, 2))),
    'quarterly': (date(2031, 10, 1), date(2031, 12, 31), 'monthly', (date(2031, 12, 1), date(2031, 12, 31))),
    'yearly': (date(2031, 1, 1), date(2031, 12, 31), 'quarterly', (date(2031, 10, 1), date(2031, 12, 31))),
}


async def _guard(level, with_completed_source):
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
    agent_id, _ = await _test_ids(conn)
    ps, pe, source_level, (ss, se) = FAR[level]
    clean = ("DELETE FROM cell_runs WHERE agent_id=$1 AND cell_type='consolidation' "
             "AND metrics->>'period_start' IN ($2, $3)")
    try:
        await conn.execute(clean, agent_id, str(ss), str(ps))
        if with_completed_source:
            await conn.execute("""INSERT INTO cell_runs (cell_type, agent_id, model, status, metrics)
                VALUES ('consolidation', $1, 'pytest-701', 'completed', $2::jsonb)""",
                agent_id, json.dumps({"period_start": str(ss), "period_end": str(se)}))
        out1 = await cw._run_higher_consolidation(pool, agent_id, level, ps, pe, source_level)
        out2 = await cw._run_higher_consolidation(pool, agent_id, level, ps, pe, source_level)
        sealed = await conn.fetch("SELECT status, items_created FROM cell_runs WHERE agent_id=$1 "
                                  "AND cell_type='consolidation' AND metrics->>'period_start'=$2 "
                                  "AND metrics->>'period_end'=$3", agent_id, str(ps), str(pe))
        return out1, out2, [dict(r) for r in sealed]
    finally:
        await conn.execute(clean, agent_id, str(ss), str(ps))
        await pool.close()
        await conn.close()


@pytest.mark.parametrize("level", ["monthly", "quarterly", "yearly"])
def test_level_waits_for_its_last_source(level, caplog):
    with caplog.at_level("WARNING"):
        out1, out2, sealed = asyncio.run(_guard(level, with_completed_source=False))
    assert out1 is None and out2 is None and sealed == []
    assert "not done yet" in caplog.text


@pytest.mark.parametrize("level", ["monthly", "quarterly", "yearly"])
def test_level_with_its_source_done_and_too_few_sources_is_recorded_done_once(level, caplog):
    """Con la fuente hecha pero menos de 2 fuentes (aquí 0), el periodo queda HECHO con 0 piezas —
    si no, el nivel de arriba esperaría para siempre a un mensual que nunca se sella — y una
    segunda pasada no apunta otro run."""
    with caplog.at_level("WARNING"):
        out1, out2, sealed = asyncio.run(_guard(level, with_completed_source=True))
    assert "not done yet" not in caplog.text
    assert sealed == [{"status": "completed", "items_created": 0}]


# --- la cadena: al terminar una capa se lanzan las de arriba que la esperaban ---

def test_cascade_runs_the_upper_levels_with_their_own_period(monkeypatch):
    calls = []

    async def fake_enabled(conn, agent_id, level):
        return level != 'yearly'          # el anual de este agente está apagado: no se lanza

    def recorder(level):
        async def run(pool, aid, cfg, ps, pe):
            calls.append((level, ps, pe))
            return "run-id"
        return run

    monkeypatch.setattr(cw, "_upper_config_enabled", fake_enabled)
    for lvl in ("monthly", "quarterly", "yearly"):
        monkeypatch.setitem(cw._BUILTIN_DISPATCH, ("consolidation", lvl), recorder(lvl))

    async def go():
        pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
        try:
            await cw._cascade_up(pool, 1, 'weekly', date(2026, 12, 28), date(2027, 1, 3))
        finally:
            await pool.close()

    asyncio.run(go())
    assert calls == [('monthly', date(2026, 12, 1), date(2026, 12, 31)),
                     ('quarterly', date(2026, 10, 1), date(2026, 12, 31))]


def test_cascade_stops_when_the_upper_level_is_not_sealed(monkeypatch):
    calls = []

    async def fake_enabled(conn, agent_id, level):
        return True

    async def monthly_not_sealed(pool, aid, cfg, ps, pe):
        calls.append(('monthly', ps, pe))
        return None                        # p. ej. la guarda lo paró: no sube más

    async def quarterly(pool, aid, cfg, ps, pe):
        calls.append(('quarterly', ps, pe))
        return "run-id"

    monkeypatch.setattr(cw, "_upper_config_enabled", fake_enabled)
    monkeypatch.setitem(cw._BUILTIN_DISPATCH, ("consolidation", "monthly"), monthly_not_sealed)
    monkeypatch.setitem(cw._BUILTIN_DISPATCH, ("consolidation", "quarterly"), quarterly)

    async def go():
        pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
        try:
            await cw._cascade_up(pool, 1, 'weekly', date(2026, 12, 28), date(2027, 1, 3))
        finally:
            await pool.close()

    asyncio.run(go())
    assert calls == [('monthly', date(2026, 12, 1), date(2026, 12, 31))]


# --- plantilla del rollup semanal: la del agente si la tiene, si no la de siempre por nombre ---

async def _rollup_template(override):
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    agent_id, _ = await _test_ids(conn)
    tid = None
    try:
        tid = await conn.fetchval("""
            INSERT INTO cell_prompt_templates (name, cell_type, content)
            VALUES ($1, 'consolidation', 'PLANTILLA PROPIA {agent_identifier}') RETURNING id
        """, f"{LABEL} rollup {uuid.uuid4()}")

        async def fake_cfg(c, aid, cell_type, level=None):
            return {"config": {"week_rollup_template_id": tid} if override else {}}
        cw_load = cw._load_cell_config
        cw._load_cell_config = fake_cfg
        try:
            got = await cw._week_rollup_template(conn, agent_id)
        finally:
            cw._load_cell_config = cw_load
        by_name = await conn.fetchval(
            "SELECT content FROM cell_prompt_templates WHERE name='CellAgent Week Rollup'")
        return got, by_name
    finally:
        if tid:
            await conn.execute("DELETE FROM cell_prompt_templates WHERE id=$1", tid)
        await conn.close()


def test_week_rollup_uses_the_agent_override():
    got, _ = asyncio.run(_rollup_template(override=True))
    assert got == 'PLANTILLA PROPIA {agent_identifier}'


def test_week_rollup_without_override_uses_the_named_template():
    got, by_name = asyncio.run(_rollup_template(override=False))
    assert got == by_name


# --- invariante de cobertura: memorias de la semana que ningún semanal cogió ---

async def _coverage():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    agent_id, ws_id = await _test_ids(conn)
    pj_id = await conn.fetchval("SELECT id FROM projects ORDER BY id LIMIT 1")
    if pj_id is None:
        pytest.skip("la base de pruebas no tiene proyectos")
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
