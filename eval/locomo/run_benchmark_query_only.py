"""LoCoMo query-only benchmark — no re-ingestion.

Discovers existing locomo-chunked-* workspaces, reconstructs session mapping
from memory tags, then runs search_and_evaluate with a configurable K.

Usage:
    ECODB_API_KEY=<key> SEARCH_LIMIT=5  python eval/locomo/run_benchmark_query_only.py
    ECODB_API_KEY=<key> SEARCH_LIMIT=25 python eval/locomo/run_benchmark_query_only.py
"""
import functools
import json
import math
import os
import sys
import time
from collections import defaultdict

import httpx

os.environ["RERANKER_ENABLED"] = "false"

print = functools.partial(print, flush=True)

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
API_KEY = os.environ.get("ECODB_API_KEY", "")
SEARCH_LIMIT = int(os.environ.get("SEARCH_LIMIT", "5"))
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "locomo10.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

CAT_NAMES = {1: "single-hop", 2: "temporal", 3: "multi-hop", 4: "open-domain", 5: "adversarial"}


def headers():
    return {"Authorization": f"Bearer {API_KEY}"}


def discover_workspaces(client: httpx.Client) -> dict[str, tuple[int, int]]:
    """Return {sample_id: (workspace_id, project_id)} for all locomo-chunked-* workspaces."""
    r = client.get(f"{API_URL}/workspaces", headers=headers(), params={"limit": 200})
    r.raise_for_status()
    result = {}
    for ws in r.json().get("items", []):
        name = ws["name"]
        if not name.startswith("locomo-chunked-"):
            continue
        sample_id = name[len("locomo-chunked-"):]
        ws_id = ws["id"]

        rp = client.get(f"{API_URL}/workspaces/{ws_id}/projects", headers=headers())
        rp.raise_for_status()
        projects = rp.json().get("items", [])
        bench = next((p for p in projects if p["name"] == "benchmark"), None)
        if bench is None and projects:
            bench = projects[0]
        if bench:
            result[sample_id] = (ws_id, bench["id"])
            print(f"  Found: {name} → ws={ws_id} proj={bench['id']}")
    return result


def reconstruct_session_mapping(client: httpx.Client, ws_id: int,
                                 sample_id: str) -> dict[str, list[str]]:
    """Fetch all memories in workspace and rebuild session_key -> [mem_ids] from tags."""
    mapping: dict[str, list[str]] = defaultdict(list)
    prefix = f"session:{sample_id}_"

    offset = 0
    while True:
        r = client.get(f"{API_URL}/memories/recent", headers=headers(), params={
            "workspace_id": ws_id, "limit": 200, "expand_scope": "true"
        })
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            break
        for m in items:
            for tag in (m.get("tags") or []):
                if tag.startswith(prefix):
                    sk = tag[len(prefix):]  # e.g. "session_1"
                    mapping[sk].append(m["id"])
                    break
        if len(items) < 200:
            break
        offset += 200

    return dict(mapping)


def evidence_to_sessions(evidence: list[str]) -> set[str]:
    sessions = set()
    for ev in evidence:
        parts = ev.split(":")
        if parts:
            num = parts[0].replace("D", "")
            try:
                sessions.add(f"session_{int(num)}")
            except ValueError:
                pass
    return sessions


def search_and_evaluate(client: httpx.Client, conv: dict, ws_id: int,
                         session_mapping: dict, conv_id: str) -> list[dict]:
    """Run all QA pairs and compute session-level recall@K with dedup."""
    memid_to_session: dict[str, str] = {}
    for sk, mem_ids in session_mapping.items():
        for mid in mem_ids:
            memid_to_session[mid] = sk

    total_queries = sum(1 for q in conv["qa"] if q.get("evidence"))
    query_num = 0
    results = []

    for q in conv["qa"]:
        evidence = q.get("evidence", [])
        gold_sessions = evidence_to_sessions(evidence)
        if not gold_sessions:
            continue

        query_num += 1
        query = q["question"]

        try:
            r = client.post(f"{API_URL}/search", headers=headers(),
                             json={
                                 "query_text": query,
                                 "workspace_id": ws_id,
                                 "limit": SEARCH_LIMIT,
                                 "include_documents": False,
                             })
            r.raise_for_status()
            search_results = r.json()
        except Exception as e:
            results.append({"question": query, "category": q.get("category", 0),
                            "error": str(e), "metrics": {}})
            continue

        # Dedup: walk ranked chunks, keep first occurrence per session
        retrieved_sessions = []
        seen: set[str] = set()
        for item in search_results.get("results", []):
            mem_id = item.get("id")
            if mem_id and mem_id in memid_to_session:
                sk = memid_to_session[mem_id]
                if sk not in seen:
                    retrieved_sessions.append(sk)
                    seen.add(sk)

        entry_metrics = {}
        for k in [1, 3, 5, 10]:
            top_k = retrieved_sessions[:k]
            found = set(top_k) & gold_sessions
            recall_any = 1.0 if found else 0.0
            recall_all = len(found) / len(gold_sessions) if gold_sessions else 0.0

            hits = [1 if s in gold_sessions else 0 for s in top_k]
            dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
            ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold_sessions), k)))
            ndcg = dcg / ideal if ideal > 0 else 0.0

            entry_metrics[f"recall_any@{k}"] = recall_any
            entry_metrics[f"recall_all@{k}"] = recall_all
            entry_metrics[f"ndcg@{k}"] = ndcg

        r1 = entry_metrics.get("recall_any@1", 0)
        r5 = entry_metrics.get("recall_any@5", 0)
        r10 = entry_metrics.get("recall_any@10", 0)
        print(f"  [{conv_id}] Query {query_num}/{total_queries}: R@1={r1:.0f} R@5={r5:.0f} R@10={r10:.0f}")

        results.append({
            "question": query,
            "category": q.get("category", 0),
            "category_name": CAT_NAMES.get(q.get("category", 0), "unknown"),
            "gold_sessions": sorted(gold_sessions),
            "retrieved_sessions": retrieved_sessions[:10],
            "metrics": entry_metrics,
        })

    return results


def print_metrics(all_results: list[dict], label: str):
    print(f"\n{'='*60}")
    print(f"LoCoMo Results -- {label}")
    print(f"{'='*60}")

    metrics_accum: dict[str, list] = defaultdict(list)
    by_category: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in all_results:
        if "error" in r or not r["metrics"]:
            continue
        for key, val in r["metrics"].items():
            metrics_accum[key].append(val)
            by_category[r["category_name"]][key].append(val)

    print(f"\nOverall ({len(metrics_accum.get('recall_any@5', []))} queries):")
    for key in sorted(metrics_accum.keys()):
        vals = metrics_accum[key]
        print(f"  {key}: {sum(vals)/len(vals):.4f}")

    print(f"\nBy category:")
    for cat_name in ["single-hop", "temporal", "multi-hop", "open-domain", "adversarial"]:
        if cat_name not in by_category:
            continue
        r5 = by_category[cat_name].get("recall_any@5", [])
        if r5:
            print(f"  {cat_name}: R@5={sum(r5)/len(r5):.4f} ({len(r5)} queries)")


def main():
    if not API_KEY:
        print("ERROR: Set ECODB_API_KEY")
        sys.exit(1)

    print(f"Loading LoCoMo dataset from {DATA_PATH}")
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    conv_by_id = {c["sample_id"]: c for c in data}
    print(f"Loaded {len(data)} conversations")
    print(f"Mode: query-only, SEARCH_LIMIT={SEARCH_LIMIT}, reranker=OFF")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"locomo_chunked_k{SEARCH_LIMIT}_results.jsonl")

    all_results = []

    with httpx.Client(timeout=300) as client:
        print("\nDiscovering locomo-chunked-* workspaces...")
        ws_map = discover_workspaces(client)

        if not ws_map:
            print("ERROR: No locomo-chunked-* workspaces found. Run run_benchmark_chunked.py first.")
            sys.exit(1)

        print(f"Found {len(ws_map)} workspaces\n")

        with open(out_path, "w") as out_f:
            for conv_idx, (sample_id, (ws_id, proj_id)) in enumerate(sorted(ws_map.items())):
                conv = conv_by_id.get(sample_id)
                if conv is None:
                    print(f"WARNING: No conv data for {sample_id}, skipping")
                    continue

                qa_count = len(conv["qa"])
                print(f"--- Conversation {conv_idx+1}/{len(ws_map)}: {sample_id} (ws={ws_id}, {qa_count} QA) ---")

                print(f"  Reconstructing session mapping from tags...")
                session_mapping = reconstruct_session_mapping(client, ws_id, sample_id)
                total_chunks = sum(len(v) for v in session_mapping.values())
                print(f"  {len(session_mapping)} sessions, {total_chunks} chunks")

                if not session_mapping:
                    print(f"  SKIPPING — no sessions found in workspace")
                    continue

                conv_results = search_and_evaluate(client, conv, ws_id, session_mapping, sample_id)

                r5_vals = [r["metrics"].get("recall_any@5", 0) for r in conv_results if r["metrics"]]
                r5_avg = sum(r5_vals) / len(r5_vals) if r5_vals else 0
                print(f"  {sample_id} R@5={r5_avg:.4f} ({len(conv_results)} queries)\n")

                for r in conv_results:
                    r["sample_id"] = sample_id
                    json.dump(r, out_f, ensure_ascii=False)
                    out_f.write("\n")

                all_results.extend(conv_results)

    print_metrics(all_results, f"EcoDB GAMR chunked query-only K={SEARCH_LIMIT}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
