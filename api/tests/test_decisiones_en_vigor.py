"""#844 (from #702, 29-oct): the quarterly template drops by design what lives in a single month
(«lo que parecía importante un mes y se evaporó no entra»), so the Regla -1, born on 30-sep, never
reached Hilo's jul-sep quarterly. A template that carries {decisiones_en_vigor} now receives the
period's decision/acuerdo memories with date, id and author, and a superseded one is left out
(Prima: an obsolete rule in the section does more harm than none, arXiv 2610.36308).
A template without the placeholder gets exactly the prompt it got before.
Offline: a fake connection and a fake LLM, no database."""
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x@127.0.0.1:1/x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cell_worker as cw  # noqa: E402

ANSWER = json.dumps({"label": "La estación", "detail": "d", "narrative": "Lo que pesó."})
DECISIONES = [
    {"id": "1a2b3c4d-0000-0000-0000-000000000001", "created_at": datetime(2026, 9, 30, 10, tzinfo=timezone.utc),
     "content": "Regla -1: antes de lanzar un subagente se pregunta a Pepe.", "autor": "Hilo", "metadata": {}},
    {"id": "5e6f7a8b-0000-0000-0000-000000000002", "created_at": datetime(2026, 9, 3, 9, tzinfo=timezone.utc),
     "content": "Telegram es el canal con Pepe.", "autor": "Hilo", "metadata": "{}"},
    {"id": "9c9c9c9c-0000-0000-0000-000000000003", "created_at": datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
     "content": "El MCP se queda como agenticos.", "autor": "Hilo",
     "metadata": {"superseded_by": "d0d0d0d0-0000-0000-0000-000000000004"}},
]
MENSUALES = [{"label": "Septiembre", "narrative": "n", "period_start": date(2026, 9, 1),
              "period_end": date(2026, 9, 30)},
             {"label": "Julio", "narrative": "n", "period_start": date(2026, 7, 1),
              "period_end": date(2026, 7, 31)}]


class FakeConn:
    def __init__(self, decisiones):
        self.decisiones = decisiones
        self.decision_queries = []

    async def fetchval(self, q, *a):
        return "Hilo" if "SELECT identifier" in q else None

    async def fetchrow(self, q, *a):
        return None  # no previous quarterly

    async def fetch(self, q, *a):
        if "m.type::text = ANY" in q and ["decision", "acuerdo"] in a:
            self.decision_queries.append(a)
            return self.decisiones
        return []


def _quarterly(template, decisiones, monkeypatch):
    seen = {}

    async def fake_llm(system, user):
        seen["system"], seen["user"] = system, user
        return ANSWER

    monkeypatch.setattr(cw, "_llm_call", fake_llm)
    conn = FakeConn(decisiones)
    token = cw._active_cell.set({"template": template})
    try:
        asyncio.run(cw._label_higher_cluster(MENSUALES, "quarterly", 3, conn, p_start=date(2026, 7, 1)))
    finally:
        cw._active_cell.reset(token)
    return seen, conn


V3 = "Consolida tu {period_name}.\n## Decisiones y reglas en vigor\n{decisiones_en_vigor}\nFin."
V2 = "Consolida tu {period_name}. Lo que se evaporó no entra."


def test_the_period_decisions_reach_the_prompt_with_date_id_and_author(monkeypatch):
    seen, conn = _quarterly(V3, DECISIONES, monkeypatch)
    s = seen["system"]
    assert "[2026-09-30] id 1a2b3c4d · Hilo · Regla -1" in s
    assert "[2026-09-03] id 5e6f7a8b · Hilo · Telegram es el canal con Pepe." in s
    # the whole quarter: from the first day of the earliest monthly to the last day of the latest
    assert conn.decision_queries and conn.decision_queries[0][-2:] == (date(2026, 7, 1), date(2026, 9, 30))


def test_a_superseded_decision_does_not_reach_the_prompt(monkeypatch):
    seen, _ = _quarterly(V3, DECISIONES, monkeypatch)
    assert "agenticos" not in seen["system"] and "9c9c9c9c" not in seen["system"]


def test_a_period_without_decisions_says_so(monkeypatch):
    seen, _ = _quarterly(V3, [], monkeypatch)
    assert "{decisiones_en_vigor}" not in seen["system"]
    assert "ninguna decisión ni acuerdo" in seen["system"]


def test_a_template_without_the_placeholder_gets_the_same_prompt_and_no_query(monkeypatch):
    seen, conn = _quarterly(V2, DECISIONES, monkeypatch)
    assert seen["system"] == "Consolida tu trimestre. Lo que se evaporó no entra."
    assert conn.decision_queries == []


def test_the_week_rollup_also_gets_them(monkeypatch):
    seen = {}

    async def fake_llm(system, user):
        seen["system"] = system
        return ANSWER

    async def v3_rollup(_conn, _agent_id):
        return "Tu semana.\n{decisiones_en_vigor}"

    monkeypatch.setattr(cw, "_llm_call", fake_llm)
    monkeypatch.setattr(cw, "_week_rollup_template", v3_rollup)
    conn = FakeConn(DECISIONES[1:2])
    temas = [{"label": "t", "narrative": "n", "metadata": {}, "period_start": date(2026, 8, 31),
              "period_end": date(2026, 9, 6)}]
    asyncio.run(cw._label_week_rollup(temas, 3, conn))
    assert "Telegram es el canal con Pepe." in seen["system"]
    assert conn.decision_queries[0][-2:] == (date(2026, 8, 31), date(2026, 9, 6))


def test_the_query_runs_against_the_real_schema(db_url):
    # The fake connection let `m.type = ANY($2::text[])` through; Postgres refused it, because
    # memories.type is the memory_type enum (found on the first real run of #845). This runs the
    # real query on the test database; no rows are needed for Postgres to check the types.
    import asyncpg

    async def run():
        conn = await asyncpg.connect(db_url)
        try:
            return await cw._decisiones_en_vigor(conn, -1, date(2026, 7, 1), date(2026, 9, 30))
        finally:
            await conn.close()

    assert asyncio.run(run()) == "(ninguna decisión ni acuerdo guardado en este periodo)"
