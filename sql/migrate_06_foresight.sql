-- Foresight: 2 columnas + indice parcial + CHECK de orden

ALTER TABLE memories ADD COLUMN IF NOT EXISTS foresight_start TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS foresight_end TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_memories_foresight_active
  ON memories (foresight_end, foresight_start)
  WHERE foresight_start IS NOT NULL;

DO $$
BEGIN
  ALTER TABLE memories ADD CONSTRAINT chk_foresight_order
    CHECK (foresight_end IS NULL OR foresight_start IS NULL
           OR foresight_end > foresight_start);
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;
