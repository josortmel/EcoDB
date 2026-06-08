-- cognition_class: narrative|work|mixed

ALTER TABLE agents ADD COLUMN IF NOT EXISTS
  cognition_class VARCHAR(10) DEFAULT 'work';

DO $$
BEGIN
  ALTER TABLE agents ADD CONSTRAINT chk_agents_cognition_class
    CHECK (cognition_class IN ('narrative', 'work', 'mixed'));
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;
