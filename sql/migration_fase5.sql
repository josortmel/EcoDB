-- ============================================================================
-- EcoDB — Fase 5 DDL Migration: Gobernanza Cognitiva
-- 8 pasos en transacción atómica.
--
-- Precondiciones:
--   - Fases 1-4 completas (schema 4.0.1)
--   - pg_dump snapshot tomado ANTES de ejecutar
--
-- Ejecutar:
--   docker exec -i ecodb-postgres psql -U ecodb -d ecodb < sql/migration_fase5.sql
--
-- Rollback:
--   pg_restore desde snapshot pre-migración
--
-- Ref: Brief v4.1-final §7, Plan construcción Fase 5 §2 Tarea 5.0
-- ============================================================================

BEGIN;

-- Paso 1: Staleness en memories (last_accessed already exists from Fase 1 — reuse it)
ALTER TABLE memories ADD COLUMN staleness TEXT DEFAULT 'active'
  CHECK (staleness IN ('active', 'stale', 'dormant', 'archived'));

-- Paso 2: Auto-link columns en memory_document_links
ALTER TABLE memory_document_links ADD COLUMN confidence REAL;
ALTER TABLE memory_document_links ADD COLUMN validated BOOLEAN DEFAULT false;

-- Paso 3: Trust + dedup + versionado + reconciled en documents
ALTER TABLE documents ADD COLUMN trust_origin TEXT DEFAULT 'manual';
ALTER TABLE documents ADD COLUMN content_fingerprint TEXT;
ALTER TABLE documents ADD COLUMN document_version INT DEFAULT 1;
ALTER TABLE documents ADD COLUMN supersedes_document_id UUID REFERENCES documents(id);
ALTER TABLE documents ADD COLUMN reconciled BOOLEAN DEFAULT false;

-- Paso 4: Índice BM25 fulltext en document_chunks
CREATE INDEX IF NOT EXISTS idx_dc_fulltext
  ON document_chunks USING gin (to_tsvector('spanish', content));

-- Paso 5: Entity alias candidates
CREATE TABLE IF NOT EXISTS entity_alias_candidates (
  id SERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  target_node_id BIGINT NOT NULL REFERENCES nodes(id),
  confidence REAL NOT NULL,
  occurrences INT DEFAULT 1,
  sample_contexts TEXT[],
  status TEXT DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'archived')),
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  reviewed_by INT REFERENCES users(id)
);

-- Paso 6: Entity merge log
CREATE TABLE IF NOT EXISTS entity_merge_log (
  id SERIAL PRIMARY KEY,
  source_node_id BIGINT NOT NULL,
  target_node_id BIGINT NOT NULL,
  target_original_id BIGINT NOT NULL,
  merged_by INT REFERENCES users(id),
  reason TEXT,
  merged_at TIMESTAMPTZ DEFAULT now(),
  undone_at TIMESTAMPTZ
);

-- Paso 7: Soft merge columns en nodes
ALTER TABLE nodes ADD COLUMN status TEXT DEFAULT 'active'
  CHECK (status IN ('active', 'merged'));
ALTER TABLE nodes ADD COLUMN merged_into BIGINT REFERENCES nodes(id);
CREATE INDEX IF NOT EXISTS idx_nodes_merged
  ON nodes (merged_into) WHERE status = 'merged';

-- Paso 8: Related documents
CREATE TABLE IF NOT EXISTS related_documents (
  source_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  target_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  relation_type TEXT
    CHECK (relation_type IN ('duplicate', 'near_duplicate', 'revision_of', 'supersedes', 'derived_from')),
  similarity REAL,
  detected_at TIMESTAMPTZ DEFAULT now(),
  confirmed_by INT REFERENCES users(id),
  PRIMARY KEY (source_id, target_id)
);
CREATE INDEX IF NOT EXISTS idx_related_source ON related_documents (source_id);
CREATE INDEX IF NOT EXISTS idx_related_target ON related_documents (target_id);

-- Version
INSERT INTO schema_version (version, notes)
VALUES ('5.0.0', 'Fase 5 Gobernanza Cognitiva: staleness, auto-link confidence, trust tiers, BM25 index, entity governance, related documents.');

COMMIT;
