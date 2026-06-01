# Migration v0.9 → v0.9.5

## Schema changes

Apply: `sql/migrate_5.0.1_to_5.1.0.sql`

```bash
docker exec -i ecodb-postgres psql -U postgres ecodb < sql/migrate_5.0.1_to_5.1.0.sql
```

### New objects

| Object | Type | Purpose |
|---|---|---|
| `propagate_user_org_id` | Function + 2 triggers | Sync `users.organization_id` from workspace_leads / project_members |
| `trg_propagate_org_ws_leads` | Trigger on `workspace_leads` | AFTER INSERT/UPDATE/DELETE |
| `trg_propagate_org_proj_members` | Trigger on `project_members` | AFTER INSERT/UPDATE/DELETE |
| `idx_audit_log_organization` | Index | Fast org-scoped audit queries |
| `check_team_org_consistency` | Function + trigger | Prevent cross-org team membership |

### Backfill

The migration runs a backfill to set `users.organization_id` for existing rows:

```sql
UPDATE users u SET organization_id = (
    SELECT DISTINCT w.organization_id
    FROM workspace_leads wl JOIN workspaces w ON w.id = wl.workspace_id
    WHERE wl.user_id = u.id AND w.organization_id IS NOT NULL
    LIMIT 1
)
WHERE u.is_ceo = false AND u.is_super = false;
```

## Conscious debt — DD8: LIMIT 1 in propagate_user_org_id

The trigger uses `LIMIT 1` when resolving `organization_id`:

```sql
SELECT DISTINCT w.organization_id INTO resolved_org_id
FROM workspace_leads wl
JOIN workspaces w ON w.id = wl.workspace_id
WHERE wl.user_id = target_user_id AND w.organization_id IS NOT NULL
LIMIT 1;
```

**Why LIMIT 1**: In the current data model, a user belongs to at most one organization. The LIMIT 1 is a guard against data corruption, not a semantic choice. If a user somehow has leads in two different orgs, the trigger picks one arbitrarily.

**When this becomes a problem**: Never in the intended usage (single-org user), but would surface if:
- Data was corrupted pre-migration
- A future feature allows cross-org contractors (not planned)

**DD8 resolution trigger**: v1.0 or first stale incident where `users.organization_id` is wrong for an existing user. Resolution: add CHECK constraint or application-level validation that prevents a user from having workspace_leads in more than one organization.

## Rollback

```bash
docker exec -i ecodb-postgres psql -U postgres ecodb < sql/rollback_5.1.0.sql
```

Rollback drops the trigger function and both triggers. `users.organization_id` values set by the backfill are NOT reverted (column remains, populated). Harmless — the column was not used by v0.9 code paths.

## API changes (v0.9.5)

- JWT tokens now include `organization_id` and `is_ceo` claims
- Rate limiting keyed by `actor_id:method:path` (was `actor_id:path`)
- New per-route rate limits: `/memories/preview` (10 rpm), `/memories` POST (20 rpm)
- `GET /graph/clusters` accepts `limit` / `offset` query params (default limit=500)
- `GET /graph/neighbors/{node}` and subgraph center lookup are now case-insensitive
- `TeamResourceLink` response model now returns `team_id` + `project_id` fields
- `onboarding` endpoint returns `contradictions: null` instead of `[]`
