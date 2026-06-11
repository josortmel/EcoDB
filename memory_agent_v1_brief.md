# Brief v2 — Memory Agent (EcoDB v1.3)

*Adversarial Loop 1 completed. 28 observations from Eco (product), Hilo (backend), Lienzo (frontend). 16 applied, 12 deferred. 0 escalated.*

## 1. Context and motivation

EcoDB v2.0 built the metacognition engine: 3 cell workers, memory_clusters table, CellAgent prompt v3, telescopic consolidation (weekly->monthly->quarterly->yearly), 22 new endpoints. The system produces clusters, narratives, foresights, tensions, and skills.

The problem: **nobody can read the output**. There are 0 MCP tools for clusters, 0 dedicated search capability over clusters, and 0 dashboard UI for metacognition. The cell workers run on hardcoded cron schedules with env-var-only configuration. The existing `_get_related_clusters()` in search.py returns a basic top-3 cosine match — functional but not controllable.

Pepe needs this for two reasons:
1. **Portfolio**: EcoDB is his job portfolio. Recruiters are contacting him. A configurable metacognition dashboard is a differentiator.
2. **Operational**: the family (4 agents) needs fractal memory for boot protocol, and Pepe needs to configure cell workers without touching Docker env vars.

Financial context: ~700 euros runway, ~3 months. Everything built must bring Pepe closer to paid work.

## 2. Design decisions (with traceability)

### D1: Cell worker configuration in database, not env vars
- Origin: [my-inference] from Pepe's "configure from dashboard"
- Reason: env vars require Docker restart. DB allows live changes. Env vars remain as fallback defaults when no DB config row exists.
- Trade-off: migration complexity
- Discarded: file-based config, separate microservice

### D2: New tables `cell_task_configs` and `cell_prompt_templates`
- Origin: [my-inference]
- Reason: `cell_task_configs` — per-agent, per-cell-type config (model, provider, schedule, enabled, thresholds). `cell_prompt_templates` — reusable prompt templates. V3 prompt becomes default. Both trigger path (API in-process) and standalone container read from these tables. [Lienzo-IA1 fix]
- Trade-off: two new tables
- Discarded: JSONB in agents table, single table for both

### D3: Schedule via cron expression + `croniter`
- Origin: [my-inference]
- Reason: standard, flexible, parseable. Cell worker evaluates cron from DB instead of hardcoded schedule. Dashboard shows friendly day/hour selectors that translate to cron (not raw cron strings exposed to user). [Eco-I2 fix]
- Trade-off: `croniter` dependency, catch-up logic refactor
- Discarded: interval-based, UI-only trigger

### D4: Three search modes via `cluster_mode` on POST /search (REVISED)
- Origin: [user-brief] + [Eco-A1 + Hilo-A1 adversarial fix]
- Reason: `cluster_mode` accepts `none` (default, current behavior) and `include` (memories + clusters as enrichment). Enrichment uses existing `related_clusters` response field with fuller ClusterSummary data. `mixed` mode: both memories and clusters scored together in a `merged_results` list. "Only clusters" is NOT on POST /search — handled by dedicated `search_clusters` endpoint + MCP tool. Keeps search.py manageable (already 62K).
- Trade-off: `mixed` mode adds response complexity
- Discarded: `cluster_mode=only` on search (redundant with dedicated tool, bloats search.py)

### D5: Cluster access via ownership rules, not content_scope heuristic (REVISED)
- Origin: [user-brief] + [Eco-A3 + Hilo-C1 + Lienzo-C2 adversarial fix]
- Reason: the v1 heuristic (>60% momento with weight < 0.7 = personal) was attacked by all three adversarials. Intimate moments at weight 0.7+ would leak. Authorship is the natural discriminant: each agent sees their own clusters + cross-agent/generic clusters. The agent_id already on memory_clusters IS the filter. No new column needed, no heuristic, no data migration.
- MCP tools: `search_clusters` returns clusters where the requesting agent has read access (own + shared workspace). Dashboard shows all for super user.
- Trade-off: no fine-grained content sensitivity filtering (deferred)
- Discarded: content_scope column, type-distribution heuristic, visibility field

### D6: 6 new MCP tools + 1 extended (REVISED)
- Origin: [user-brief] + [Hilo-C2 + Eco-A2 adversarial fix]
- New tools (6):
  - `search_clusters(query_text, agent_identifier, level, limit)` — cosine on centroids + BM25 on labels
  - `list_clusters(agent_identifier, level, status, limit)` — filtered listing
  - `read_cluster(cluster_id, include_members, include_sources)` — detail + optional members/sources
  - `get_briefing(agent_identifier)` — foresights + tensions + telescopic summary
  - `get_telescopic_view(agent_identifier, levels)` — fractal boot: narratives chain weekly->monthly->quarterly->yearly [Eco-A2/G1 fix, moved from OUT to IN]
  - `narrate_cluster(cluster_id, narrative)` — manual narration (ownership required)
- Extended (1): `search` tool gains `cluster_mode` parameter (default "none")
- Trade-off: 7 tool additions to the MCP
- Discarded: 8 separate tools (merged members/sources into read_cluster params), update_cluster_status in MCP (super-only, dashboard only)

### D7: Dashboard page "Memory Agent" — standalone, 4 tabs
- Origin: [user-brief] + [Lienzo-DA4]
- Sections as tabs: **Briefing** (first/default — what Pepe sees on open), Configs (CRUD + trigger + toggle), Clusters (browse/read/approve), Telemetry (cell_runs + health)
- Real-time: page subscribes to cell.run.* and cluster.* SSE events [Lienzo-G1/Hilo-G3 fix]
- Section accent color: violeta desaturado `oklch(65% 0.08 290)` [Lienzo-G2 proposal accepted]
- Non-super: read-only clusters + briefing tab, configs/trigger disabled [Lienzo-G4]
- Trade-off: new page, new interaction patterns (cron editor, large text editor, hierarchical cluster nav)
- Discarded: Settings subsection

### D8: `search_clusters` uses cosine on `memory_clusters.centroid`
- Origin: [my-inference]
- Reason: centroids exist (512-dim Jina v4). Already proven in `_get_related_clusters()`. Dedicated endpoint and MCP tool with proper filtering, pagination, and access control.
- Trade-off: centroid = average, less precise than member search
- Discarded: re-embedding narratives, member-level search

### D9: `cell_type` as VARCHAR, not enum (REVISED)
- Origin: [Eco-I1 + Hilo-A2 + Lienzo-C1 adversarial fix]
- Reason: Pepe said "no hard limit on tasks." The 3 existing types (consolidation, foresight, skill_distillation) have built-in handlers. New types use a generic handler: load prompt template, inject agent context, call model, store result. The trigger endpoint also accepts any cell_type, routing to the generic handler if no built-in exists.
- Trade-off: generic handler is less specialized than built-in
- Discarded: enum (blocks extensibility)

### D10: Model router for multi-provider support (NEW)
- Origin: [Hilo-A3 adversarial fix]
- Reason: if each task config can specify a different model, the cell worker needs provider routing. `cell_task_configs` stores `model` (e.g., "deepseek-chat", "claude-sonnet-4-6") and `provider` (e.g., "deepseek", "anthropic"). Key lookup by env convention: `{PROVIDER_UPPER}_API_KEY`. V1: deepseek (current) + anthropic. LangChain handles abstraction if installed; httpx fallback routes by provider.
- Trade-off: adds provider abstraction layer
- Discarded: single-provider only, model enum

### D11: GRANT for ecodb_cell on new tables (NEW)
- Origin: [Hilo-IA1 adversarial fix]
- Reason: ecodb_cell role (invariant 21) needs SELECT on cell_task_configs and cell_prompt_templates to read its own config. Migration must extend GRANT. No INSERT/UPDATE (cell worker doesn't write configs).

## 3. Scope

### In
- SQL migration: `cell_task_configs`, `cell_prompt_templates` tables. GRANT for ecodb_cell.
- API endpoints: CRUD cell configs (4), CRUD prompt templates (4), `POST /search_clusters`, extended `POST /search` with cluster_mode
- Cell worker refactor: DB config, template system, cron scheduling, model router, catch-up refactor
- 6 new MCP tools + 1 extended (see D6)
- Dashboard "Memory Agent" page: 4-tab layout (Briefing, Configs, Clusters, Telemetry)
- Seed migration: 12 configs (4 agents x 3 types) + v3 prompt as default template
- Fractal boot loading via `get_telescopic_view` MCP tool

### Out (conscious debt)
- LangChain improvements (deprioritized by Pepe)
- OAuth/SSO, graph isolation (future customer triggers)
- Frozen replay eval (T12), pytest-asyncio errors
- Prompt template versioning (v1 stores latest only)
- Structured template editor (v1 = textarea)
- Jinja2 template engine (v1 = Python f-string placeholders)
- Cell worker horizontal scaling

## 4. Success criteria (verifiable)

1. `SELECT COUNT(*) FROM cell_task_configs WHERE enabled=true` >= 16 after seed (4 narrative agents x 4 configs: weekly consol + monthly consol + foresight + skill_distill)
2. `POST /cells/trigger/consolidation?agent_identifier=Prima` reads model + prompt from cell_task_configs
3. `POST /search` with `cluster_mode=include` returns enriched `related_clusters` with full ClusterSummary
4. `POST /search` with `cluster_mode=mixed` returns `merged_results` interleaving memories and clusters
5. MCP `search_clusters(query_text="workflow design", limit=5)` returns clusters ranked by cosine
6. MCP `get_telescopic_view(agent_identifier="Prima")` returns weekly->monthly narrative chain
7. MCP `get_briefing(agent_identifier="Prima")` returns foresights + tensions + telescopic
8. Dashboard Memory Agent loads 4 tabs with live SSE updates
9. Cell worker: change schedule_cron in DB -> picked up next cycle without restart
10. Trigger endpoint accepts custom cell_type and routes to generic handler

## 5. Explicit debt

- Prompt template versioning (v1 = latest only)
- Structured template editor (v1 = textarea)
- Jinja2 templates (v1 = f-string placeholders)
- Content sensitivity filtering (v1 = ownership rules, fine-grained deferred)
- Cell worker horizontal scaling
- Cron edge case validation
- Cross-page navigation details (follows existing patterns)
- NavRail overflow check for 9th item

## 6. Questions resolved by adversarial

All 8 original questions answered through adversarial process:
1. content_scope -> ownership rules (no column needed)
2. custom tasks -> VARCHAR cell_type + generic handler
3. cluster_mode=include -> enriched related_clusters, no shape break
4. model not found -> fallback chain: DB config model -> env var CELL_MODEL -> "deepseek-chat"
5. tool count -> 6 new + 1 extended (merged members/sources)
6. real-time -> SSE events already exist, dashboard subscribes
7. catch-up -> croniter evaluates missed periods from DB config
8. search_clusters filter -> ownership-based, not hardcoded scope
