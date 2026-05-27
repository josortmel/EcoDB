# LoCoMo Benchmark

Evaluates EcoDB's GAMR search engine against [LoCoMo](https://github.com/snap-research/LoCoMo) (Maharana et al., ACL 2024).

## What it measures

Long-term conversational memory: given multi-session dialogues between two people, find which session(s) contain the answer to a question. Tests single-hop, temporal, multi-hop, open-domain, and adversarial recall.

## Dataset

- 10 conversations, 272 sessions, 1,986 QA pairs
- Each session ~2.5K chars (all under 16K — fits in EcoDB without truncation)
- Evidence field provides retrieval ground truth (no LLM judge needed)

## Running

```bash
# 1. Download data (if not already present)
mkdir -p eval/locomo/data
curl -sL https://raw.githubusercontent.com/snap-research/LoCoMo/main/data/locomo10.json -o eval/locomo/data/locomo10.json

# 2. Run benchmark
ECODB_API_KEY=<key> python eval/locomo/run_benchmark.py
```

Each conversation loads into an isolated workspace, runs ~200 queries, and reports R@K per category.

## Results

### With Docling chunking (5-turn sliding windows, 1-turn overlap)

| Metric | K=5 | K=10 | K=20 |
|--------|:---:|:----:|:----:|
| Recall@1 | 0.774 | 0.756 | 0.774 |
| Recall@5 | 0.914 | 0.906 | **0.922** |
| Recall@10 | * | 0.931 | **0.959** |

### Without chunking (monolithic sessions)

| Metric | Score |
|--------|:-----:|
| Recall@5 | 0.769 |
| Recall@10 | 0.894 |

### With cross-encoder reranking (no chunking)

| Metric | Score |
|--------|:-----:|
| Recall@1 | 0.578 |
| Recall@5 | 0.793 |

See [`eval/BENCHMARKS.md`](../BENCHMARKS.md) for full analysis.
