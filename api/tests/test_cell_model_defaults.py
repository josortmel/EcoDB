"""#716 (23-oct): (1) no default may name a retired DeepSeek model: deepseek-chat and
deepseek-reasoner were discontinued on 2026-07-24 (api-docs.deepseek.com/updates, read
23-oct); a config created without a model, or a fallback path, asked for a model that no
longer exists. (2) DeepSeek ships new builds under the SAME name (V4.1-Flash-1017 on
17-oct, still «deepseek-flash»), so each cell run records the `model` the API ANSWERED
with, not just the one we asked for. Test (2) runs against the TEST database (conftest)."""
import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg
import httpx
import pytest
import respx

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402
import settings  # noqa: E402
from cell_configs import CellConfigCreate  # noqa: E402

RETIRED = re.compile(r"""["'](deepseek-chat|deepseek-reasoner)["']""")


def test_no_default_names_a_retired_model():
    hits = [f"{p.name}:{i}" for p in API_DIR.glob("*.py")
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if RETIRED.search(line)]
    assert hits == [], f"retired DeepSeek model as a default in: {hits}"


def test_a_new_config_without_model_gets_the_current_default():
    cfg = CellConfigCreate(agent_identifier="Hilo", cell_type="consolidation")
    assert cfg.model == settings.DEFAULT_LLM_MODEL == "deepseek-flash"


# Measured 23-oct with a real call: DeepSeek answers model="deepseek-flash" (the alias, NOT
# the build), so the build change is only visible in system_fingerprint.
ANSWERED = "deepseek-flash"
FINGERPRINT = "e72d3c7f663d3e1383b00b3884cb4501"


async def _one_run():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    agent_id = await conn.fetchval("SELECT id FROM agents ORDER BY id LIMIT 1")
    if agent_id is None:
        pytest.skip("la base de pruebas no tiene agentes")
    token = cw._active_cell.set({"provider": "deepseek", "model": "deepseek-flash", "key": "k-test"})
    run_id = None
    try:
        run_id = await cw._create_run(conn, "pytest-716", agent_id, "2031-01-01", "2031-01-07")
        await cw._llm_call("sys", "user")
        await cw._complete_run(conn, run_id, 0)
        return await conn.fetchrow("SELECT metrics->'responded_models' AS m, metrics->'system_fingerprints' AS f "
                                   "FROM cell_runs WHERE id=$1", run_id)
    finally:
        cw._active_cell.reset(token)
        if run_id:
            await conn.execute("DELETE FROM cell_runs WHERE id=$1", run_id)
        await conn.close()


@respx.mock
def test_the_run_records_the_model_that_answered():
    respx.post("https://api.deepseek.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": ANSWERED, "system_fingerprint": FINGERPRINT, "choices": [{"message": {"content": "{}"}}]}))
    row = asyncio.run(_one_run())
    assert row["m"] is not None and ANSWERED in row["m"]
    assert row["f"] is not None and FINGERPRINT in row["f"]
