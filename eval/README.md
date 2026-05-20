# EcoDB Evaluation Framework

Benchmark tools for measuring GAMR search quality.

## Golden Set Evaluation

`golden_set.py` runs queries against EcoDB and measures R@K and MRR.

### Metrics

- **R@K (Recall at K):** fraction of relevant memories in top K results
- **MRR (Mean Reciprocal Rank):** average of 1/rank for first relevant result

### Results

EcoDB GAMR on production dataset (1400+ memories, 60 queries):

| Metric | Score |
|--------|-------|
| R@5 | 0.56 |
| MRR | 0.39 |
| Multimodal R@5 | 0.70 |
