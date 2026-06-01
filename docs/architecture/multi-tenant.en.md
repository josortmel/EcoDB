# Multi-Tenant Architecture

*EcoDB v0.9.0. June 2026.*

---

## Overview

EcoDB v0.8 was single-tenant: one installation, one team, no isolation between users. v0.9 adds organization-level isolation so multiple teams can share an EcoDB instance without seeing each other's data.

The design principle: **design for 300, build for 5.** The schema and permission model support hundreds of users across dozens of organizations. The infrastructure (in-memory rate limiting, single-node PostgreSQL) is sized for small-scale deployments. When real load demands it, the infrastructure scales without schema changes.

## Organization model

```
Organization (tenant boundary)
├── Workspaces (departments)
│   ├── Projects
│   │   ├── Members (agents and users)
│   │   └── Memories, Documents
│   └── Workspace Leads
└── CEO (org-level admin)

Superuser (global, cross-org)
```

An organization is the isolation boundary. Every memory, document, workspace, project, team, API key, and audit entry belongs to exactly one organization. Queries never return data from another organization — the scoping is enforced at the SQL level, not application-level filtering.

## Role hierarchy

| Role | Scope | Creates | Manages | Reads |
|------|-------|---------|---------|-------|
| **Superuser** | Global | Organizations, users, agents, ontology | Everything | Everything |
| **CEO** | Organization | Workspaces, projects within their org | Members, trust tiers, entity dictionary, alias candidates within their org | All org data |
| **Workspace Lead** | Workspace | Projects within their workspace | Members within their workspace | Workspace data |
| **Project Member** | Project | Memories, triples within their project | Own content | Project data + public workspace data |

CEO is the organizational admin. They see everything in their org, manage workspace structure, and execute a defined set of admin operations — but never touch another org's data, and never touch global ontology (that's superuser territory).

## Authentication

### API key as identity

EcoDB uses API keys as the primary identity mechanism, not OAuth or daily login flows. An API key is issued once and carries permissions via JWT.

```
API key (stored, hashed) → POST /auth/login → JWT (1h TTL, carries org_id + role + permissions)
```

Every JWT — for every role, not just CEO — carries `organization_id`. This means the permission system can scope queries to the correct organization without additional database lookups on every request.

**Why not OAuth?** EcoDB users are agents and developers who configure an API key once in their MCP client settings. OAuth introduces login friction for always-on agents — even with long-lived tokens, the refresh flow adds complexity without clear benefit at this scale. The tradeoff is a 1-hour window post-revocation where a stolen JWT remains valid. Acceptable at <50 users; JWT blacklisting deferred to larger deployments.

### API key lifecycle

```
CREATE ─────────────────────────────────────────────────────► Active
  POST /auth/api-keys
  Returns: ecodb_<base64> (shown once, never again)

ROTATE ──── grace period (default 24h, max 720h) ──────────► Old key expires
  POST /auth/api-keys/{id}/rotate {grace_hours: 24}
  → New key B issued (active immediately)
  → Old key A enters grace period (still works until grace_until)
  → A.replaced_by_key_id = B.id (chain pointer)

GRACE ──────────────────────────────────────────────────────► Both work
  Both A and B authenticate successfully
  Zero-downtime rotation: swap keys in client configs at your pace

EXPIRY ─────────────────────────────────────────────────────► Old key dead
  After grace_until: first failed auth auto-deactivates A
  Returns 401 "api key grace period expired"

LIMITS:
  → Max 3 active non-grace keys per user (oldest auto-deactivated on rotation)
  → Re-rotating a key already in grace → 409 "rotate the successor instead"
  → Concurrent rotations serialized via SELECT FOR UPDATE → 409 on race
```

**Who can rotate:** the key owner, the CEO of the key owner's org, or superuser.

## Data isolation

### Organization-scoped (isolated)

Everything that belongs to a specific team:

- **Memories** — search, search_recent, save, read, delete all scoped to actor's org
- **Documents** — register, reindex, chunks, search_in_document
- **Workspaces and Projects** — CRUD scoped to org
- **Teams** — cross-org membership blocked by database trigger (not application code)
- **API keys** — create, list, rotate all scoped to org
- **Admin operations** — alias candidates filtered, merge/undo org-checked, trust tier / doc confirmation org-checked
- **Audit log** — every entry carries `organization_id`
- **Rate limiting** — per-user bucket, independent across orgs

### Global (shared across orgs)

Knowledge structure shared across all organizations:

- **Graph nodes and triples** — entities and relationships are global by design. An entity like "PostgreSQL" shouldn't exist N times for N orgs. The graph is a shared ontology, not tenant data.
- **Entity dictionary** — canonical names, aliases, and categories
- **Canonical predicates** — the ~100 approved relationship types with ontological metadata
- **Stop entities** — exclusion list for NER

**Why global graph?** The graph stores structural knowledge ("PostgreSQL is a technology", "FastAPI uses Uvicorn"), not private data. Private data lives in memories, which are org-scoped. The graph is a shared vocabulary that helps all organizations find connections — without revealing what any specific organization stored.

## Admin operations

Seven operations are accessible to CEOs, scoped to their organization's data:

| Operation | Endpoint | What it does |
|-----------|----------|-------------|
| Alias candidates | `GET /admin/alias-candidates` | List entity alias candidates (org-filtered) |
| Review alias | `PUT /admin/alias-candidates/{id}` | Approve/reject candidate, optional merge |
| Merge entities | `POST /admin/merge-entities` | Soft-merge source into target (both org-checked) |
| Undo merge | `POST /admin/undo-merge` | Revert a merge operation |
| Document trust | `PUT /admin/documents/{id}/trust-tier` | Set trust tier 0–3 (doc org-checked) |
| Confirm related | `PUT /admin/related-documents/confirm` | Confirm document pair (both docs org-checked) |
| Graph vocabulary | `GET /admin/graph-vocabulary` | Read entity dictionary + approved predicates |

All gated by `_check_admin_op`: superuser passes unconditionally, CEO passes if the operation is in the allowed set AND the target entity/document belongs to their org. Everyone else gets 403. Orphaned entities (no org links) require superuser — CEOs never operate on unowned data.

## Rate limiting

Per-user sliding window, configurable via environment variables:

| Parameter | Default | Scope |
|-----------|---------|-------|
| `RATE_LIMIT_DEFAULT` | 120 req/min | General endpoints |
| `RATE_LIMIT_SEARCH` | 60 req/min | Search endpoints |
| `RATE_LIMIT_WINDOW` | 60 seconds | Window size |

Response on 429: `Retry-After` header with seconds until reset. All responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.

Implementation: in-memory sliding window middleware. JWT verified with the real secret (no spoofing). API keys get their own bucket via hash prefix. State lost on restart (acceptable at current scale). Redis replacement deferred to >50 concurrent users.

## Audit trail

Every mutation endpoint writes to `audit_log` with `organization_id`:

- **Agents**: save_identity
- **Auth**: create_api_key, rotate_api_key
- **Documents**: register, reindex, delete
- **Events**: agent_session
- **Graph**: save_triple, save_triples_batch, delete_triple
- **Workspaces**: create, update, delete
- **Admin**: merge_entities, undo_merge

CEOs can query audit entries for their organization. Superusers see all.

## Security model

### IDOR prevention

Auth before fetch, unified error responses. A 403 never reveals "this resource exists in another org" — the response is identical to "this resource doesn't exist." No existence oracles.

### Fail-closed on orphaned entities

When `_check_admin_op` resolves an entity's org membership and finds no links (orphaned entity), it returns 403 instead of falling back to the actor's org. Superuser required for orphaned entities. This prevents a CEO from accidentally claiming unowned data.

### Database-level enforcement

Cross-org constraints on teams are enforced by PostgreSQL triggers, not application code. Even if the API layer has a bug, the database rejects cross-org team membership.

## Design decisions

| Decision | Choice | Tradeoff |
|----------|--------|----------|
| Denormalized `users.organization_id` | 0 JOINs per request; trigger propagation on membership changes | Slight complexity in triggers; acceptable for query performance |
| API key as identity | No daily login; key carries permissions via JWT | 1h revocation window without blacklist |
| JWT carries org_id for all roles | Permission checks need no DB lookup for org scoping | JWT size slightly larger |
| In-memory rate limiting | Simple, no external dependency | Lost on restart; Redis deferred to >50 users |
| Grace period rotation | Zero-downtime key swap; both keys work during window | Briefly 2 valid keys per user |
| Graph globally shared | Universal ontology; entities not duplicated per org | CEOs can see entity names (not memories) across orgs |
| Fail-closed on orphaned entities | No accidental data claims | Superuser intervention needed for cleanup |
| Team constraints at DB level | Can't be bypassed by application bugs | Trigger debugging harder than application code |
| `visible_project_ids` pre-filter on graph discovery | Truncation doesn't discard accessible results | Slight query complexity increase |

## Migration

For installations upgrading from v0.8.x, see [`migration-v0.8-to-v0.9.md`](../migration-v0.8-to-v0.9.md).

The migration creates a Default organization and assigns all existing users to it. Existing single-tenant deployments continue working without configuration changes — multi-tenancy is additive, not breaking.
