#!/usr/bin/env python3
"""One-time: resolve all expected_descriptions to expected_ids via pure ANN.

Produces /tmp/queries_all_resolved.yaml with deterministic expected_ids
frozen at current DB state. Run inside ecodb-api container.
"""
import asyncio
import sys
import yaml
from pathlib import Path

import asyncpg
import httpx

DATABASE_URL = __import__("os").environ["DATABASE_URL"]
EMBEDDINGS_URL = __import__("os").environ.get("EMBEDDINGS_URL", "http://embeddings:8090")
INPUT_PATH = Path("/tmp/queries_all.yaml")
OUTPUT_PATH = Path("/tmp/queries_all_resolved.yaml")


async def embed_text(client: httpx.AsyncClient, text: str) -> str:
    r = await client.post(
        f"{EMBEDDINGS_URL}/embed/text",
        json={"texts": [text], "prompt_name": "query"},
        timeout=30.0,
    )
    r.raise_for_status()
    emb = r.json()["embeddings"][0]
    return "[" + ",".join(str(v) for v in emb) + "]"


async def ann_top1(conn, vec: str) -> str | None:
    rows = await conn.fetch(
        """
        SELECT bm.memory_id::text AS id
        FROM (
            SELECT DISTINCT ON (me.memory_id)
                me.memory_id,
                1 - (me.embedding <=> $1::vector) AS score
            FROM memory_embeddings me
            ORDER BY me.memory_id, me.embedding <=> $1::vector ASC
        ) bm
        JOIN memories m ON m.id = bm.memory_id
        WHERE (m.staleness IS NULL OR m.staleness NOT IN ('dormant', 'archived'))
        ORDER BY bm.score DESC
        LIMIT 1
        """,
        vec,
    )
    return rows[0]["id"] if rows else None


async def main():
    with open(INPUT_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    queries = data["queries"]

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    resolved_queries = []
    n_resolved = 0
    n_skipped = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with pool.acquire() as conn:
            for i, q in enumerate(queries, 1):
                q_out = dict(q)

                if q.get("expected_ids"):
                    # Already has IDs — keep as-is
                    resolved_queries.append(q_out)
                    n_skipped += 1
                    continue

                descs = q.get("expected_descriptions", [])
                if not descs:
                    q_out["expected_ids"] = []
                    resolved_queries.append(q_out)
                    n_skipped += 1
                    continue

                ids = []
                for desc in descs:
                    try:
                        vec = await embed_text(client, desc)
                        hit = await ann_top1(conn, vec)
                        if hit:
                            ids.append(hit)
                    except Exception as e:
                        print(f"  WARN [{i}] desc embed failed: {e}", file=sys.stderr)

                q_out["expected_ids"] = ids
                resolved_queries.append(q_out)
                n_resolved += 1
                print(f"  [{i:3d}/243] {q['query'][:50]:50s}  → {ids}")

    await pool.close()

    out_data = {"queries": resolved_queries}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        yaml.dump(out_data, f, allow_unicode=True, default_flow_style=False)

    print(f"\nDone. resolved={n_resolved} already_had_ids={n_skipped}")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
