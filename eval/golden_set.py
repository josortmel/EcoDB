#!/usr/bin/env python3
"""Golden set evaluation for EcoDB GAMR search quality."""
import argparse
import os
import sys
import io
import json
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import yaml

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
QUERIES_PATH = Path(__file__).parent / "queries.yaml"
K = 5

def load_queries(path: Path) -> list[dict]:
    """Load and validate queries.yaml."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    queries = data.get("queries", [])
    if not queries:
        print("ERROR: No queries found in", path)
        sys.exit(1)
    return queries

def get_auth_headers() -> dict:
    """Get auth headers. Try ECODB_EVAL_API_KEY env var first, then .env file."""
    key = os.environ.get("ECODB_EVAL_API_KEY")
    if not key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ECODB_EVAL_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"')
                    break
    if not key:
        # Try getting a JWT token via bootstrap key
        key = os.environ.get("ECODB_API_KEY")
    if not key:
        print("WARNING: No API key found. Set ECODB_EVAL_API_KEY env var.")
        return {}
    return {"Authorization": f"Bearer {key}"}

def search(client: httpx.Client, query: str, headers: dict) -> list[str]:
    """Execute search and return list of result IDs (top K)."""
    for attempt in range(3):
        try:
            resp = client.post(
                f"{API_URL}/search",
                json={"query_text": query, "limit": K, "include_documents": True},
                headers=headers,
                timeout=30.0,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", data.get("items", []))
            ids = []
            for r in results[:K]:
                rid = r.get("id") or r.get("memory_id") or r.get("document_id")
                if rid:
                    ids.append(str(rid))
            return ids
        except Exception as e:
            print(f"  ERROR searching '{query[:50]}': {e}")
            return []
    print(f"  ERROR searching '{query[:50]}': rate limited after 3 retries")
    return []

def recall_at_k(expected: list[str], found: list[str]) -> float:
    if not expected:
        return 1.0
    return len(set(expected) & set(found)) / len(expected)

def reciprocal_rank(expected: list[str], found: list[str]) -> float:
    expected_set = set(expected)
    for i, fid in enumerate(found):
        if fid in expected_set:
            return 1.0 / (i + 1)
    return 0.0

def get_feature_flags() -> dict:
    """Read current feature flag values."""
    flags = {}
    for name in ["ENABLE_BM25", "ENABLE_AUTO_LINK", "ENABLE_WEIGHT_DYNAMIC",
                  "ENABLE_TRUST_TIERS", "ENABLE_STOP_ENTITIES_DYNAMIC", "ENABLE_TENSION_DETECTION"]:
        flags[name] = os.environ.get(name, "false").lower() in ("true", "1", "yes")
    return flags

def generate_report(results: list[dict], tag: str) -> str:
    """Generate markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    mean_recall = sum(r["recall"] for r in results) / total if total else 0
    mean_mrr = sum(r["rr"] for r in results) / total if total else 0

    # Per category
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "recall_sum": 0, "rr_sum": 0}
        categories[cat]["count"] += 1
        categories[cat]["recall_sum"] += r["recall"]
        categories[cat]["rr_sum"] += r["rr"]

    flags = get_feature_flags()

    lines = [
        f"# Golden Set Evaluation — {tag} — {now}\n",
        "## Summary\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Queries | {total} |",
        f"| Mean Recall@{K} | {mean_recall:.3f} |",
        f"| MRR | {mean_mrr:.3f} |",
        "",
        "## Per Category\n",
        "| Category | Count | Recall@5 | MRR |",
        "|----------|-------|----------|-----|",
    ]
    for cat, vals in sorted(categories.items()):
        c = vals["count"]
        lines.append(f"| {cat} | {c} | {vals['recall_sum']/c:.3f} | {vals['rr_sum']/c:.3f} |")

    lines += ["", "## Feature Flags\n", "| Flag | Value |", "|------|-------|"]
    for name, val in sorted(flags.items()):
        lines.append(f"| {name} | {val} |")

    lines += [
        "", "## Per Query Detail\n",
        f"| # | Query | Category | Recall@{K} | RR | Expected | Found | Missing |",
        "|---|-------|----------|----------|----|----------|-------|---------|",
    ]
    for i, r in enumerate(results, 1):
        missing = set(r["expected"]) - set(r["found"])
        lines.append(
            f"| {i} | {r['query'][:40]} | {r['category']} | {r['recall']:.2f} | "
            f"{r['rr']:.2f} | {len(r['expected'])} | "
            f"{len(set(r['expected']) & set(r['found']))} | {len(missing)} |"
        )

    return "\n".join(lines) + "\n"

def compare_reports(file1: str, file2: str):
    """Compare two report files and print deltas."""
    def parse_summary(path):
        metrics = {}
        with open(path) as f:
            in_summary = False
            for line in f:
                if "## Summary" in line:
                    in_summary = True
                    continue
                if in_summary and line.startswith("|") and "Metric" not in line and "---" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) == 2:
                        try:
                            metrics[parts[0]] = float(parts[1])
                        except ValueError:
                            metrics[parts[0]] = parts[1]
                if in_summary and line.startswith("##") and "Summary" not in line:
                    break
        return metrics

    m1 = parse_summary(file1)
    m2 = parse_summary(file2)

    print(f"\nComparison: {file1} → {file2}\n")
    for key in ["Mean Recall@5", "MRR"]:
        v1 = m1.get(key, 0)
        v2 = m2.get(key, 0)
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            delta = v2 - v1
            symbol = "+" if delta >= 0 else ""
            marker = "ok" if delta >= 0 else "REGRESSION"
            print(f"  {key}: {v1:.3f} -> {v2:.3f} ({symbol}{delta:.3f}) {marker}")

def main():
    parser = argparse.ArgumentParser(description="EcoDB Golden Set Evaluation")
    parser.add_argument("--output", help="Save report to file")
    parser.add_argument("--tag", default="baseline", help="Tag for this run")
    parser.add_argument("--compare", nargs=2, metavar=("FILE1", "FILE2"), help="Compare two reports")
    parser.add_argument("--queries", default=str(QUERIES_PATH), help="Path to queries YAML")
    args = parser.parse_args()

    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    queries = load_queries(Path(args.queries))
    headers = get_auth_headers()

    print(f"Running {len(queries)} queries against {API_URL}...")
    results = []

    with httpx.Client() as client:
        for i, q in enumerate(queries, 1):
            query_text = q["query"]
            expected = [str(x) for x in q.get("expected_ids", [])]
            if not expected and q.get("expected_descriptions"):
                for desc in q["expected_descriptions"]:
                    desc_results = search(client, desc, headers)
                    if desc_results:
                        expected.append(desc_results[0])  # take top-1 match
            category = q.get("category", "unknown")

            found = search(client, query_text, headers)
            rec = recall_at_k(expected, found)
            rr = reciprocal_rank(expected, found)

            print(f"  [{i}/{len(queries)}] {query_text[:50]:50s} R@5={rec:.2f} RR={rr:.2f}")
            results.append({
                "query": query_text,
                "category": category,
                "expected": expected,
                "found": found,
                "recall": rec,
                "rr": rr,
            })

    report = generate_report(results, args.tag)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + report)

if __name__ == "__main__":
    main()
