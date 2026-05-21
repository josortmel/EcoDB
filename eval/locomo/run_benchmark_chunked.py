"""LoCoMo benchmark on EcoDB -- chunked session ingestion variant.

Splits each session into 5-turn windows (overlap=1) before ingesting.
Uses limit=100 + session-level dedup to evaluate recall@K.
Reranker disabled (RERANKER_ENABLED=false) for retrieval baseline.

Usage:
    ECODB_API_KEY=<key> python eval/locomo/run_benchmark_chunked.py
"""
import functools
import json
import math
import os
import sys
import time
from collections import defaultdict

import httpx

# Reranker off — measuring retrieval, not ranking
os.environ["RERANKER_ENABLED"] = "false"

print = functools.partial(print, flush=True)

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
API_KEY = os.environ.get("ECODB_API_KEY", "")
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "locomo10.json")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

CAT_NAMES = {1: "single-hop", 2: "temporal", 3: "multi-hop", 4: "open-domain", 5: "adversarial"}

CHUNK_WINDOW = 5
CHUNK_OVERLAP = 1
SEARCH_LIMIT = 100


def headers():
    return {"Authorization": f"Bearer {API_KEY}"}


def create_workspace(client: httpx.Client, name: str) -> tuple[int, int]:
    """Create workspace + project, return (workspace_id, project_id)."""
    r = client.post(f"{API_URL}/workspaces", headers=headers(),
                     json={"name": name})
    r.raise_for_status()
    ws_id = r.json()["id"]

    r = client.post(f"{API_URL}/workspaces/{ws_id}/projects", headers=headers(),
                     json={"name": "benchmark"})
    r.raise_for_status()
    proj_id = r.json()["id"]
    return ws_id, proj_id


def load_conversation_sessions(client: httpx.Client, conv: dict,
                                ws_id: int, proj_id: int,
                                sample_id: str) -> dict:
    """Load all sessions as chunked memories (5-turn windows, overlap=1).

    Returns mapping: session_key -> [list of memory_ids for all chunks]
    """
    c = conv["conversation"]
    session_keys = sorted(
        [k for k in c if k.startswith("session_") and not k.endswith("_date_time")],
        key=lambda x: int(x.split("_")[1])
    )

    mapping = {}
    step = CHUNK_WINDOW - CHUNK_OVERLAP  # 4

    for sk in session_keys:
        turns = c[sk]
        date = c.get(f"{sk}_date_time", "")

        # Build chunks: window=5, step=4
        chunks = []
        i = 0
        while i < len(turns):
            window = turns[i:i + CHUNK_WINDOW]
            chunks.append(window)
            if i + CHUNK_WINDOW >= len(turns):
                break
            i += step

        n = len(chunks)
        mem_ids = []

        for chunk_i, window in enumerate(chunks):
            text = "\n".join(f"{t['speaker']}: {t['text']}" for t in window)
            tag_session = f"session:{sample_id}_{sk}"

            for attempt in range(5):
                r = client.post(f"{API_URL}/memories", headers=headers(),
                                 json={
                                     "content": text,
                                     "type": "tecnico",
                                     "workspace_id": ws_id,
                                     "project_id": proj_id,
                                     "tags": [tag_session, f"chunk:{chunk_i}", f"total_chunks:{n}", f"date:{date}"],
                                 })
                if r.status_code == 503:
                    wait = 2 ** attempt
                    print(f"    503 on {sk} chunk {chunk_i}, retry {attempt+1}/5 in {wait}s...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                break
            else:
                print(f"    FAILED: {sk} chunk {chunk_i} after 5 retries")
                continue

            mem_id = r.json()["id"]
            mem_ids.append(mem_id)
            time.sleep(0.3)

        if mem_ids:
            mapping[sk] = mem_ids
            print(f"    {sk}: {len(turns)} turns -> {n} chunks, {len(mem_ids)} memories ingested")

    return mapping


def evidence_to_sessions(evidence: list[str]) -> set[str]:
    """Convert evidence dialog IDs to session keys.

    'D1:3' -> 'session_1', 'D12:5' -> 'session_12'
    """
    sessions = set()
    for ev in evidence:
        parts = ev.split(":")
        if len(parts) >= 1:
            num = parts[0].replace("D", "")
            try:
                sessions.add(f"session_{int(num)}")
            except ValueError:
                pass
    return sessions


def search_and_evaluate(client: httpx.Client, conv: dict, ws_id: int,
                         session_mapping: dict, conv_id: str) -> list[dict]:
    """Run all QA pairs for a conversation and compute metrics.

    session_mapping: session_key -> [list of memory_ids]
    Deduplicates chunks back to session level before evaluating recall@K.
    """
    # Reverse map: any chunk memory_id -> session_key
    memid_to_session = {}
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
        seen = set()
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
    """Print aggregated metrics."""
    print(f"\n{'='*60}")
    print(f"LoCoMo Results -- {label}")
    print(f"{'='*60}")

    metrics_accum = defaultdict(list)
    by_category = defaultdict(lambda: defaultdict(list))

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
        cat_metrics = by_category[cat_name]
        r5 = cat_metrics.get("recall_any@5", [])
        if r5:
            print(f"  {cat_name}: R@5={sum(r5)/len(r5):.4f} ({len(r5)} queries)")


def main():
    if not API_KEY:
        print("ERROR: Set ECODB_API_KEY")
        sys.exit(1)

    print(f"Loading LoCoMo dataset from {DATA_PATH}")
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} conversations, {sum(len(c['qa']) for c in data)} QA pairs")
    print(f"Chunking: window={CHUNK_WINDOW}, overlap={CHUNK_OVERLAP}, search_limit={SEARCH_LIMIT}, reranker=OFF")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "locomo_chunked_results.jsonl")

    all_results = []

    with httpx.Client(timeout=300) as client, open(out_path, "w") as out_f:
        for conv_idx, conv in enumerate(data):
            sample_id = conv["sample_id"]
            c = conv["conversation"]
            session_keys = [k for k in c if k.startswith("session_") and not k.endswith("_date_time")]
            qa_count = len(conv["qa"])

            print(f"\n--- Conversation {conv_idx+1}/10: {sample_id} ({len(session_keys)} sessions, {qa_count} QA) ---")

            ws_name = f"locomo-chunked-{sample_id}"
            ws_id, proj_id = create_workspace(client, ws_name)
            print(f"  Workspace: {ws_id}, Project: {proj_id}")

            print(f"  Loading {len(session_keys)} sessions (chunked)...")
            session_mapping = load_conversation_sessions(client, conv, ws_id, proj_id, sample_id)
            total_chunks = sum(len(v) for v in session_mapping.values())
            print(f"  Loaded {len(session_mapping)}/{len(session_keys)} sessions ({total_chunks} total chunks)")

            if len(session_mapping) == 0:
                print(f"  SKIPPING -- no sessions loaded")
                continue

            print(f"  Running {qa_count} queries...")
            conv_results = search_and_evaluate(client, conv, ws_id, session_mapping, sample_id)

            r5_vals = [r["metrics"].get("recall_any@5", 0) for r in conv_results if r["metrics"]]
            r5_avg = sum(r5_vals) / len(r5_vals) if r5_vals else 0
            print(f"  {sample_id} R@5={r5_avg:.4f} ({len(conv_results)} queries evaluated)")

            for r in conv_results:
                r["sample_id"] = sample_id
                json.dump(r, out_f, ensure_ascii=False)
                out_f.write("\n")

            all_results.extend(conv_results)

    print_metrics(all_results, "EcoDB GAMR chunked (5-turn windows, overlap=1, session dedup)")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
