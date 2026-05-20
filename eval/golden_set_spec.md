# Spec — eval/golden_set.py

## Purpose

Evaluate GAMR search quality against a curated set of queries with expected results.
Computes Recall@5 and MRR (Mean Reciprocal Rank) per query and aggregated.
Designed to run before/after activating each Fase 5 feature flag.

## Usage

```bash
cd C:\Users\Admin\Documents\EcoDB
python eval/golden_set.py                           # run all queries, print report
python eval/golden_set.py --output eval/baseline.md # save report to file
python eval/golden_set.py --tag "pre-bm25"          # tag run for comparison
python eval/golden_set.py --compare eval/baseline.md eval/post_bm25.md  # diff two runs
```

## Dependencies

- httpx (already in api requirements)
- pyyaml (add to requirements if not present, or use ruamel.yaml)
- tabulate (for pretty printing, optional — fallback to plain text)

## Input

`eval/queries.yaml` — YAML file with annotated queries:

```yaml
queries:
  - query: "text"
    category: factual|historical|analytical|contextual|cross_modal
    expected_ids: ["uuid-1", "uuid-2"]          # memory_ids or document_ids
    expected_descriptions: ["fallback text"]     # resolved to IDs at runtime
    notes: "optional"
```

## Algorithm

For each query:
1. Call POST /search with `query_text=query, limit=5, include_documents=true`
2. Collect returned IDs (memories + document chunks → parent document_id)
3. Compute:
   - **Recall@5** = |expected ∩ returned| / |expected|
   - **Reciprocal Rank** = 1 / rank_of_first_expected (0 if none found)

Aggregate:
- **Mean Recall@5** = avg across all queries
- **MRR** = avg reciprocal rank across all queries
- Per-category breakdown (factual, historical, analytical, contextual, cross_modal)

## Output format (markdown)

```markdown
# Golden Set Evaluation — {tag} — {datetime}

## Summary
| Metric | Value |
|--------|-------|
| Queries | 42 |
| Mean Recall@5 | 0.73 |
| MRR | 0.65 |

## Per Category
| Category | Count | Recall@5 | MRR |
|----------|-------|----------|-----|
| factual | 15 | 0.80 | 0.72 |
| historical | 10 | 0.65 | 0.58 |
| ... | | | |

## Feature Flags
| Flag | Value |
|------|-------|
| ENABLE_BM25 | false |
| ENABLE_AUTO_LINK | false |
| ... | |

## Per Query Detail
| # | Query | Category | Recall@5 | RR | Expected | Found | Missing |
|---|-------|----------|----------|----|----------|-------|---------|
| 1 | "qué es GAMR?" | factual | 1.00 | 1.00 | 2 | 2 | 0 |
| 2 | ... | | | | | | |
```

## Auth

Use API key from env var `ECODB_EVAL_API_KEY` or fallback to reading from
`C:\Users\Admin\Documents\EcoDB\.env` if exists.
API base URL from `ECODB_API_URL` env var, default `http://localhost:8080`.

## Config

```python
API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
QUERIES_PATH = "eval/queries.yaml"
K = 5  # top-K for recall
```

## Error handling

- If queries.yaml doesn't exist or has <1 query: exit with message
- If API unreachable: exit with message
- If a query fails: log error, score as 0, continue
- expected_descriptions resolution: call /search with description text, take top-1 ID.
  If no match found, warn and skip that expected result

## Comparison mode (--compare)

Read two markdown output files. Parse Summary tables. Print delta:

```
Recall@5: 0.73 → 0.81 (+0.08) ✓
MRR:      0.65 → 0.72 (+0.07) ✓
```

Per-category deltas. Flag regressions (negative delta) with ✗.
