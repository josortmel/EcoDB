# EcoDB Backup & Restore Runbook

Last verified: 2026-05-13 (Fase 4, schema 4.0.0, ecodb-postgres:1.0.0)

---

## Backup

```bash
MSYS_NO_PATHCONV=1 docker exec ecodb-postgres pg_dump \
  -U ecodb -d ecodb -F c -f /tmp/ecodb_backup.dump
```

Copy out of container:
```bash
docker cp ecodb-postgres:/tmp/ecodb_backup.dump \
  ./backups/ecodb_$(date +%Y%m%d).dump
```

`-F c` = custom format (compressed, supports selective restore). Use `-F p` for plain SQL if needed for inspection.

---

## Restore — Temp DB (verification)

```bash
# 1. Create target DB
docker exec ecodb-postgres psql -U ecodb -d postgres \
  -c "CREATE DATABASE ecodb_restore_test"

# 2. Restore
MSYS_NO_PATHCONV=1 docker exec ecodb-postgres pg_restore \
  -U ecodb -d ecodb_restore_test /tmp/ecodb_backup.dump

# 3. Verify (see checklist below)

# 4. Cleanup
docker exec ecodb-postgres psql -U ecodb -d postgres \
  -c "DROP DATABASE ecodb_restore_test"
```

## Restore — New volume (production recovery)

```bash
# 1. Stop API + MCP (leave postgres running)
docker compose stop api mcp

# 2. Drop + recreate DB
docker exec ecodb-postgres psql -U ecodb -d postgres \
  -c "DROP DATABASE ecodb; CREATE DATABASE ecodb"

# 3. Restore
MSYS_NO_PATHCONV=1 docker exec ecodb-postgres pg_restore \
  -U ecodb -d ecodb /tmp/ecodb_backup.dump

# 4. Restart services
docker compose up -d api mcp
```

---

## Verification Checklist

### SQL counts

```bash
TARGET_DB=ecodb_restore_test   # or ecodb for production

docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB \
  -c "SELECT count(*) FROM memories"
# Expected: matches pre-backup count

docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB \
  -c "SELECT count(*) FROM nodes"
# Expected: matches pre-backup count

docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB \
  -c "SELECT count(*) FROM triples"
# Expected: matches pre-backup count

docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB \
  -c "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
# Expected: current schema version (e.g. 4.0.0)
```

### AGE / Cypher traversals

**REQUIRED:** `LOAD 'age'` + `SET search_path = public, ag_catalog` must precede every Cypher query in a new session. AGE does not persist across `psql` invocations.

```bash
# Entity count — must match SQL nodes count
docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB -c \
  "LOAD 'age'; SET search_path = public, ag_catalog;
   SELECT * FROM cypher('ecodb_graph', \$\$MATCH (n:Entity) RETURN count(n)\$\$)
   AS (cnt agtype);"

# Traversal smoke test
docker exec ecodb-postgres psql -U ecodb -d $TARGET_DB -c \
  "LOAD 'age'; SET search_path = public, ag_catalog;
   SELECT * FROM cypher('ecodb_graph', \$\$
     MATCH (n:Entity {name: 'admin'})-[r]-(m)
     RETURN n.name, type(r), m.name LIMIT 5
   \$\$) AS (src agtype, rel agtype, tgt agtype);"
# Expected: rows with the node's relations
```

### API health

```bash
curl http://localhost:8080/health
# Expected: {"status":"ok","embeddings":"ok",...}
```

---

## Known Issues

### AGE requires LOAD + search_path per session
`pg_restore` restores AGE graph data correctly, but AGE is a shared_preload_libraries extension. In `psql` sessions (not the running API), you must manually run:
```sql
LOAD 'age';
SET search_path = public, ag_catalog;
```
before any `cypher()` call. The API container sets this automatically via its pool connection init.

### AGE count must equal SQL nodes count
After restore, `SELECT count(*) FROM nodes` (SQL) and `MATCH (n:Entity) RETURN count(n)` (AGE) should be equal. A mismatch indicates AGE sync drift — run `_ensure_node` repair or rebuild AGE graph from nodes table.

### schema_version_target in API /health
`schema_version_target` in `/health` reflects `settings.py`, not the live DB. After a schema migration, update `settings.SCHEMA_VERSION` and rebuild the API image.

---

## Verified Results (2026-05-13, schema 4.0.0)

| Check | Result |
|-------|--------|
| memories | 1224 |
| nodes | 212 |
| triples | 359 |
| schema_version | 4.0.0 |
| AGE entity count | 212 (= nodes ✓) |
| AGE traversal (sample node) | 5 rows, RELATES_TO edges ✓ |
| pg_restore exit code | 0 (clean) |
