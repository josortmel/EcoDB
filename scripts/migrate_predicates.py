"""EcoDB Fase 3b.6 — Migración de predicados existentes al vocabulario canónico.

Lee todos los predicados únicos de la tabla triples, los mapea contra
predicates_canonical (exact → alias → embedding similarity), y actualiza
las tripletas con el predicado canónico.

Predicados que no mapean con confidence >= THRESHOLD van a pending_predicates.

Rollback: pg_dump snapshot antes de ejecutar. Abort si >25% no mapean.

Uso:
  docker exec ecodb-api python /tmp/migrate.py              # dry-run
  docker exec ecodb-api python /tmp/migrate.py --execute     # migración real
"""
import asyncio
import asyncpg
import httpx
import json
import os
import sys
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ecodb:ecodb_dev_pass@localhost:5432/ecodb")
EMBEDDINGS_URL = os.environ.get("EMBEDDINGS_URL", "http://embeddings:8090")
THRESHOLD = float(os.environ.get("MAPPER_THRESHOLD", "0.70"))
ABORT_OVERRIDE = "--force" in sys.argv  # Legacy migration override

# Group A: workflow artifact patterns → auto-archive
WORKFLOW_ARTIFACT_PATTERNS = [
    "propone_", "añade_", "tiene_bug", "tiene_deuda", "tiene_limitacion",
    "tiene_hipotesis", "tiene_competidor", "se_archivo_en", "fue_investigacion",
    "genero_hipotesis", "tiene_como_texto", "fue_diseñado_en_sesion",
    "requiere_fase", "pendiente_", "cerrado_en", "bloqueado_por",
    "resuelto_en", "deuda_", "workaround_", "versión_",
]

def is_workflow_artifact(predicate: str) -> bool:
    lex = predicate.strip().lower().replace(" ", "_")
    return any(lex.startswith(p) or p in lex for p in WORKFLOW_ARTIFACT_PATTERNS)


def normalize_lexical(predicate: str) -> str:
    return predicate.strip().lower().replace(" ", "_").replace("-", "_")


async def embed_text(client: httpx.AsyncClient, text: str) -> list[float] | None:
    try:
        r = await client.post(f"{EMBEDDINGS_URL}/embed/text", json={
            "texts": [text.replace("_", " ")],
            "task": "retrieval",
            "prompt_name": "query",
            "truncate_dim": 512,
        }, timeout=30.0)
        if r.status_code == 200:
            return r.json()["embeddings"][0]
    except Exception:
        pass
    return None


async def main():
    execute = "--execute" in sys.argv
    conn = await asyncpg.connect(DATABASE_URL)

    print(f"{'='*60}")
    print(f"EcoDB Predicate Migration {'DRY RUN' if not execute else 'EXECUTING'}")
    print(f"Threshold: {THRESHOLD}")
    print(f"{'='*60}")

    # Get all unique predicates from triples
    predicates = await conn.fetch(
        "SELECT predicate, count(*) as cnt FROM triples GROUP BY predicate ORDER BY count(*) DESC"
    )
    print(f"\nUnique predicates in triples: {len(predicates)}")

    # Load canonical predicates
    canonicals = await conn.fetch(
        "SELECT name FROM predicates_canonical WHERE state IN ('approved','experimental','candidate')"
    )
    canonical_set = {r["name"] for r in canonicals}
    print(f"Canonical predicates available: {len(canonical_set)}")

    # Load aliases
    aliases = await conn.fetch("SELECT alias, canonical, domain FROM predicate_aliases")
    alias_map = {}
    for a in aliases:
        alias_map[(a["alias"], a["domain"])] = a["canonical"]
        if a["domain"] is not None:
            alias_map.setdefault((a["alias"], None), a["canonical"])

    # Resolve each predicate
    results = {"exact": [], "alias": [], "embedding": [], "pending": [], "archived": []}
    embedding_client = httpx.AsyncClient()

    for row in predicates:
        pred = row["predicate"]
        cnt = row["cnt"]
        lexeme = normalize_lexical(pred)

        # Stage 1: exact match
        if lexeme in canonical_set:
            results["exact"].append((pred, lexeme, cnt, 1.0))
            continue

        # Stage 2: alias
        canonical_via_alias = alias_map.get((lexeme, None))
        if canonical_via_alias:
            results["alias"].append((pred, canonical_via_alias, cnt, 1.0))
            continue

        # Stage 3: embedding similarity
        vec = await embed_text(embedding_client, lexeme)
        if vec:
            best = await conn.fetchrow("""
                SELECT name, 1 - (embedding <=> $1::vector) AS similarity
                FROM predicates_canonical
                WHERE state IN ('approved','experimental','candidate')
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 1
            """, str(vec))
            if best and float(best["similarity"]) >= THRESHOLD:
                results["embedding"].append((pred, best["name"], cnt, float(best["similarity"])))
                continue

        if is_workflow_artifact(pred):
            results["archived"].append((pred, None, cnt, 0.0))
        else:
            results["pending"].append((pred, None, cnt, 0.0))

    await embedding_client.aclose()

    # Report
    total = len(predicates)
    mapped = len(results["exact"]) + len(results["alias"]) + len(results["embedding"])
    archived = len(results["archived"])
    pending = len(results["pending"])
    pct_unmapped = ((pending + archived) / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Exact match: {len(results['exact'])}")
    print(f"  Alias match: {len(results['alias'])}")
    print(f"  Embedding match (>={THRESHOLD}): {len(results['embedding'])}")
    print(f"  Archived (workflow artifacts): {archived}")
    print(f"  Pending (real, needs review): {pending}")
    print(f"  Total mapped to canonical: {mapped}/{total}")
    print(f"  Unmapped (archived+pending): {archived+pending} ({pct_unmapped:.1f}%)")

    if results["embedding"]:
        print(f"\n  Top embedding matches:")
        for orig, canon, cnt, conf in sorted(results["embedding"], key=lambda x: -x[3])[:20]:
            print(f"    '{orig}' → '{canon}' (conf={conf:.3f}, {cnt} triples)")

    if results["pending"]:
        print(f"\n  Pending (top 20 by usage):")
        for orig, _, cnt, _ in sorted(results["pending"], key=lambda x: -x[2])[:20]:
            print(f"    '{orig}' ({cnt} triples)")

    # Abort check (skip for legacy migration with --force)
    if pending > 0 and (pending / total * 100) > 25 and not ABORT_OVERRIDE:
        print(f"\n*** ABORT: {pending/total*100:.1f}% real pending > 25%. Use --force for legacy migration. ***")
        if execute:
            print("Migration NOT executed.")
            await conn.close()
            return
    elif ABORT_OVERRIDE:
        print(f"\n  --force: abort override for legacy migration (documented in orquestacion.md)")

    if execute:
        print(f"\n{'='*60}")
        print(f"EXECUTING MIGRATION...")
        print(f"{'='*60}")

        async with conn.transaction():
            updated = 0
            dupes_removed = 0
            # Update exact + alias + embedding matches
            for category in ["exact", "alias", "embedding"]:
                for orig, canon, cnt, conf in results[category]:
                    if orig == canon:
                        continue
                    # Remove would-be duplicates: triples that already have the canonical predicate
                    # for the same (subject_id, object_id) pair
                    removed = await conn.execute("""
                        DELETE FROM triples WHERE id IN (
                            SELECT t1.id FROM triples t1
                            WHERE t1.predicate = $2
                              AND EXISTS (
                                  SELECT 1 FROM triples t2
                                  WHERE t2.subject_id = t1.subject_id
                                    AND t2.object_id = t1.object_id
                                    AND t2.predicate = $1
                              )
                        )
                    """, canon, orig)
                    removed_count = int(removed.split()[-1]) if removed else 0
                    dupes_removed += removed_count
                    # Now safe to update
                    await conn.execute("""
                        UPDATE triples
                        SET predicate = $1,
                            original_predicate = CASE WHEN $2 != $1 THEN $2 ELSE original_predicate END,
                            mapper_confidence = $3
                        WHERE predicate = $2
                    """, canon, orig, conf)
                    updated += cnt

            # Insert pending predicates (real)
            for orig, _, cnt, _ in results["pending"]:
                await conn.execute("""
                    INSERT INTO pending_predicates (predicate, frequency, status)
                    VALUES ($1, $2, 'pending')
                    ON CONFLICT (predicate) DO UPDATE SET
                        frequency = pending_predicates.frequency + $2,
                        last_seen = now()
                """, normalize_lexical(orig), cnt)

            # Insert archived (workflow artifacts)
            for orig, _, cnt, _ in results["archived"]:
                await conn.execute("""
                    INSERT INTO pending_predicates (predicate, frequency, status)
                    VALUES ($1, $2, 'archived')
                    ON CONFLICT (predicate) DO UPDATE SET
                        frequency = pending_predicates.frequency + $2,
                        status = 'archived',
                        last_seen = now()
                """, normalize_lexical(orig), cnt)

        # Post-migration stats
        new_unique = await conn.fetchval("SELECT count(DISTINCT predicate) FROM triples")
        pending_count = await conn.fetchval("SELECT count(*) FROM pending_predicates WHERE status = 'pending'")
        outside = await conn.fetchval("""
            SELECT count(DISTINCT predicate) FROM triples
            WHERE predicate NOT IN (SELECT name FROM predicates_canonical WHERE state IN ('approved','deprecated'))
              AND predicate NOT IN (SELECT predicate FROM pending_predicates)
        """)

        print(f"\nPOST-MIGRATION:")
        print(f"  Duplicate triples removed before update: {dupes_removed}")
        print(f"  Unique predicates in triples: {new_unique} (was {total})")
        print(f"  Pending predicates: {pending_count}")
        print(f"  Outside canonical+pending (CE-3): {outside}")
        print(f"  CE-3 {'PASS' if outside == 0 else 'FAIL'}: {outside} outside")
        print(f"\nMigration completed: {datetime.now(timezone.utc).isoformat()}")
    else:
        print(f"\n--- DRY RUN: nothing changed. Run with --execute to migrate. ---")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
