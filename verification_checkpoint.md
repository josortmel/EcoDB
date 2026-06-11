# verification_checkpoint — Memory Agent v1.3 — 2026-06-11

## Real system state

### Docker services (all healthy)
ecodb-api :8080, ecodb-postgres :5435, ecodb-worker, ecodb-ner :8092, ecodb-embeddings, ecodb-mcp :8091

### Schema
- schema_version: 5.2.0
- 101 API endpoints (OpenAPI verified)
- memory_clusters: 17 columns (id, agent_id, workspace_id, level, label, detail, narrative, centroid vector(512), member_ids UUID[], source_ids UUID[], pattern_flags jsonb, metadata jsonb, period_start, period_end, created_at, status, narrated_at)
- cell_runs: 14 columns (id, cell_type, agent_id, model, prompt_version, started_at, finished_at, status, tokens_used, cost_usd, items_created, errors jsonb, metrics jsonb, created_at)
- agents: 7 columns (id, identifier, user_id, active, last_seen, created_at, cognition_class)
- NO cell_task_configs table (to be created)
- NO cell_prompt_templates table (to be created)

### Agents
| id | identifier | active | cognition_class |
|----|-----------|--------|-----------------|
| 1 | Eco | true | narrative |
| 2 | Prima | true | narrative |
| 3 | Hilo | true | narrative |
| 4 | Lienzo | true | narrative |
| 5 | Faro | true | work |
| 6 | SIN_AUTOR | true | work |
| 7 | Escribano | true | work |

### Clusters
- 229 weekly active + 4 monthly active = 233 total
- Prima: 56 weekly + 1 monthly. Avg cluster size: 8.5 members
- All clusters status='active', all narrated

### Cell runs
- 30 runs in 30 days: 28 consolidation, 2 foresight, 0 skill_distillation
- 0 errors in 24h. Last consolidation: 2026-06-09. No cost tracking.

### Existing search cluster integration
`_get_related_clusters()` in search.py: cosine + BM25 on centroids/labels, top 3, status='active', user-scoped.

### Cell worker config (current — all env vars)
CELL_MODEL=deepseek-chat, THRESHOLD_NARRATIVE=0.45, THRESHOLD_WORK=0.55, MAX_MEMORIES=500, MIN_CLUSTER=2. Cron hardcoded in main().

### MCP: 32 tools, 0 for clusters/briefing/cells.

## Findings for Spec

F1: _get_related_clusters() already exists — cluster_mode=include extends it, not duplicates.
F2: agents table is lean (7 cols). Dashboard agent management may need display_name, description.
F3: cell_runs.prompt_version exists but always null — templates should populate this.
F4: 41 open tensions, 0 resolved. Tension management in Briefing tab.
F5: skill_distillation never ran. Seed config should enable it.
F6: trigger endpoint has hardcoded 3 cell_types regex — must change for extensibility.
F7: PATCH /agents/{identifier} exists — covers part of agent config.
