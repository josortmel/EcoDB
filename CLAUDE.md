# EcoDB — Project CLAUDE.md

Memoria colectiva compartida para equipos multi-agente. PostgreSQL + pgvector + Apache AGE + Jina v4 + GLiNER + MCP.

## Versiones actuales

- API: `0.23.0` (imagen Docker) / API_VERSION `0.9.0`
- Schema: `5.1.1`
- MCP: `1.6.0`
- Embeddings: `0.2.5`
- NER: `1.0.0`
- Postgres: `1.0.0` (PG16 + pgvector + AGE 1.5.0)
- Release pública: `v0.9.5`

## Arquitectura — 6 servicios Docker

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   MCP :8091 │────▶│  API :8080  │────▶│ Postgres    │
│  (proxy)    │     │  (FastAPI)  │     │ :5435→5432  │
└─────────────┘     └──┬───┬──┬───┘     │ pgvector    │
                       │   │  │         │ AGE graph   │
              ┌────────┘   │  └───────┐ │ pg_trgm     │
              ▼            ▼          ▼ └─────────────┘
     ┌────────────┐  ┌──────────┐  ┌──────┐
     │ Embeddings │  │   NER    │  │ LLM  │
     │ Jina v4    │  │ GLiNER   │  │ opt. │
     │ GPU/CUDA   │  │ CPU      │  │ CPU  │
     │ (interno)  │  │ :8092→   │  └──────┘
     └────────────┘  │    8091  │
                     └──────────┘
```

- **postgres** — PG16, imagen custom con AGE compilado. Data en named volume `ecodb_data`. Puerto host `127.0.0.1:5435`.
- **api** — FastAPI + uvicorn. Motor GAMR (10 etapas), auth JWT, CRUD. Puerto `8080`.
- **embeddings** — Jina v4 512-dim, INT8 GPU. Solo accesible internamente (sin puerto host). HF cache bind-mount `:ro`.
- **mcp** — Proxy MCP→API. SSE transport. Puerto `8091`. Sin lógica de negocio.
- **ner** — GLiNER NER para extracción de entidades. CPU-only. Puerto host `8092`, interno `8091`.
- **llm** (opcional, profile `with-llm`) — llama.cpp + Qwen 2.5 3B. Para clasificación, HyDE.
- **worker** (opcional, profile `with-ingestion`) — Ingesta de documentos (PDF/DOCX/audio).

## Estructura del repo

```
EcoDB/
├── api/                    # FastAPI backend — TODA la lógica de negocio
│   ├── main.py             # App factory, routers, middleware
│   ├── settings.py         # Config central (env vars, feature flags, GAMR weights)
│   ├── search.py           # Motor GAMR (62K, archivo más grande)
│   ├── memories.py         # CRUD memorias (45K)
│   ├── graph.py            # Grafo AGE — Cypher queries (36K)
│   ├── admin.py            # Endpoints admin (34K)
│   ├── auth.py             # JWT + API keys
│   ├── permissions.py      # Cascada de permisos (workspace→project)
│   ├── worker.py           # Pipeline ingesta documentos (23K)
│   ├── gliner_service.py   # NER client + entity dictionary
│   ├── embeddings_client.py # Client httpx → embeddings service
│   ├── reranker.py         # Cross-encoder (Etapa 10 GAMR)
│   ├── bootstrap_first_apikey.py  # Script primer arranque
│   ├── Dockerfile
│   ├── requirements.txt
│   └── tests/              # pytest — 17 archivos de test
├── mcp/
│   ├── server.py           # 32 tools MCP, proxy puro (61K)
│   ├── Dockerfile
│   └── requirements.txt
├── embeddings/
│   ├── server.py           # Jina v4 embedding server (21K)
│   └── Dockerfile
├── ner/
│   ├── server.py           # GLiNER NER server (1.4K)
│   └── Dockerfile
├── sql/
│   ├── init.sql            # Schema completo (38K) — se ejecuta en primer boot
│   └── migrate_*.sql       # Migraciones incrementales
├── docker/
│   └── Dockerfile.postgres # PG16 + pgvector + AGE custom build
├── scripts/
│   ├── setup.sh            # Bootstrap: genera .env, verifica deps
│   ├── backup.sh / restore.sh
│   └── seed_predicates.py  # Semilla del grafo de predicados
├── eval/                   # Benchmarks (LoCoMo, golden set, latencia)
├── docs/
│   ├── architecture/       # Briefs de diseño (governance, ingestion, intelligence, product)
│   └── plans/              # Planes de construcción por sesión
├── docker-compose.yml      # Compose principal
├── docker-compose.seed.yml # Dataset demo
├── .env.example
├── CHANGELOG.md
└── README.md
```

## Schema de base de datos (init.sql)

Tablas principales:
- `users` — con `is_super` (único) e `is_ceo` (mutuamente excluyentes)
- `user_emails` — tabla puente, email como PK (unicidad global)
- `organizations` — empresa cliente, 1:1 con CEO
- `workspaces` — departamento dentro de org
- `projects` — dentro de workspace, `is_common` para proyectos compartidos
- `workspace_leads`, `project_leads`, `project_members` — permisos por rol
- `teams`, `team_members`, `team_resources` — equipos ad-hoc cross-workspace
- `memories` — con `embedding vector(512)`, `visibility`, `type`, `tags TEXT[]`, soft-delete
- `agent_identity` — fragmentos ordenados por `(agent_id, version, fragment_idx)`
- `memory_type_config` — pesos base y decay por tipo
- `entity_dictionary` — diccionario curado para NER
- `entity_links` — links entidad↔memoria
- `documents`, `document_chunks` — ingesta documental
- `schema_version` — versionado de schema

Grafo: `ecodb_graph` en Apache AGE (Cypher). Sync automático via triggers SQL→AGE.

## Motor GAMR — 10 etapas

1. Clasificación query_type (factual/historical/analytical/contextual)
2. Filtro permisos cascada
3. Búsqueda semántica coseno (pgvector HNSW)
4. BM25 lexical (pg_trgm)
5. Expansión por grafo (AGE Cypher)
6. Resolución de fuentes
7. Coherencia temporal (freshness scoring)
8. Detección de contradicciones
9. Score compuesto multiplicativo (pesos por query_type en `GAMR_WEIGHTS_BM25`)
10. Re-ranking cross-encoder (MiniLM-L-6-v2, SHA-pinned)

## Feature flags (settings.py)

Todos controlados por env vars, `_env_bool()`:
- `ENABLE_BM25` — búsqueda lexical
- `ENABLE_BM25_EXPANSION` — expansión BM25
- `ENABLE_AUTO_LINK` — linking automático entidades→grafo
- `ENABLE_WEIGHT_DYNAMIC` — peso dinámico por acceso
- `ENABLE_TRUST_TIERS` — tiers de confianza
- `ENABLE_STOP_ENTITIES_DYNAMIC` — stop entities dinámicas
- `ENABLE_TENSION_DETECTION` — detección contradicciones
- `ENABLE_HYDE` — Hypothetical Document Embeddings
- `ENABLE_POST_HOC_CLASSIFIER` — clasificación post-hoc
- `ENABLE_LLM_TELEMETRY` — telemetría LLM
- `ENABLE_CONTEXT_INJECTION` — inyección de contexto en MCP

## Auth

- API keys: formato `ecodb_<base64url>`, hasheadas con bcrypt + pepper
- JWT: HS256, TTL configurable (default 1h)
- MCP hace intercambio API key → JWT automáticamente, con refresh en 401
- `validate_production_secrets()` bloquea arranque en producción con secretos dev

## Desarrollo local

```bash
# Tests (requiere postgres en :5435)
cd api && python -m pytest tests/ -v

# API local contra servicios Docker
docker compose up postgres embeddings ner -d
cd api && uvicorn main:app --reload --port 8080

# Rebuild imagen API
docker compose build api

# Ver logs
docker compose logs -f api mcp
```

## Primer arranque (usuario nuevo)

```bash
git clone https://github.com/josortmel/ecodb && cd ecodb
./scripts/setup.sh                    # genera .env con secretos random
docker compose up --build -d          # construye imágenes + descarga modelos (~35 GB)
docker compose logs -f embeddings ner # esperar "model loaded"
docker exec ecodb-api python bootstrap_first_apikey.py
# copiar la key a .env → ECODB_API_KEY=ecodb_...
docker compose restart mcp
```

## Errores comunes / deuda conocida

- **Media path**: tras release pública se arregló ruta hardcodeada `C:\EcoDB\media` → relativa al proyecto. Si media no funciona, verificar `ECODB_MEDIA_DIR` y `WINDOWS_MEDIA_PREFIX`.
- **Embeddings re-download**: si HF cache no es bind-mount, cada rebuild descarga ~7GB. Usar `HF_CACHE_PATH` en `.env`.
- **AGE no disponible para PG17**: imagen postgres anclada a PG16 por Apache AGE 1.5.0.
- **Reranker first-request**: pre-cacheado en Dockerfile con SHA pin. Si SHA no coincide con runtime → re-download.
- **NER puerto**: internamente usa 8091, pero host expone 8092 (conflicto con MCP que usa 8091).
- **Primer boot MCP**: MCP no arranca hasta generar API key con `bootstrap_first_apikey.py` y reiniciar el servicio.
- **Backup/restore scripts**: verificar que `ECODB_CONTAINER` coincide con el container_name en docker-compose.yml (default: `ecodb-postgres`).
- **Worker SSE events**: require `INTERNAL_BROADCAST_SECRET` in `.env`. If dashboard shows no document events, check this env var first.
- **Media volume no compartido**: API y worker deben montar el MISMO volumen `ecodb_media:/app/media`. Si solo worker lo monta, uploads vía API caen en capa efímera invisible al worker → "file not found". Verificar `volumes:` en ambos servicios docker-compose.
- **Docker build --no-cache**: innecesario para añadir dependencias pip. Basta con modificar `requirements.txt` → la capa COPY se invalida sola y pip install re-ejecuta. `--no-cache` baja torch entero (532MB+) sin necesidad.
- **Media dir permissions**: el volumen Docker se crea como root. El contenedor API corre como `apiuser`. Post-deploy: `docker exec -u root ecodb-api sh -c "mkdir -p /app/media && chown apiuser:apiuser /app/media"`.

## Deuda técnica — deep hunt v0.9 (2026-06-01)

### Spec §7 — deferred by design

| # | Item | Trigger |
|---|------|---------|
| DD1 | OAuth / SSO enterprise | First customer with corporate SSO |
| DD2 | Scopes per-API-key (read-only, write, admin) | Customer needing read-only keys |
| DD3 | Redis rate limiting (currently in-memory) | >50 concurrent users |
| DD4 | Graph isolation by partitioning (org-scoped) | Customer with sensitive data (health, finance) |
| DD5 | entity_dictionary per-org | Customer with private NER categories |
| DD6 | superuser visible_project_ids without LIMIT | >200 projects in production |
| DD7 | Automatic scoping middleware (currently grep-verified) | Team grows beyond manual verification |
| DD8 | Periodic reconciliation of users.organization_id | v1.0 or first stale incident |

### Architectural — multi-org infrastructure (not blocking single-org)

| # | Item | Severity | Trigger |
|---|------|----------|---------|
| VS1/VS2 | Graph endpoints without org scoping | HIGH for multi-org | Second org in production (DD4) |
| VS-L2-6 | MCP single API key (no per-agent isolation) | MEDIUM | Per-agent key rotation needed (DD2) |
| IC4 | Super audit_log has org_id=NULL on org resources | MEDIUM | Audit forensics requirement |

### Pre-existing (found during v0.9 deep hunt)

| # | Item | Severity |
|---|------|----------|
| F3 | AGE hop-2 timeout under load → silent result degradation (has statement_timeout but still occurs under load) | MEDIUM |

### Test coverage gaps

- `graph.py` — no tests for expand_by_graph() or detect_contradictions()
- `worker.py` — no tests for circuit breaker, re-indexing, file hash
- `admin.py` — no tests for redistribute or entity_dictionary

## Invariantes — NO tocar sin entender

1. `init.sql` se ejecuta solo en primer boot (docker-entrypoint-initdb.d). Cambios posteriores van en `sql/migrate_*.sql`.
2. `EMBEDDING_DIM = 512` — debe coincidir con el modelo Jina v4 y la columna `vector(512)` en SQL.
3. Reranker SHA pin — Dockerfile pre-cache y runtime deben usar el mismo SHA (`c5ee24cb16019beea0893ab7796b1df96625c6b8`).
4. `ecodb_graph` — nombre del grafo AGE. Hardcodeado en SQL y en `graph.py`.
5. `search_path = public, ag_catalog` — persistido a nivel DATABASE. Sin esto, AGE no funciona.
6. Solo UN superusuario (partial unique index `idx_users_one_super`).
7. `is_super` e `is_ceo` mutuamente excluyentes (CHECK constraint).
8. HF cache del embeddings montado `:ro` — trust_remote_code con revision pinned.
9. NER Dockerfile DEBE pinear versiones iguales a api/ (fastapi, uvicorn) para evitar drift.
10. backup.sh/restore.sh container name DEBE coincidir con docker-compose.yml.
11. MCP server.py — TODAS las tools deben usar _ok()/_err() para error handling. No devolver `resp` raw.
12. GAMR_WEIGHTS_BM25 en settings.py — los pesos deben sumar ~1.0 por query_type.
13. `users.organization_id` debe ser consistente con workspace membership — si un user es CEO de org A, sus workspaces deben pertenecer a org A. Violarlo corrompe el modelo de permisos en cascada.
14. `_CEO_ALLOWED_ADMIN_OPS` frozenset en `permissions.py` controla qué operaciones admin puede ejecutar un CEO. Añadir operaciones a este set tiene implicaciones de seguridad — requiere revisión explícita antes de cada adición.
15. `INTERNAL_BROADCAST_SECRET` env var must be set for worker SSE events to reach the broadcast endpoint. Without it, all document lifecycle events are silently dropped.

## Roadmap

- **v0.8.6** ✓ completada: Fix seguridad + primer arranque + robustez. Sin features nuevas.
- **v0.9.0** ✓ completada: Multi-tenant — organization_id en JWT, CEO scoping, API key rotation con grace period, rate limiting headers, audit log completo, schema v5.1.0.
- **v0.9.5** ✓ completada: Debt resolution — SSE org-scoped broadcast, method-aware rate limiting, Louvain SQL pre-filtering, search user_id document exclusion, graph org scoping design doc, trigger verification tests, 10 mechanical fixes. Dashboard backend endpoints (B1-B9) included.
- **v1.0**: Dashboard Electron — React+Vite+Tailwind. Frontend. Spec+Plan by Prima. Lienzo building. Backend endpoints delivered:
  - `GET /graph/all` — full graph paginated (limit/offset, degree DESC, cluster_id)
  - `POST/PUT/DELETE /admin/predicates` — predicates CRUD (super-only)
  - `POST /admin/merge-entities` — keep_as_alias flag for merge+alias
  - `POST /documents/upload` — multipart file upload (dashboard ingestion)
  - `POST /admin/attention-inbox/summary` + `/details` — org-scoped governance inbox
  - `GET /api/v1/stats/timeline` — daily activity timeline
  - `PUT /memories/{id}/staleness` — manual staleness management
  - `POST /memories/preview` — GLiNER dry-run
  - `GET /graph/clusters` — Louvain communities (paginated)
  - FB-ALIAS pipeline fix: rejected candidates not re-proposed

## Licencia

PolyForm Noncommercial 1.0.0. Uso personal/educativo/no-comercial libre. Uso comercial requiere licencia de Eco Consulting.
