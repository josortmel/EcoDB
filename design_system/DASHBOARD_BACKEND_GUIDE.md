# Dashboard Backend Integration Guide

**For**: Lienzo (frontend builder)
**From**: Hilo (backend builder)
**Date**: 2026-06-01
**Status**: All backend prerequisites complete. Frontend can connect to live API.

---

## 1. How to connect

Base URL: `http://localhost:8080`

Auth: every request needs `Authorization: Bearer <api_key>` header.

```typescript
// Example: TanStack Query setup
const API_BASE = "http://localhost:8080";

async function apiFetch(path: string, opts?: RequestInit) {
  const key = await window.ecodb.getToken(); // from electron-store
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      ...opts?.headers,
      "Authorization": `Bearer ${key}`,
      "Content-Type": "application/json",
    },
  });
  if (res.status === 401) {
    // Key expired or revoked → redirect to auth screen
    window.ecodb.clearApiKey();
    throw new Error("auth_expired");
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}
```

---

## 2. Route prefixes — CRITICAL

Different routers have different prefixes. This is configured in `api/main.py`:

| Router | Mount point | Example full path |
|--------|------------|-------------------|
| stats | `/api/v1/stats` | `GET /api/v1/stats/timeline?period=30` |
| events | `/api/v1/events` | `GET /api/v1/events/stream` |
| search | `/search` | `POST /search` |
| memories | `/memories` | `GET /memories/recent` |
| admin | `/admin` | `GET /admin/attention-inbox/summary` |
| auth | `/auth` | `GET /auth/me` |
| graph | `/graph` | `GET /graph/clusters` |

**The /stats and /events routes have `/api/v1` prefix. Everything else does NOT.**

---

## 3. Dashboard endpoints — complete reference

### Command Center

#### Attention Inbox Summary
```
GET /admin/attention-inbox/summary
→ {"classes": {"stale_memories": 118, "pending_alias_candidates": 18, "unconfirmed_relations": 0, "low_trust_documents": 0}, "total": 136}
```

#### Attention Inbox Details (paginated)
```
GET /admin/attention-inbox/details?decision_class=stale_memories&limit=20&offset=0
→ {"class": "stale_memories", "total": 118, "items": [{id, content, type, staleness, created_at, updated_at, agent_identifier}], "limit": 20, "offset": 0}
```
Valid classes: `stale_memories`, `pending_alias_candidates`, `unconfirmed_relations`, `low_trust_documents`

#### Timeline
```
GET /api/v1/stats/timeline?period=30
→ {"period_days": 30, "timeline": [{"date": "2026-06-01", "memories": 11, "documents": 0, "searches": 3}, ...]}
```

#### Other stats (pre-existing)
```
GET /api/v1/stats/memories    → memory counts by type, workspace, project
GET /api/v1/stats/graph       → node/triple/predicate counts
GET /api/v1/stats/agents      → agent list with last_seen
GET /api/v1/stats/search      → search volume, avg latency
GET /api/v1/stats/system      → DB size, container health
GET /api/v1/stats/knowledge   → staleness distribution, duplicate candidates
```

### Knowledge Explorer

#### Search (GAMR)
```
POST /search
Body: {"query_text": "...", "limit": 20, "include_documents": true}
→ {"query": "...", "query_type": "contextual", "results": [...], "warnings": [...], "count": 20, ...}
```
Note: `warnings` field is new — contains machine-parseable messages like "user_id filter active: document chunks excluded"

#### Recent memories
```
GET /memories/recent?limit=20
→ {"items": [...], "total": N, ...}
```

#### Staleness update
```
PUT /memories/{uuid}/staleness
Body: {"staleness": "stale"}  // one of: active, stale, dormant, archived
→ {"memory_id": "...", "staleness": "stale"}
```

#### Memory preview (GLiNER dry-run)
```
POST /memories/preview
Body: {"content": "Pepe trabaja en Eco Consulting con EcoDB"}
→ {"entities": [{"text": "Eco Consulting", "label": "organizacion", "score": 1.0, "source": "dictionary"}], "entity_count": 3, "suggested_triples": [...]}
```
Rate limited: 10/min per user.

### Graph Studio

#### Subgraph (D3-compatible)
```
GET /graph/subgraph?center=EcoDB&depth=2
→ {"center": "EcoDB", "depth": 2, "nodes": [{id, name, type, degree, cluster_id?}], "edges": [{source, target, predicate}]}
```
If >400 nodes: returns `"truncated": true` with top 200 by degree + cluster summaries.

#### Clusters (Louvain communities)
```
GET /graph/clusters?limit=500&offset=0
→ {"clusters": [{"cluster_id": 0, "node_count": 15, "nodes": [{node_id, name}]}], "cluster_count": 8, "total_nodes": 120, "last_computed": "2026-06-01T12:00:00Z"}
```
Computed hourly by background governance cycle.

#### Neighbors
```
GET /graph/neighbors/EcoDB?depth=2
→ {"center": "EcoDB", "depth": 2, "neighbors": ["Pepe", "Prima", ...]}
```
Case-insensitive lookup.

### SSE Events
```
GET /api/v1/events/stream
→ SSE stream: event: memory_created\ndata: {"memory_id": "...", "type": "tecnico"}\n\n
```
Events are org-filtered. Non-super clients only see their org's events. Event types:
- `memory_created` — new memory saved
- `search_completed` — search finished
- `contradiction_detected` — contradictions found in search
- `tension_detected` — super-only, background governance
- `agent_connected` / `agent_disconnected` — agent session events
- `document_indexed` / `document_failed` / `duplicate_detected` — document lifecycle

### Settings

#### Auth info
```
GET /auth/me → {user_id, email, name, is_super, is_ceo, organization_id, lead_workspaces}
```

#### API key management
```
GET /auth/api-keys → [{id, user_id, name, active, grace_until, ...}]
POST /auth/api-keys/{id}/rotate → {new_key_id, new_api_key, old_key_id, grace_until, ...}
```

#### Admin endpoints (super/CEO)
```
GET /admin/graph-vocabulary → {entities: [...], predicates: [...]}
GET /admin/entity-dictionary → [{id, name, entity_type, notes}]
POST/PUT/DELETE /admin/entity-dictionary/{id}
GET /admin/stop-entities → [{id, name, reason}]
POST/DELETE /admin/stop-entities/{id}
```

---

## 4. Rate limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /memories/preview | 10/min | 60s |
| POST /memories | 20/min | 60s |
| POST /search | 60/min | 60s |
| Everything else | 120/min | 60s |

Response headers on every request: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.
On 429: `Retry-After` header (seconds).

---

## 5. Error handling

| Status | Meaning | Action |
|--------|---------|--------|
| 200/201 | Success | Parse body |
| 400 | Bad request (validation) | Show error detail |
| 401 | Auth expired/invalid | Redirect to key input screen |
| 403 | No permission | Show "no access" |
| 404 | Not found | Handle gracefully |
| 409 | Conflict (duplicate) | Show conflict message |
| 422 | Validation error | Show field errors |
| 429 | Rate limited | Wait `Retry-After` seconds, retry |
| 500 | Server error | Show generic error, log |

---

## 6. TypeScript types (mirror Pydantic models)

```typescript
interface SearchResult {
  id: string;
  user_id: number | null;
  agent_identifier: string | null;
  workspace_id: number;
  project_id: number;
  type: string;
  content_type: string;
  visibility: string;
  content: string;
  tags: string[];
  weight: number;
  score: number;
  semantic_score: number;
  graph_score: number;
  freshness_score: number;
  score_breakdown: { semantic: number; graph: number; weight: number; freshness: number; bm25: number };
  matched_modality: string;
  media_path: string | null;
  created_at: string;
  source_type: "memory" | "document_chunk";
  trust_warnings: string[];
}

interface SearchResponse {
  query: string;
  query_type: string;
  results: SearchResult[];
  count: number;
  limit: number;
  duration_ms: number;
  graph_context: any[];
  contradictions: any[];
  warnings: string[];
  audit_id: string | null;
}

interface InboxSummary {
  classes: Record<string, number>;
  total: number;
}

interface TimelineDay {
  date: string;
  memories: number;
  documents: number;
  searches: number;
}

interface GraphNode {
  id: number;
  name: string;
  type: string;
  degree: number;
  cluster_id?: number;
}

interface GraphEdge {
  source: number;
  target: number;
  predicate: string;
}

interface SubgraphResponse {
  center: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
  total_nodes?: number;
  shown_nodes?: number;
  clusters?: { cluster_id: number; node_count: number; sample_nodes: number[] }[];
}

interface ClusterGroup {
  cluster_id: number;
  node_count: number;
  nodes: { node_id: number; name: string }[];
}

interface ClustersResponse {
  clusters: ClusterGroup[];
  cluster_count: number;
  total_nodes: number;
  last_computed: string | null;
}

interface PreviewResponse {
  entities: { text: string; label: string; score: number; source: string }[];
  entity_count: number;
  suggested_triples: { subject: string; predicate: string; object: string }[];
}
```

---

## 7. Graph Studio notes

- Graph is currently **global** (all orgs share nodes). See `docs/design/graph-org-scoping.md` for future direction.
- Louvain clusters are computed **hourly** by background governance. `last_computed` field tells you when.
- Subgraph >400 nodes auto-truncates to top 200 by degree. Check `truncated` field.
- Node names are case-insensitive for lookup but preserving for display (first writer's casing wins).
- `cluster_id` on subgraph nodes comes from `graph_clusters` table — may be null for recently created nodes not yet clustered.

---

## 8. Files you work in

```
EcoDB/
├── dashboard/          ← YOUR directory (create it)
│   ├── src/
│   │   ├── main.ts
│   │   ├── preload.ts
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── lib/
│   │   ├── types/      ← put the TypeScript types above here
│   │   └── __tests__/
│   ├── package.json
│   ├── vite.config.ts
│   ├── electron-builder.yml
│   └── tailwind.config.ts
```

Do NOT modify anything in `api/`, `mcp/`, `sql/`, `docker/`. Backend is frozen for your phase.

---

## 9. Spec+Plan

Your full task list with batches, estimates, and dependencies:
`F:\obsidian\GuildWars\Eco_Consulting\Faro\Informes\Diseno\EcoDB_dashboard\ecodb_dashboard_spec_plan.md`
