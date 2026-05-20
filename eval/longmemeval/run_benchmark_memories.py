"""Run LongMemEval-S without Docling -- direct memory API.

Each session stored as one memory. GAMR searches memories directly.
"""
import json
import math
import os
import sys
import time
from collections import defaultdict

import httpx

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
API_KEY = os.environ.get("ECODB_API_KEY", "")
MAX_CONTENT = 16_000

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def headers():
    return {"Authorization": f"Bearer {API_KEY}"}


def load_config():
    path = os.path.join(DATA_DIR, "benchmark_config.json")
    with open(path) as f:
        return json.load(f)


def load_dataset():
    path = os.path.join(DATA_DIR, "longmemeval_s_cleaned.json")
    with open(path) as f:
        return json.load(f)


def load_sessions_as_memories(client: httpx.Client, dataset: list, workspace_id: int, project_id: int) -> dict:
    entry = dataset[0]
    sessions = entry["haystack_sessions"]
    session_ids = entry["haystack_session_ids"]

    mapping = {}
    truncated = 0
    for i, (sess, sid) in enumerate(zip(sessions, session_ids)):
        text = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in sess)
        if len(text) > MAX_CONTENT:
            truncated += 1
            print(f"  WARNING: session {sid} truncated ({len(text)} -> {MAX_CONTENT} chars)")
            text = text[:MAX_CONTENT]

        r = client.post(f"{API_URL}/memories", headers=headers(),
                         json={
                             "content": text,
                             "type": "tecnico",
                             "workspace_id": workspace_id,
                             "project_id": project_id,
                             "tags": [f"session:{sid}", "longmemeval"],
                         })
        r.raise_for_status()
        mem_id = r.json()["id"]
        mapping[mem_id] = sid
        if (i + 1) % 10 == 0:
            print(f"  Loaded {i+1}/{len(sessions)} sessions")

    if truncated:
        print(f"  {truncated} sessions truncated to {MAX_CONTENT} chars")
    print(f"Loaded {len(sessions)} sessions as memories")

    mapping_path = os.path.join(DATA_DIR, "memory_id_mapping.json")
    with open(mapping_path, "w") as f:
        json.dump(mapping, f, indent=2)
    return mapping


def search_ecodb(client: httpx.Client, query: str, workspace_id: int, limit: int = 50):
    r = client.post(f"{API_URL}/search", headers=headers(),
                     json={
                         "query_text": query,
                         "workspace_id": workspace_id,
                         "limit": limit,
                     })
    r.raise_for_status()
    return r.json()


def compute_metrics_at_k(retrieved_sessions, gold_sessions, k):
    top_k = retrieved_sessions[:k]
    gold_set = set(gold_sessions)
    found = set(top_k) & gold_set
    recall_any = 1.0 if found else 0.0
    recall_all = len(found) / len(gold_set) if gold_set else 0.0
    hits = [1 if sid in gold_set else 0 for sid in top_k]
    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold_set), k)))
    ndcg = dcg / ideal if ideal > 0 else 0.0
    return {"recall_any": recall_any, "recall_all": recall_all, "ndcg_any": ndcg}


def run_benchmark():
    if not API_KEY:
        print("ERROR: Set ECODB_API_KEY"); sys.exit(1)

    config = load_config()
    workspace_id = config["workspace_id"]
    project_id = config["project_id"]
    dataset = load_dataset()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "memory_results.jsonl")

    with httpx.Client(timeout=120) as client:
        mapping_path = os.path.join(DATA_DIR, "memory_id_mapping.json")
        if os.path.exists(mapping_path):
            with open(mapping_path) as f:
                memid_to_session = json.load(f)
            print(f"Using existing memory mapping ({len(memid_to_session)} entries)")
        else:
            print("Loading sessions as memories...")
            memid_to_session = load_sessions_as_memories(client, dataset, workspace_id, project_id)

        print(f"\nRunning LongMemEval-S ({len(dataset)} queries, memory mode)")
        metrics_accum = defaultdict(list)
        skipped = 0
        errors = 0

        with open(out_path, "w") as out_f:
            for i, entry in enumerate(dataset):
                qid = entry["question_id"]
                if "_abs" in qid:
                    skipped += 1
                    continue

                query = entry["question"]
                gold_sessions = entry["answer_session_ids"]

                try:
                    results = search_ecodb(client, query, workspace_id)
                except Exception as e:
                    print(f"  ERROR on {qid}: {e}")
                    errors += 1
                    continue

                retrieved_sessions = []
                seen = set()
                for item in results.get("results", []):
                    mem_id = item.get("id")
                    if mem_id and mem_id in memid_to_session:
                        sid = memid_to_session[mem_id]
                        if sid not in seen:
                            retrieved_sessions.append(sid)
                            seen.add(sid)

                entry_metrics = {}
                for k in [1, 3, 5, 10]:
                    m = compute_metrics_at_k(retrieved_sessions, gold_sessions, k)
                    for name, val in m.items():
                        key = f"session_{name}@{k}"
                        entry_metrics[key] = val
                        metrics_accum[key].append(val)

                result_entry = {
                    "question_id": qid,
                    "question_type": entry.get("question_type", ""),
                    "question": query,
                    "gold_session_ids": gold_sessions,
                    "retrieved_session_ids": retrieved_sessions[:10],
                    "metrics": entry_metrics,
                }
                json.dump(result_entry, out_f)
                out_f.write("\n")

                if (i + 1) % 50 == 0:
                    r5 = sum(metrics_accum.get("session_recall_all@5", [0])) / max(len(metrics_accum.get("session_recall_all@5", [])), 1)
                    print(f"  Progress: {i+1}/{len(dataset)} | Running R@5={r5:.4f}")

    print(f"\n{'='*60}")
    print(f"LongMemEval-S Results (Direct Memory, no Docling)")
    print(f"{'='*60}")
    evaluated = len(dataset) - skipped - errors
    print(f"Queries: {evaluated} evaluated, {skipped} skipped, {errors} errors")
    print()
    for key in sorted(metrics_accum.keys()):
        vals = metrics_accum[key]
        avg = sum(vals) / len(vals)
        print(f"  {key}: {avg:.4f}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    run_benchmark()
