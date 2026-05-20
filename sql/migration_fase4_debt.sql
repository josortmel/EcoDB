-- ============================================================================
-- EcoDB — Fase 4 Debt Cleanup DDL
-- Constraints missed in original migration.
-- ============================================================================

BEGIN;

-- F4-3: processing_metrics JSONB size limit (prevent storage DoS)
ALTER TABLE documents ADD CONSTRAINT chk_processing_metrics_size
    CHECK (processing_metrics IS NULL OR pg_column_size(processing_metrics) < 65536);

-- F4-4: section_path length limit (prevent storage DoS + future path traversal)
ALTER TABLE document_chunks ADD CONSTRAINT chk_section_path_len
    CHECK (section_path IS NULL OR char_length(section_path) <= 500);

-- schema_version_target cosmetic fix
INSERT INTO schema_version (version, notes)
VALUES ('4.0.1', 'Fase 4 debt cleanup: processing_metrics size limit, section_path length limit');

COMMIT;
