# Spec — Memory Agent (EcoDB v1.3)

*References: Brief v2 (memory_agent_v1_brief.md), verification_checkpoint.md (2026-06-11)*

## 1. Schema / DDL

### New migration: `sql/migrate_5.2.0_to_5.3.0_memory_agent.sql`

```sql
BEGIN;

-- Prompt templates
CREATE TABLE IF NOT EXISTS cell_prompt_templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    cell_type TEXT NOT NULL,
    content TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(name)
);

-- Cell task configs
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

CREATE INDEX IF NOT EXISTS idx_cell_task_configs_agent ON cell_task_configs(agent_id);
CREATE INDEX IF NOT EXISTS idx_cell_task_configs_enabled ON cell_task_configs(agent_id, enabled) WHERE enabled = true;

-- Fix NULL level uniqueness (PostgreSQL: NULL != NULL in UNIQUE)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cell_task_configs_null_level
ON cell_task_configs(agent_id, cell_type) WHERE level IS NULL;

-- Extend agents table for dashboard management
ALTER TABLE agents ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS description TEXT;

-- GRANT for ecodb_cell role (invariant 21 extension)
GRANT SELECT ON cell_task_configs TO ecodb_cell;
GRANT SELECT ON cell_prompt_templates TO ecodb_cell;

-- LLM provider keys (encrypted at rest)
CREATE TABLE IF NOT EXISTS llm_provider_keys (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    api_key_encrypted BYTEA NOT NULL,
    model_default TEXT,
    display_name TEXT,
    added_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider)
);

-- GRANT for ecodb_cell to read provider keys
GRANT SELECT ON llm_provider_keys TO ecodb_cell;

-- Remove cell_type CHECK constraint on cell_runs (allows custom types)
-- Original constraint: CHECK (cell_type IN ('consolidation','foresight','skill_distillation'))
ALTER TABLE cell_runs DROP CONSTRAINT IF EXISTS cell_runs_cell_type_check;

-- Update schema version
UPDATE schema_version SET version = '5.3.0', updated_at = NOW();

COMMIT;
```

### Seed migration: `sql/seed_memory_agent.sql`

Seeds 12 configs for 4 narrative agents x 3 cell types + inserts v3 prompt as default template. Runs after schema migration.

```sql
-- Default prompt template (v3)
INSERT INTO cell_prompt_templates (name, cell_type, content, is_default)
VALUES ('CellAgent v3 Weekly', 'consolidation', '{{V3_PROMPT_CONTENT}}', true)
ON CONFLICT (name) DO NOTHING;

-- Auto-seed configs for all active agents
INSERT INTO cell_task_configs (agent_id, cell_type, model, provider, prompt_template_id, schedule_cron, level, config)
SELECT a.id, ct.cell_type, 'deepseek-chat', 'deepseek',
       (SELECT id FROM cell_prompt_templates WHERE is_default AND cell_type = ct.cell_type LIMIT 1),
       ct.schedule_cron, ct.level, ct.config::jsonb
FROM agents a
CROSS JOIN (VALUES
    ('consolidation', '0 3 * * 0', 'weekly', '{"threshold": 0.45}'),
    ('consolidation', '0 5 1 * *', 'monthly', '{}'),
    ('foresight', '0 2 * * *', NULL, '{}'),
    ('skill_distillation', '0 4 * * 0', NULL, '{}')
) AS ct(cell_type, schedule_cron, level, config)
WHERE a.active = true
ON CONFLICT (agent_id, cell_type, level) DO NOTHING;
```

## 2. API endpoint signatures

### Cell Task Configs CRUD

```
GET /api/v1/cells/configs
  Query: agent_identifier?: string, cell_type?: string, enabled?: boolean
  Auth: super or owner
  Response: { items: CellTaskConfig[], total: int }

POST /api/v1/cells/configs
  Auth: super only
  Body: {
    agent_identifier: string,       // required
    cell_type: string,              // required, any string
    enabled?: boolean,              // default true
    model?: string,                 // default "deepseek-chat"
    provider?: string,              // default "deepseek"
    prompt_template_id?: int,       // FK to templates
    schedule_cron?: string,         // null = manual only
    level?: "weekly"|"monthly"|"quarterly"|"yearly"|null,
    config?: object                 // additional params
  }
  Response: CellTaskConfig
  Errors: 409 (duplicate agent+type+level), 404 (agent not found), 422 (invalid cron)

PUT /api/v1/cells/configs/{config_id}
  Auth: super only
  Body: partial CellTaskConfig (any subset of fields)
  Response: CellTaskConfig
  Errors: 404, 422

DELETE /api/v1/cells/configs/{config_id}
  Auth: super only
  Response: 204
```

**CellTaskConfig shape:**
```json
{
  "id": 1,
  "agent_id": 2,
  "agent_identifier": "Prima",
  "cell_type": "consolidation",
  "enabled": true,
  "model": "deepseek-chat",
  "provider": "deepseek",
  "prompt_template_id": 1,
  "prompt_template_name": "CellAgent v3 Weekly",
  "schedule_cron": "0 3 * * 0",
  "level": "weekly",
  "config": {"threshold": 0.45},
  "last_run": "2026-06-09T19:33:13Z",
  "last_run_status": "completed",
  "created_at": "...",
  "updated_at": "..."
}
```

### Prompt Templates CRUD

```
GET /api/v1/cells/templates
  Query: cell_type?: string
  Auth: super or owner
  Response: { items: PromptTemplate[], total: int }

POST /api/v1/cells/templates
  Auth: super only
  Body: { name: string, cell_type: string, content: string, is_default?: boolean }
  Response: PromptTemplate

PUT /api/v1/cells/templates/{template_id}
  Auth: super only
  Body: partial
  Response: PromptTemplate

DELETE /api/v1/cells/templates/{template_id}
  Auth: super only
  Response: 204
  Errors: 409 (template in use by configs)
```

### Search extension

```
POST /search (existing — extended)
  Body adds: cluster_mode?: "none"|"include"|"mixed"  (default: "none")

  When cluster_mode="none": current behavior, related_clusters may still appear (existing _get_related_clusters)
  When cluster_mode="include": related_clusters populated with full ClusterSummary + narrative_preview (max 200 chars)
  When cluster_mode="mixed": new field merged_results with union type items

  Response extension for "mixed":
    merged_results: MergedResultItem[]

  MergedResultItem = {
    result_type: "memory" | "cluster",
    score: float,  // normalized 0-1
    // if memory:
    memory?: SearchResult,
    // if cluster:
    cluster?: ClusterSearchResult
  }

  ClusterSearchResult = {
    id: uuid,
    level: string,
    label: string,
    narrative_preview: string,  // first 200 chars
    agent_identifier: string,
    period_start: date,
    period_end: date,
    member_count: int,
    vector_score: float,
    bm25_score: float
  }
```

**Score normalization for mixed mode** [Hilo-R1]: GAMR composite scores (0-1 range already) and centroid cosine scores (0-1) are both normalized. For merged ranking: `final_score = score * type_weight` where type_weight is configurable (default: memory=1.0, cluster=0.8 — clusters slightly demoted to prevent stale clusters outranking fresh memories).

### Dedicated cluster search endpoint

```
POST /api/v1/clusters/search
  Auth: any authenticated
  Body: {
    query_text: string,           // min 3, max 2000
    agent_identifier?: string,    // filter by agent (see DEFAULT FILTER below)
    level?: string,               // filter by level
    status?: string,              // default "active"
    limit?: int                   // 1-50, default 10
  }

  DEFAULT FILTER (contamination prevention — Pepe's "mesa" rule):
  - WITHOUT agent_identifier: only clusters from SIN_AUTOR agent (generic/technical).
    WHERE a.identifier = 'SIN_AUTOR'
  - WITH agent_identifier: that agent's own clusters + SIN_AUTOR.
    WHERE (a.identifier = $agent_identifier OR a.identifier = 'SIN_AUTOR')
  - Super via dashboard: no filter (sees all).
  - cluster_mode=include/mixed on POST /search: same rule as without agent_identifier
    (only SIN_AUTOR/generic clusters enrich general search, never another agent's personal clusters).
  Response: {
    results: ClusterSearchResult[],
    count: int,
    duration_ms: float
  }
```

### Telescopic view endpoint

```
GET /api/v1/clusters/telescopic
  Query: agent_identifier: string (required), levels?: string (comma-sep, default "weekly,monthly,quarterly,yearly")
  Auth: agent owner or super
  Response: {
    agent_identifier: string,
    weekly: ClusterNarrativeSummary[],    // last 4
    monthly: ClusterNarrativeSummary[],   // last 3
    quarterly: ClusterNarrativeSummary[], // last 4
    yearly: ClusterNarrativeSummary[]     // all
  }

  ClusterNarrativeSummary = {
    id: uuid,
    label: string,
    narrative: string,  // full text
    period_start: date,
    period_end: date,
    member_count: int,
    source_count: int
  }
```

### Agent management extensions

```
GET /api/v1/agents
  Auth: super or owner (sees own agents)
  Response: { items: AgentSummary[], total: int }

  AgentSummary = {
    id: int,
    identifier: string,
    display_name: string | null,
    description: string | null,
    active: boolean,
    cognition_class: string,
    last_seen: datetime | null,
    cell_configs_count: int,
    clusters_count: int,
    last_cell_run: datetime | null
  }

POST /api/v1/agents
  Auth: super only
  Body: { identifier: string, display_name?: string, description?: string, cognition_class?: string }
  Response: AgentSummary
  Errors: 409 (duplicate identifier)

PATCH /agents/{identifier} (existing — extended)
  Body adds: display_name?: string, description?: string
```

### LLM Provider Keys

```
GET /api/v1/providers
  Auth: super only
  Response: { items: ProviderKeySummary[], total: int }

  ProviderKeySummary = {
    id: int,
    provider: string,
    api_key_masked: string,  // "sk-...xxxx" (last 4 chars only)
    model_default: string | null,
    display_name: string | null,
    created_at: datetime
  }

POST /api/v1/providers
  Auth: super only
  Body: {
    provider: string,          // e.g. "deepseek", "anthropic", "openai"
    api_key: string,           // plaintext — encrypted before storage
    model_default?: string,    // e.g. "deepseek-chat", "claude-haiku-4-5-20251001"
    display_name?: string      // e.g. "DeepSeek Production"
  }
  Response: ProviderKeySummary
  Errors: 409 (provider already exists)

PUT /api/v1/providers/{provider_id}
  Auth: super only
  Body: { api_key?: string, model_default?: string, display_name?: string }
  Response: ProviderKeySummary

DELETE /api/v1/providers/{provider_id}
  Auth: super only
  Response: 204
  Errors: 409 (provider in use by cell configs)
```

**Encryption**: Fernet symmetric encryption (cryptography library). `ENCRYPTION_KEY` must be a valid Fernet key (32-byte URL-safe base64). Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If not set or invalid format, API refuses to start (same pattern as `validate_production_secrets()`). Encrypt on write, decrypt on read in cell worker only. API never returns plaintext keys — GET returns masked ("sk-****...last4").

**ENCRYPTION_KEY must be in docker-compose.yml** for both api AND ecodb-cell services (invariant).

**Key rotation**: if ENCRYPTION_KEY changes, all stored keys become unreadable. Rotation = re-encrypt all rows with new key (one-time script, not migration). Documented as explicit debt.

**Cell worker key lookup priority**: DB (llm_provider_keys) > env var ({PROVIDER}_API_KEY) > error.

### Trigger endpoint extension [F6]

```
POST /api/v1/cells/trigger/{cell_type}
  cell_type: string (remove hardcoded regex — accept any non-empty string)
  If cell_type in (consolidation, foresight, skill_distillation): use built-in handler
  Else: use generic handler (load template from config, inject agent context, call model, store result as memory)
```

## 3. MCP tools (6 new + 1 extended)

All follow existing proxy pattern in mcp/server.py.

```python
@mcp.tool()
def search_clusters(query_text: str, agent_identifier: Optional[str] = None,
                    level: Optional[str] = None, limit: int = 10) -> dict:
    """Search clusters by semantic similarity (cosine on centroids + BM25 on labels)."""
    # POST /api/v1/clusters/search

@mcp.tool()
def list_clusters(agent_identifier: str, level: Optional[str] = None,
                  status: str = "active", limit: int = 20) -> dict:
    """List clusters filtered by agent, level, status."""
    # GET /api/v1/clusters?agent_identifier=...

@mcp.tool()
def read_cluster(cluster_id: str, include_members: bool = False,
                 include_sources: bool = False) -> dict:
    """Read cluster detail with optional members and sources."""
    # GET /api/v1/clusters/{id} + conditionally /members and /sources

@mcp.tool()
def get_briefing(agent_identifier: str) -> dict:
    """Get agent briefing: foresights, tensions, pending clusters, telescopic summary."""
    # GET /api/v1/briefing?agent_identifier=...

@mcp.tool()
def get_telescopic_view(agent_identifier: str,
                        levels: str = "weekly,monthly,quarterly,yearly") -> dict:
    """Load agent's fractal memory chain for boot protocol."""
    # GET /api/v1/clusters/telescopic?agent_identifier=...&levels=...

@mcp.tool()
def narrate_cluster(cluster_id: str, narrative: str) -> dict:
    """Write or update cluster narrative (requires ownership)."""
    # PUT /api/v1/clusters/{id}/narrate
```

**Extended:** `search` tool gains `cluster_mode` parameter (default "none").

## 4. Cell worker refactor

### Config loading
```python
async def _load_cell_config(conn, agent_id, cell_type, level=None):
    """Load config from DB. Fallback to env vars if no row."""
    row = await conn.fetchrow("""
        SELECT ctc.*, cpt.content AS prompt_content
        FROM cell_task_configs ctc
        LEFT JOIN cell_prompt_templates cpt ON cpt.id = ctc.prompt_template_id
        WHERE ctc.agent_id = $1 AND ctc.cell_type = $2
          AND (ctc.level IS NOT DISTINCT FROM $3) AND ctc.enabled = true
    """, agent_id, cell_type, level)
    if row is None:
        return _env_var_defaults(cell_type)
    return dict(row)
```

### Model router [D10] — updated with DB key lookup
```python
from cryptography.fernet import Fernet

_FERNET = None
def _get_fernet():
    global _FERNET
    if _FERNET is None:
        key = os.environ.get("ENCRYPTION_KEY", "")
        if not key:
            raise RuntimeError("ENCRYPTION_KEY not set")
        _FERNET = Fernet(key.encode() if len(key) == 44 else Fernet.generate_key())
    return _FERNET

async def _get_provider_key(conn, provider: str) -> str:
    """DB first, env var fallback."""
    row = await conn.fetchrow(
        "SELECT api_key_encrypted FROM llm_provider_keys WHERE provider=$1", provider)
    if row:
        return _get_fernet().decrypt(row["api_key_encrypted"]).decode()
    env_key = os.environ.get(f"{provider.upper()}_API_KEY", "")
    if env_key:
        return env_key
    raise ValueError(f"No API key for provider {provider}")

async def _llm_call_routed(conn, system_prompt, user_prompt, provider, model):
    """Route LLM call to correct provider with DB key lookup."""
    key = await _get_provider_key(conn, provider)
    # ... httpx call with provider-specific format
```

### Cron scheduler (replaces hardcoded main loop)
```python
from croniter import croniter

async def main():
    pool = await asyncpg.create_pool(DATABASE_URL)
    await recover_stuck_runs(pool)
    while True:
        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            configs = await conn.fetch("""
                SELECT ctc.*, a.identifier FROM cell_task_configs ctc
                JOIN agents a ON a.id = ctc.agent_id
                WHERE ctc.enabled = true AND ctc.schedule_cron IS NOT NULL
            """)
        for cfg in configs:
            cron = croniter(cfg["schedule_cron"], now - timedelta(minutes=5))
            next_run = cron.get_next(datetime)
            if next_run <= now:
                if not await _check_idempotency(...):
                    asyncio.create_task(_run_cell(pool, cfg))
        await asyncio.sleep(60)
```

### Generic handler for custom cell types [D9]
```python
async def _run_generic_cell(pool, config, agent_id):
    """Execute a custom cell type using its prompt template."""
    # 1. Load prompt template from config
    # 2. Inject agent context (identity, recent memories, calibration)
    # 3. Call model via router
    # 4. Store result as memory with type from config or 'observacion'
    # 5. Record in cell_runs
```

## 5. Dashboard — Memory Agent page

### Tab 1: Briefing (default)
- Calls GET /api/v1/briefing
- Shows: active foresights (urgency-sorted), open tensions, telescopic summary preview
- Actions: dismiss foresight, dismiss/resolve tension
- SSE: subscribes to foresight.triggered

### Tab 2: Configs
- **LLM Providers section** (top, collapsible): GET /api/v1/providers
  - Provider cards: name + model_default + key masked + edit/delete
  - "Add Provider" button. If 0 providers: expanded with hint "Configure at least one LLM provider to run cell workers."
  - If providers exist: collapsed by default
  - Input field: type="password" with show/hide toggle (same pattern as AuthScreen API key)
- **Agents + Cell Configs** (below providers):
  - Calls GET /api/v1/agents (agent list with cell_configs_count)
  - Per agent expandable: GET /api/v1/cells/configs?agent_identifier=X
  - Per config row: toggle enabled, edit (modal: model selector GROUPED BY PROVIDER, cron schedule builder, template selector), trigger button
  - Model selector: if no providers configured → "Add a provider first" with link to providers section
  - Create new config: modal with agent selector, cell_type input, model, schedule, template
  - Create new agent: modal with identifier, display_name, cognition_class
  - SSE: cell.run.started → loading indicator, cell.run.completed → refresh

### Tab 3: Clusters
- Calls GET /api/v1/clusters?agent_identifier=X (filterable by level, status)
- Cluster card: label, level, period, member_count, narrative preview
- Click → drawer with full narrative, members list (lazy-load), sources/parents (telescopic nav)
- Actions: approve candidate, reject, narrate (textarea)
- SSE: cluster.created → toast + refresh

### Tab 4: Telemetry
- Calls GET /api/v1/cells/runs (paginated, filterable by type/agent/status)
- Health summary: GET /api/v1/cells/health
- Table: run_id, cell_type, agent, model, status, duration, items_created, errors
- SSE: cell.run.* events for live updates

### Section color
`--sec-memory-agent: oklch(65% 0.08 290)` (desaturated violet)

### NavRail
9th item: icon Brain or Cpu, label "Memory Agent"

## 6. Error handling

| Endpoint | Error | Response |
|----------|-------|----------|
| POST /cells/configs | duplicate agent+type+level | 409 Conflict |
| POST /cells/configs | invalid cron expression | 422 with detail |
| POST /cells/configs | agent not found | 404 |
| POST /cells/trigger/{cell_type} | no config for custom type | 422 "no config found for cell_type X" |
| POST /cells/trigger/{cell_type} | model provider key not set | 422 "API key not configured for provider X" |
| DELETE /cells/templates/{id} | template in use | 409 "template referenced by N configs" |
| POST /clusters/search | query_text < 3 chars | 422 |
| GET /clusters/telescopic | agent not found | 404 |

## 7. Success criteria per component

### Backend (Hilo)
- [ ] Migration applies cleanly on existing schema 5.2.0
- [ ] 12 configs seeded after migration for active agents
- [ ] Trigger reads config from DB, falls back to env vars
- [ ] search cluster_mode=include enriches related_clusters
- [ ] search cluster_mode=mixed returns merged_results
- [ ] POST /clusters/search returns cosine-ranked results
- [ ] GET /clusters/telescopic returns narrative chain
- [ ] Cell worker cron loop reads from DB
- [ ] Model router supports deepseek + anthropic
- [ ] Generic handler stores result as memory

### MCP (Hilo)
- [ ] 6 new tools registered in server.py
- [ ] search tool accepts cluster_mode parameter
- [ ] search_clusters returns ranked results
- [ ] get_telescopic_view returns fractal chain

### Frontend (Lienzo)
- [ ] Memory Agent page with 4 tabs
- [ ] Briefing tab loads on open
- [ ] Configs tab shows agents + nested configs
- [ ] Cluster browser with drawer detail
- [ ] Telemetry table with SSE live updates
- [ ] NavRail 9th item without overflow
- [ ] Section color tokens applied
