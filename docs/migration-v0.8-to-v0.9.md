# Migration Guide: EcoDB v0.8.x → v0.9.0

## Prerequisites

- EcoDB v0.8.6 running with all containers healthy
- Database backup (recommended): `./scripts/backup.sh`
- Schema version must be 5.0.1

## Step 1: Apply DDL migration

```bash
docker exec -i ecodb-postgres psql -U ecodb -d ecodb < sql/migrate_5.0.1_to_5.1.0.sql
```

Verify:
```bash
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;"
# Expected: 5.1.0
```

The migration is idempotent — safe to run multiple times.

## Step 2: Invalidate pre-migration JWTs

Pre-migration JWTs lack `organization_id` for non-CEO roles. Invalidate them:

```bash
# 1. Set JWT TTL to 1 second
# In .env, set: JWT_TTL_SECONDS=1

# 2. Restart API
docker compose restart api

# 3. Wait 2 seconds for existing JWTs to expire
sleep 2

# 4. Restore normal JWT TTL
# In .env, set: JWT_TTL_SECONDS=3600

# 5. Restart API
docker compose restart api
```

After this, all clients must re-authenticate. New JWTs will carry `organization_id` for all roles.

## Step 3: Rebuild and restart all services

```bash
docker compose up --build -d
```

## Step 4: Verify

```bash
# Check schema version
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;"

# Check new columns exist
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='organization_id';"

# Check triggers
docker exec ecodb-postgres psql -U ecodb -d ecodb -c "SELECT tgname FROM pg_trigger WHERE tgname LIKE 'trg_%';"

# Check API health
curl http://localhost:8080/health
```

## Rollback

If issues arise, rollback the DDL changes:

```bash
docker exec -i ecodb-postgres psql -U ecodb -d ecodb < sql/rollback_5.1.0.sql
```

Note: The Default organization created during migration is preserved (no data loss).

## What changed

- `users.organization_id`: cached org membership for all roles (was CEO-only via query)
- `api_keys`: `replaced_by_key_id` + `grace_until` columns for key rotation
- `teams.organization_id`: org membership for cross-org isolation
- `audit_log.organization_id`: org attribution for all audit entries
- 4 new triggers: org propagation (workspace_leads, project_members) + team cross-org constraints
- JWT payload: `organization_id` now present for all roles (workers, leads, CEOs), not just CEOs
- API key grace period: rotated keys expire after grace_until
- Admin endpoints: 7 operations now accessible to org CEOs (was super-only)
- Rate limiting: per-user sliding window (configurable via ECODB_RATE_LIMIT)
- Graph discovery: pre-filtered by visible_project_ids before truncation
