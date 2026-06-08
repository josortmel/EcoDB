-- memory_clusters + cell_runs + role ecodb_cell + GRANTs

-- 1. memory_clusters
-- SIN UNIQUE constraint en period — un agente produce N clusters por semana
-- (uno por tema). Idempotencia se gestiona via cell_runs
-- (si existe run completed para agent+period -> skip).
CREATE TABLE IF NOT EXISTS memory_clusters (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id        INT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  workspace_id    INT NOT NULL REFERENCES workspaces(id),
  level           TEXT NOT NULL
                  CHECK (level IN ('weekly','monthly','quarterly','yearly')),
  label           TEXT NOT NULL,
  detail          TEXT,
  narrative       TEXT,
  centroid        vector(512),
  member_ids      UUID[] NOT NULL
                  CHECK (array_length(member_ids, 1) > 0
                         AND array_length(member_ids, 1) <= 500),
  source_ids      UUID[]
                  CHECK (source_ids IS NULL
                         OR array_length(source_ids, 1) <= 200),
  pattern_flags   JSONB DEFAULT '{}',
  metadata        JSONB NOT NULL DEFAULT '{}'
                  CHECK (pg_column_size(metadata) < 131072),
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now(),
  status          TEXT DEFAULT 'candidate'
                  CHECK (status IN ('candidate','active','rejected','superseded')),
  narrated_at     TIMESTAMPTZ,
  CHECK (period_start <= period_end)
);

-- Indices para memory_clusters
CREATE INDEX IF NOT EXISTS idx_mc_agent_level
  ON memory_clusters (agent_id, level, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_mc_centroid
  ON memory_clusters USING hnsw (centroid vector_cosine_ops)
  WITH (m=16, ef_construction=200);
CREATE INDEX IF NOT EXISTS idx_mc_status
  ON memory_clusters (status) WHERE status = 'candidate';
CREATE INDEX IF NOT EXISTS idx_mc_period
  ON memory_clusters (period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_mc_pattern_flags
  ON memory_clusters USING gin (pattern_flags);
CREATE INDEX IF NOT EXISTS idx_mc_member_ids
  ON memory_clusters USING gin (member_ids);
CREATE INDEX IF NOT EXISTS idx_mc_source_ids
  ON memory_clusters USING gin (source_ids);
CREATE INDEX IF NOT EXISTS idx_mc_label_fts
  ON memory_clusters USING gin (to_tsvector('spanish', label));

-- 2. cell_runs — telemetria operacional de celulas
CREATE TABLE IF NOT EXISTS cell_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cell_type       TEXT NOT NULL
                  CHECK (cell_type IN ('consolidation','foresight','skill_distillation')),
  agent_id        INT REFERENCES agents(id),
  model           TEXT NOT NULL,
  prompt_version  TEXT,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  status          TEXT DEFAULT 'running'
                  CHECK (status IN ('running','completed','failed')),
  tokens_used     INT CHECK (tokens_used IS NULL OR tokens_used >= 0),
  cost_usd        REAL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  items_created   INT DEFAULT 0 CHECK (items_created >= 0),
  errors          JSONB DEFAULT '[]'
                  CHECK (pg_column_size(errors) < 65536),
  metrics         JSONB NOT NULL DEFAULT '{}'
                  CHECK (pg_column_size(metrics) < 65536),
  created_at      TIMESTAMPTZ DEFAULT now(),
  CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_cr_cell_type
  ON cell_runs (cell_type, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cr_agent
  ON cell_runs (agent_id) WHERE agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cr_idempotency
  ON cell_runs (agent_id, cell_type, status);
CREATE INDEX IF NOT EXISTS idx_cr_metrics_period
  ON cell_runs ((metrics->>'period_start'), (metrics->>'period_end'))
  WHERE status IN ('completed', 'running');

-- 3. Role fallback PRIMERO (la policy lo referencia con TO ecodb_cell)
DO $$
DECLARE
  _pw TEXT := coalesce(
    current_setting('ecodb.cell_password', true),
    'ecodb_cell_dev_only'
  );
BEGIN
  EXECUTE format('CREATE ROLE ecodb_cell LOGIN PASSWORD %L', _pw);
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

-- 4. RLS en cell_runs DESPUES (el role ya existe)
ALTER TABLE cell_runs ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  CREATE POLICY cell_runs_cell_policy ON cell_runs
    FOR ALL TO ecodb_cell USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END$$;

-- 5. GRANTs EXPLICITOS — solo tablas necesarias, NO ALL TABLES
DO $$
BEGIN
  GRANT USAGE ON SCHEMA public TO ecodb_cell;

  -- Lectura: solo tablas que la celula necesita (incluye projects para resolver workspace)
  GRANT SELECT ON memories, agent_identity, agents, nodes, triples,
    memory_entity_links, memory_clusters, cell_runs,
    memory_type_config, workspaces, projects TO ecodb_cell;

  -- Escritura en clusters: SIN narrative/narrated_at (frontera de autoria)
  GRANT INSERT (id, agent_id, workspace_id, level, label, detail, centroid,
    member_ids, source_ids, pattern_flags, metadata,
    period_start, period_end, created_at, status)
    ON memory_clusters TO ecodb_cell;

  -- Escritura en memories: celula foresight escribe foresight_start/end,
  -- celula skills inserta memorias tipo skill con metadata estructurada
  GRANT INSERT (
    user_id, agent_id, workspace_id, project_id,
    type, content, metadata,
    weight, weight_base, tags,
    foresight_start, foresight_end
  ) ON memories TO ecodb_cell;

  GRANT UPDATE (
    type, metadata, tags,
    foresight_start, foresight_end,
    updated_at
  ) ON memories TO ecodb_cell;

  -- Cell runs: INSERT + UPDATE solo columnas de finalizacion
  GRANT INSERT ON cell_runs TO ecodb_cell;
  GRANT UPDATE (finished_at, status, tokens_used, cost_usd,
    items_created, errors, metrics)
    ON cell_runs TO ecodb_cell;

EXCEPTION WHEN undefined_object THEN
  RAISE WARNING 'ecodb_cell role missing — GRANTs skipped. Run initdb or re-run migration.';
END$$;

-- SIN trigger guard_cluster_narrative.
-- pg_restore dispara triggers INSERT per-fila: un snapshot con clusters narrados
-- seria irrestauable. La frontera de autoria se enforce por:
--   (a) GRANT column-level: ecodb_cell no puede INSERT/UPDATE narrative (PG rechaza)
--   (b) CI test: verifica GRANT en cada deploy
--   (c) API: PUT /clusters/{id}/narrate verifica agent ownership en Python

-- Schema version
INSERT INTO schema_version (version, notes) VALUES
  ('5.2.0', 'Metacognition: foresight, metadata, caso/skill, cognition_class, memory_clusters, cell_runs, ecodb_cell role')
ON CONFLICT (version) DO NOTHING;
