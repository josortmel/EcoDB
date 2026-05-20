-- ============================================================================
-- EcoDB — Fase 4 DDL Migration (Tarea 4.0)
-- 8 pasos en transacción atómica.
--
-- Precondiciones:
--   - Fases 1-3 completas
--   - Tablas documents, document_chunks, document_entity_links VACÍAS
--   - pg_dump snapshot tomado ANTES de ejecutar
--
-- Ejecutar:
--   docker exec -i ecodb-postgres psql -U ecodb -d ecodb < sql/migration_fase4.sql
--
-- Rollback:
--   pg_restore desde snapshot pre-migración
-- ============================================================================

BEGIN;

-- Paso 1: Extender CHECK constraint documents.status para 'deleted'
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('queued', 'processing', 'indexed', 'failed', 'deleted'));

-- Paso 2: Nuevas columnas en documents
ALTER TABLE documents ADD COLUMN retry_count INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN processing_started_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN processing_metrics JSONB;
ALTER TABLE documents ADD COLUMN base_weight REAL NOT NULL DEFAULT 0.3;

-- Paso 3: DROP documents.embedding + índice HNSW
-- D3 Brief: Solo chunks se embeden. Embedding a nivel documento no aporta.
DROP INDEX IF EXISTS idx_documents_embedding;
ALTER TABLE documents DROP COLUMN IF EXISTS embedding;

-- Paso 4: section_path en document_chunks
ALTER TABLE document_chunks ADD COLUMN section_path TEXT;

-- Paso 5: Cambiar PK document_entity_links para incluir chunk_id granular
-- Tabla está vacía → safe to drop+recreate PK.
-- chunk_id pasa de nullable a NOT NULL (cada entity link debe apuntar a un chunk).
ALTER TABLE document_entity_links DROP CONSTRAINT document_entity_links_pkey;
ALTER TABLE document_entity_links ALTER COLUMN chunk_id SET NOT NULL;
ALTER TABLE document_entity_links ADD PRIMARY KEY (document_id, entity_node_id, chunk_id);
-- FK CASCADE: si se borran chunks (re-indexación), los entity links se borran.
ALTER TABLE document_entity_links DROP CONSTRAINT IF EXISTS document_entity_links_chunk_id_fkey;
ALTER TABLE document_entity_links ADD CONSTRAINT document_entity_links_chunk_id_fkey
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE;

-- Paso 6: Índice en memory_document_links(memory_id)
-- Acelera JOINs de GAMR Etapa 5 (source resolution por memoria).
CREATE INDEX IF NOT EXISTS idx_mdl_memory ON memory_document_links (memory_id);

-- Paso 7: Índice en document_chunks(document_id)
-- Acelera lookup de chunks por documento (leer_documento, re-indexación).
CREATE INDEX IF NOT EXISTS idx_dc_document_id ON document_chunks (document_id);

-- Paso 8: Tabla stop_entities
-- Entidades que NO generan nodos AGE ni document_entity_links.
-- Seed manual por Eco antes de Tarea 4.5.
CREATE TABLE stop_entities (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    reason      TEXT,
    created_by  INT NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (name_normalized)
);

-- No explicit index needed: UNIQUE(name_normalized) creates implicit btree (BC3 adv-code)

-- Schema version bump
INSERT INTO schema_version (version, notes)
VALUES ('4.0.0', 'Fase 4 ingesta documentos: status deleted, retry/metrics/base_weight, DROP doc embedding, section_path chunks, PK entity_links granular, stop_entities table');

COMMIT;
