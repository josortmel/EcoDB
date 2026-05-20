"""Generate co-occurrence triples from memory_entity_links.

For each pair of entities that co-occur in >= THRESHOLD memories,
creates a 'related_to' triple with weight = co-occurrence count.
Dual write: SQL triples table + AGE graph.

Idempotent: ON CONFLICT DO NOTHING on triples.
Safe: only creates 'related_to' edges, does not modify existing triples.

Run inside ecodb-api container:
    python /app/scripts/generate_cooccurrence_triples.py [--threshold 2] [--dry-run]
"""
import argparse
import asyncio
import json
import os
import time

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ecodb:ecodb_dev_pass@postgres:5432/ecodb")
GRAPH_NAME = "ecodb_graph"
PREDICATE = "related_to"
AUTHOR = "system:cooccurrence"


async def main(threshold: int = 2, dry_run: bool = False):
    conn = await asyncpg.connect(DATABASE_URL)

    triples_before = await conn.fetchval("SELECT count(*) FROM triples")
    cooc_before = await conn.fetchval(
        "SELECT count(*) FROM triples WHERE predicate = $1", PREDICATE
    )
    print(f"BEFORE: {triples_before} triples total, {cooc_before} related_to")

    pairs = await conn.fetch("""
        SELECT mel1.entity_node_id AS entity_a,
               mel2.entity_node_id AS entity_b,
               count(*) AS co_count
        FROM memory_entity_links mel1
        JOIN memory_entity_links mel2
            ON mel1.memory_id = mel2.memory_id
            AND mel1.entity_node_id < mel2.entity_node_id
        JOIN nodes n1 ON n1.id = mel1.entity_node_id AND n1.status = 'active'
        JOIN nodes n2 ON n2.id = mel2.entity_node_id AND n2.status = 'active'
        GROUP BY mel1.entity_node_id, mel2.entity_node_id
        HAVING count(*) >= $1
        ORDER BY co_count DESC
    """, threshold)

    print(f"Co-occurring pairs (>={threshold} memories): {len(pairs)}")

    if dry_run:
        for p in pairs[:20]:
            a = await conn.fetchval("SELECT name FROM nodes WHERE id = $1", p["entity_a"])
            b = await conn.fetchval("SELECT name FROM nodes WHERE id = $1", p["entity_b"])
            print(f"  {a} ↔ {b}: {p['co_count']} memories")
        if len(pairs) > 20:
            print(f"  ... and {len(pairs) - 20} more")
        await conn.close()
        return

    start = time.time()
    created = 0
    skipped = 0
    age_errors = 0

    for p in pairs:
        tr = conn.transaction()
        await tr.start()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO triples (subject_id, predicate, object_id, author)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (subject_id, predicate, object_id) DO NOTHING
                RETURNING id
                """,
                p["entity_a"], PREDICATE, p["entity_b"], AUTHOR,
            )
            if row is None:
                await tr.rollback()
                skipped += 1
                continue

            params = json.dumps({
                "sid": p["entity_a"],
                "oid": p["entity_b"],
                "pred": PREDICATE,
            })
            await conn.execute(
                f"""
                SELECT * FROM cypher('{GRAPH_NAME}', $$
                    MATCH (s:Entity {{sql_id: $sid}}), (o:Entity {{sql_id: $oid}})
                    CREATE (s)-[r:RELATES_TO {{predicate: $pred}}]->(o)
                    RETURN id(r)
                $$, $1::agtype) AS (edge_id agtype)
                """,
                params,
            )
            await tr.commit()
            created += 1
        except Exception as e:
            await tr.rollback()
            age_errors += 1
            if age_errors <= 5:
                print(f"  AGE error (rolled back SQL+AGE): {e}")

        created += 1

    elapsed = time.time() - start

    triples_after = await conn.fetchval("SELECT count(*) FROM triples")
    cooc_after = await conn.fetchval(
        "SELECT count(*) FROM triples WHERE predicate = $1", PREDICATE
    )

    print(f"\nDone in {elapsed:.1f}s")
    print(f"Created: {created}, Skipped (existing): {skipped}, AGE errors: {age_errors}")
    print(f"AFTER: {triples_after} triples total, {cooc_after} related_to")

    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(threshold=args.threshold, dry_run=args.dry_run))
