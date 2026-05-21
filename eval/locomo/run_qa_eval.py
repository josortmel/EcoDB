"""LoCoMo QA evaluation -- phase 2.

Reads retrieval results from phase 1, generates answers with Haiku,
evaluates correctness with Sonnet judge. Computes QA F1 per category.

Usage:
    python eval/locomo/run_qa_eval.py
"""
import functools
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict

print = functools.partial(print, flush=True)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "locomo10.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results", "locomo_results.jsonl")
OUT_PATH = os.path.join(os.path.dirname(__file__), "results", "locomo_qa_results.jsonl")

ANSWERER_MODEL = "claude-sonnet-4-6"
JUDGE_MODEL = "claude-sonnet-4-6"
MAX_QUERIES = int(os.environ.get("MAX_QUERIES", "0"))  # 0 = unlimited

CAT_NAMES = {1: "single-hop", 2: "temporal", 3: "multi-hop", 4: "open-domain", 5: "adversarial"}


def run_claude(prompt: str, model: str, timeout: int = 120) -> str:
    """Call `claude -p --model <model>` with prompt on stdin. Returns stdout text."""
    try:
        result = subprocess.run(
            [os.environ.get("CLAUDE_CMD", "claude"), "-p", "--model", model],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"claude exited {result.returncode}: {err}")
        return result.stdout.decode("utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude -p timed out after {timeout}s")


def load_dataset() -> dict:
    """Load locomo10.json. Returns {sample_id: conv_entry}."""
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {entry["sample_id"]: entry for entry in data}


def load_retrieval_results() -> dict:
    """Load locomo_results.jsonl. Returns {(sample_id, question): retrieved_sessions}."""
    if not os.path.exists(RESULTS_PATH):
        print(f"ERROR: {RESULTS_PATH} not found. Run run_benchmark.py first.")
        sys.exit(1)
    mapping = {}
    with open(RESULTS_PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            key = (r["sample_id"], r["question"])
            mapping[key] = r.get("retrieved_sessions", [])
    return mapping


def get_session_texts(conv_entry: dict, session_keys: list[str]) -> str:
    """Build context string from session keys for the given conversation."""
    c = conv_entry["conversation"]
    parts = []
    for sk in session_keys:
        if sk not in c:
            continue
        turns = c[sk]
        date = c.get(f"{sk}_date_time", "")
        header = f"[{sk}" + (f", {date}" if date else "") + "]"
        text = "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def judge_answer(gold: str, hypothesis: str) -> int:
    """Ask Sonnet to judge if hypothesis matches gold. Returns 0 or 1."""
    judge_prompt = (
        f"Gold answer: {gold}\n"
        f"Predicted answer: {hypothesis}\n\n"
        "Is the predicted answer correct? Consider partial matches as correct "
        "if the key information is present.\n"
        'Reply with ONLY a JSON object: {"score": 0} or {"score": 1}'
    )
    try:
        response = run_claude(judge_prompt, JUDGE_MODEL)
        # Find JSON in response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(response[start:end])
            return int(parsed.get("score", 0))
    except Exception as e:
        print(f"    Judge parse error: {e} | response: {response[:100]}")
    return 0


def main():
    print(f"Loading dataset from {DATA_PATH}")
    dataset = load_dataset()
    print(f"Loaded {len(dataset)} conversations")

    print(f"Loading retrieval results from {RESULTS_PATH}")
    retrieval = load_retrieval_results()
    print(f"Loaded {len(retrieval)} retrieval entries")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    scores_accum = defaultdict(list)
    total_evaluated = 0
    total_errors = 0
    total_done = 0

    with open(OUT_PATH, "w", encoding="utf-8") as out_f:
        for sample_id, conv_entry in sorted(dataset.items()):
            qa_pairs = conv_entry.get("qa", [])
            print(f"\n--- {sample_id} ({len(qa_pairs)} QA pairs) ---")
            conv_scores = []

            for qi, q in enumerate(qa_pairs):
                if MAX_QUERIES > 0 and total_done >= MAX_QUERIES:
                    break
                question = q["question"]
                gold_answer = q.get("answer", "")
                category = q.get("category", 0)
                evidence = q.get("evidence", [])

                if not evidence or not gold_answer:
                    continue

                retrieved_sessions = retrieval.get((sample_id, question), [])

                if not retrieved_sessions:
                    context = "[No sessions retrieved]"
                else:
                    context = get_session_texts(conv_entry, retrieved_sessions[:5])
                    if not context:
                        context = "[Retrieved sessions not found in dataset]"

                answerer_prompt = (
                    "You are answering a question about a person's life based on their conversation history.\n\n"
                    f"Conversation sessions:\n{context}\n\n"
                    f"Question: {question}\n"
                    "Answer concisely in 1-2 sentences."
                )

                try:
                    hypothesis = run_claude(answerer_prompt, ANSWERER_MODEL)
                    time.sleep(0.5)
                    score = judge_answer(gold_answer, hypothesis)
                    time.sleep(0.5)
                except RuntimeError as e:
                    print(f"  ERROR: {e}")
                    total_errors += 1
                    continue

                cat_name = CAT_NAMES.get(category, "unknown")
                scores_accum[cat_name].append(score)
                scores_accum["overall"].append(score)
                conv_scores.append(score)
                total_evaluated += 1
                total_done += 1

                print(f"  cat={cat_name} score={score} | Q: {question[:70]}")

                result_entry = {
                    "sample_id": sample_id,
                    "question": question,
                    "gold_answer": gold_answer,
                    "hypothesis": hypothesis,
                    "score": score,
                    "category": category,
                    "category_name": cat_name,
                    "retrieved_sessions": retrieved_sessions[:5],
                }
                json.dump(result_entry, out_f, ensure_ascii=False)
                out_f.write("\n")
                out_f.flush()

            if conv_scores:
                conv_f1 = sum(conv_scores) / len(conv_scores)
                print(f"  {sample_id} F1={conv_f1:.4f} ({len(conv_scores)} evaluated)")

    # Final report
    print(f"\n{'='*60}")
    print(f"LoCoMo QA Evaluation Results")
    print(f"{'='*60}")
    print(f"Total evaluated: {total_evaluated}, errors: {total_errors}")
    print()

    overall = scores_accum.get("overall", [])
    if overall:
        print(f"Overall F1: {sum(overall)/len(overall):.4f} ({len(overall)} queries)")

    print(f"\nBy category:")
    for cat_name in ["single-hop", "temporal", "multi-hop", "open-domain", "adversarial"]:
        vals = scores_accum.get(cat_name, [])
        if vals:
            print(f"  {cat_name}: F1={sum(vals)/len(vals):.4f} ({len(vals)} queries)")

    print(f"\nFull results: {OUT_PATH}")


if __name__ == "__main__":
    main()
