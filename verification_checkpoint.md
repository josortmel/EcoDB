# verification_checkpoint — 2026-06-05 12:15 Europe/Madrid

## Metadatos
- **Proyecto**: C:\Users\Admin\Documents\EcoDB
- **Fecha y hora**: 2026-06-05 12:15 CET
- **Autor**: Prima (Arquitecto)
- **Brief de referencia**: consolidacion_v1_brief.md v2

---

## 1. Estado real del sistema (comandos ejecutados)

### schema_version storage
- `init.sql:46-50`: TABLE `schema_version` (version TEXT PK, applied_at TIMESTAMPTZ, notes TEXT). NOT a GUC.
- Query correcta: `SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1`

### Migration files — transaction wrapping
- `migrate_3_0h_multimodal.sql`: NO BEGIN/COMMIT — runs in autocommit
- `migrate_5.0.1_to_5.1.0.sql`: HAS `BEGIN;` on line 3
- `migrate_5.1.0_to_5.1.1.sql`: HAS `BEGIN;` on line 1
- `trigger_age_sync.sql`: NO BEGIN/COMMIT — runs in autocommit
- **Implication**: runner MUST wrap each file in `conn.transaction()` for atomicity. Files with own BEGIN create nested tx (PG WARNING, safe).

### settings.py state
- Line 18: `ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")` — defaults to production (B8)
- Line 22: `API_VERSION = os.environ.get("API_VERSION", "0.9.0")` — docstring says "0.1.0" (V8)
- Line 23: `SCHEMA_VERSION = "5.1.0"` — drift, should be "5.1.1" (V1)
- Line 42: `_default_origins = "http://localhost:8080,http://localhost:8081"` — 8081 orphan (V7)
- Line 79-124: `validate_production_secrets()` validates JWT_SECRET, API_KEY_PEPPER, CORS, EMBEDDINGS_URL, LLAMA_CPP_URL. Does NOT validate INTERNAL_BROADCAST_SECRET.

### main.py lifespan
- Line 71: `settings.validate_production_secrets()` — first call
- Line 91-103: `load_dictionary_to_cache(pool)` — uses `get_pool()` at line 93
- **Runner insertion point**: after line 71, before line 91. Runner calls `get_pool()` itself.

### Dockerfile.api
- Line 23: `mkdir -p /app/media && chown -R apiuser:apiuser /app/.cache /app/media` — chown at build time only
- Line 31: Explicit COPY of .py files — NO sql/ directory
- Line 40: `USER apiuser` — permanent, no entrypoint override
- Line 52: CMD uvicorn — no ENTRYPOINT defined
- **gosu**: NOT installed in image

### INTERNAL_BROADCAST_SECRET
- `events.py:21`: `os.environ.get("INTERNAL_BROADCAST_SECRET", "")` — defaults to ""
- `events.py:157`: `if _INTERNAL_BROADCAST_SECRET and secret_header == _INTERNAL_BROADCAST_SECRET`
- `worker.py:114`: same pattern
- `docker-compose.yml:124,215`: hardcoded default `fa8b0c02ef55b172afdf48ecc32330ae`

### Dashboard errMsg.ts
- Lines 24-36: handles 429, 403, 422 specifically. All other errors (including 500) fall to `fallback` parameter (generic message from caller). No info disclosure — but misleading message for 500 ("Couldn't reach EcoDB" when backend DID respond).

### .env.example
- EXISTS (62 lines). Has DB_PASSWORD, JWT_SECRET, API_KEY_PEPPER, CORS, LLM, reranker.
- Does NOT have INTERNAL_BROADCAST_SECRET.

---

## 2. Contadores reales

- Migration SQL files in sql/: init.sql + 4 migrations + 2 non-idempotent (fase4, fase5) + 2 debt files + 1 pre-migrate
- Docker-compose services: postgres, embeddings, api, mcp, ner, worker (with-ingestion), llm (with-llm)
- Dashboard: Electron + Vite + React + TypeScript, package.json version 1.1.0

---

## 3. Hallazgos concretos que el Spec debe citar

- **H1**: schema_version es TABLE no GUC (init.sql:46-50). Spec §3 query must use SELECT FROM table.
- **H2**: 2 of 4 migration files lack BEGIN/COMMIT. Runner must wrap in transaction.
- **H3**: validate_production_secrets() is at settings.py:79-124. Adding INTERNAL_BROADCAST_SECRET goes here.
- **H4**: Dockerfile has no ENTRYPOINT, USER apiuser at line 40. D10 requires entrypoint.sh + gosu install.
- **H5**: errMsg.ts already guards against info disclosure (only 422 shows detail). Fix is adding 5xx case with server-side message, not removing the guard.
- **H6**: .env.example at root, 62 lines. INTERNAL_BROADCAST_SECRET must be added.
- **H7**: Runner insertion point: main.py between line 71 (validate_production_secrets) and line 91 (dictionary cache). get_pool() available — called at line 93, runner calls it independently.
- **H8**: gosu not in image — must be installed via apt-get in Dockerfile build stage.
