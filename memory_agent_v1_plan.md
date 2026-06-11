# Plan — Memory Agent (EcoDB v1.3)

*References: Brief v2, Spec v1 (memory_agent_v1_spec.md), verification_checkpoint.md*

## Task overview

| # | Task | Owner | Est. | Depends on |
|---|------|-------|------|------------|
| T1 | SQL migration + seed + cell_runs CHECK fix | Hilo | 2.5h | — |
| T2 | Cell configs CRUD endpoints | Hilo | 3h | T1 |
| T3 | Prompt templates CRUD endpoints | Hilo | 2h | T1 |
| T4 | Agent management extensions | Hilo | 1.5h | T1 |
| T5 | Cluster search endpoint (reuse existing models) | Hilo | 1.5h | T1 |
| T6 | Telescopic view endpoint (reuse query patterns) | Hilo | 1h | T1 |
| T7 | Search cluster_mode extension | Hilo | 3h | T5 |
| T8 | Cell worker DB config + cron refactor | Hilo | 4h | T2, T3 |
| T9 | LLM provider keys + encryption | Hilo | 2.5h | T1 |
| T10 | Model router (extend existing llm_provider.py) | Hilo | 1.5h | T8, T9 |
| T11 | Generic cell handler | Hilo | 2h | T8, T10 |
| T12 | Trigger endpoint extension | Hilo | 1h | T8 |
| T13 | MCP tools (6 new + 1 extended, 5/6 have backend) | Hilo | 2h | T5, T6, T7 |
| T14 | Dashboard Memory Agent page | Lienzo | 13h | T2-T7, T9 |
| **Total** | | | **40h** | |

*Estimates revised after Hilo's codebase pre-mapping (2026-06-11). Savings from reuse: clusters.py models, llm_provider.py ABC pattern, briefing.py already complete, 5/6 MCP tools have backend endpoints. Critical addition: cell_runs CHECK constraint removal in T1.*

---

## T1 — SQL migration + seed + cell_runs CHECK fix

**objetivo**: Create cell_task_configs, cell_prompt_templates, llm_provider_keys tables. Extend agents. Drop cell_runs cell_type CHECK constraint (allows custom types). Seed defaults.

**archivos_a_tocar**: `sql/migrate_5.2.0_to_5.3.0_memory_agent.sql`, `sql/seed_memory_agent.sql`, `api/settings.py` (SCHEMA_VERSION), `api/migrations.py` (MIGRATIONS list)

**accion**:
1. Write migration SQL per Spec section 1 DDL
2. Write seed SQL that inserts v3 prompt as default template + 12 configs for active agents
3. Bump SCHEMA_VERSION to "5.3.0" in settings.py
4. Append both migrations to MIGRATIONS list in migrations.py
5. Run migration against local postgres

**pre_condiciones**: Schema is at 5.2.0 (verified in checkpoint)

**post_condiciones**: `SELECT COUNT(*) FROM cell_task_configs` >= 16. `SELECT COUNT(*) FROM cell_prompt_templates` >= 1. agents table has display_name and description columns.

**tests**:
```bash
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT COUNT(*) FROM cell_task_configs;"
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT COUNT(*) FROM cell_prompt_templates;"
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "\d agents" | grep display_name
```

**criterio_de_exito**: All 3 queries return expected values. API starts without migration errors.

**rollback**: `DROP TABLE IF EXISTS cell_task_configs, cell_prompt_templates CASCADE; ALTER TABLE agents DROP COLUMN IF EXISTS display_name, DROP COLUMN IF EXISTS description;`

**depende_de**: none

---

## T2 — Cell configs CRUD endpoints

**objetivo**: CRUD API for cell_task_configs per Spec section 2.

**archivos_a_tocar**: `api/cell_configs.py` (new), `api/main.py` (register router)

**accion**:
1. Create cell_configs.py with router prefix `/cells/configs`
2. Implement GET (list with filters), POST (create with validation), PUT (update), DELETE
3. Validate cron expressions with croniter on POST/PUT
4. Join with cell_runs for last_run/last_run_status in response
5. Auth: super-only for POST/PUT/DELETE, super-or-owner for GET
6. Register router in main.py

**pre_condiciones**: T1 migration applied

**post_condiciones**: `curl -X GET localhost:8080/api/v1/cells/configs?agent_identifier=Prima` returns configs

**tests**:
```bash
# List configs
curl -s -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/configs?agent_identifier=Prima" | python -m json.tool
# Create config
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/api/v1/cells/configs" -d '{"agent_identifier":"Prima","cell_type":"custom_test","model":"deepseek-chat","provider":"deepseek"}' | python -m json.tool
```

**criterio_de_exito**: All 4 CRUD operations work. Duplicate agent+type+level returns 409. Invalid cron returns 422.

**rollback**: no_destructiva (remove router from main.py, delete file)

**depende_de**: T1

---

## T3 — Prompt templates CRUD endpoints

**objetivo**: CRUD API for cell_prompt_templates per Spec section 2.

**archivos_a_tocar**: `api/cell_templates.py` (new), `api/main.py` (register router)

**accion**:
1. Create cell_templates.py with router prefix `/cells/templates`
2. Implement GET (list), POST (create), PUT (update), DELETE (with in-use check)
3. Auth: super-only for write, super-or-owner for read
4. Register router in main.py

**pre_condiciones**: T1 migration applied

**post_condiciones**: `curl GET localhost:8080/api/v1/cells/templates` returns at least 1 template (v3 default)

**tests**:
```bash
curl -s -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/templates" | python -m json.tool
# Delete template in use
curl -s -X DELETE -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/templates/1" # should return 409
```

**criterio_de_exito**: CRUD works. Delete of in-use template returns 409.

**rollback**: no_destructiva

**depende_de**: T1

---

## T4 — Agent management extensions

**objetivo**: Agent listing endpoint + extend PATCH with new fields per Spec.

**archivos_a_tocar**: `api/agents.py` (extend), `api/main.py` (register new route if needed)

**accion**:
1. Add `GET /api/v1/agents` — list all agents with summary (cell_configs_count, clusters_count, last_cell_run via subqueries)
2. Extend existing PATCH /agents/{identifier} to accept display_name, description
3. Add `POST /api/v1/agents` — create new agent (super-only)
4. Auth: super sees all, owner sees own agents

**pre_condiciones**: T1 migration applied (display_name, description columns exist)

**post_condiciones**: `curl GET localhost:8080/api/v1/agents` returns 7 agents with summary stats

**tests**:
```bash
curl -s -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/agents" | python -m json.tool
```

**criterio_de_exito**: Returns all 7 agents with correct counts. PATCH updates display_name.

**rollback**: no_destructiva

**depende_de**: T1

---

## T5 — Cluster search endpoint

**objetivo**: POST /api/v1/clusters/search — semantic search on cluster centroids per Spec.

**archivos_a_tocar**: `api/clusters.py` (add endpoint), `api/embeddings_client.py` (reuse embed function)

**accion**:
1. Add `POST /clusters/search` to existing clusters router
2. Embed query_text via embeddings_client (same as search.py)
3. Cosine search on memory_clusters.centroid + BM25 on label
4. Filter by agent ownership (agent sees own + workspace-shared clusters)
5. Return ClusterSearchResult shape per Spec

**pre_condiciones**: Embeddings service running, clusters exist with centroids

**post_condiciones**: `POST /api/v1/clusters/search` with query_text returns ranked results

**tests**:
```bash
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/api/v1/clusters/search" -d '{"query_text":"workflow design","limit":5}' | python -m json.tool
```

**criterio_de_exito**: Returns clusters ranked by cosine score. Empty query returns 422.

**rollback**: no_destructiva

**depende_de**: T1

---

## T6 — Telescopic view endpoint

**objetivo**: GET /api/v1/clusters/telescopic — fractal memory chain for boot.

**archivos_a_tocar**: `api/clusters.py` (add endpoint)

**accion**:
1. Add `GET /clusters/telescopic` to clusters router
2. Query memory_clusters by agent, status='active', grouped by level
3. Return full narratives (not previews) ordered by period_end DESC
4. Limits: weekly 4, monthly 3, quarterly 4, yearly all
5. Auth: agent owner or super

**pre_condiciones**: Clusters exist for the agent

**post_condiciones**: `GET /api/v1/clusters/telescopic?agent_identifier=Prima` returns weekly + monthly narratives

**tests**:
```bash
curl -s -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/clusters/telescopic?agent_identifier=Prima" | python -m json.tool
```

**criterio_de_exito**: Returns 4 levels with correct limits. Full narrative text included.

**rollback**: no_destructiva

**depende_de**: T1

---

## T7 — Search cluster_mode extension

**objetivo**: Extend POST /search with cluster_mode parameter per Spec.

**archivos_a_tocar**: `api/search.py` (SearchRequest, SearchResponse, _get_related_clusters, search_memories)

**accion**:
1. Add `cluster_mode` field to SearchRequest (default "none")
2. Add `cluster_mode` echo and `merged_results` to SearchResponse
3. `cluster_mode=include`: extend existing _get_related_clusters to return full ClusterSummary + narrative_preview, increase limit from 3 to 10
4. `cluster_mode=mixed`: run both memory GAMR and cluster cosine search, normalize scores, interleave into merged_results with MergedResultItem union type
5. Score normalization: memory scores already 0-1, cluster cosine 0-1, cluster weight=0.8

**pre_condiciones**: T5 (cluster search logic exists to reuse)

**post_condiciones**: `POST /search` with cluster_mode=include returns enriched related_clusters. cluster_mode=mixed returns merged_results.

**tests**:
```bash
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/search" -d '{"query_text":"workflow design","cluster_mode":"include"}' | python -c "import sys,json; r=json.load(sys.stdin); print(len(r.get('related_clusters',[])))"
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/search" -d '{"query_text":"workflow design","cluster_mode":"mixed"}' | python -c "import sys,json; r=json.load(sys.stdin); print(len(r.get('merged_results',[])))"
```

**criterio_de_exito**: include returns >0 related_clusters with narrative_preview. mixed returns merged_results with both memory and cluster items.

**rollback**: no_destructiva (remove cluster_mode handling, revert to hardcoded _get_related_clusters)

**depende_de**: T5

---

## T8 — Cell worker DB config + cron refactor

**objetivo**: Cell worker reads config from DB instead of env vars. Cron from DB schedules.

**archivos_a_tocar**: `api/cell_worker.py` (major refactor of main loop + config loading), `api/requirements.txt` (add croniter)

**accion**:
1. Add `_load_cell_config()` per Spec section 4
2. Modify `run_consolidation()`, `run_foresight_extraction()`, `run_skill_distillation()` to accept config dict
3. Replace `_build_cell_system_prompt()` to use template from config (fall back to hardcoded if no template)
4. Replace hardcoded main() cron loop with croniter-based scheduler that reads cell_task_configs
5. Preserve env-var fallback: if no config row, use CELL_MODEL etc.
6. Update catch-up logic to use croniter for missed period detection
7. Populate cell_runs.prompt_version with template name when available [F3]
8. Add croniter to requirements.txt

**pre_condiciones**: T2 and T3 deployed (configs and templates in DB)

**post_condiciones**: Cell worker starts, reads configs from DB, executes on schedule. Trigger endpoint also reads DB config.

**tests**:
```bash
# Trigger with DB config
curl -s -X POST -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/trigger/consolidation?agent_identifier=Prima&level=weekly"
# Check cell_runs for prompt_version populated
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT prompt_version FROM cell_runs ORDER BY created_at DESC LIMIT 1;"
```

**criterio_de_exito**: Trigger uses model from DB config. prompt_version populated in cell_runs. Changing config in DB reflects on next trigger without restart.

**rollback**: Revert cell_worker.py to pre-refactor (git checkout). Env vars still work.

**depende_de**: T2, T3

---

## T9 — LLM provider keys + encryption

**objetivo**: CRUD for LLM provider API keys with Fernet encryption at rest. Dashboard can manage provider keys.

**archivos_a_tocar**: `api/providers.py` (new), `api/main.py` (register router), `api/crypto.py` (new — Fernet wrapper), `api/requirements.txt` (add cryptography)

**accion**:
1. Create crypto.py: Fernet encrypt/decrypt using ENCRYPTION_KEY from env. Validate on startup.
2. Create providers.py: CRUD endpoints per Spec. Encrypt api_key on POST/PUT, return masked on GET.
3. Add `cryptography` to requirements.txt
4. Add ENCRYPTION_KEY generation to scripts/setup.sh
5. Register router in main.py

**pre_condiciones**: T1 (llm_provider_keys table exists)

**post_condiciones**: `POST /api/v1/providers` stores encrypted key. `GET /api/v1/providers` returns masked key. Cell worker can decrypt and use.

**tests**:
```bash
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/api/v1/providers" -d '{"provider":"deepseek","api_key":"sk-test-12345","model_default":"deepseek-chat"}'
curl -s -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/providers" | python -m json.tool
# Verify key is masked: "sk-...2345"
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT provider, api_key_encrypted FROM llm_provider_keys;" 
# Verify encrypted (BYTEA, not plaintext)
```

**criterio_de_exito**: Keys encrypted in DB. GET returns masked. Cell worker decrypts successfully. Missing ENCRYPTION_KEY blocks API startup.

**rollback**: no_destructiva

**depende_de**: T1

---

## T10 — Model router (with DB key lookup)

**objetivo**: Support multiple LLM providers with keys from DB (encrypted) or env var fallback.

**archivos_a_tocar**: `api/cell_worker.py` (replace _llm_call with routed version using crypto.py)

**accion**:
1. Implement `_get_provider_key(conn, provider)` — DB first (decrypt via crypto.py), env var fallback
2. Implement `_llm_call_routed(conn, system_prompt, user_prompt, provider, model)` per Spec
3. V1 providers: deepseek (existing httpx), anthropic (Messages API)
4. LangChain path: if ecodb-langchain installed AND provider supported, use LangChain; else httpx
5. Fallback chain: DB key -> env var -> error with clear message

**pre_condiciones**: T8 (config loading), T9 (crypto + provider keys table)

**post_condiciones**: Config with provider="anthropic" uses key from DB. Fallback to env var if no DB key.

**tests**:
```bash
# Add anthropic key via API
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/api/v1/providers" -d '{"provider":"anthropic","api_key":"sk-ant-test","model_default":"claude-haiku-4-5-20251001"}'
# Change config to anthropic, trigger
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "UPDATE cell_task_configs SET provider='anthropic', model='claude-haiku-4-5-20251001' WHERE agent_id=2 AND cell_type='foresight';"
curl -s -X POST -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/trigger/foresight?agent_identifier=Prima"
```

**criterio_de_exito**: Cell run uses DB key for anthropic. Missing key returns clear error. Env var fallback works when no DB row.

**rollback**: no_destructiva

**depende_de**: T8, T9

---

## T10 — Generic cell handler

**objetivo**: Support custom cell types beyond the 3 built-in per Spec D9.

**archivos_a_tocar**: `api/cell_worker.py` (add generic handler)

**accion**:
1. Implement `_run_generic_cell()` per Spec section 4
2. Load prompt template, inject agent context (identity + recent memories)
3. Call model via router, parse JSON response
4. Store result as memory with configurable type (default 'observacion')
5. Record in cell_runs

**pre_condiciones**: T8, T9

**post_condiciones**: Custom cell_type triggers and produces a memory

**tests**:
```bash
# Create custom config
curl -s -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "http://localhost:8080/api/v1/cells/configs" -d '{"agent_identifier":"Prima","cell_type":"daily_summary","model":"deepseek-chat","provider":"deepseek","prompt_template_id":1}'
# Trigger it
curl -s -X POST -H "Authorization: Bearer $KEY" "http://localhost:8080/api/v1/cells/trigger/daily_summary?agent_identifier=Prima"
```

**criterio_de_exito**: Custom type executes without error. Result stored as memory. cell_runs records the execution.

**rollback**: no_destructiva

**depende_de**: T8, T9

---

## T11 — Trigger endpoint extension

**objetivo**: Remove hardcoded cell_type regex, accept any string per Spec [F6].

**archivos_a_tocar**: `api/cells.py` (trigger endpoint)

**accion**:
1. Change Path parameter from regex `^(consolidation|foresight|skill_distillation)$` to `min_length=1, max_length=64`
2. Route: if cell_type in built-in set -> existing handler. Else -> generic handler from T10.
3. If no config found for custom type -> 422 with clear message

**pre_condiciones**: T8, T10

**post_condiciones**: `POST /cells/trigger/daily_summary?agent_identifier=Prima` works

**tests**: Same as T10

**criterio_de_exito**: Arbitrary cell_type accepted. Unknown type without config returns 422.

**rollback**: no_destructiva (restore regex)

**depende_de**: T8, T10

---

## T12 — MCP tools (6 new + 1 extended)

**objetivo**: Add cluster/briefing/telescopic tools to MCP server per Spec section 3.

**archivos_a_tocar**: `mcp/server.py`

**accion**:
1. Add 6 new tools following existing proxy pattern: search_clusters, list_clusters, read_cluster, get_briefing, get_telescopic_view, narrate_cluster
2. Extend existing `search` tool with `cluster_mode` optional parameter
3. Each tool: docstring, type hints, _api_post/_api_get call, _ok/_err response handling

**pre_condiciones**: T5, T6, T7 (backend endpoints exist)

**post_condiciones**: MCP server registers 38 tools (32 + 6). All callable from Claude Code.

**tests**:
```bash
# Verify tool count via MCP
python -c "from mcp.server.fastmcp import FastMCP; import server; print(len(server.mcp._tool_manager._tools))"
```

**criterio_de_exito**: 38 tools registered. search_clusters returns results. get_telescopic_view returns narratives.

**rollback**: no_destructiva (remove tool functions)

**depende_de**: T5, T6, T7

---

## T13 — Dashboard Memory Agent page

**objetivo**: Full Memory Agent page with 4 tabs per Spec section 5.

**archivos_a_tocar**: `dashboard/src/pages/MemoryAgentPage.tsx` (new), `dashboard/src/components/memory-agent/` (new directory), `dashboard/src/hooks/useMemoryAgent.ts` (new), `dashboard/src/App.tsx` (route), `dashboard/src/components/NavRail.tsx` (9th item), `dashboard/src/lib/api.ts` (new API calls), `dashboard/src/locales/en.json` (translations), design system tokens

**accion**:
1. Create page scaffold with 4 tabs (Briefing default)
2. Briefing tab: foresights list, tensions list, telescopic preview
3. Configs tab: agent list -> expandable configs -> edit modal with cron builder + model selector + template selector
4. Clusters tab: filterable list -> drawer with narrative + members
5. Telemetry tab: runs table + health summary
6. SSE subscriptions for cell.run.* and cluster.* events
7. NavRail: add 9th item with Brain icon
8. Section color token `--sec-memory-agent`
9. Create new agent modal
10. i18n keys

**pre_condiciones**: T2-T7 backend endpoints available

**post_condiciones**: Memory Agent page accessible from NavRail, all 4 tabs functional

**tests**: Manual verification in Electron dev mode. Typecheck passes for both renderer and electron tsconfig.

**criterio_de_exito**: Page loads, 4 tabs work, SSE updates live, cron editor translates to expressions, trigger button fires cell run.

**rollback**: no_destructiva (remove page, route, NavRail item)

**depende_de**: T2, T3, T4, T5, T6, T7

---

## Execution order (parallelizable)

```
Phase 1 (T1): Migration — 2h
Phase 2 (T2+T3+T4+T5+T6 parallel): API endpoints — 3h (longest: T2)
Phase 3 (T7+T8 parallel): Search extension + cell worker refactor — 4h
Phase 4 (T9+T10+T11 sequential): Model router + generic handler + trigger — 5h
Phase 5 (T12): MCP tools — 3h (needs Phase 2+3)
Phase 6 (T13): Dashboard — 12h (needs Phase 2, can start during Phase 3)

Critical path: T1 → T2 → T8 → T10 → T11 = 13h
Total: Hilo 27h + Lienzo 13h = 40h. With parallelism: ~19h elapsed.
```
