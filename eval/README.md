# EcoDB Evaluation Framework

Benchmark tools for measuring GAMR search quality.

## LoCoMo paper baselines (ACL 2024)

The LoCoMo authors (Snap Research) evaluated [DRAGON](https://arxiv.org/abs/2302.07452) as their retrieval baseline, testing three retrieval unit types:

| Retrieval unit | R@5 | R@10 | R@25 | R@50 |
|---------------|:---:|:----:|:----:|:----:|
| Dialog turns | 0.588 | 0.675 | 0.799 | 0.848 |
| Observations | 0.496 | 0.571 | 0.660 | 0.711 |
| Session summaries | 0.751 (R@5) | 0.907 (R@10) | — | — |

EcoDB's approach (5-turn chunked sessions) is closest to the Dialog unit type. At K=5, EcoDB achieves 0.914 R@5 vs DRAGON Dialog's 0.588 — a +33 percentage-point improvement. Even against the strongest baseline (session summaries at 0.751), EcoDB's 0.914 represents a +16pp improvement with finer-grained retrieval units.

No other system has published retrieval Recall@K on LoCoMo. Other AI memory systems (Mem0, Zep, Letta, ByteRover, Hindsight) evaluate on LLM-as-Judge QA accuracy, which is a different metric measuring end-to-end answer correctness rather than retrieval quality.

## Golden Set Evaluation

`golden_set.py` runs queries against EcoDB and measures R@K and MRR.

### Metrics

- **R@K (Recall at K):** fraction of relevant memories in top K results
- **MRR (Mean Reciprocal Rank):** average of 1/rank for first relevant result

See [`BENCHMARKS.md`](BENCHMARKS.md) for internal golden set methodology and results.

## Scripts

| Script | Purpose |
|--------|---------|
| `golden_set.py` | Internal golden set evaluation (R@5, MRR) |
| `gamr_k_eval.py` | GAMR K-ablation evaluation |
| `pure_ann_eval.py` | ANN-only baseline (no GAMR) |
| `latency_measure.py` | Search latency benchmarks |
| `resolve_ground_truth.py` | Pre-resolve expected descriptions to IDs |
| `reindex_memories.py` | Re-index memories for benchmark |
| `sync_age.py` | Sync AGE graph state |
| `sync_predicates.py` | Sync predicate ontology |
| `seed_dictionary.py` | Seed entity dictionary |
