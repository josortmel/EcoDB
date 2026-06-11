-- EcoDB v1.3 Memory Agent — schema 5.2.0 → 5.3.0
-- Tables: cell_prompt_templates, cell_task_configs, llm_provider_keys
-- Extensions: agents (display_name, description), cell_runs (CHECK removal)
-- GRANTs: ecodb_cell SELECT on new tables

BEGIN;

-- 1. Prompt templates — reusable prompt texts for cell workers
CREATE TABLE IF NOT EXISTS cell_prompt_templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    cell_type TEXT NOT NULL,
    content TEXT NOT NULL CHECK (char_length(content) <= 32000),
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(name)
);

-- 2. Cell task configs — per-agent, per-cell-type, per-level configuration
CREATE TABLE IF NOT EXISTS cell_task_configs (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    cell_type TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    model TEXT NOT NULL DEFAULT 'deepseek-chat',
    provider TEXT NOT NULL DEFAULT 'deepseek',
    prompt_template_id INTEGER REFERENCES cell_prompt_templates(id),
    schedule_cron TEXT,
    level TEXT CHECK (level IS NULL OR level IN ('weekly','monthly','quarterly','yearly')),
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(agent_id, cell_type, level)
);

CREATE INDEX IF NOT EXISTS idx_cell_task_configs_agent
    ON cell_task_configs(agent_id);
CREATE INDEX IF NOT EXISTS idx_cell_task_configs_enabled
    ON cell_task_configs(agent_id, enabled) WHERE enabled = true;

-- PostgreSQL: NULL != NULL in UNIQUE constraints.
-- Without this, multiple rows with (same agent, same type, NULL level) are allowed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cell_task_configs_null_level
    ON cell_task_configs(agent_id, cell_type) WHERE level IS NULL;

-- Enforce at most one is_default=true per cell_type
CREATE UNIQUE INDEX IF NOT EXISTS idx_cell_prompt_templates_default
    ON cell_prompt_templates(cell_type) WHERE is_default = true;

-- 3. Extend agents table for dashboard management
ALTER TABLE agents ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS description TEXT;

-- 4. LLM provider keys — encrypted at rest with Fernet
CREATE TABLE IF NOT EXISTS llm_provider_keys (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    model_default TEXT,
    display_name TEXT,
    added_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider)
);

-- 5. GRANTs for ecodb_cell role (invariant 21 extension)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ecodb_cell') THEN
        GRANT SELECT ON cell_task_configs TO ecodb_cell;
        GRANT SELECT ON cell_prompt_templates TO ecodb_cell;
        GRANT SELECT ON llm_provider_keys TO ecodb_cell;
        -- BH1: post day-99 pivot the cell writes narrative AS the agent (loads
        -- the agent identity, marks metadata.cell_generated=true). That is
        -- legitimate authorship, so the standalone ecodb_cell role (cron/catch-up
        -- path) needs to write narrative/narrated_at — without this, scheduled
        -- consolidation fails with "permission denied for table memory_clusters".
        GRANT INSERT, UPDATE (narrative, narrated_at) ON memory_clusters TO ecodb_cell;
        -- VS_L5_1 / VS_L5_2: close the generic-cell handler (_run_generic_cell)
        -- write path for ecodb_cell. Custom cell types store their result as a
        -- memory and update the cell_runs telemetry row; without these grants ALL
        -- custom cell types fail with "permission denied" on the cron/catch-up path.
        GRANT INSERT (visibility) ON memories TO ecodb_cell;
        GRANT UPDATE (prompt_version, model) ON cell_runs TO ecodb_cell;
    ELSE
        RAISE NOTICE 'ecodb_cell role not found — GRANTs skipped. Run 00-cell-role.sql then re-grant.';
    END IF;
END $$;

-- 6. Remove cell_type CHECK constraint on cell_runs (allows custom types)
ALTER TABLE cell_runs DROP CONSTRAINT IF EXISTS cell_runs_cell_type_check;

-- 7. Schema version bump
INSERT INTO schema_version (version) VALUES ('5.3.0') ON CONFLICT DO NOTHING;

COMMIT;
