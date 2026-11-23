"""#1362: after the migrations, a brand-new database has every predicate-vocabulary table the code uses.

predicates_canonical, predicate_aliases and pending_predicates came from before the first commit and no
migration created them: they only existed in the family's database, and on a fresh install the vocabulary
endpoint died with «relation "predicates_canonical" does not exist». 5.7.0 creates them. Runs against the
throwaway test DB (conftest), never the live one.
"""

import asyncio
import sys
from pathlib import Path

import asyncpg
import pytest

API = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API))
from conftest import TEST_DB_URL  # noqa: E402
import migrations  # noqa: E402

TABLES = ("predicates_canonical", "predicate_aliases", "pending_predicates")


@pytest.fixture(autouse=True)
def _at_repo_root(monkeypatch):
    monkeypatch.chdir(API.parent)  # MIGRATIONS paths are relative to the repo root, like /app in the container


async def _tables_after_migrations() -> dict[str, bool]:
    pool = await asyncpg.create_pool(dsn=TEST_DB_URL, min_size=1, max_size=1)
    try:
        await migrations.run_migrations(pool)
        async with pool.acquire() as conn:
            return {t: await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{t}") for t in TABLES}
    finally:
        await pool.close()


def test_the_predicate_tables_exist_after_migrations():
    assert asyncio.run(_tables_after_migrations()) == {t: True for t in TABLES}


def test_predicates_schema_is_a_registered_migration():
    names = [name for name, _ in migrations.MIGRATIONS]
    assert "5.7.0_predicates_schema" in names
    assert "5.7.0_predicates_schema" not in migrations._BEFORE_REGISTRY  # new: it runs, it is not a baseline
