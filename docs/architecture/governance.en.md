# Brief v3 — EcoDB phaseb: Knowledge Graph Governance

*the research lead. May 11, 2026. Architect. Post-Loop 1 adversarial v1 (23 items) + adversarial v2 (17 items) + 6 external reviews (3 per version). All REQUIRED resolved.*

---

## 1. Context and motivation

EcoDB is the organization's unified memory system. PostgreSQL 16 + pgvector + Apache AGE. In production since May 9, 2026 (day 67). Phases 1-2 complete. phasea nearly complete.

The graph has a structural problem. Post-purge on May 11: 1040 nodes, 954 triples, 720 unique predicates. Predicates/triples ratio of 0.75. The graph still lacks a common vocabulary.

Three external models (ChatGPT, Gemini, DeepSeek) converged: EcoDB needs knowledge governance — predicates with ontological metadata, validation pipeline, node typing, temporality, and separation of facts vs beliefs.

**Why now:** phasea (GAMR Stage 4, graph expansion) amplifies garbage if there is no governance. phase (documents) will ingest more data. Govern before growing.

---

## 2. Design decisions (with traceability)

### D1: Closed vocabulary — target 100 predicates, cap 130 with quarterly review
- Origin: [research] 3/3 models + [user-brief] 4/4 peers + [research] DeepSeek review
- Reason: 720 predicates for 954 triples is unsustainable. A closed vocabulary forces consistency.
- Trade-off: loses free expressiveness. Mitigated by pending_predicates table (see D11).
- Limit: each new predicate requires 3+ real triples. Quarterly review if >100 are needed.

### D2: Eliminate "es" — split into instancia_de, tipo_de, rol_de, alias_de
- Origin: [research] Convergence 3/3 external models
- Reason: "es" absorbs identity, type, role, equivalence, alias.
- Trade-off: four predicates where there was one.

### D3: Epistemological cluster — cree, afirma, sospecha, verifica, contradice
- Origin: [research] Convergence 3/3 external models
- Reason: multi-agent system where beliefs must not be persisted as truths.
- Trade-off: complexity in writing — the agent chooses between sabe/cree/afirma/sospecha.

### D4: Causality and transformation
- Origin: [research] ChatGPT + DeepSeek (2/3)
- Predicates: causa, provoca, habilita, bloquea, se_convierte_en, evoluciona_a, migra_a, fusiona_con.
- Reason: without causality, the graph describes but does not explain.

### D5: Ontological metadata per predicate
- Origin: [research] ChatGPT + DeepSeek (2/3)
- Fields: symmetric (bool), inverse_of (text nullable), transitive (bool), domain_types (text[]), range_types (text[]).
- Reason: avoids duplicating triples for inverses. Enables future inference.

### D6: Temporality as edge properties
- Origin: [research] Convergence 3/3
- New fields in triples table: valid_from (timestamptz nullable), valid_to (timestamptz nullable), assertion_confidence (real, 0-1, confidence in the fact), source_agent (text nullable).
- For migrated triples: valid_from = original created_at, source_agent = 'MIGRACION_LEGACY'.
- Note: assertion_confidence measures certainty of the FACT. It is distinct from mapper_confidence which measures certainty of the NORMALIZATION PROCESS (see D8).

### D7: Node typing — lazy typing
- Origin: [research] ChatGPT + Gemini + [research] DeepSeek review (lazy typing)
- Implementation: new nodes require type at creation. Existing nodes type = 'unknown'. Prioritize manual classification of the top 20% by connection degree.
- Available types: persona, agente_ia, organizacion, lugar, producto, proyecto, tecnologia, concepto, artefacto, evento, unknown.
- Note: the original 6 categories from entity_dictionary are expanded to 11 to cover technical nodes (Docker, PostgreSQL → tecnologia) and narrative nodes (paladin, magia → concepto).
- Type validation is PERMISSIVE for 'unknown' nodes (any predicate allowed). Strict only for nodes with an assigned type.

### D8: Hybrid normalization pipeline — 5 stages, reordered
- Origin: [research] ChatGPT (5-stage pipeline) + Gemini (cache) + DeepSeek (ANN) + adversarial A4 (reorder)
- Corrected order (embeddings at the end, not in the middle):
  1. Lexical normalization (lowercase, snake_case, trim) — <1ms
  2. Lexeme cache + manual aliases by domain — <1ms if hit
  3. Structural type validation (domain_types/range_types from the matrix) — <1ms
  4. Embedding similarity with ANN index (pgvector on predicate_embeddings) — <50ms
  5. Human-in-the-loop: if mapper_confidence < 0.70 → triple is saved with needs_review=true + original_predicate preserved
- Latency budget: <500ms total per save_triple (full pipeline included).
- Low-confidence CE: mapper_confidence < 0.70 → needs_review=true, original_predicate preserved in metadata, triple accessible but flagged. mapper_confidence >= 0.70 → automatic mapping.
- Alias table has column domain (text nullable). Global alias if domain=null. Specific alias if domain='tecnico'/'narrativo'/'diseno'.

### D9: Domain authority — SUGGESTION for the human, not an automatic rule
- Origin: [research] Gemini proposal + [research] DeepSeek + ChatGPT review (both recommend guidance, not automation) + adversarial C3/A5 (contradiction with scope)
- Post-adversarial correction: original D9 stated "wins for global reasoning". That implied automation. Corrected: authority is predicate metadata (authority_agents text[] in predicates_canonical). When GAMR detects a contradiction, it FLAGS it with "agent X has suggested authority over this cluster". The human resolves. The system does NOT resolve automatically.
- Trade-off: requires human intervention for contradictions. Acceptable in single-tenant.

### D10: Keep protege, escribe, gobierna
- Origin: [my-inference] + 4/4 peers
- Reason: real semantic nuances, not theoretical. The graph exists to capture nuances.

### D11: Table pending_predicates for unmapped predicates (NEW)
- Origin: [research] DeepSeek review
- Reason: during migration, predicates that do not map with sufficient confidence are not discarded. They go to pending_predicates with usage frequency. If they reach 3+ uses, they are evaluated for vocabulary inclusion. Otherwise, they are archived.

### D12: Ontology versioning (NEW)
- Origin: [research] DeepSeek review + ChatGPT review + adversarial L5
- Implementation: each predicate has state (experimental → candidate → approved → deprecated → archived → forbidden) + deprecated_since (timestamptz) + replaced_by (text nullable).
- Deprecated predicates are not deleted. Historical triples with a deprecated predicate are queried via COALESCE(replaced_by, predicate).
- Without versioning, the first predicate merge breaks historical queries with no rollback.

### D13: Inverse inference as a PostgreSQL view from day 1 (NEW)
- Origin: [research] Gemini review + adversarial R2
- Implementation: SQL view combining the direct triple with its inverse using inverse_of from predicates_canonical. ~10 lines of SQL. No data duplication.
- The view includes an `inferred BOOLEAN` field — true for inferred edges, false for explicit ones. Agents never see an inferred edge indistinguishable from an explicit one.
- GAMR and endpoints using the view propagate the inferred field so the agent knows it is an inference, not a stored fact.
- Reason: deferring this was unjustified debt — the cost is minimal and the benefit is immediate bidirectional navigation.

### D14: Separate core ontology vs domain ontology (NEW)
- Origin: [research] ChatGPT review
- Core (very stable, rare changes): parte_de, depende_de, causa, instancia_de, tipo_de, crea, usa...
- Domain (flexible, evolves by domain): ama, simboliza, usa_paleta, antagonista_de...
- Benefit: global stability with local flexibility. Core is not modified without formal review. Domain evolves per domain with quarterly review.
- Fields in DDL: `ontology_layer` = 'core' or 'domain'. `cluster` = semantic group (e.g. "Amor y deseo"). `domain` = knowledge area (e.g. "narrativo", "tecnico", "diseno") — nullable for universal predicates. All three fields have distinct semantics and are not redundant.
- Formal core review: requires a written proposal + approval from the platform owner + review by the peer with authority over the affected domain. Minimum 1 week between proposal and application. Domain: the peer with authority proposes, the platform owner approves, immediate application.

---

## 3. Scope

### In scope:
- DDL for predicates_canonical table with complete ontological metadata
- DDL for predicate_aliases table (variant → canonical, with domain)
- DDL for pending_predicates table (unmapped predicates, with frequency)
- New fields in triples table: valid_from, valid_to, assertion_confidence, source_agent
- New fields in nodes table: type (text, default 'unknown')
- Column needs_review (bool) + mapper_confidence (real) + original_predicate (text) in triples
- SQL view for bidirectional inverse inference
- Normalization pipeline in save_triple of the MCP (5 reordered stages)
- Seed of the vocabulary with ~100 agreed predicates + metadata
- Migration of 720 current predicates to canonical vocabulary (with rollback)
- Manual classification of top 20% nodes by degree (rest = 'unknown')
- Endpoint GET /graph/triples?needs_review=true (minimum viable for governance)
- Ontology Console as a phase task (Electron dashboard with the design lead)

### Out of scope (conscious debt):
- Automatic reasoning over transitivity/symmetry (metadata is stored but not exploited in queries)
- Automatic contradiction resolution (system flags + suggests authority, human resolves)
- Differentiated thresholds per cluster (during the phase without thresholds, the mapper may commit higher-severity errors in identity/technical clusters than in emotional ones — documented as accepted risk)
- Reification of complex relationships (documented rule: "if a relationship needs >3 own attributes, it should be a node" — communicated to agents even though implementation is deferred)
- Semantic budgets per domain (operational process, not code)
- Automatic archival of expired triples >90 days (future monthly process)

---

## 4. DDL for predicates_canonical (resolves adversarial L1)

```sql
CREATE TABLE predicates_canonical (
  name            TEXT PRIMARY KEY,
  cluster         TEXT NOT NULL,
  ontology_layer  TEXT NOT NULL CHECK (ontology_layer IN ('core', 'domain')),
  domain          TEXT,
  description     TEXT,
  symmetric       BOOLEAN NOT NULL DEFAULT false,
  inverse_of      TEXT REFERENCES predicates_canonical(name) DEFERRABLE INITIALLY DEFERRED,
  transitive      BOOLEAN NOT NULL DEFAULT false,
  domain_types    TEXT[] NOT NULL DEFAULT '{}',
  range_types     TEXT[] NOT NULL DEFAULT '{}',
  authority_agents TEXT[] NOT NULL DEFAULT '{}',
  state           TEXT NOT NULL DEFAULT 'approved'
                  CHECK (state IN ('experimental','candidate','approved','deprecated','archived','forbidden')),
  deprecated_since TIMESTAMPTZ,
  replaced_by     TEXT REFERENCES predicates_canonical(name),
  embedding          vector(512),
  embedding_model    TEXT DEFAULT 'jina-v4',
  embedding_version  TEXT,
  embedding_updated  TIMESTAMPTZ,
  created_at         TIMESTAMPTZ DEFAULT now(),
  updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_pc_cluster ON predicates_canonical (cluster);
CREATE INDEX idx_pc_state ON predicates_canonical (state);
CREATE INDEX idx_pc_embedding ON predicates_canonical
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
```

```sql
CREATE TABLE predicate_aliases (
  alias       TEXT NOT NULL,
  canonical   TEXT NOT NULL REFERENCES predicates_canonical(name),
  domain      TEXT,
  auto_learned BOOLEAN DEFAULT false,
  confirmations INT DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (alias, domain)
);
-- ACL: super-only write for manual aliases.
-- auto_learned is a field reserved for phase (learning by feedback).
-- In phaseb, auto_learned is always false and confirmations is always 0.
```

```sql
CREATE TABLE pending_predicates (
  predicate      TEXT PRIMARY KEY,
  frequency      INT DEFAULT 1,
  status         TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','promoted','archived','rejected')),
  reviewed_by    INT REFERENCES users(id),
  first_seen     TIMESTAMPTZ DEFAULT now(),
  last_seen      TIMESTAMPTZ DEFAULT now(),
  archive_after  TIMESTAMPTZ DEFAULT (now() + INTERVAL '90 days'),
  sample_triples JSONB DEFAULT '[]'
);
-- TTL: monthly process moves to 'archived' those pending with
-- frequency < 3 AND last_seen < now() - 90 days.
-- 'promoted' = moved to predicates_canonical.
-- 'rejected' = discarded with documented reason.
```

---

## 5. Success criteria (verifiable)

- CE-1: SELECT count(*) FROM predicates_canonical WHERE state = 'approved' returns between 90 and 130
- CE-2: Each approved predicate has symmetric, inverse_of, transitive, domain_types, range_types, cluster, ontology_layer not null
- CE-3: SELECT count(*) FROM triples WHERE predicate NOT IN (SELECT name FROM predicates_canonical WHERE state IN ('approved','deprecated')) AND predicate NOT IN (SELECT predicate FROM pending_predicates) returns 0. NOTE: triples with a predicate in pending_predicates do NOT participate in canonical GAMR reasoning (Stage 4 expansion excludes them). pending is quarantine, not a vocabulary extension
- CE-4: save_triple with free predicate "hecho_por" normalizes to "crea" and the response includes original_predicate + canonical_predicate + mapper_confidence
- CE-5: save_triple with predicate "ama" + subject type "tecnologia" + object type "persona" returns a validation error (node with assigned type). With subject type "unknown" → passes (permissive)
- CE-6: SELECT count(*) FROM nodes WHERE type IS NULL returns 0 (all have a type, even if 'unknown')
- CE-7: valid_from, valid_to, assertion_confidence, source_agent exist in triples. New triples fill source_agent as mandatory. Migrated triples have source_agent = 'MIGRACION_LEGACY'
- CE-8: Full save_triple pipeline < 500ms measured end-to-end
- CE-9: save_triple with mapper_confidence < MAPPER_THRESHOLD (configurable, default 0.70 provisional — to be calibrated with a 50-triple pilot post-seed) saves the triple with needs_review=true + original_predicate preserved. The threshold is an env var, not hardcoded. Tests use the env var value, not a literal
- CE-10: SQL inverse view works: querying hijo_de also returns padre_de inferred WITH field inferred=true
- CE-11: Operational target for unknown nodes: <50% at phaseb launch, <30% within 30 days. Top 20% by degree manually classified before launch
- CE-12: save_triple MCP response includes mapper_confidence + original_predicate + canonical_predicate when normalization occurs (updated MCP contract)

---

## 6. Rollback plan for migration (resolves adversarial L3)

Before migrating predicates:
1. pg_dump snapshot of tables triples + nodes + predicate_embeddings
2. Migration script generates a dry-run report: how many map with confidence >= 0.70, how many go to pending_predicates, how many do not map
3. Abort criterion: if >25% of triples do not map with confidence >= 0.70, abort and manual review
4. If abort: restore from snapshot, review vocabulary, retry
5. Migrated triples preserve original_predicate in JSONB metadata

---

## 7. Explicit debt

- Differentiated thresholds per cluster: during the phase without thresholds, errors in identity/technical clusters (instancia_de vs tipo_de) have higher severity than errors in emotional clusters (quiere vs ama). Accepted risk, documented.
- Complete node classification: top 20% by degree manually classified. Rest = 'unknown' with permissive validation. Complete classification is gradual.
- Reification: rule "if a relationship needs >3 attributes → node" documented and communicated to agents. Implementation deferred until a real case arises.
- Archival of expired triples: future monthly process (historical_triples).
- Ontology Console: phase, the design lead designs UI. Meanwhile: endpoint GET /graph/triples?needs_review=true + direct queries.

---

## 8. Loop 1 closure — adversarial item resolution

### Adversarial v1 (23 items): 7 REQUIRED resolved in Brief v2
### Adversarial v2 (17 items): 7 REQUIRED resolved in Brief v3

| Item | Resolution |
|------|-----------|
| A1 (FK DEFERRABLE) | APPLIED — DDL corrected |
| A2 (CE-3 pending as canonical) | APPLIED — explicit note: pending excluded from GAMR |
| A3 (CE-9 threshold hardcoded) | APPLIED — configurable via env var, provisional |
| A4 (embedding provenance) | APPLIED — embedding_model + embedding_version in DDL |
| C1 (auto_learned scope) | APPLIED — documented as reserved for phase |
| L1 (alias ACL) | APPLIED — super-only documented |
| L2 (pending TTL) | APPLIED — states + archive_after 90 days |

### SOFT resolved in Brief v3
| Item | Resolution |
|------|-----------|
| C2 (inferred marker) | APPLIED — inferred field in view + CE-10 |
| C3 (domain vs cluster) | APPLIED — semantics clarified in D14 |
| L3 (formal core review) | APPLIED — process defined in D14 |
| L4 (unknown target) | APPLIED — CE-11: <50% at launch, <30% in 30 days |
| S3 (MCP response contract) | APPLIED — CE-12 |
| R3 (unknown target) | APPLIED — CE-11 |
| R4 (inferred marker) | APPLIED — D13 + CE-10 |

### DEFERRED with justification
| Item | Reason |
|------|-------|
| A5 (node degree distribution) | Calculated in verification_checkpoint Loop 2. Not Brief data |
| S1 (seed predicate embeddings) | Implicit prerequisite of the seed — executed as part of the task |
| S2 (narrative vocabulary coverage) | Seed vocabulary validated with Eco before execution. Not a Brief blocker |
| R2 (split table into 3) | With 100 predicates, one table is manageable. If it reaches 500+, refactor |

## 9. Questions for Loop 2 (Spec + Plan)

1. The inverse view with the inferred field — performance with 10k triples? Materialize if necessary?
2. The normalization pipeline — concrete implementation in the MCP's server.py. Where does each stage live?
3. The seed of ~100 predicates — complete list with metadata. Who produces it? Eco + the research lead + the design lead?
4. 50-triple pilot to calibrate threshold — before or after mass migration?
5. GAMR Stage 4 excludes pending — change in search.py or in the MCP?
