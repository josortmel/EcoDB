-- metadata JSONB + indices + ALTER TYPE

-- metadata JSONB con NOT NULL, cap 64KB, GIN index
ALTER TABLE memories ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
DO $$
BEGIN
  ALTER TABLE memories ADD CONSTRAINT chk_memories_metadata_size
    CHECK (pg_column_size(metadata) < 65536);
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

-- GIN para queries sobre metadata (cases por task_type, skills por status)
CREATE INDEX IF NOT EXISTS idx_memories_metadata
  ON memories USING gin (metadata jsonb_path_ops);

-- Indices compuestos para briefing/foresight/cases queries
CREATE INDEX IF NOT EXISTS idx_memories_agent_type
  ON memories (agent_id, type);
CREATE INDEX IF NOT EXISTS idx_memories_agent_foresight
  ON memories (agent_id, foresight_end)
  WHERE foresight_start IS NOT NULL;

-- Enum values (PG16, IF NOT EXISTS valido, autocommit en asyncpg)
ALTER TYPE memory_type ADD VALUE IF NOT EXISTS 'caso';
ALTER TYPE memory_type ADD VALUE IF NOT EXISTS 'skill';
