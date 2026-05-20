#!/usr/bin/env python3
"""GAMR search quality at K=5 and K=10 — single pass (fetches limit=10, slices for @5).

Run from host: python eval/gamr_k_eval.py
Requires: ECODB_EVAL_API_KEY or ECODB_API_KEY env var, API on http://localhost:8080
"""
import os
import sys
import json
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import yaml

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
QUERIES_PATH = Path(__file__).parent / "queries_all_resolved.yaml"


def get_auth_headers() -> dict:
    key = os.environ.get("ECODB_EVAL_API_KEY") or os.environ.get("ECODB_API_KEY", "")
    if not key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith(("ECODB_EVAL_API_KEY=", "ECODB_API_KEY=")):
                    key = line.split("=", 1)[1].strip().strip('"\'')
                    break
    return {"Authorization": f"Bearer {key}"} if key else {}


def search(client: httpx.Client, query: str, headers: dict, limit: int = 10) -> list[str]:
    for attempt in range(3):
        try:
            resp = client.post(
                f"{API_URL}/search",
                json={"query_text": query, "limit": limit},
                headers=headers,
                timeout=45.0,
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", data.get("items", []))
            ids = []
            for r in results[:limit]:
                rid = r.get("id") or r.get("memory_id") or r.get("document_id")
                if rid:
                    ids.append(str(rid))
            return ids
        except Exception as e:
            if attempt == 2:
                print(f"  ERROR '{query[:40]}': {e}", file=sys.stderr)
            else:
                time.sleep(1)
    return []


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


def main():
    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = yaml.safe_load(f)["queries"]

    headers = get_auth_headers()
    if not headers:
        print("WARNING: no API key — requests may fail auth", file=sys.stderr)

    print(f"Running {len(queries)} queries against {API_URL} (limit=10, single pass)...\n")

    results = []
    with httpx.Client() as client:
        for i, q in enumerate(queries, 1):
            query_text = q["query"]
            category = q.get("category", "unknown")
            expected = [str(x) for x in q.get("expected_ids", [])]

            if not expected and q.get("expected_descriptions"):
                for desc in q["expected_descriptions"]:
                    desc_found = search(client, desc, headers, limit=1)
                    if desc_found:
                        expected.append(desc_found[0])

            found10 = search(client, query_text, headers, limit=10)

            r5 = recall_at_k(expected, found10, 5)
            r10 = recall_at_k(expected, found10, 10)
            mrr5 = mrr_at_k(expected, found10, 5)
            mrr10 = mrr_at_k(expected, found10, 10)

            print(
                f"  [{i:2d}/{len(queries)}] {query_text[:48]:48s}"
                f"  R@5={r5:.2f} R@10={r10:.2f}  MRR@5={mrr5:.2f} MRR@10={mrr10:.2f}"
            )
            results.append({
                "query": query_text,
                "category": category,
                "expected": expected,
                "found": found10,
                "r5": r5, "r10": r10, "mrr5": mrr5, "mrr10": mrr10,
            })

    # Aggregate
    total = len(results)
    categories: dict = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "r5": 0.0, "r10": 0.0, "mrr5": 0.0, "mrr10": 0.0}
        categories[cat]["count"] += 1
        for k in ("r5", "r10", "mrr5", "mrr10"):
            categories[cat][k] += r[k]

    def avg(cat_data, key):
        return cat_data[key] / cat_data["count"]

    print(f"\n=== GAMR full pipeline — {total} queries ===")
    print(f"{'':16s}  n   R@5    R@10   MRR@5  MRR@10")
    print(f"{'':16s}  -   -----  -----  -----  ------")
    for cat in sorted(categories):
        v = categories[cat]
        c = v["count"]
        print(
            f"  {cat:14s}  {c:2d}  "
            f"{avg(v,'r5'):.3f}  {avg(v,'r10'):.3f}  "
            f"{avg(v,'mrr5'):.3f}  {avg(v,'mrr10'):.3f}"
        )

    overall_r5 = sum(r["r5"] for r in results) / total
    overall_r10 = sum(r["r10"] for r in results) / total
    overall_mrr5 = sum(r["mrr5"] for r in results) / total
    overall_mrr10 = sum(r["mrr10"] for r in results) / total
    print(f"\n  {'OVERALL':14s}  {total:2d}  {overall_r5:.3f}  {overall_r10:.3f}  {overall_mrr5:.3f}  {overall_mrr10:.3f}")

    output = {
        "tag": "gamr-full",
        "total": total,
        "overall": {"r5": round(overall_r5, 3), "r10": round(overall_r10, 3),
                    "mrr5": round(overall_mrr5, 3), "mrr10": round(overall_mrr10, 3)},
        "categories": {
            cat: {k: round(avg(v, k), 3) for k in ("r5", "r10", "mrr5", "mrr10")}
            for cat, v in categories.items()
        },
    }
    print("\n" + json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
