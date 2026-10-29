"""#813: in the 28-oct regeneration 2 of 111 week rollups were stored with label «unlabeled» and
narrative NULL (Prima 12-18 oct, Lienzo 7-13 sep): an LLM answer without the keys was saved as is,
and the monthly, which reads the rollups, lost that week. Now an answer without narrative or label
is retried, and if it never comes nothing is inserted, so the next pass rebuilds the rollup.
Offline: a fake connection and a fake LLM, no database."""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x@127.0.0.1:1/x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cell_worker as cw  # noqa: E402

GOOD = json.dumps({"label": "La semana", "detail": "d", "narrative": "Lo que pasó.", "metadata": {}})


class FakeConn:
    def __init__(self):
        self.inserts = []

    async def fetchval(self, q, *a):
        if "INSERT INTO memory_clusters" in q:
            self.inserts.append(a)
            return "new-rollup"
        if "SELECT identifier" in q:
            return "Hilo"
        return None  # no active rollup yet

    async def fetch(self, q, *a):
        if "FROM memory_clusters" in q:
            return [{"id": "c1", "workspace_id": 1, "label": "tema", "narrative": "n", "detail": None,
                     "centroid": None, "member_ids": ["m1"], "metadata": {},
                     "period_start": date(2026, 10, 12), "period_end": date(2026, 10, 18)}]
        return []


def _run(answers, monkeypatch):
    calls = []

    async def fake_llm(_system, _user):
        calls.append(1)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    async def no_template(_conn, _agent_id):
        return None

    monkeypatch.setattr(cw, "_llm_call", fake_llm)
    monkeypatch.setattr(cw, "_week_rollup_template", no_template)
    monkeypatch.setattr(cw, "LLM_DELAYS", [0, 0, 0])
    conn = FakeConn()
    result = asyncio.run(cw._ensure_week_rollup(conn, 3, date(2026, 10, 12), date(2026, 10, 18)))
    return result, conn, len(calls)


def test_an_answer_without_narrative_is_retried(monkeypatch):
    result, conn, calls = _run(["{}", GOOD], monkeypatch)
    assert result == "new-rollup" and calls == 2
    assert conn.inserts[0][2] == "La semana" and conn.inserts[0][4] == "Lo que pasó."


def test_never_a_narrative_means_no_empty_rollup(monkeypatch):
    result, conn, calls = _run(['{"label": "x"}'], monkeypatch)
    assert result is None and conn.inserts == []
    assert calls == cw.MAX_LLM_RETRIES


def test_a_good_answer_is_stored_first_time(monkeypatch):
    result, conn, calls = _run([GOOD], monkeypatch)
    assert result == "new-rollup" and calls == 1
