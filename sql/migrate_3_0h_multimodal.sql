-- Migration: multimodal support + node canonicalization.
-- Adds memory_embeddings table (1:N embeddings per memory).
--
-- WARNING: This migration is destructive (moves embeddings, modifies nodes table).
-- Review carefully before executing. Rollback section at the end.
--
-- Ejecutar: docker exec ecodb-postgres psql -U ecodb -d ecodb -f /path/migrate_3_0h_multimodal.sql
-- Rollback: ver sección ROLLBACK al final.

BEGIN;

-- -------------------------------------------------------------------------
-- 1. Tabla memory_embeddings (1:N — una memoria puede tener N embeddings)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    memory_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    modality    TEXT NOT NULL CHECK (modality IN ('text', 'image', 'audio')),
    embedding   vector(512) NOT NULL,
    source_ref  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (memory_id, modality)
);

CREATE INDEX IF NOT EXISTS idx_me_embedding ON memory_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

CREATE INDEX IF NOT EXISTS idx_me_memory ON memory_embeddings (memory_id);
CREATE INDEX IF NOT EXISTS idx_me_modality ON memory_embeddings (modality);

-- -------------------------------------------------------------------------
-- 2. Migrar embeddings existentes de memories.embedding → memory_embeddings
-- -------------------------------------------------------------------------
INSERT INTO memory_embeddings (memory_id, modality, embedding, source_ref, created_at)
SELECT id, 'text', embedding, NULL, created_at
FROM memories
WHERE embedding IS NOT NULL
ON CONFLICT (memory_id, modality) DO NOTHING;

-- -------------------------------------------------------------------------
-- 3. Canonización nodos (3.0g fusionada) — name_canonical en tabla nodes
-- -------------------------------------------------------------------------
-- PRE-CHECK OBLIGATORIO antes de ejecutar (BC4 adv-code + VS3 adv-seg):
--   SELECT lower(name) AS canonical, count(*), array_agg(name)
--   FROM nodes GROUP BY lower(name) HAVING count(*) > 1;
-- Si devuelve filas → resolver duplicados manualmente ANTES de esta migración
-- (merge nodos: UPDATE triples SET subject_id/object_id, DELETE nodo duplicado).
-- Si devuelve 0 filas → safe para continuar.

ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name_canonical TEXT
    GENERATED ALWAYS AS (lower(name)) STORED;

CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_canonical
    ON nodes (name_canonical);

-- -------------------------------------------------------------------------
-- 4. Verificación post-migración
-- -------------------------------------------------------------------------
-- Ejecutar manualmente tras la migración:
--   SELECT count(*) FROM memory_embeddings;  -- debe coincidir con count(*) FROM memories WHERE embedding IS NOT NULL
--   SELECT count(*) FROM nodes WHERE name_canonical IS NULL;  -- debe ser 0
--   SELECT name, name_canonical FROM nodes LIMIT 10;  -- verificar canonización

-- -------------------------------------------------------------------------
-- ROLLBACK (si algo falla post-deploy):
--   DROP INDEX IF EXISTS idx_nodes_canonical;
--   ALTER TABLE nodes DROP COLUMN IF EXISTS name_canonical;
--   DROP TABLE IF EXISTS memory_embeddings;
-- -------------------------------------------------------------------------

COMMIT;
