---
workflow: design
fecha: 2026-05-12
proyecto: EcoDB
tipo: construction-brief
version: "4.1-final"
autor: the research lead
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md (original phase)
  - 2026-05-12_EcoDB_fase4_plan_construccion.md (inherited debt)
  - fase4_ingesta_brief.md v3.1-final (explicit debt)
  - EcoDB_aportaciones_deepseek_F5.md
  - EcoDB_aportaciones_Gemini_F5.md
  - EcoDB_aportaciones_ChatGPT_F5.md
tags:
  - workflow/design
  - proyecto/ecodb
  - tipo/brief
  - estado/v2
  - nivel/critical
---

# Brief — EcoDB phase: Cognitive Governance (v2)

*the research lead, May 12, 2026. v4 integrates adversarial Loop 1 + 2 rounds from 3 external consultancies.*

---

## 1. Context and motivation

EcoDB after the previous phase has: episodic memories, indexed documents with chunks, governed graph, GAMR 8 stages with document expansion and source resolution. The system indexes and searches. But it does not yet GOVERN its own knowledge.

This phase introduces cognitive governance: hybrid retrieval, linking with graduated confidence, dynamic weight with decay, entity governance with reversibility, document trust tiers, deduplication by detection (not by automatic action), and cognitive observability.

**Guiding principle of this phase (new, emergent from the 3 consultancies):** the system DETECTS and SUGGESTS. The human (or the supervising agent) DECIDES and CONFIRMS. Epistemic automation without validation produces cognitive drift that is detected weeks later, when it has already contaminated retrieval, expansion, and decisions.

**Key conceptual shift:** similarity ≠ relation ≠ identity ≠ replacement. This phase cannot treat these concepts as equivalent.

---

## 2. Design decisions (with traceability)

### D1: Hybrid retrieval — vector + BM25 + graph with feature flag

- Origin: [my-inference] + [research] 3 consultancies (convergence)
- Decision: BM25 as 5th GAMR signal. PostgreSQL already has a GIN fulltext index on memories. Add equivalent on document_chunks. Composite score goes from 4 to 5 signals with redistributed weights.
- **Feature flag** ([research] DeepSeek): `ENABLE_BM25=true` (env var). Disableable without restart. When false, GAMR uses the original 4 signals. Allows instant rollback if BM25 degrades retrieval.
- **Calibration**: before activating in production, run a smoke test with 20 typical queries. Verify that top-3 improve subjectively. CE-17 formalizes this.
- Structural filters in search: `fecha_desde`, `fecha_hasta`, `doc_type`, `agent_identifier`, `tags`.
- Trade-off: redistributing weights without a test dataset is risky. Mitigated by feature flag + smoke test. Empirical calibration post-deployment.
- **Deferred debt**: RRF (Reciprocal Rank Fusion) as alternative to weighted sum. Cross-encoder reranking. Evaluate with the design lead for dashboard.

### D2: Automatic linking with graduated confidence

- Origin: [user-brief] master plan + [research] 3 consultancies (convergence: similarity ≠ epistemic relation)
- **Change from v1**: auto-links do NOT enter with the same weight as manual links. They have reduced weight until validation.
- **Feature flag** ([L3] adversarial): `ENABLE_AUTO_LINK=true` (env var). Disableable without restart. When false, no auto-links are created. Kill switch if the threshold generates massive false positives.
- Decision: when saving a memory, if ENABLE_AUTO_LINK=true, search for similar chunks. If `cosine > AUTO_LINK_THRESHOLD` (default **0.78**, configurable, lowered from 0.85 per DeepSeek recommendation):
  - Create `memory_document_links` with `link_type='auto'`, `confidence=cosine_score`, `validated=false`.
  - Max 3 auto-links per memory.
  - In GAMR Stage 5, auto-links with `validated=false` receive **0.5x** of the normal source_score. Manual and validated links receive 1.0x.
  - **Unvalidated auto-links do NOT increment last_accessed_at** ([research] ChatGPT v2 — avoid feedback loops where auto-links self-reinforce unverified memories).
  - Validation: the agent or admin can confirm with tool `validar_link(memory_id, document_id)` → `validated=true`.
- New columns in memory_document_links: `confidence REAL`, `validated BOOLEAN DEFAULT false`.
- Rationale: the consultancies agree — embedding similarity is not epistemic relation. Auto-links can be false. Reduced weight + validation prevents self-reinforcement of incorrect links.
- Trade-off: until validated, auto-links have lower impact on source_score. Acceptable — reduced impact is better than contamination.

### D3: Dynamic weight with decay + access as auxiliary signal

- Origin: [user-brief] master plan + [research] ChatGPT (access_count dangerous) + DeepSeek (decay floor)
- Decision:
  ```
  effective_weight = weight_base * freshness_modifier
  freshness_modifier = max(0.0, 1 - decay_rate * days_since_creation)  -- floor 0.0, no 0.3
  ```
  `access_count` does NOT multiply weight directly. It is an auxiliary signal for observability.
  - **last_accessed_at** ([research] DeepSeek v2 + ChatGPT v2): new column `memories.last_accessed_at TIMESTAMPTZ`. Updated each time a memory is returned as a result in `buscar` (not in admin/write operations). Replaces `access_count` as the basis for ALL temporal staleness conditions. `access_count` is kept as a historical counter but is NOT used for stale marking.
- **Corrected stale condition [A1] adversarial L2**: the stale condition is `freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days` (or last_accessed_at IS NULL and created_at < now() - 60 days). Does NOT use access_count. **Change from v1**: removed multiplicative access_boost. Reason ([research] ChatGPT): access_count mixes real relevance with retrieval bias. A frequently accessed document may simply be central or easy to retrieve, not better.
- **Decay floor → 0.0** ([research] DeepSeek): weight can tend toward zero. But **stale marking activates first**: if `freshness_modifier < 0.3` AND `last_accessed_at < now() - 60 days` → mark as `stale` (do not auto-archive — see D10).
- Decay by type (already configured in memory_type_config): agreements/decisions decay_rate=0.0 (never decay). Technical decay_rate=0.10. Moments 0.02. Observations 0.05.
- Trade-off: removing access_boost loses the signal "frequently consulted memories are probably useful". Acceptable — the signal was ambiguous and ChatGPT argued convincingly that it produces self-reinforcement.
- **Debt**: exponential decay (`e^(-λt)`) as alternative if linear proves too aggressive. Evaluate with real data.

### D4: Entity governance — candidates, soft merge, reversibility

- Origin: [my-inference] + [research] 3 consultancies (total convergence: reversibility mandatory)
- **Critical change from v1**: NOTHING is merged or created directly. Everything goes through candidates.
- Decision:
  - **DDL clarification [A3] adversarial**: the `nodes` table EXISTS as a standard PostgreSQL table since the previous phase (init.sql §1.6, `id SERIAL PRIMARY KEY, name TEXT UNIQUE`). EcoDB uses dual-write: SQL `nodes` + AGE `:Entity`. FKs to `nodes(id)` are valid. The adversarial detected a false positive due to lack of context — but this brief must be self-contained, so it is made explicit here.
  - **Alias candidates**: new table `entity_alias_candidates`:
    ```sql
    CREATE TABLE entity_alias_candidates (
      id SERIAL PRIMARY KEY,
      source_name TEXT NOT NULL,
      target_node_id BIGINT NOT NULL REFERENCES nodes(id),
      confidence REAL NOT NULL,
      occurrences INT DEFAULT 1,
      sample_contexts TEXT[],
      status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','archived')),
      first_seen TIMESTAMPTZ DEFAULT now(),
      last_seen TIMESTAMPTZ DEFAULT now(),
      reviewed_by INT REFERENCES users(id)
    );
    ```
    When GLiNER detects an entity with embedding >0.90 similar to an existing node, a candidate is created. The admin reviews and approves/rejects via tool `revisar_alias_candidato(id, decision)`. Approved → creates alias in predicate_aliases. Rejected → marked, not re-proposed.
    **Purge [L4] adversarial**: candidates with status='pending' and last_seen > 90 days → auto-archive. Candidates with status='rejected' are kept indefinitely (to avoid re-proposing them). Limit: max 500 simultaneous pending candidates — if exceeded, those with the lowest occurrences are purged first.
  - **Soft merge**: merge does NOT delete the node. Instead:
    ```sql
    -- absorbed node
    UPDATE nodes SET status='merged', merged_into=target_id WHERE id=source_id;
    ```
    **AGE resolution** ([research] Gemini v2 blocker): AGE is not aware of the `status` column in SQL. Resolution is done in the **application layer BEFORE Cypher**: when GAMR Stage 4 obtains entity_node_ids from memory_entity_links/document_entity_links, it first resolves merged_into via SQL, then passes the final IDs to Cypher. The AGE node of the merge source continues to exist but is never queried directly.
    **Chain compression** ([research] ChatGPT v2): `merged_into` ALWAYS points to the final root (union-find pattern). After each merge, recompute redirects to avoid chains A→B→C. Index: `CREATE INDEX idx_nodes_merged ON nodes(merged_into) WHERE status='merged'`.
    Endpoint `deshacer_merge(source_node_id)` restores the node to active status.
    Table `entity_merge_log` for auditing with date, actor, reason. **Column target_original_id** ([A3] adversarial L2): stores the target PRE-compression, not the compressed root. If A→B and then B→C (compression makes A→C), the merge_log for A records target_original_id=B. Thus, deshacer_merge(A) restores A→B, not A→C.
  - **Dynamic stop entities**: compute `entity_document_frequency` periodically (background). Entities with freq > 50% of the corpus → attenuated weight in expansion (`weight / (1 + log10(doc_freq))`). Manual list from the previous phase remains as override. Background computation, not real-time.
  - **Intra-document reconciliation**: asynchronous, does not block indexing ([research] DeepSeek v2). The document is marked `indexed` upon completing embedding+GLiNER. Reconciliation runs in background (APScheduler) and updates a flag `reconciled BOOLEAN DEFAULT false` in documents. Configurable: param `reconcile_entities: bool = true` in registrar_documento. With `false`, reconciliation is skipped. Reconciliation timeout: 10s per document — if exceeded, skip + log warning.
- Rationale: all 3 consultancies agreed — irreversible merge, direct aliases, and aggressive auto-archiving are the main risks of this phase. Candidates + soft merge + reversibility eliminate the risk without losing the capability.

### D5: Document trust tiers with slow decay on tier 3

- Origin: [research] ChatGPT v1 + [research] 3 consultancies v5 (convergence: tier 3 must not have zero decay)
- Decision: same table as the previous phase (`documents.trust_tier SMALLINT DEFAULT 1`). Effect:

  | Tier | base_weight multiplier | source_score Decay |
  |------|--------------------------|-------------------|
  | 0 | ×0.5 | DECAY_DAYS=7 (fast) |
  | 1 | ×1.0 | DECAY_DAYS=14 (normal) |
  | 2 | ×1.5 | DECAY_DAYS=28 (slow) |
  | 3 | ×2.0 | DECAY_DAYS=90 (very slow, NOT infinite) |

- **Change from v1**: tier 3 no longer has "freshness=1.0 always". It has very slow decay (90 days) but NOT infinite. A master plan that changed 90+ days ago DOES penalize memories based on the previous version.
- **Version change** ([research] Gemini): if a tier 3 document has `supersedes_document_id` (it is a new version), only the most recent version inherits tier 3. The previous one drops to tier 1.
- New column: `trust_origin TEXT DEFAULT 'manual'` (preparation for a future phase: manual/inherited/inferred/system, only manual in this phase).
- MCP Tool: `clasificar_documento(document_id, trust_tier)`.

### D6: Deduplication by detection, not by automatic action

- Origin: [my-inference] + [research] 3 consultancies (convergence 3/3: detect + notify, do not archive)
- **Critical change from v1**: do NOT auto-supersede documents. Separate similarity from replacement.
- Decision:
  - `content_fingerprint TEXT` in documents (hash of normalized extracted text).
  - **Identical fingerprint** (exactly the same text): do not re-index, log "duplicate skipped". Only automatic case.
  - **Near-duplicate** (average embedding cosine > 0.92): create entry in new table `related_documents`:
    ```sql
    CREATE TABLE related_documents (
      source_id UUID REFERENCES documents(id),
      target_id UUID REFERENCES documents(id),
      relation_type TEXT CHECK (relation_type IN ('duplicate','near_duplicate','revision_of','supersedes','derived_from')),
      similarity REAL,
      detected_at TIMESTAMPTZ DEFAULT now(),
      confirmed_by INT REFERENCES users(id),
      PRIMARY KEY (source_id, target_id)
    );
    ```
  - SSE event `duplicate_detected` with both document_ids + similarity score.
  - The admin or agent decides: confirm as supersedes (tool `confirmar_relacion_documento`) or ignore.
  - `status='superseded'` only by confirmed human action, never automatic.
  - **content_fingerprint format** ([research] DeepSeek v2): normalization before hashing: lowercase, strip multiple whitespace + line breaks, remove punctuation. SHA-256 of the normalized text.
  - **related_documents limit** ([research] ChatGPT v2): max 20 relations per document. Only top-k by similarity.
  - **Purge** ([research] DeepSeek v2): related_documents without confirmed_by and detected_at > 90 days → automatic purge. Confirmed entries are kept indefinitely.
- Rationale: similar documents are not necessarily replacements. Two PostgreSQL guides can have cosine 0.93 and be distinct valid documents. Auto-superseding removes legitimate knowledge.

### D7: Minimal document versioning (Option A)

- Decision: no change from v1. `document_version INT DEFAULT 1` + `supersedes_document_id UUID NULL`. Counter incremented on re-index. Previous chunks are not preserved (daily pg_dump as snapshot).
- **Explicit debt**: DELETE+INSERT chunks destroys chunk-granular traceability. Option B (preserve historical chunks) deferred.

### D8: Observability — operational + cognitive

- Origin: [my-inference] + [research] 3 consultancies (convergence: cognitive observability missing)
- Decision:
  - **Worker /metrics**: throughput, per-stage times, queue, GPU peak (no change from v1).
  - **Dashboard-ready aggregations**: GET /stats/documents, /stats/ingestion, /stats/search extended.
  - **SSE alerts**: queue > 50, failure rate > 20%, GPU > 90% VRAM.
  - **Per-result explainability** (NEW v4 — [research] ChatGPT v2 + Gemini v2): each SearchResult includes `score_breakdown` with all 5 individual scores + applied multipliers (staleness, trust_tier, chunk_score_factor). Allows the platform owner to debug "why is this result ranked high".
  - **Per-result trust_warnings** (NEW v4 — [research] Gemini v2): if a result is based on an unvalidated auto-link or a stale memory, the field `trust_warnings: string[]` flags it. The agent can warn the user that the information is "second-class".
  - **Cognitive observability** ([research] ChatGPT v1):
    - GET /stats/knowledge: entity_count, alias_candidate_count, merge_count, orphan_entity_count, stale_memory_count, duplicate_candidate_count, graph_density, top_entities_by_degree.
    - These metrics are the foundation for the future phase dashboard. Without them, the design lead designs blind.
  - **Debt**: explicit agent feedback (tool marcar_util) deferred to a future phase.

### D9: Graph-derived tags with limit

- Decision: no conceptual change from v1. Auto-tag by typed entities.
- **Limit**: maximum **10 auto_tags** per memory ([research] DeepSeek 15, Gemini 5, compromise 10). Selected by entity_confidence descending.
- **Normalization**: lowercase, spaces removed (`auto_tag:proyecto:ecodb`).
- Trade-off: 10 may be too many for short memories. Acceptable — the GIN index handles long arrays without degradation.

### D10: Emergent signals — semantic tension, stale marking

- Origin: [user-brief] master plan + [research] 3 consultancies (convergence: reduce automation)
- **Critical changes from v1**:
  1. **Renamed**: "cross-document contradictions" → "semantic tension" ([research] ChatGPT). Embedding similarity does not detect logical contradiction; it detects semantic proximity with temporal difference. Language matters.
  2. **Graph-guided, not brute force** ([research] Gemini): only compare new memory with chunks that share at least 2 entities in the graph. Reduces search space from O(N*M) to O(~100).
  3. **Auto-archive → stale marking** ([research] ChatGPT + DeepSeek): do NOT automatically move to archived_memories. Instead, mark memories as `stale`:
     - Condition: freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days (or NULL and created_at < now() - 60 days).
     - State: new field `memories.staleness TEXT DEFAULT 'active'` CHECK IN ('active','stale','dormant','archived').
     - `stale`: additional 50% weight reduction in GAMR. Visible in search but with indicator.
     - `dormant`: 90% weight reduction. Only appears with `include_dormant=true`.
     - `archived`: only by explicit admin action. Excluded from search. Queryable via admin.
     - **Unarchive**: tool `desarchivar_memoria(memory_id)` → returns to 'active'.
  - **Defined transitions [A2/L1] adversarial**:
     - active → stale: `freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days` (or last_accessed_at IS NULL and created_at < now() - 60 days)
     - stale → dormant: `last_accessed_at < now() - 90 days` (30 additional days without access since stale)
     - dormant → archived: only by admin action via `archivar_memoria(memory_id)`
     - any state → active: access or update resets to active
  - Memories of type 'decision' or 'acuerdo' are NEVER automatically marked stale (regardless of decay or access). Only by admin action.
  - **Reconciliation + auto-link concurrency [Q6]**: sequential, not parallel. Auto-link executes AFTER intra-document reconciliation finishes. This way entities are already reconciled when similar memories are searched.
  - **Background intelligence [Q10]**: **inside the Docker worker** ([research] Gemini v2 — host cron is a portability anti-pattern). Use `APScheduler` integrated in the worker process. Every hour executes in order: stop entities freq update → stale marking → tension detection → purge alias_candidates pending >90d → purge unconfirmed related_documents >90d ([A4] adversarial L2). Serialized with ingestion via internal lock (they do not compete for resources). When migrating to VPS (future phase), there is no external configuration to replicate — everything lives in Docker. Eventual consistency documented: background metrics may have up to 1 hour of delay relative to actual state.
- Rationale: all 3 consultancies agreed — auto-archiving knowledge is dangerous. A critical decision from 6 months ago without accesses may be vital. Gradual marking (active→stale→dormant) provides visibility without destroying knowledge.

---

## 3. Scope

### In scope:
- BM25 as 5th GAMR signal with feature flag + structural filters
- Automatic linking with confidence + validated + reduced weight
- Dynamic weight with decay (floor 0.0) + access as auxiliary signal
- Entity governance: alias candidates, reversible soft merge, merge_log, dynamic stop entities background
- Trust tiers (0-3) with per-tier decay (tier 3 = 90 days, not infinite) + trust_origin
- Deduplication: content_fingerprint + related_documents table + detect/notify
- Minimal document versioning (option A)
- Operational + cognitive observability (GET /stats/knowledge)
- Derived tags with limit 10
- Graph-guided semantic tension + gradual stale marking (active/stale/dormant/archived)
- New MCP tools: validar_link, clasificar_documento, revisar_alias_candidato, merge_entities, deshacer_merge, desarchivar_memoria, confirmar_relacion_documento
- Configurable intra-document reconciliation
- score_breakdown per SearchResult (explainability) + trust_warnings
- Background intelligence: stop entities freq, tension detection, stale marking, candidate/related purge

### Out of scope (conscious debt):
- Scanned PDF OCR (future phase)
- Source code chunking (no use case)
- Async hybrid worker (future phase VPS)
- RRF as alternative to weighted sum (future phase with the design lead)
- Cross-encoder reranking (future phase)
- Exponential decay (evaluate if linear does not fit)
- Explicit agent feedback / marcar_util (future phase dashboard)
- Dynamic / inherited trust tiers (future phase)
- Generative summaries (requires decision from the platform owner on LLM cost)
- Subgraph consolidation (future phase)
- Full document versioning Option B (deferred)
- logical_chunk_id / stable_chunk_hash (deferred)
- parent_section_id (re-index acceptable)
- Multi-hop retrieval (prior research needed)

---

## 4. Success criteria (verifiable)

- CE-1: `buscar(query_text="plan maestro")` with ENABLE_BM25=true returns master plan as top result.
- CE-2: ENABLE_BM25=false → GAMR uses original 4 signals. Results equivalent to pre-phase.
- CE-3: **BM25 calibration protocol** ([A1/L2] adversarial): 20 predefined typical queries. the platform owner + 1 agent evaluate each query with binary verdict "better/same/worse" comparing top-3 with ENABLE_BM25=true vs false. Pass: ≥80% "better" or "same" AND 0 "worse" queries in factual/historical type. If fails: ENABLE_BM25=false + recalibrate weights.
- CE-4: saving a memory similar to a document → auto memory_document_links with link_type='auto', confidence, validated=false.
- CE-5: auto-link with validated=false → source_score × 0.5 in GAMR. After validar_link → × 1.0.
- CE-6: technical memory created 60 days ago, last_accessed_at NULL or > 60 days → freshness_modifier = 0.0, marked stale. Technical memory created 60 days ago BUT last_accessed_at 30 days ago → NOT stale.
- CE-7: agreement memory 60 days old → freshness_modifier = 1.0 (decay_rate=0.0). Never automatically stale.
- CE-8: GLiNER detects entity similar to existing node → entity_alias_candidates created (not a direct alias).
- CE-9: admin approves candidate → alias created in predicate_aliases. Rejects → marked, not re-proposed.
- CE-10: merge_entities → source node status='merged', merged_into=target. GAMR resolves transparently.
- CE-11: deshacer_merge → source node restored to active. References restored.
- CE-12: entity with doc_freq > 50% of corpus → weight automatically attenuated in expansion.
- CE-13: tier 3 document → base_weight ×2.0, decay_days=90. Tier 3 that changed 90+ days ago DOES penalize.
- CE-14: document with supersedes_document_id → only the most recent version inherits high tier.
- CE-15: indexing identical PDF (fingerprint match) → does not re-index, log "duplicate skipped".
- CE-16: near-duplicate detected → related_documents entry + SSE duplicate_detected. Does NOT auto-supersede.
- CE-17: GET /stats/knowledge returns entity_count, alias_candidates, merges, orphans, stale, duplicates, graph_density.
- CE-18: memory with staleness='stale' → 50% reduced weight in GAMR. With 'dormant' → 90% reduced, only with include_dormant=true.
- CE-19: memory of type 'decision' → NEVER automatically marked stale.
- CE-20: desarchivar_memoria → returns to 'active', appears in normal search.
- CE-21: each SearchResult includes `score_breakdown` with all 5 signals + multipliers. the platform owner can see why a result ranks high.
- CE-22: result based on unvalidated auto-link → `trust_warnings: ["unvalidated auto-link"]` in SearchResult.
- CE-23: merge_entities with chain A→B→C → merged_into compressed: A→C, B→C (union-find). GAMR resolves merged_into in SQL before Cypher.
- CE-24: reconciliation of long document → document marked `indexed` immediately, `reconciled=false`. Reconciliation runs in background. If exceeds 10s → skip + log.
- CE-25: last_accessed_at is updated when a memory appears in search results. It is NOT updated by unvalidated auto-links.

---

## 5. Explicit debt

- **RRF vs weighted sum**: weights are heuristic. RRF would be more robust but more complex. Evaluate in a future phase.
- **Exponential decay**: linear may be too aggressive for historical knowledge. Monitor with cognitive observability.
- **access_count underutilized**: relegated to auxiliary signal. Could feed dynamic trust_tiers in a future phase.
- **Auto-learned aliases false positives**: candidates mitigate but do not eliminate. Periodic manual review necessary.
- **related_documents without enforcement**: the table detects but does not prevent indexing duplicates. This is intentional — the system suggests, it does not decide.
- **Expensive reconciliation**: ~5s per large document. Configurable but not globally disableable.
- **Stale marking calibration**: 60 days + 0.3 threshold are estimates. Adjust with real data.
- **Trust tier manual only**: does not scale to 500+ documents. Inherited/inferred in a future phase.
- **BM25 Spanish only**: fulltext index uses to_tsvector('spanish'). Documents in English will have degraded BM25. Multi-language in a future phase.

---

## 6. Consolidated GAMR formula (resolution [L5] adversarial)

All signals and multipliers in one place:

```
# Stage 8 — Composite score (5 signals with feature flags)
if ENABLE_BM25:
    gamr_score = (
        semantic_score * W_semantic[query_type] +
        graph_score    * W_graph[query_type] +
        weight_signal  * W_weight[query_type] +
        freshness_score * W_freshness[query_type] +
        bm25_score     * W_bm25[query_type]
    )
else:
    gamr_score = (original 4-signal formula with previous phase weights)

# Weight signal with decay and staleness
freshness_modifier = max(0.0, 1 - decay_rate * days_since_creation)
staleness_penalty = 1.0 if active, 0.5 if stale, 0.1 if dormant
weight_signal = weight_base * freshness_modifier * staleness_penalty

# Source resolution (Stage 5, previous phase)
source_score = 0.5 + 0.5 * freshness_factor  # DOCUMENT_DECAY_DAYS=14-90 per tier
effective_weight = weight_signal * source_score

# Auto-link modifier (this phase)
if link.validated == false:
    source_score *= 0.5  # unvalidated auto-links weigh half

# Document expansion (Stage 4, previous phase)
doc_edge_weight = documents.base_weight  # default 0.3, configurable per doc
# Budget: MAX_MEMORY_EXPANSION=15, MAX_DOCUMENT_EXPANSION=5
# Max 2 chunks per document via ROW_NUMBER

# Chunk score final (include_documents)
if source_type == 'document_chunk':
    final_score = gamr_score * CHUNK_SCORE_FACTOR  # default 0.7
```

---

## 7. Atomic DDL migration plan (resolution [A5] adversarial)

```sql
BEGIN;

-- 1. Staleness + last_accessed_at in memories
ALTER TABLE memories ADD COLUMN staleness TEXT DEFAULT 'active'
  CHECK (staleness IN ('active','stale','dormant','archived'));
ALTER TABLE memories ADD COLUMN last_accessed_at TIMESTAMPTZ;

-- 2. Auto-link columns in memory_document_links
ALTER TABLE memory_document_links ADD COLUMN confidence REAL;
ALTER TABLE memory_document_links ADD COLUMN validated BOOLEAN DEFAULT false;

-- 3. Trust + dedup + reconciled in documents
ALTER TABLE documents ADD COLUMN trust_origin TEXT DEFAULT 'manual';
ALTER TABLE documents ADD COLUMN content_fingerprint TEXT;
ALTER TABLE documents ADD COLUMN document_version INT DEFAULT 1;
ALTER TABLE documents ADD COLUMN supersedes_document_id UUID REFERENCES documents(id);
ALTER TABLE documents ADD COLUMN reconciled BOOLEAN DEFAULT false;

-- 4. BM25 index on document_chunks
CREATE INDEX IF NOT EXISTS idx_dc_fulltext
  ON document_chunks USING gin (to_tsvector('spanish', content));

-- 5. Entity alias candidates
CREATE TABLE IF NOT EXISTS entity_alias_candidates (
  id SERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  target_node_id BIGINT NOT NULL REFERENCES nodes(id),  -- nodes is a standard SQL table (previous phase §1.6)
  confidence REAL NOT NULL,
  occurrences INT DEFAULT 1,
  sample_contexts TEXT[],
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','archived')),
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  reviewed_by INT REFERENCES users(id)
);

-- 6. Entity merge log
CREATE TABLE IF NOT EXISTS entity_merge_log (
  id SERIAL PRIMARY KEY,
  source_node_id BIGINT NOT NULL,
  target_node_id BIGINT NOT NULL,       -- final root post-compression
  target_original_id BIGINT NOT NULL,   -- direct target pre-compression (for undo)
  merged_by INT REFERENCES users(id),
  reason TEXT,
  merged_at TIMESTAMPTZ DEFAULT now(),
  undone_at TIMESTAMPTZ
);

-- 7. Soft merge columns in nodes
ALTER TABLE nodes ADD COLUMN status TEXT DEFAULT 'active'
  CHECK (status IN ('active','merged'));
ALTER TABLE nodes ADD COLUMN merged_into BIGINT REFERENCES nodes(id);
CREATE INDEX IF NOT EXISTS idx_nodes_merged ON nodes(merged_into) WHERE status='merged';

-- 8. Related documents
CREATE TABLE IF NOT EXISTS related_documents (
  source_id UUID REFERENCES documents(id),
  target_id UUID REFERENCES documents(id),
  relation_type TEXT CHECK (relation_type IN ('duplicate','near_duplicate','revision_of','supersedes','derived_from')),
  similarity REAL,
  detected_at TIMESTAMPTZ DEFAULT now(),
  confirmed_by INT REFERENCES users(id),
  PRIMARY KEY (source_id, target_id)
);
CREATE INDEX IF NOT EXISTS idx_related_source ON related_documents(source_id);
CREATE INDEX IF NOT EXISTS idx_related_target ON related_documents(target_id);

COMMIT;
```

Prior pg_dump mandatory. Rollback: inverse DROP/ALTER script available. New tables are empty — no data risk.

---

## 8. Questions the Adversarial should ask (Loop 2)

1. **soft merge overhead**: GAMR has to resolve `merged_into` for each node in expansion. With 100 merges, that is 100 redirects per search. Latency impact?
2. **staleness vs weight**: a stale memory has freshness_modifier < 0.3 AND 50% reduced weight. Is the double penalty intentional or excessive?
3. **related_documents without action**: the table detects near-duplicates but if nobody reviews, it grows indefinitely. Is there a cleanup mechanism?
4. **BM25 on document_chunks**: the GIN fulltext index does not exist on document_chunks (only on memories). It needs to be created. DDL migration?
5. **entity_alias_candidates volume**: with 1000 documents, GLiNER can generate hundreds of candidates. Is there automatic purging of unreviewed candidates?
6. **Intra-doc reconciliation + auto-link**: both create relationships automatically. Do they execute sequentially or in parallel? Can they produce contradictory results?
7. **trust_origin column**: only 'manual' in this phase. Is it worth creating the column now or is it YAGNI?
8. **multiple feature flags**: BM25 has a flag. Should auto-link, decay, auto-tags also have one?
9. **staleness field in memories**: another DDL migration. Atomic with the rest of this phase's changes?
10. **Background intelligence**: reconciliation, stop freq, tension detection, stale marking. Who executes them? The ingestion worker or a separate process?
