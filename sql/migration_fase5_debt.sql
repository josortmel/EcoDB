BEGIN;

-- VS5-1: Prevent document self-supersede (circular reference DoS)
ALTER TABLE documents ADD CONSTRAINT chk_no_self_supersede
  CHECK (supersedes_document_id IS NULL OR supersedes_document_id != id);

-- VS5-2: Prevent self-relation in related_documents
ALTER TABLE related_documents ADD CONSTRAINT chk_no_self_relation
  CHECK (source_id != target_id);

-- VS5-3: Prevent self-merge in merge log
ALTER TABLE entity_merge_log ADD CONSTRAINT chk_no_self_merge
  CHECK (source_node_id != target_node_id);

-- VS5-4: Prevent node merged into itself
ALTER TABLE nodes ADD CONSTRAINT chk_no_self_merged_into
  CHECK (merged_into IS NULL OR merged_into != id);

-- VS5-7: Content fingerprint must be exactly 64 chars (SHA-256 hex)
ALTER TABLE documents ADD CONSTRAINT chk_fingerprint_len
  CHECK (content_fingerprint IS NULL OR length(content_fingerprint) = 64);

-- F5B0-07: Confidence/similarity range [0,1]
ALTER TABLE entity_alias_candidates ADD CONSTRAINT chk_confidence_range
  CHECK (confidence BETWEEN 0 AND 1);
ALTER TABLE related_documents ADD CONSTRAINT chk_similarity_range
  CHECK (similarity IS NULL OR similarity BETWEEN 0 AND 1);
ALTER TABLE memory_document_links ADD CONSTRAINT chk_mdl_confidence_range
  CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);

-- F5B0-04: Indexes for entity_alias_candidates query patterns
CREATE INDEX IF NOT EXISTS idx_eac_source_name ON entity_alias_candidates (source_name);
CREATE INDEX IF NOT EXISTS idx_eac_target_node ON entity_alias_candidates (target_node_id);
CREATE INDEX IF NOT EXISTS idx_eac_pending ON entity_alias_candidates (status) WHERE status = 'pending';

-- F5B0-05: Indexes for entity_merge_log
CREATE INDEX IF NOT EXISTS idx_eml_source ON entity_merge_log (source_node_id);
CREATE INDEX IF NOT EXISTS idx_eml_target ON entity_merge_log (target_node_id);

-- F5B0-08: supersedes ON DELETE SET NULL
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_supersedes_document_id_fkey;
ALTER TABLE documents ADD CONSTRAINT documents_supersedes_document_id_fkey
  FOREIGN KEY (supersedes_document_id) REFERENCES documents(id) ON DELETE SET NULL;

-- F5B0-09: Drop redundant idx_related_source (PK already covers source_id)
DROP INDEX IF EXISTS idx_related_source;

-- VS5-12: Limit sample_contexts array size
ALTER TABLE entity_alias_candidates ADD CONSTRAINT chk_sample_contexts_len
  CHECK (sample_contexts IS NULL OR array_length(sample_contexts, 1) <= 20);

-- Update schema version
INSERT INTO schema_version (version, notes)
VALUES ('5.0.1', 'Fase 5 debt: self-reference CHECKs, confidence ranges, indexes, ON DELETE SET NULL supersedes.');

COMMIT;
