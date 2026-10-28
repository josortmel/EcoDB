"""#708 (28-oct, Prima lo cazó): migrations.py vuelve a ejecutar TODAS las migraciones en cada arranque de la api, y
sql/seed_higher_prompts.sql reapuntaba TODAS las configs mensuales, trimestrales y anuales a «CellAgent
Monthly/Quarterly/Yearly». Cada reinicio deshacía en silencio las plantillas elegidas por agente (la decisión 81 de
Pepe: «lo concreto se conserva», 3283-3285), sin tocar updated_at. Ahora la siembra solo reapunta lo que sigue en la
plantilla de origen («CellAgent Higher Consolidation») o en ninguna. Corre contra la base de PRUEBAS (conftest)."""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

SEED = Path(__file__).resolve().parents[2] / "sql" / "seed_higher_prompts.sql"
NAME = "pytest-708 plantilla elegida"


async def _go():
    conn = await asyncpg.connect(dsn=TEST_DB_URL)
    try:
        cfg = await conn.fetchrow("""SELECT id, prompt_template_id FROM cell_task_configs
                                     WHERE cell_type='consolidation' AND level='monthly' ORDER BY id LIMIT 1""")
        if cfg is None:
            pytest.skip("la base de pruebas no tiene configs mensuales")
        chosen = await conn.fetchval("""INSERT INTO cell_prompt_templates (name, cell_type, content, is_default)
                                        VALUES ($1, 'consolidation', 'x', false)
                                        ON CONFLICT (name) DO UPDATE SET content='x' RETURNING id""", NAME)
        legacy = await conn.fetchval("SELECT id FROM cell_prompt_templates WHERE name='CellAgent Higher Consolidation'")
        try:
            await conn.execute("UPDATE cell_task_configs SET prompt_template_id=$1 WHERE id=$2", chosen, cfg["id"])
            await conn.execute(SEED.read_text(encoding="utf-8"))
            kept = await conn.fetchval("SELECT prompt_template_id FROM cell_task_configs WHERE id=$1", cfg["id"])
            rewired = None
            if legacy is not None:
                await conn.execute("UPDATE cell_task_configs SET prompt_template_id=$1 WHERE id=$2", legacy, cfg["id"])
                await conn.execute(SEED.read_text(encoding="utf-8"))
                rewired = await conn.fetchval("""SELECT t.name FROM cell_task_configs c JOIN cell_prompt_templates t
                                                 ON t.id=c.prompt_template_id WHERE c.id=$1""", cfg["id"])
            return chosen, kept, rewired
        finally:
            await conn.execute("UPDATE cell_task_configs SET prompt_template_id=$1 WHERE id=$2",
                               cfg["prompt_template_id"], cfg["id"])
            await conn.execute("DELETE FROM cell_prompt_templates WHERE name=$1", NAME)
    finally:
        await conn.close()


def test_the_seed_keeps_a_chosen_template_and_rewires_the_legacy_one():
    chosen, kept, rewired = asyncio.run(_go())
    assert kept == chosen
    assert rewired in (None, "CellAgent Monthly")
