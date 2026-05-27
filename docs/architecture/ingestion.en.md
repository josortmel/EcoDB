---
workflow: design
fecha: 2026-05-12
proyecto: EcoDB
tipo: construction-brief
version: "3.1-final"
autor: the research lead
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md
  - 2026-05-12_EcoDB_Fase3_GAMR.md
  - 2026-05-11_EcoDB_asentamiento.md
  - EcoDB_Fase4_preguntas_diseno.md (the engineering lead)
  - 2026-05-08_prima_nota_diseno_fase2_3a.md
  - EcoDB_aportaciones_deepseek_F4.md + v2
  - EcoDB_aportaciones_Gemini_F4.md + v2
  - EcoDB_aportaciones_ChatGPT_F4.md + v2
  - adversarial_report.md (Loop 1, 5 REQUIRED)
tags:
  - workflow/design
  - project/ecodb
  - type/brief
  - status/v3
  - level/critical
---

# Brief — EcoDB phase: Document Ingestion (v3)

*the research lead, May 12, 2026. v3.1 final — integrates Loop 1 (5 REQUIRED) + Loop 2 (4 REQUIRED) + 2 rounds from 3 external consultancies.*

---

## 1. Context and motivation

EcoDB is the organization's unified memory system. PostgreSQL 16 + pgvector + Apache AGE. In production since May 9 (day 67). Phases 1-3 complete (schema, permissions, GAMR 8 stages, graph governance). 194 typed nodes, 358 triples, 121 canonical predicates, 946+ memories.

phase adds document ingestion: files on disk (PDF, DOCX, TXT, MD, audio) are indexed, chunked, embedded with Jina v4, entities extracted with GLiNER, and integrated with the existing GAMR engine. The document schema already exists but the tables are empty. The placeholder worker exists in docker-compose with `--profile with-ingestion`.

**Why now:** Phases 1-3 built episodic memory (what agents live and decide). phase adds reference memory (what exists in documents).

---

## 2. Design decisions (with traceability)

### D1: Enriched search, not unified

- Origin: [my-inference] + [research] 3 consultancies
- Decision: `search` searches memories by default. Parameter `include_documents: bool = false`. When true, GAMR searches document_chunks with `source_type: "memory" | "document_chunk"` in ALL results (always present, default "memory" — backward-compatible). Chunks receive `chunk_score_factor = 0.7` (env var `CHUNK_SCORE_FACTOR`). Maximum `max_document_results = 3` (configurable). Separate tool `search_in_document(document_id, query)`.
- **Resolution [L2] adversarial**: `source_type` always present in SearchResult. For current callers without include_documents, all results have `source_type="memory"` — new field but constant value, not breaking. CE-19 verifies backward compatibility.

### D2: Chunking **960 tokens** with 128 overlap, hybrid strategy

- Origin: [my-inference] + [research] consultancies + adversarial [A1]
- **Correction v3**: semantic chunk reduced from 1024 to **960 tokens** to align with GLiNER sub-chunking. 2 windows of 512 tokens with 64 overlap cover exactly 960 tokens with no gap: window 1 [0-511], window 2 [448-959]. No orphan tokens.
- Overlap between consecutive chunks: **128 tokens** (~13%).
- Strategy by type: markdown respects headers, PDF respects Docling sections, prose recursive split, audio 60s segments. **Explicit fallback**: if Docling detects no structure, falls back to recursive splitting and logs the condition.
- **No chunk_order added**: the schema already has `chunk_index INT NOT NULL` with `UNIQUE(document_id, chunk_index)` which serves the same purpose. Redundant column avoided. **Resolution [C1] adversarial.**
- `section_path TEXT NULL` added to document_chunks (hierarchical navigation).

### D3: Drop column `documents.embedding`

- Decision: `ALTER TABLE documents DROP COLUMN embedding`. `DROP INDEX idx_documents_embedding`. Only chunks are embedded.

### D4: Docling in worker, no GPU OCR

- Decision: Docling in worker container. `CUDA_VISIBLE_DEVICES=''` forced. Timeout per document: 5 min (`PARSE_TIMEOUT_SECONDS`). Day-1 formats: PDF, TXT, MD, DOCX, HTML.
- **Per-stage timeout resolution** (DeepSeek v2 contribution): the worker has independent timeouts per stage: `PARSE_TIMEOUT=300s`, `EMBED_TIMEOUT=120s`, `GLINER_TIMEOUT=120s`. If a stage exceeds its timeout, the document is marked 'failed' with a descriptive stage error, **retry_count is incremented** ([PD1] adversarial L2), and the worker **continues with the next document**. If retry_count reaches 3, it remains permanently 'failed'. `reindex_document` resets retry_count to 0 for manual admin retry.

### D5: Whisper on CPU, configurable model

- Decision: Whisper CPU. `WHISPER_MODEL` env var (default: `small`). Verify model is installed before implementing. Auto language detection. Temporal segments as chunks with timestamps.
- **Timing corrected**: 30-40x real time. 1h audio → 30-40 min CPU. Documented.
- **Whisper stage timeout**: `WHISPER_TIMEOUT=1800s` (30 min). Audio exceeding this → 'failed'. Worker continues.

### D6: Async queue LISTEN/NOTIFY + retries

- Decision: channel `ecodb_ingest`, payload only document_id, sequential worker with SELECT FOR UPDATE SKIP LOCKED. Retry B+C: max 3 retries → 'failed' + SSE. **Crash recovery**: every 5 min the worker looks for documents with status='processing' and stale `processing_started_at` (>10 min) and resets them to 'queued'. This 10-min timeout is NOT a processing timeout — it only detects dead workers. Processing timeouts are the per-stage ones from D4+D5 (PARSE=300s, EMBED=120s, GLINER=120s, WHISPER=1800s).
- **Circuit breaker for embeddings service** (DeepSeek v2 contribution): if the embeddings service fails 3 times in 1 minute, the worker opens the circuit and waits 30 seconds before retrying. Documents remain 'queued' without consuming retries. Prevents failure cascades.
- **Resolution [A2] adversarial**: DDL migration extends CHECK constraint:
  ```sql
  ALTER TABLE documents DROP CONSTRAINT documents_status_check;
  ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('queued','processing','indexed','failed','deleted'));
  ```

### D7: Source resolution — source_score with concrete parameters

- Origin: [my-inference] + adversarial [A4+C2] + consultancies v2
- **Resolution [A4+C2] adversarial**: formula with explicit parameters:
  ```
  freshness_factor = 1.0 - min(1.0, days_since_doc_changed / DOCUMENT_DECAY_DAYS)
  source_score = 0.5 + 0.5 * freshness_factor
  ```
  `DOCUMENT_DECAY_DAYS = 14` (env var). A document changed today: source_score=1.0. 7 days ago: 0.75. 14+ days ago: 0.5. Document not modified since the memory was created: freshness_factor=1.0 always (does not penalize for document age, only for subsequent changes).
- **Resolution [A5] adversarial — 3 GAMR Stage 5 edge cases:**
  1. **N linked documents**: `source_score = min(scores)`. If any source is stale, the memory is suspect. Conservative.
  2. **Document with status='deleted'**: `source_score = 0.5` (minimum). The memory still exists but its source disappeared. Not 1.0 (that would mean "no source to penalize", opposite semantics).
  3. **Index**: `CREATE INDEX idx_mdl_memory ON memory_document_links (memory_id)`. Without it, Stage 5 does a seq scan per candidate memory.
- Manual linking on day 1 via `source_document_id` in `save_memory`.

### D8: Host-side watchdog

- Decision: Python script on host. Calls API on detecting changes. Write completion check (2s stable). Daily polling as fallback.
- **Deployment**: Task Scheduler on Windows (trigger: logon + repeat every 5 min on failure). Systemd on Linux (phase).
- **Documented as "best effort"**: the watchdog is a latency improvement, not a guarantee. Daily polling is the real safety net. If the watchdog dies, documents are indexed with up to 24h delay. Acceptable for single-tenant.
- **[S2] adversarial resolved.**

### D9: Obsolescence — DELETE + INSERT + knowledge boundary

- Decision: DELETE chunks + INSERT new ones (CASCADE). Soft delete documents (status='deleted'). Entities from deleted documents excluded from GAMR expansion.
- **FK corrected** ([A2] DeepSeek v1): `chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE`
- **file_hash**: SHA-256 of raw file bytes. Not of extracted text. Implication: PDFs with embedded timestamps that change without content change will produce re-indexing. Acceptable — cost is low and the alternative (text hash) requires full parsing to verify.
- **Explicit debt** ([C1] ChatGPT v2): re-indexing breaks chunk_ids. Memories that cited a specific chunk_id lose the reference (FK CASCADE deletes the link). Chunk-granular traceability does not survive re-indexing. Documented.

### D10: Per-chunk entities with corrected GLiNER sub-chunking

- Decision: GLiNER over 2 windows of 512 tokens per 960-token chunk. Overlap 64 tokens. Full coverage: window 1 [0-511], window 2 [448-959] = 960 tokens covered, 0 gap.
- **Conflict resolution** (DeepSeek v2 contribution): if the same entity appears in both windows, take the instance with the higher GLiNER score. Deduplicate by (entity_name_normalized, entity_type).
- PK: `(document_id, entity_node_id, chunk_id)` + FK CASCADE. **Note** ([SD4] adversarial L2): chunk_id becomes implicitly NOT NULL by being part of PK. Entity links without chunk_id (at document level) are no longer possible. Accepted — extraction always operates at chunk level.
- **Stop entities**: `stop_entities` table in DB. Super-only CRUD (4 endpoints `/admin/stop-entities`). Initial list manually curated: high-frequency, low-semantic-value system/infrastructure terms. Criterion: if the entity would appear in >50% of documents in any domain, it is a candidate. Quarterly review.
- **Pipeline order** ([SD3] adversarial L2): entity_dictionary lookup-first → GLiNER residual → merge → **stop entities filter POST-MERGE**. Stop entities do not delete existing graph nodes (created by memories), they only prevent creation of new document_entity_links. Thus, a "Docker" node created by memories continues to exist and be expandable, but new documents do not reinforce its connectivity.
- **Frequency metrics** (phase debt): dynamic frequency-based attenuation (`weight / log(doc_freq)`) deferred. Manual list sufficient for phase.

### D11: MCP tools — 7 tools

- `register_document(uri, project_id, doc_type?, visibility?)`: absolute path, auto-detect type, copy to media store, 202.
- `document_status(document_id)`: status + progress + metadata + processing_metrics.
- `list_documents(project_id?, workspace_id?)`: permission-filtered.
- `search_in_document(document_id, query_text)`: top 5 chunks.
- `read_document(document_id, start_chunk?, end_chunk?, limit?)`: content concatenated by chunk_index. **Default limit: 50 chunks** (~38K tokens). If document exceeds and no range is specified, returns first 50 with `truncated: true` indicator and `total_chunks: N`. **Resolution [L4] adversarial.**
- `reindex_document(document_id)`: forces re-processing. Super-only or creator.
- `unlink_document(document_id)`: soft delete.

### D12: Metadata with Pydantic validation

- `DocumentMetadata` Pydantic: title, author, page_count, language, file_created_at, file_size_bytes. Unexpected fields are logged and discarded.
- `ChunkMetadata` Pydantic: page, section_header, timestamp_start, timestamp_end, char_offset.
- **Controlled vocabulary for language** (ChatGPT v2 contribution): ISO 639-1 codes (es, en, fr...), not free text.

### D13: Processing metrics with gpu_peak_mb

- Column `processing_metrics JSONB` in documents:
  ```json
  {
    "parse_ms": 1200,
    "chunk_count": 52,
    "embed_ms": 5300,
    "gliner_ms": 4100,
    "total_ms": 12400,
    "gpu_peak_mb": 4820
  }
  ```
- **Resolution [A3] adversarial**: `gpu_peak_mb` restored. Read from `torch.cuda.max_memory_allocated()` post-embedding. Most valuable field for detecting silent OOMs and verifying Docling does not use GPU.

### D14: Differential edge weight + separate expansion budget

- Origin: [research] ChatGPT v1+v2 + DeepSeek/Gemini v2
- Edge weight: `documents.base_weight REAL DEFAULT 0.3` (new column). Administrator can raise to 0.8 for canonical documents (master plan, specs). GAMR Stage 4 uses `d.base_weight` instead of a hardcoded constant. **Resolution of 0.3 arbitrariness** (DeepSeek v2 + Gemini v2 contribution).
- **Separate expansion budget** (ChatGPT v2 contribution): `MAX_MEMORY_EXPANSION = 15`, `MAX_DOCUMENT_EXPANSION = 5` (env vars). Independent limits — not just edge weight. A huge document cannot occupy more than 5 slots in expansion even if it has many entities.
- **max_chunks_per_document_in_expansion = 2** (ChatGPT v2): if a document appears via 10 different entities, it only contributes 2 chunks to the expanded pool. Prevents contextual dominance.

### D15: GAMR Stage 4 — deduplication + exclusion + budgets

- **Correction [SD1+CO1] adversarial L2**: DO NOT use `DISTINCT ON (document_id)` (returns exactly 1 row, contradicts max=2). Instead: `ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY shared_entities DESC) <= 2` to limit to top 2 chunks per document in the expansion pool. Then, apply `MAX_DOCUMENT_EXPANSION=5` on the total of distinct documents.
- WHERE d.status != 'deleted' for knowledge boundary.
- D14 budgets applied.

---

## 3. DDL migration plan (Resolution [L1] adversarial)

**Atomic procedure** — same pattern as previous phase:

1. `pg_dump` snapshot before starting
2. Single SQL script with all DDL changes in one transaction:

```sql
BEGIN;

-- 1. Extend CHECK constraint documents.status
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
  CHECK (status IN ('queued','processing','indexed','failed','deleted'));

-- 2. New columns in documents
ALTER TABLE documents ADD COLUMN retry_count INT DEFAULT 0;
ALTER TABLE documents ADD COLUMN processing_started_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN processing_metrics JSONB;
ALTER TABLE documents ADD COLUMN base_weight REAL DEFAULT 0.3;

-- 3. Drop embedding column + index
DROP INDEX IF EXISTS idx_documents_embedding;
ALTER TABLE documents DROP COLUMN IF EXISTS embedding;

-- 4. New column in document_chunks
ALTER TABLE document_chunks ADD COLUMN section_path TEXT;

-- 5. PK change + FK CASCADE in document_entity_links
ALTER TABLE document_entity_links DROP CONSTRAINT document_entity_links_pkey;
ALTER TABLE document_entity_links
  DROP CONSTRAINT IF EXISTS document_entity_links_chunk_id_fkey;
ALTER TABLE document_entity_links
  ADD CONSTRAINT document_entity_links_chunk_id_fkey
  FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE;
ALTER TABLE document_entity_links
  ADD PRIMARY KEY (document_id, entity_node_id, chunk_id);

-- 6. Index for memory_document_links (GAMR Stage 5)
CREATE INDEX IF NOT EXISTS idx_mdl_memory
  ON memory_document_links (memory_id);

-- 6b. Index for document_chunks.document_id (check_visibility JOIN)
-- PostgreSQL does NOT create indexes on FKs automatically (correction [G1] adversarial L2)
CREATE INDEX IF NOT EXISTS idx_dc_document_id
  ON document_chunks (document_id);

-- 7. Stop entities table
CREATE TABLE IF NOT EXISTS stop_entities (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  name_normalized TEXT UNIQUE NOT NULL,
  reason TEXT,
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

COMMIT;
```

3. **Abort criterion**: if any ALTER fails, atomic ROLLBACK. The empty tables (documents, document_chunks, document_entity_links) have no data to lose, but the transaction protects schema integrity.
4. **Manual rollback**: if reverting post-commit is needed, inverse script available (ADD COLUMN embedding, DROP stop_entities, etc.). pg_dump as final safety net.

---

## 4. Scope

### In scope:
- Single-thread Python worker with LISTEN/NOTIFY + CUDA_VISIBLE_DEVICES='' + embeddings circuit breaker + per-stage timeouts
- Parsers: Docling (PDF, DOCX, TXT, MD, HTML) + Whisper (audio, CPU, configurable)
- Hybrid chunking **960 tokens** + 128 overlap + explicit fallback
- 2x512 sub-chunking for GLiNER (full coverage of 960 tokens)
- Chunk embedding with Jina v4
- GLiNER + stop entities (DB table) + lookup-first pipeline
- document_entity_links with granular chunk_id + FK CASCADE
- Per-document edge weight (`documents.base_weight`) + separate expansion budget (memory 15 / document 5) + max 2 chunks/doc in expansion
- DISTINCT + exclusion removed from GAMR expansion
- GAMR Stage 5 source resolution complete (formula, 3 edge cases, index)
- Host-side watchdog (best effort) + daily polling (guarantee)
- Obsolescence: DELETE+INSERT chunks + soft delete documents + knowledge boundary
- 7 MCP tools (with limits on read_document)
- Atomic DDL migration with rollback (section 3)
- source_type always present in SearchResult (backward-compatible)
- Pydantic metadata + ISO 639-1 vocabulary for language
- processing_metrics with gpu_peak_mb
- check_visibility for documents (inherited from parent)

### Out of scope (conscious debt):
- Scanned PDF OCR (phase)
- Source code chunking with tree-sitter (phase)
- Automatic memory-document linking by embedding (phase)
- Queue priority (deferred)
- rclone VPS (phase)
- Document versioning (phase)
- Trust tiers (documents.base_weight is minimal version; formal tiers phase-6)
- Semantic near-duplicate deduplication (phase)
- Entity dictionary governance at scale (phase)
- Hybrid async worker ThreadPool (phase, if bottleneck)
- Inter-chunk entity reconciliation (phase)
- Dynamic stop entities by frequency (phase)
- Hybrid retrieval BM25 + structural filters (phase)
- parent_section_id for tree retrieval (phase — re-index acceptable for our volume)
- logical_chunk_id / stable_chunk_hash for post-reindexing traceability (phase)
- Re-indexing breaks chunk_ids: memories citing a chunk_id lose the reference (CASCADE). Chunk-granular traceability does not survive re-indexing.
- Worker /metrics endpoint aggregated (phase)
- Semantic drift vs file drift in source_score (phase)
- Operational runbooks (construction phase)

---

## 5. Success criteria (verifiable)

- CE-1: `docker compose --profile with-ingestion up` starts worker healthy
- CE-2: Register PDF via MCP → status queued→processing→indexed. Chunks with embeddings. Sequential chunk_index. processing_metrics with timings + gpu_peak_mb.
- CE-3: `search(query_text="...", include_documents=true)` returns results with `source_type="document_chunk"` + `source_type="memory"`. Chunks with score x chunk_score_factor. Max 3 document chunks.
- CE-4: `search_in_document(document_id, query_text)` returns top 5 chunks.
- CE-5: `read_document(document_id)` returns content concatenated by chunk_index. Document >50 chunks without range: truncated=true + total_chunks.
- CE-6: Host-side watchdog detects new file → API → worker indexes.
- CE-7: File modified → re-hash → re-indexes. SSE `source_updated`.
- CE-8: File deleted → `status='deleted'` (extended CHECK constraint allows value). Excluded from search.
- CE-9: MP3 audio → Whisper CPU → chunks with timestamps → embeddings → sub-chunked entities.
- CE-10: retry_count=3 → status='failed' + SSE `document_failed`.
- CE-11: `save_memory(source_document_id=uuid)` → memory_document_links. source_score calculated: document unchanged→1.0, modified 7 days ago→0.75, 14+ days ago→0.5. With `DOCUMENT_DECAY_DAYS=14`.
- CE-12: document_entity_links with granular chunk_id (NOT NULL by PK). GAMR Stage 4 expands with `d.base_weight` (default 0.3). Document budget 5. Max 2 chunks/doc via ROW_NUMBER PARTITION BY document_id.
- CE-13: Permissions: chunks filtered via check_visibility of parent document.
- CE-14: Ingestion latency for 50-page PDF < **7 minutes** (parse + chunk + embed + GLiNER sub-chunk x 2).
- CE-15: GLiNER covers full 960 tokens with no gap (2x512, overlap 64).
- CE-16: Stop entities do not generate AGE nodes or links.
- CE-17: PDF without structure → fallback to recursive splitting + log.
- CE-18: documents.embedding dropped + index dropped.
- CE-19: `search(query_text="...", include_documents=false)` returns results with `source_type="memory"` in all — backward compatibility verified with current callers.
- CE-20: Memory linked to N documents: source_score = min(scores). Memory linked to deleted document: source_score=0.5.
- CE-21: Circuit breaker: if embeddings fails 3 times in 1 min, worker waits 30s. Documents remain 'queued'.
- CE-22: Per-stage timeout: parse exceeds 5 min → 'failed' with error "parse_timeout" + retry_count incremented. Worker continues with next.
- CE-23: `search(query_text="...")` WITHOUT include_documents parameter (omitted, not explicit false) → results with `source_type="memory"`. Backward compatibility by omission.
- CE-24: Stop entities filter POST-MERGE: entity "Docker" in stop_entities + existing node from memories → no document_entity_link created but node remains in graph.

---

## 6. Questions the Adversarial should ask (Loop 2)

1. **Atomic DDL migration**: verify that the section 3 script is executable as-is on PostgreSQL 16 + AGE. Especially the DROP/ADD PK on document_entity_links with an empty table.
2. **documents.base_weight interaction with chunk_score_factor**: a document with base_weight=0.8 + chunk_score_factor=0.7 produces an effective score of 0.56. Is this the correct semantics? Are both multiplied or does only one apply?
3. **960 sub-chunking + 128 overlap between chunks**: the last chunk of a document may have <960 tokens. If it has 400 tokens, is it processed as a single 400-token window for GLiNER?
4. **Circuit breaker scope**: protects against embeddings service failure. But what happens if PostgreSQL goes down? Or if the embeddings service responds slowly (not failing, but 60s per request)?
5. **Stop entities and entity_dictionary**: these are two tables governing the same pipeline (entity extraction). The interaction is not specified. Does the dictionary match first (lookup-first), with stop entities filtering afterward? Or are stop entities checked before the dictionary?

---

## Annex A — Adversarial Loop 1 closure

### APPLIED_FIXES (5 REQUIRED):
| Item | Change in Brief v3 |
|------|---------------------|
| [A2] CHECK constraint | D6: explicit ALTER TABLE in DDL migration (section 3) |
| [A4+C2] decay_period | D7: DOCUMENT_DECAY_DAYS=14, explicit formula, CE-11 with expected values |
| [A5] Stage 5 spec | D7: 3 edge cases (min scores, deleted=0.5, memory_document_links index) |
| [L1] atomic migration | New section 3: transactional SQL script + pg_dump + rollback |
| [L2] source_type breaking | D1: always present, default "memory", CE-19 backward compatibility |

### APPLIED_FIXES (SOFT adopted):
| Item | Change |
|------|--------|
| [A1] sub-chunking math | D2: chunk reduced to 960 tokens (full coverage) |
| [A3] gpu_peak_mb | D13: restored in processing_metrics |
| [C1] chunk_order vs index | D2: existing chunk_index used, no column added |
| [L4] read_document limit | D11: default 50 chunks, truncated indicator |
| [L5] stop_entities table | D10: DB table with super-only CRUD |
| [S1] file_hash | D9: SHA-256 raw bytes specified |
| [S2] watchdog deploy | D8: Task Scheduler Windows, systemd Linux, documented as best effort |

### DEFERRED_AS_DEBT:
| Item | Justification |
|------|---------------|
| [L3] parent_section_id | section_path covers navigation. Re-index in phase acceptable for <1000 docs |
| [S3] check_visibility JOIN | **Corrected in L2**: PostgreSQL does NOT create indexes on FKs. Index `idx_dc_document_id` added to migration script (section 3, step 6b). Resolved. |

### Adopted external v2 contributions:
| Source | Contribution | Decision |
|--------|-----------|----------|
| ChatGPT v2 | Separate memory/document expansion budget | D14: 15/5 |
| ChatGPT v2 | max_chunks_per_document_in_expansion | D14: 2 |
| ChatGPT v2 | Re-indexing breaks chunk links | Explicit debt |
| DeepSeek v2 | Embeddings circuit breaker | D6 |
| DeepSeek v2 | Per-stage timeouts | D4+D5 |
| DeepSeek v2 | documents.base_weight | D14 |
| Gemini v2 | documents.base_weight | D14 (convergence with DeepSeek) |
| Gemini v2 | Chunk 960 tokens | D2 (convergence with adversarial) |
| DeepSeek v2 | Sub-chunking conflict resolution | D10: highest score wins |

### Deferred external v2 contributions with justification:
| Contribution | Justification |
|-----------|---------------|
| logical_chunk_id / stable_chunk_hash (ChatGPT) | Premature for phase. Requires a document versioning model that does not exist. |
| Formalized semantic windows (ChatGPT) | Correct abstraction but overengineering for phase. |
| Pipeline as independent layers (ChatGPT) | Conceptually sound. Phase worker is simple enough to refactor later. |
| Hybrid async worker ThreadPool (Gemini) | Single-tenant, FIFO with per-stage timeouts is sufficient. If Whisper blocks too much, phase. |
| Replaceable queue interface (ChatGPT) | Worker is ~200 lines. Refactorable without prior abstraction. |
| Dynamic stop entities by frequency (ChatGPT/DeepSeek) | Manual list for phase. Frequency metrics and log(doc_freq) attenuation in phase. |
| Exponential vs linear decay (DeepSeek v2) | Linear 14 days first. If calibration shows it does not fit, pivot to exponential. |
| Audio as second-class pipeline (ChatGPT v2) | Single FIFO worker sufficient. Per-stage timeouts mitigate blocking. |
| Worker /metrics endpoint (DeepSeek v2) | processing_metrics in DB is sufficient for phase. Aggregated endpoint in phase. |
| Watchdog local sqlite queue (DeepSeek v2) | Daily polling is the real safety net. Local queue is overengineering. |
