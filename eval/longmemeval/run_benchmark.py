"""Run LongMemEval-S benchmark against EcoDB GAMR search (Docling pipeline).

Tests the FULL pipeline: Docling ingestion -> chunking -> NER -> embedding -> GAMR search.
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


def load_doc_mapping():
    path = os.path.join(DATA_DIR, "doc_id_mapping.json")
    with open(path) as f:
        return json.load(f)


def build_docid_to_session(dataset, doc_mapping):
    entry = dataset[0]
    session_ids = entry["haystack_session_ids"]
    mapping = {}
    for i, sid in enumerate(session_ids):
        filename = f"session_{i:03d}.md"
        for dm in doc_mapping:
            if dm["filename"] == filename:
                mapping[dm["doc_id"]] = sid
                break
    return mapping


def search_ecodb(client: httpx.Client, query: str, workspace_id: int, limit: int = 50):
    r = client.post(f"{API_URL}/search", headers=headers(),
                     json={
                         "query_text": query,
                         "workspace_id": workspace_id,
                         "limit": limit,
                         "include_documents": True,
                         "max_document_results": 20,
                     })
    r.raise_for_status()
    return r.json()


def compute_metrics_at_k(retrieved_sessions: list, gold_sessions: list, k: int) -> dict:
    top_k = retrieved_sessions[:k]
    gold_set = set(gold_sessions)

    hits = [1 if sid in gold_set else 0 for sid in top_k]
    found = set(top_k) & gold_set

    recall_any = 1.0 if found else 0.0
    recall_all = len(found) / len(gold_set) if gold_set else 0.0

    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold_set), k)))
    ndcg = dcg / ideal if ideal > 0 else 0.0

    return {"recall_any": recall_any, "recall_all": recall_all, "ndcg_any": ndcg}


def run_benchmark():
    if not API_KEY:
        print("ERROR: Set ECODB_API_KEY"); sys.exit(1)

    config = load_config()
    workspace_id = config["workspace_id"]
    dataset = load_dataset()
    doc_mapping = load_doc_mapping()
    docid_to_session = build_docid_to_session(dataset, doc_mapping)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "docling_results.jsonl")

    print(f"Running LongMemEval-S benchmark ({len(dataset)} queries)")
    print(f"Workspace: {workspace_id}, API: {API_URL}")
    print(f"Mode: Docling pipeline (document search)")

    metrics_accum = defaultdict(list)
    skipped = 0
    errors = 0

    with httpx.Client(timeout=120) as client, open(out_path, "w") as out_f:
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
                doc_id = item.get("document_id")
                if doc_id and doc_id in docid_to_session:
                    sid = docid_to_session[doc_id]
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
    print(f"LongMemEval-S Results (Docling pipeline)")
    print(f"{'='*60}")
    evaluated = len(dataset) - skipped - errors
    print(f"Queries: {evaluated} evaluated, {skipped} abstention skipped, {errors} errors")
    print()
    for key in sorted(metrics_accum.keys()):
        vals = metrics_accum[key]
        avg = sum(vals) / len(vals)
        print(f"  {key}: {avg:.4f}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    run_benchmark()
