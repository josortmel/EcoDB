#!/usr/bin/env python3
"""Pure ANN cosine similarity eval — no GAMR, no BM25, no composite scoring.

Embed query → ORDER BY cosine distance → compare vs expected.
Outputs R@5, R@10, MRR@5, MRR@10 in a single pass (fetches K=10, slices for @5).
Run inside ecodb-api container: python /tmp/pure_ann_eval.py
"""
import asyncio
import json
import os
import sys
import yaml
from pathlib import Path

import asyncpg
import httpx

DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDINGS_URL = os.environ.get("EMBEDDINGS_URL", "http://embeddings:8090")
QUERIES_PATH = Path("/tmp/queries_all_resolved.yaml")
K = 10  # fetch top-10; slice to 5 for @5 metrics


async def embed_text(client: httpx.AsyncClient, text: str) -> str:
    r = await client.post(
        f"{EMBEDDINGS_URL}/embed/text",
        json={"texts": [text], "prompt_name": "query"},
        timeout=30.0,
    )
    r.raise_for_status()
    emb = r.json()["embeddings"][0]
    return "[" + ",".join(str(v) for v in emb) + "]"


async def ann_search(conn, vec: str, limit: int = K) -> list[str]:
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
        LIMIT $2
        """,
        vec, limit,
    )
    return [r["id"] for r in rows]


def recall_at_k(expected: list, found: list, k: int) -> float:
    if not expected:
        return 1.0
    return len(set(expected) & set(found[:k])) / len(expected)


def mrr_at_k(expected: list, found: list, k: int) -> float:
    expected_set = set(expected)
    for i, fid in enumerate(found[:k]):
        if fid in expected_set:
            return 1.0 / (i + 1)
    return 0.0


async def main():
    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = yaml.safe_load(f)["queries"]

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with pool.acquire() as conn:
            for i, q in enumerate(queries, 1):
                query_text = q["query"]
                category = q.get("category", "unknown")
                expected_ids = [str(x) for x in q.get("expected_ids", [])]

                if not expected_ids and q.get("expected_descriptions"):
                    for desc in q["expected_descriptions"]:
                        try:
                            dvec = await embed_text(client, desc)
                            desc_results = await ann_search(conn, dvec, limit=1)
                            if desc_results:
                                expected_ids.append(desc_results[0])
                        except Exception as e:
                            print(f"  WARN: desc embed failed: {e}", file=sys.stderr)

                try:
                    qvec = await embed_text(client, query_text)
                    found = await ann_search(conn, qvec, limit=K)
                except Exception as e:
                    print(f"  ERROR [{i}] {query_text[:50]}: {e}", file=sys.stderr)
                    found = []

                r5 = recall_at_k(expected_ids, found, 5)
                r10 = recall_at_k(expected_ids, found, 10)
                mrr5 = mrr_at_k(expected_ids, found, 5)
                mrr10 = mrr_at_k(expected_ids, found, 10)

                print(
                    f"  [{i:3d}/{len(queries)}] {query_text[:46]:46s}"
                    f"  R@5={r5:.2f} R@10={r10:.2f}  MRR5={mrr5:.2f} MRR10={mrr10:.2f}"
                )
                results.append({
                    "query": query_text, "category": category,
                    "expected": expected_ids, "found": found,
                    "r5": r5, "r10": r10, "mrr5": mrr5, "mrr10": mrr10,
                })

    await pool.close()

    total = len(results)
    categories: dict = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "r5": 0.0, "r10": 0.0, "mrr5": 0.0, "mrr10": 0.0}
        categories[cat]["count"] += 1
        for k in ("r5", "r10", "mrr5", "mrr10"):
            categories[cat][k] += r[k]

    def avg(v, key):
        return v[key] / v["count"]

    print(f"\n=== PURE ANN (no GAMR) — {total} queries ===")
    print(f"{'':16s}  n    R@5    R@10   MRR@5  MRR@10")
    print(f"{'':16s}  --   -----  -----  -----  ------")
    for cat in sorted(categories):
        v = categories[cat]
        c = v["count"]
        print(f"  {cat:14s}  {c:3d}  {avg(v,'r5'):.3f}  {avg(v,'r10'):.3f}  {avg(v,'mrr5'):.3f}  {avg(v,'mrr10'):.3f}")

    ov_r5 = sum(r["r5"] for r in results) / total
    ov_r10 = sum(r["r10"] for r in results) / total
    ov_mrr5 = sum(r["mrr5"] for r in results) / total
    ov_mrr10 = sum(r["mrr10"] for r in results) / total
    print(f"\n  {'OVERALL':14s}  {total:3d}  {ov_r5:.3f}  {ov_r10:.3f}  {ov_mrr5:.3f}  {ov_mrr10:.3f}")

    output = {
        "tag": "pure-ann-243",
        "total": total,
        "overall": {"r5": round(ov_r5, 3), "r10": round(ov_r10, 3),
                    "mrr5": round(ov_mrr5, 3), "mrr10": round(ov_mrr10, 3)},
        "categories": {
            cat: {k: round(avg(v, k), 3) for k in ("r5", "r10", "mrr5", "mrr10")}
            for cat, v in categories.items()
        },
    }
    print("\n" + json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
