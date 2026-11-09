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

## Total loss — you lost the machine AND the `.env`

The two sections above assume your `.env` survived. This one is for the day it didn't: the disk died, the server is gone, and all you have is a backup file.

### What to keep, and where

| Keep this | Why | Where |
|---|---|---|
| The backup (`.dump` or `.sql.gz` from `scripts/backup.sh`) | It is your memory. Everything else can be rebuilt. | Off the machine: another disk, a private repo, cloud storage. |
| The keys of your **external providers** (`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `CELL_LLM_KEY`, and any provider key you saved in EcoDB) | EcoDB cannot regenerate them: they belong to your provider account. | Your password manager. |
| *Optional:* the list of files where your clients keep their EcoDB key (MCP configs, scripts) | `restore.sh --key-targets` rewrites them for you. | One path per line, outside the repo. |

You do **not** need to keep the `.env`. Its secrets are regenerated (next section). Keeping it in the same place as the backup would be worse: whoever gets the backup would also get the keys.

### What you lose, on purpose

The backup does not carry the `.env`, so after a total loss:

- **Every old API key stops working.** Keys are hashed with a pepper that lived in the `.env`; `--recover` deactivates all of them and issues two new ones (`familia-<date>` and `mcp-service-<date>`).
- **Provider keys stored inside EcoDB are deleted.** They were encrypted with `ENCRYPTION_KEY`, which is gone. Before deleting them, `restore.sh` prints which provider and name each one was, so you know what to paste again.
- **Database passwords, JWT secret and broadcast secret** are new. Nothing outside EcoDB should depend on them.

Your memories, documents, graph and clusters are all in the backup and come back intact.

### How to come back

```bash
# 1. Fresh clone and images
git clone https://github.com/josortmel/EcoDB.git && cd EcoDB
bash scripts/setup.sh --non-interactive --cpu   # or without --cpu if you have a GPU

# 2. Start ONLY postgres, then restore with --recover
docker compose up -d postgres
bash scripts/restore.sh /path/to/backup.dump \
  --target=ecodb --allow-dangerous --recover \
  [--key-targets=/path/outside/repo/key_targets.txt]

# 3. Start the rest
docker compose up -d
```

What `--recover` does, in order:

1. Restores the backup into `ecodb`.
2. Prints the provider keys you will have to paste again, then deletes them.
3. Sets new database passwords (`ALTER ROLE`), deactivates every old API key and creates the two new ones.
4. Writes the new secrets into `.env` (`ECODB_DB_PASSWORD`, `CELL_DB_PASSWORD`, `ECODB_JWT_SECRET`, `ECODB_API_KEY_PEPPER`, `ECODB_API_KEY`, `INTERNAL_BROADCAST_SECRET`, `ENCRYPTION_KEY`).
5. Saves the two new API keys in `.recovered_keys` (permissions 600, next to `.env`). They are **not** printed.
6. If you passed `--key-targets`, replaces the old `ecodb_…` key with the new family key in each listed file.

### After restoring: checklist

- [ ] Memory count equals the backup's (see *SQL counts* below).
- [ ] `curl http://localhost:8080/health` answers `ok`.
- [ ] Your clients use the new key from `.recovered_keys`, and a real `search` returns results.
- [ ] You pasted the external provider keys again into `.env` (and in the dashboard, the ones `restore.sh` listed).
- [ ] **Check `ECODB_ENV` in `.env`.** Today, if the variable is missing, `--recover` sets it to `development`. A recovered *production* install must say `ECODB_ENV=production`: set it by hand and restart the API. (An explicit option for this is planned.)
- [ ] Delete `.recovered_keys` once every client has its new key.

### Things that can go wrong

- **Never run plain `docker compose up` next to another running EcoDB on the same machine.** The compose file pins container names: you would replace the other instance's containers.
- **Optional services keep their own secrets.** If you used the alerting override (`docker-compose.alerting.yml`), set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` again: `restore.sh` does not list them yet.
- The first start downloads the embedding model (several GB). If the download stalls, restarting the container resumes it.

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
