"""#816 (1): rebuilding past weeks (the #702 regeneration, 28-oct) wrote one «Identity tension» per
rebuilt week, all dated today: 101 that crowded the recent days of every boot. Now only a recently
closed week gets one, and never a second one for the same week. Offline: fake conn + fake LLM."""
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x@127.0.0.1:1/x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cell_worker as cw  # noqa: E402

TENSION = json.dumps({"tensions": [{"observed_trait": "o", "declared_trait": "d",
                                    "tension_type": "gap"}]})


class FakeConn:
    def __init__(self, existing_for_week=False):
        self.existing_for_week = existing_for_week
        self.inserts = []

    async def fetchval(self, q, *a):
        if "metadata->>'week_start'" in q:
            return 1 if self.existing_for_week else None
        if "FROM projects" in q:
            return 1
        return None  # no dismissed tension in cooldown

    async def execute(self, q, *a):
        if "INSERT INTO memories" in q:
            self.inserts.append(a)


def _run(monkeypatch, week_end, existing=False):
    calls = []

    async def fake_llm(_s, _u):
        calls.append(1)
        return TENSION

    async def no_embed(_t):
        return None

    monkeypatch.setattr(cw, "_llm_call", fake_llm)
    monkeypatch.setattr(cw, "_embed_for_memory", no_embed)
    conn = FakeConn(existing)
    memories = [{"id": f"m{i}", "type": "momento"} for i in range(6)]
    n = asyncio.run(cw._detect_identity_tensions(
        conn, 3, 1, [{"content": "soy Hilo"}], memories, week_end - timedelta(days=6), week_end))
    return n, conn, len(calls)


def test_a_rebuilt_old_week_gets_no_tension_and_no_llm_call(monkeypatch):
    n, conn, calls = _run(monkeypatch, date.today() - timedelta(days=30))
    assert (n, conn.inserts, calls) == (0, [], 0)


def test_the_week_that_just_closed_gets_one_with_its_week(monkeypatch):
    week_end = date.today() - timedelta(days=1)
    n, conn, calls = _run(monkeypatch, week_end)
    assert n == 1 and calls == 1
    meta = json.loads(conn.inserts[0][4])
    assert meta["week_start"] == str(week_end - timedelta(days=6)) and meta["week_end"] == str(week_end)


def test_a_second_run_of_the_same_week_adds_nothing(monkeypatch):
    n, conn, calls = _run(monkeypatch, date.today() - timedelta(days=1), existing=True)
    assert (n, conn.inserts, calls) == (0, [], 0)
