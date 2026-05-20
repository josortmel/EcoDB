# LongMemEval-S Benchmark

Evaluates EcoDB's GAMR search engine against [LongMemEval](https://github.com/xiaowu0162/LongMemEval) (ICLR 2025).

## What it measures

Session-level retrieval: given ~40 conversation sessions and a question, find which session(s) contain the answer. Metrics: Recall@K and NDCG@K.

## Two evaluation modes

1. **Docling pipeline** (`run_benchmark.py`) — sessions ingested as Markdown documents via Docling (parse → chunk → NER → embed → graph). Tests the full EcoDB pipeline.

2. **Direct memory** (`run_benchmark_memories.py`) — sessions loaded as individual memories. Tests GAMR search without document chunking.

## Running

```bash
# 1. Prepare data
python eval/longmemeval/prepare_data.py

# 2. Start services with benchmark overlay
docker compose -f docker-compose.yml -f docker-compose.benchmark.yml up -d

# 3a. Docling mode
ECODB_API_KEY=<key> python eval/longmemeval/ingest_sessions.py
ECODB_API_KEY=<key> python eval/longmemeval/run_benchmark.py

# 3b. Memory mode
ECODB_API_KEY=<key> python eval/longmemeval/run_benchmark_memories.py
```

## Results

TODO: fill after running benchmark.
