"""Migration runner for EcoDB, with a registry of what has been applied.

Runs inside the FastAPI lifespan, after validate_production_secrets()
and before the dictionary cache. Uses pg_advisory_lock to serialize
concurrent startups (future multi-replica).

#812 (Hilo, 16-nov-2026): it used to re-run EVERY migration on EVERY
startup and trusted them all to be idempotent. They are, as SQL, but
7 seeds do `ON CONFLICT (name) DO UPDATE SET content = ...`, so every
restart of the api rewrote those prompt templates and undid any hand
edit (#708 was one of those, found by Prima on 28-oct). Now each
migration is recorded in `schema_migrations` with the sha256 of its
file, and runs again only when the file changes: a change in the repo
still reaches the database, a restart no longer does.

A database that was already migrated before the registry existed is
not re-run on the first startup with this code: the names in
_BEFORE_REGISTRY are recorded as applied ("baseline", like Flyway's).
That list is closed on purpose: a migration added after #812 always
runs, baseline or not.
"""
import hashlib
import logging
import time
from pathlib import Path

import settings

log = logging.getLogger("ecodb.migrations")

MIGRATIONS: list[tuple[str, str]] = [
    ("3_0h_multimodal",   "sql/migrate_3_0h_multimodal.sql"),
    ("5.1.0_multitenant", "sql/migrate_5.0.1_to_5.1.0.sql"),
    ("5.1.1_clusters",    "sql/migrate_5.1.0_to_5.1.1.sql"),
    ("age_sync_triggers", "sql/trigger_age_sync.sql"),
    # --- Metacognicion ---
    ("5.2.0_foresight",      "sql/migrate_06_foresight.sql"),
    ("5.2.0_types_schema",   "sql/migrate_07a_types_schema.sql"),
    ("5.2.0_types_config",   "sql/migrate_07b_types_config.sql"),
    ("5.2.0_agents",         "sql/migrate_08_agents.sql"),
    ("5.2.0_metacognition",  "sql/migrate_09_metacognition.sql"),
    # --- Memory Agent v1.3 ---
    ("5.3.0_memory_agent",   "sql/migrate_5.2.0_to_5.3.0_memory_agent.sql"),
    ("5.3.0_memory_agent_seed", "sql/seed_memory_agent.sql"),
    # Level-specific higher-consolidation prompts (monthly/quarterly/yearly) + config rewire.
    ("5.3.0_higher_prompts", "sql/seed_higher_prompts.sql"),
    # v2: per-section word budgets + completeness check (v4-pro undershot
    # global targets — Eco's quarterly came out at 1/3 of the 2500-word floor).
    ("5.3.1_higher_prompts_v2", "sql/seed_higher_prompts_v2.sql"),
    # #478: nodos buscados y emparejados sin tildes (unaccent + f_unaccent inmutable + índice).
    ("5.4.0_unaccent_nodes", "sql/migrate_5.4.0_unaccent_nodes.sql"),
    # #569: columnas de revisión del mapeo de predicados (producción ya las tenía, sin migración).
    ("5.4.1_triple_review_columns", "sql/migrate_5.4.1_triple_review_columns.sql"),
    # #816: lo que gana embedding (célula, backfill, PUT) entra en memory_embeddings, que es lo que lee search.
    ("5.5.0_sync_text_embedding", "sql/migrate_5.5.0_sync_text_embedding.sql"),
]

# #812: the migrations that existed when the registry was introduced. Closed list:
# do NOT add new names here.
_BEFORE_REGISTRY = frozenset(name for name, _ in MIGRATIONS)

# #1332: claves de solo lectura. Va DESPUÉS de fijar _BEFORE_REGISTRY: es una migración nueva, se registra y corre.
MIGRATIONS.append(("5.6.0_api_keys_read_only", "sql/migrate_5.6.0_api_keys_read_only.sql"))

_REGISTRY = """CREATE TABLE IF NOT EXISTS schema_migrations (
    name       text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    baseline   boolean NOT NULL DEFAULT false
)"""
# A database is "already migrated" when the object created by the last migration of
# _BEFORE_REGISTRY exists (5.5.0 creates this function; a brand-new volume doesn't have it).
_ALREADY_MIGRATED = "SELECT to_regprocedure('public.sync_text_embedding()') IS NOT NULL"

_LOCK_KEY = 728_1990


def _sha(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


async def _record(conn, name: str, sha: str, baseline: bool = False) -> None:
    await conn.execute(
        """INSERT INTO schema_migrations (name, sha256, baseline) VALUES ($1, $2, $3)
           ON CONFLICT (name) DO UPDATE SET sha256 = EXCLUDED.sha256, applied_at = now(),
                                            baseline = EXCLUDED.baseline""",
        name, sha, baseline)


async def run_migrations(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", _LOCK_KEY, timeout=600)
        try:
            had_registry = await conn.fetchval("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
            await conn.execute(_REGISTRY)
            files = [(name, Path(path).read_text(encoding="utf-8")) for name, path in MIGRATIONS]
            if not had_registry and await conn.fetchval(_ALREADY_MIGRATED):
                for name, sql in files:
                    if name in _BEFORE_REGISTRY:
                        await _record(conn, name, _sha(sql), baseline=True)
                log.info("migrations: registry created over an already migrated database "
                         "(baseline of %d, nothing re-run)", len(_BEFORE_REGISTRY))
            applied = {r["name"]: r["sha256"]
                       for r in await conn.fetch("SELECT name, sha256 FROM schema_migrations")}
            for name, sql in files:
                sha = _sha(sql)
                if applied.get(name) == sha:
                    log.debug("migration already applied: %s", name)
                    continue
                t0 = time.monotonic()
                try:
                    await conn.execute(sql, timeout=300)
                except Exception:
                    log.error("migration FAILED: %s", name)
                    raise
                await _record(conn, name, sha)
                elapsed = (time.monotonic() - t0) * 1000
                log.info("migration %s: %s (%.0f ms)",
                         "CHANGED, re-applied" if name in applied else "OK", name, elapsed)
            log.info("schema at target %s", settings.SCHEMA_VERSION)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _LOCK_KEY)
