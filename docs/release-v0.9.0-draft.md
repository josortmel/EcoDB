# EcoDB v0.9.0 — Multi-tenant

EcoDB goes multi-tenant. Organization isolation across all endpoints, API key rotation with zero-downtime grace periods, CEO-level admin operations, and audit trail on every mutation.

## Highlights

**Organization isolation** — Every JWT now carries `organization_id` for all roles (Workers, Leads, CEOs). Search, memory access, admin operations, and API key management are all scoped to the user's organization. Super users retain platform-wide access.

**API key rotation** — `POST /auth/api-keys/{key_id}/rotate` issues a replacement key while the old key stays valid during a configurable grace period (1-720 hours). Both keys work simultaneously. No client coordination needed. Max 3 active keys per user with automatic cleanup.

**CEO admin access** — 7 admin endpoints now accessible to organization CEOs (was super-only): alias candidate review, entity merge/undo, document trust tiers, related document confirmation, and graph vocabulary. All operations are org-scoped with fail-closed permission checks.

**Graph discovery pre-filter** — Search graph discovery now filters by `visible_project_ids` before truncation, preventing cross-org memory leakage through graph traversal paths.

**Complete audit trail** — ~40 audit_log calls across 14 files. Every mutation endpoint writes an audit record with `organization_id`. Covers memories, projects, teams, workspaces, agents, auth, documents, events, graph, and admin operations.

**Rate limiting hardened** — JWT signature now verified in rate limiter (prevents bucket spoofing). `Retry-After` and `X-RateLimit-*` headers on all responses.

## Schema migration

Schema v5.0.1 → v5.1.0. Migration is idempotent with rollback script included.

```bash
# Apply migration
docker exec -i ecodb-postgres psql -U ecodb -d ecodb < sql/migrate_5.0.1_to_5.1.0.sql

# Rebuild containers
docker compose up --build -d
```

New columns: `users.organization_id`, `api_keys.replaced_by_key_id`, `api_keys.grace_until`, `teams.organization_id`, `audit_log.organization_id`. 4 new triggers for org propagation and team cross-org constraints.

Full migration guide: [`docs/migration-v0.8-to-v0.9.md`](docs/migration-v0.8-to-v0.9.md)

## Claude Desktop support

MCP server now accepts `--transport stdio` as a CLI argument, fixing the port conflict when Claude Desktop launches the MCP via `docker exec`. See updated README for configuration.

## Security

3 adversarial review loops (code quality + security). ~35 findings identified and resolved:
- Cross-org data leakage in admin endpoints → org-scoped queries
- IDOR oracles (404 vs 403) → unified 404 responses
- API key rotation chain corruption → serialized with `SELECT FOR UPDATE`
- Rate limit bucket spoofing → JWT signature verification
- Grace-period zombie keys → auto-deactivation on failed auth

## What's next

- **v1.0 Dashboard** — React+Vite+Tailwind frontend (Spec+Plan ready)
- **Installation experience** — simplified setup for new users
- **Graph isolation** — per-org graph partitioning (deferred to first customer with sensitive data)
