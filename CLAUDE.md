# EcoDB — Project CLAUDE.md

Memoria colectiva compartida para equipos multi-agente. PostgreSQL + pgvector + Apache AGE + Jina v4 + GLiNER + MCP.

## Versiones actuales

- API: `0.25.0` (imagen Docker) / API_VERSION `0.9.0`
- Schema: `5.3.0`
- MCP: `1.8.0` (40 tools: 32 base + 8 clusters/navegación)
- Embeddings: `0.2.5`
- NER: `1.0.0`
- Postgres: `1.0.0` (PG16 + pgvector + AGE 1.5.0)
- Cell Worker: `0.2.0` (profile `with-metacognition`, config desde DB + cron croniter)
- ecodb-langchain: `0.2.0` (SDK 13 tools nativas + 40 via MCP parity)
- Release pública: `v1.3.1` (Progressive zoom + fractal navigation)

## Arquitectura — 6 servicios Docker

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   MCP :8091 │────▶│  API :8080  │────▶│ Postgres    │
│  (proxy)    │     │  (FastAPI)  │     │ :5435→5432  │
└─────────────┘     └──┬───┬──┬───┘     │ pgvector    │
                       │   │  │         │ AGE graph   │
              ┌────────┘   │  └───────┐ │ pg_trgm     │
              ▼            ▼          ▼ └─────────────┘
     ┌────────────┐  ┌──────────┐  ┌──────┐  ┌──────────┐
     │ Embeddings │  │   NER    │  │ LLM  │  │ Cell     │
     │ Jina v4    │  │ GLiNER   │  │ opt. │  │ Worker   │
     │ GPU/CUDA   │  │ CPU      │  │ CPU  │  │ opt.     │
     │ (interno)  │  │ :8092→   │  └──────┘  │ DeepSeek │
     └────────────┘  │    8091  │             └──────────┘
                     └──────────┘
```

- **postgres** — PG16, imagen custom con AGE compilado. Data en named volume `ecodb_data`. Puerto host `127.0.0.1:5435`.
- **api** — FastAPI + uvicorn. Motor GAMR (10 etapas), auth JWT, CRUD. Puerto host `127.0.0.1:8080` y `[::1]:8080` (solo loopback desde el 28-sep, #382).
- **embeddings** — Jina v4 512-dim, INT8 GPU. Solo accesible internamente (sin puerto host). HF cache bind-mount `:ro`.
- **mcp** — Proxy MCP→API. SSE transport. Puerto host `127.0.0.1:8091` y `[::1]:8091`. Sin lógica de negocio. **NO autentica a su cliente**: usa su propia ECODB_API_KEY, así que quien llegue al puerto tiene las 40 tools (search/read/save/delete/identity). NUNCA publicarlo fuera de loopback sin poner auth delante (#383).
- **ner** — GLiNER NER para extracción de entidades. CPU-only. Puerto host `127.0.0.1:8092` y `[::1]:8092`, interno `8091`.
- **llm** (profile `with-llm`, **OFF por defecto** — `with-llm` NO está en `COMPOSE_PROFILES`; además parado a propósito el 2026-08-24: la API usa DeepSeek y HyDE local está desactivado) — llama.cpp + Qwen 2.5 3B. Para clasificación, HyDE.
- **worker** (profile `with-ingestion`, **ON por defecto** vía `COMPOSE_PROFILES` en `.env`) — Ingesta de documentos (PDF/DOCX/audio).
- **ecodb-cell** (profile `with-metacognition`, **ON por defecto** vía `COMPOSE_PROFILES` en `.env` desde 2026-08-24) — Cell worker: consolidation (weekly clustering), foresight extraction (daily), skill distillation (weekly). **Es el ÚNICO que corre el scheduler de consolidación programada** (croniter sobre `cell_task_configs`); el trigger de la API es solo MANUAL/bajo demanda, no tiene calendario. Apagar cell congela la memoria telescópica (el boot de los agentes). Conecta directamente a postgres con role `ecodb_cell` (least-privilege). LLM: LangChain si ecodb-langchain instalado, httpx directo a DeepSeek como fallback. EcoDB NO requiere ecodb-langchain para funcionar. Detalle del mecanismo (scheduler DB-config, catch-up, células): `api/cell_worker.md`.

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
│   ├── cell_worker.py      # Metacognition cells: clustering + prompts + writes. LLM: LangChain (ecodb-langchain) si instalado, httpx fallback si no
│   ├── pagination.py       # Shared paginate() helper (extracted from 5 files)
│   ├── shared_models.py    # Shared Pydantic models (CaseResponse, TensionAction)
│   ├── clusters.py         # Cluster CRUD (8 endpoints)
│   ├── briefing.py         # Briefing endpoint (foresights + tensions + telescopic)
│   ├── foresights.py       # Foresight listing endpoint
│   ├── cases.py            # Case listing endpoint
│   ├── skills.py           # Skill listing + detail + status endpoints
│   ├── cells.py            # Cell telemetry endpoints (runs + health)
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
├── ecodb-langchain/        # SDK LangChain + agente LangGraph + cell engine
│   ├── src/ecodb_langchain/
│   │   ├── client.py       # EcoDBClient — httpx sync, auth JWT, 1:1 con MCP
│   │   ├── tools.py        # 9 tools LangChain nativas
│   │   ├── agent.py        # StateGraph LangGraph (ReAct, model-agnostic)
│   │   ├── mcp_tools.py    # 32 tools via langchain-mcp-adapters
│   │   ├── retriever.py    # BaseRetriever sobre GAMR
│   │   ├── memory.py       # Memoria durable cross-session
│   │   └── cell_agent.py   # Reemplazo de _llm_call para cell_worker
│   └── tests/
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
- `memories` — con `embedding vector(512)`, `visibility`, `type`, `tags TEXT[]`, soft-delete, `foresight_start/end` (temporal signals), `metadata JSONB` (structured per-type data)
- `memory_clusters` — clusters de memorias por agente. Niveles: weekly/monthly/quarterly/yearly. `narrative` (escrita por CellAgent automáticamente o por owner via PUT /narrate). `centroid vector(512)`, `member_ids UUID[]` (cap 500), `source_ids UUID[]` (apilamiento telescópico), `status` (candidate/active/rejected/superseded)
- `cell_runs` — telemetría de ejecuciones de células. RLS habilitado para role ecodb_cell.
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

## Sistema de alias de entidades

Detección de nombres similares de entidades para unificar duplicados. Pipeline:

1. **Detección automática**: al crear una memoria, `link_entities_from_content()` (graph.py) extrae entidades vía GLiNER + diccionario y llama a `detect_alias_candidates()` (gliner_service.py). Compara cada nombre contra nodos existentes con `pg_trgm.similarity() >= 0.65`.
2. **Escaneo manual**: `POST /admin/alias-candidates/scan` con threshold, max_per_name, name_filter y dry_run configurables desde la dashboard.
3. **Revisión**: `PUT /admin/alias-candidates/{id}` — approve/reject manual. Campos `merge` (ejecutar fusión) y `reverse` (invertir dirección: target→source en vez de source→target).
4. **Listado**: `GET /admin/alias-candidates?status=pending|approved|rejected|archived` — histórico completo.
5. **Inbox**: `GET /admin/attention-inbox/summary` incluye `pending_alias_candidates` count.

Archivos clave: `gliner_service.py` (detección + scan), `graph.py` (link_entities_from_content), `admin.py` (endpoints review/scan/list), `background.py` (purga >90 días).

## Desarrollo local

```bash
# Tests (requiere postgres en :5435)
cd api && python -m pytest tests/ -v

# API local contra servicios Docker
docker compose up postgres embeddings ner -d
cd api && uvicorn main:app --reload --port 8080

# Rebuild imagen API (build context es la raíz del repo, no ./api)
docker compose build api

# Ver logs
docker compose logs -f api mcp
```

## Primer arranque (usuario nuevo)

```bash
git clone https://github.com/josortmel/ecodb && cd ecodb
./scripts/setup.sh                    # genera .env con secretos random
# IMPORTANTE: .env debe incluir esta línea (worker + cell always-on):
#   COMPOSE_PROFILES=with-ingestion,with-metacognition
# Sin ella, `docker compose up -d` levanta solo 5/8 servicios (sin worker ni cell)
# y la consolidación de memoria programada NO corre → la vista telescópica se congela.
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
- **Puertos SIEMPRE con IP de loopback (28-sep, #382)**: `"8080:8080"` sin IP = 0.0.0.0 = toda la LAN (la Ethernet está en perfil Público y la regla «Docker Desktop Backend» deja entrar). Hasta el 28-sep API, MCP y NER estaban así, y el MCP daba la memoria entera sin credenciales. Se publica DOS veces, `127.0.0.1:P:P` y `[::1]:P:P`, porque en Windows `localhost` resuelve primero a ::1 y los MCP del host usan `http://localhost:8080`. Comprobar con `docker ps` que la columna Ports no diga 0.0.0.0. Acceso remoto = `tailscale serve` hacia localhost (#383), nunca atar Docker a la IP de Tailscale.
- **Primer boot MCP**: MCP no arranca hasta generar API key con `bootstrap_first_apikey.py` y reiniciar el servicio.
- **Backup/restore scripts**: verificar que `ECODB_CONTAINER` coincide con el container_name en docker-compose.yml (default: `ecodb-postgres`).
- **Worker SSE events**: require `INTERNAL_BROADCAST_SECRET` in `.env`. If dashboard shows no document events, check this env var first.
- **INTERNAL_BROADCAST_SECRET rotation (existing installs)**: versions before v1.2.0 shipped with a public default (`fa8b0c02ef55b172afdf48ecc32330ae`) in docker-compose.yml. Any install that didn't override this var was using a known-public secret. Rotate: `openssl rand -hex 32` → set `INTERNAL_BROADCAST_SECRET=<new>` in `.env` → `docker compose restart api worker`.
- **Media volume no compartido**: API y worker deben montar el MISMO volumen `ecodb_media:/app/media`. Si solo worker lo monta, uploads vía API caen en capa efímera invisible al worker → "file not found". Verificar `volumes:` en ambos servicios docker-compose.
- **Docker build --no-cache**: innecesario para añadir dependencias pip. Basta con modificar `requirements.txt` → la capa COPY se invalida sola y pip install re-ejecuta. `--no-cache` baja torch entero (532MB+) sin necesidad.
- **Media dir permissions**: el volumen Docker se crea como root. El contenedor API corre como `apiuser`. Post-deploy: `docker exec -u root ecodb-api sh -c "mkdir -p /app/media && chown apiuser:apiuser /app/media"`.
- **Alias candidates vacíos**: si `GET /admin/alias-candidates?status=pending` devuelve 0 resultados con muchos nodos activos, el pipeline de memoria probablemente no está llamando a `detect_alias_candidates()`. Verificar que `link_entities_from_content()` recibe `pool`. Ejecutar `POST /admin/alias-candidates/scan` para poblar retroactivamente.
- **Alias threshold muy alto**: `_ALIAS_SIM_THRESHOLD` en `gliner_service.py`. Si no se generan candidatos, bajar a 0.55-0.60. Si hay demasiado ruido (fechas, números), subir a 0.70-0.75. El valor 0.65 está calibrado para nombres de entidad.
- **`POST /memories` → 503 / `save_memory` ReadTimeout con todo "Up"** (7-sep-2026, dos veces): `ecodb-embeddings` pasa a `unhealthy` (healthcheck 10 s vencido) con el encoder colgado («Encoding texts… 0/1» apilado), 400-600 % de CPU y 3-4 GB de GPU retenidos, sin ninguna línea de error en su log. Causa en el HOST: la 2080 Ti llena (vmwp/Docker ~6,4 GB + `dwm.exe` 3-4,6 GB en dos instancias al ~50 % del motor 3D; sospechosos NVIDIA App Overlay y escalado 150 %). Diagnóstico: `docker inspect ecodb-embeddings --format '{{json .State.Health.Log}}'`, `nvidia-smi`, y en PowerShell `Get-Counter '\GPU Process Memory(*)\Dedicated Usage'` (memoria de GPU por PID; nvidia-smi no la da en WDDM). Remedio: `docker restart ecodb-embeddings` (sin estado; healthy en 60-80 s). Deuda: el encoder debería fallar rápido o caer a CPU avisando, no colgarse en silencio.
- **Backup a GitHub corrupto con «PUSH OK»** (7-sep-2026): `ecodb-backup/backup.ps1` hacía `docker exec pg_dump | docker exec -i gzip > fichero`; desde PowerShell 7 el pipeline convierte los bytes gzip en texto UTF-16 con U+FFFD (irrecuperable) y el script lo subió confirmado. Regla: bytes binarios nunca por el pipeline ni la redirección de PowerShell — comprimir DENTRO del contenedor (`sh -c "pg_dump … | gzip -c > /tmp/x.gz && gzip -t /tmp/x.gz"`), `docker cp` fuera, comprobar la firma `1F 8B`, y verificar por contenido (`zcat | tail`, filas de `COPY public.memories`), nunca por tamaño ni exit code. Push sin terminal: `git -c credential.helper='!gh auth git-credential' push`.
- **DeepSeek 402 Payment Required en `ecodb-cell`**: el saldo se agota sin aviso; `LLM attempt N failed … 402` y `Cell consolidation/weekly agent N failed`. El catch-up del cell worker solo mira UNA ventana hacia atrás (`_catch_up`, ver FARO_ESTADO L47): si el 402 dura más de una cadencia, esa semana/mes no se narra nunca. Comprobar saldo o cambiar `CELL_LLM_PROVIDER`/`CELL_LLM_URL`/`CELL_LLM_MODEL` (env del contenedor) antes del siguiente disparo (`docker logs ecodb-cell | grep "Cron fire"`).
- **Deriva grafo AGE↔SQL** (21-sep-2026, tickets #336/#337): `graph_stats` cuenta de SQL (`triples`/`nodes`) pero el grafo AGE proyectado va CORTO — medido: SQL 6736 aristas vs AGE 6162 (~574 de deriva, 8,5 %) y 54 nodos SQL sin `:Entity`. **Qué lee cada store**: SQL (completos) → `graph_stats`, `/graph/search` fuzzy, `/graph/all`, grados, clusters; AGE → `neighbors`, `path`, `subgraph`, Y el search semántico GAMR (`expand_by_graph` hace el salto por cypher en AGE, graph.py:393; `graph_score` entra multiplicativo en el score, search.py:646 → search mantiene RECALL pero el RANKING queda sesgado, y `graph_discovery=True` pierde recall). **Dos mecanismos medidos**: (A) 249 aristas con un endpoint sin `:Entity` — `_create_age_edge` (graph.py:339) hace `MATCH+CREATE`, si el MATCH no matchea crea 0 y NO lanza (verde callado); (B) ~325 con ambos endpoints presentes y sin arista, causa SIN identificar (candidatos: el trigger SQL→AGE de línea 135 cubre nodos pero quizá no aristas / merge no limpia AGE / purga histórica). Fix en #337 (recomendado B: `_create_age_edge` falla ruidoso si crea 0 + `sync_age` controlado con daemon pausado). **Relacionado con F3** (timeout silencioso, ya conocido): hoy localizado en search.py:407-412 y confirmado que el warning del timeout NO llega al array `warnings` de la respuesta (solo al log `ecodb.gamr`) — para detectarlo hay que leer el log, no `response.warnings`.

## Evolución 2026-09-25 (rama evo/2026-09-25, índice FarOS #371) — lo que hay que saber

- **Despliegue (actualizado tras #373):** `api/constraints.txt` fija las 174 versiones de producción (pip freeze del contenedor vivo) y la base es `python:3.12.13-slim@sha256:229a2c5b…`; un `docker compose build api` reproduce producción paquete a paquete (certificado 25-sep). Se puede volver a construir normal. Rollback de emergencia: `ecodb-api:0.25.0-prevo` (rootfs de producción exportado, NUNCA `docker commit`: hornea secretos). api, worker y ecodb-cell comparten imagen: se recrean los tres. Deuda: los paquetes de apt siguen sin fijar.
- **El MCP de los agentes es el `mcp/server.py` del HOST (stdio), leído del árbol de trabajo de este repo.** Un cambio en server.py entra en cada sesión al reiniciar su MCP; nunca dejar server.py roto en disco. El contenedor `ecodb-mcp` es otro cliente.
- **Tests: `conftest` rechaza la base viva** (puerto 5435 / host postgres, también vía PGHOST/PGPORT/DSN) salvo `ECODB_ALLOW_LIVE_TESTS=1`. BD de pruebas: contenedor `ecodb-test-pg` en 5436 (`TEST_DB_PORT=5436`). Incidente del 25-sep: una corrida contra la viva (limpió sus fixtures; residuo x.md borrado; 5 API keys pytest-* activas desde junio, una super → desactivadas).
- **Grafo: AGE = proyección canónica de SQL `triples`** (extremos resueltos por merged_into a su nodo activo, sin bucles, sin duplicados). SQL guarda la historia (las tripletas de nodos fusionados se quedan, undo_merge las necesita). `_create_age_edge` hace MERGE idempotente y lanza `GraphSyncError` si faltan vértices de dos extremos activos; extremos inactivos se saltan. merge/undo reconcilian en la misma transacción. `POST /graph/reconcile` (super, dry_run por defecto, LOCK nodes+triples). `graph/stats` expone `age_edges / age_edges_expected / age_drift` — **drift ≠ 0 = neighbors/path/search leen un grafo distinto a SQL**. Causa real de la deriva 336/337: TODAS las aristas perdidas tocaban nodos `merged` (el "mecanismo B" era una lectura errónea: `_ensure_node` resucitaba vértices de nodos fusionados). Reconciliado 25-sep: −493 → 0.
- **Dormancia:** memorias sin acceso 60+90 días pasan a `dormant` y search las excluye por defecto (55 % de la base el 25-sep). Ahora: `include_dormant` en el MCP, warning con cuántas escondió un filtro de tags/fechas, y una memoria devuelta se despierta (stale/dormant→active; archived no).
- **Regla de la casa aplicada:** un cero o un canal que no hace lo que su nombre dice se rotula en `warnings` (fechas de anchura cero, dormidas escondidas, filtros de modalidad/usuario que excluyen documentos, related_clusters que falló, consulta que nombra un agente sin filtrarlo).
- **Célula:** la semanal agrupa solo memorias de su semana (la ventana ±3 días creaba clusters gemelos: 29 pares superseded). Reintento cada hora durante 48 h dentro del periodo del fire; `consolidation_gaps()` en `/cells/health` y en `warnings` de la vista progresiva. Los clusters "Arcos y puntos ciegos" son meta-clusters semanales por diseño (centroide NULL, 2 miembros de relleno fijos): no son gemelos.
- **register_document** sube los bytes por `POST /documents/upload` (con `doc_type`, tope 50 MB, denylist y permisos antes de escribir). Antes copiaba a la carpeta del host y el worker leía el volumen → todo documento desde julio quedaba `failed`.
- **Reranker (#243/#374):** el cross-encoder ms-marco es solo inglés y, en modo `replace`, dejaba fuera del top-k aciertos en español. `rerank_mode` = replace|blend|off (por petición o env `RERANK_MODE`); **por defecto blend, α=0.7** (`RERANK_BLEND_ALPHA`), elegido con un benchmark de 5 variantes (sin filtro, P@1/P@5 0,43/0,71 → 0,50/0,86). El orden final es siempre el score compuesto; el reranker solo decide quién entra, y su nota va en `reranker_score`. Recalibrar α tras #374/#375.
- **#359:** el canal de documentos del graph_context se ordena por similitud a la consulta, sin duplicados, y cada item dice `ranked_by`. `DOC_EXPANSION_MIN_SIMILARITY` = 0.0 (ningún umbral absoluto separa: consultas en español sin relación llegan a 0,58–0,63).

## 13-oct-2026 (Hilo) — lo que hay que saber

- **Búsqueda (#486, decide Pepe): el salto 2 de `expand_by_graph` (search.py:514-538) no termina nunca en 5 s.**
  En la semana del 6-oct: 82 de 82 búsquedas de la API con «AGE query timed out hop=2», y 139 «canceling
  statement» en postgres. Cada búsqueda pierde ~5 s y el salto 2 no aporta nada al graph_bonus. El
  `SET LOCAL statement_timeout` va fuera de una transacción y no hace nada (postgres deja un WARNING).
  Medido en solo lectura: `[*2]` desde los hubs (Pepe, Eco, Hilo y EcoDB, grado 285-664) pasa de 30 s;
  el salto 1 más el 2 por SQL por conjuntos sobre `ecodb_graph._ag_label_edge` tardan 0,375 s. Esto
  completa lo que se apuntó como F3 en la deuda de abajo.
- **Tildes (#478): DESPLEGADO el 15-oct a las 10:15 (#494, merge 50aa8a8).** Prima lo verificó el 14 sobre
  una copia. Lleva la migración 5.4.0 (unaccent + `f_unaccent` IMMUTABLE + índice) y `renormalize_dictionary()`
  en el arranque (17 entradas arregladas; la línea de log no sale porque el logger de `gliner_service` está en
  WARNING, así que se comprueba por datos). `normalize_name` ahora QUITA las tildes («España» → «espana»).
  Imagen viva al 15-oct a las 14:22 = **c725e774** (#513; ya NO es la viva, ver la sección del 15-oct): `0.25.0-pre494` (92459ef1, para volver
  atrás) + los 4 módulos de HEAD (gliner_service, graph, main, migrations), con pip freeze igual al de
  producción (66f66faa). Se hace como capa porque el build en frío no tenía caché y volvía a bajar CUDA y apt
  (EcoDB 77487c0d). **OJO:** `ecodb-api:0.25.0-coldbuild494` (37e54376) es un build en frío que terminó solo en
  BuildKit después de matar el cliente y se quedó con la etiqueta (EcoDB a7b3fd95). Tiene OTRO pip freeze: no
  usarlo. Antes de recrear contenedores, comprobar md5 de los módulos y pip freeze de la imagen etiquetada.
  **Reindexado hecho (#513):** las fusiones de Prima (#479, merge_log 65-86) y después
  `eval/reindex_dictionary_unaccent.py --apply`: 1.058 enlaces, 0 hacia nodos fusionados, y el segundo simulacro
  da 0. Ese script sustituye a `eval/reindex_memories.py`, que busca con `lower(name) = normalize_name(...)` y
  ahora enlazaría al gemelo sin tilde: no usar el viejo. `search_nodes` solo devuelve nodos activos.
- **Base de PRUEBAS (5436):** `docker compose -p ecodb-test -f docker-compose.yml -f docker-compose.testdb.yml
  up -d postgres` (mismo initdb que producción, volumen aparte). Tests de la api desde la RAÍZ del repo
  (`TEST_DB_PORT=5436 python -m pytest api/tests/...`); desde api/ no encuentra `sql/`.
- **Flash es el modelo de la cell, y ya está en git** (819f07d, antes 93473ff; 15-oct: decisión de Pepe, en producción desde el
  10-sep). Siguen SIN COMMITEAR en este árbol README.md, scripts/setup.*, alerting/, docker-compose.alerting.yml,
  docker-compose.autoheal.yml, AUTOHEAL_DEPLOY.md y api/cell_worker.md, de dueño sin identificar. Construir
  siempre desde un worktree limpio del commit que se despliega, o con una capa como la del #513.
- **Migraciones:** el contenedor api monta `./sql` del host en `/app/sql`, pero `migrations.py` va dentro
  de la imagen. Un .sql nuevo se ve en el contenedor al momento, pero solo se aplica tras un rebuild que
  lleve su línea en MIGRATIONS.
- **Simulacro de restauración del backup:** el contenedor de prueba deja un volumen anónimo si se borra
  sin `-v`. Usar `docker rm -f -v`, y no fiarse de `pg_isready` durante el init: esperar a «PostgreSQL
  init process complete». Receta: EcoDB aa7f97f9. El del 13-oct restauró las 6.727 memorias.
- **Los scripts de `scripts/` exigen `DATABASE_URL` (#488, 14-oct):** `sync_age.py`, `seed_predicates.py`,
  `migrate_predicates.py` y `generate_cooccurrence_triples.py` ya no tienen valor por defecto (antes era
  `localhost:5432`, que es el Postgres NATIVO de Windows, o `postgres:5432`, que solo existe dentro de Docker, con
  la clave de desarrollo escrita). Sin la variable salen con código 1 antes de conectar y dicen qué poner: desde
  el host `127.0.0.1:5435`, dentro de Docker `postgres:5432`. `sync_age.py` VACÍA el grafo AGE antes de
  rehacerlo: nunca contra producción sin el daemon parado.
- **mcp** (fijado `<2.0.0`; la 1.x solo recibe arreglos de seguridad): 1.29.1 desde el 15-oct (#386). El MCP de
  EcoDB también descarta en silencio los argumentos no declarados: #492, el mismo arreglo que el #339 de FarOS.

## 15-oct-2026, tarde (Hilo) — lo que hay que saber

- **16-oct, 11:22 (#447, decisión 42 de Pepe): los triggers de AGE (`sql/trigger_age_sync.sql`) pasan nombre e id
  como parámetro agtype** (`EXECUTE … $cypher$…$name…$cypher$, $1 … USING jsonb_build_object(...)::text::agtype`), no
  con format(%L): un nombre con apóstrofo («McGee's») rompía el INSERT del nodo entero. Aplicado a producción con psql
  (no hace falta imagen nueva: el trigger vive en la base). Después: 3.884 nodos = 3.884 vértices. Test
  `api/tests/test_age_trigger_comillas.py`. CASI-ACCIDENTE al probarlo: un DELETE con un id sacado del texto de psql
  apuntó al nodo 1 (Eco) y lo paró una FK. En producción, ningún id pasa por el shell: la fila se identifica en el
  propio SQL, con RETURNING, y dentro de BEGIN/ROLLBACK cuando se pueda.
- **16-oct, 10:57 (#561, fase 2b de #386): imágenes vivas** (capas en `Hilo/_deploy494/Dockerfile.overlay561-*`;
  para volver atrás, retaguear `-pre561` y recrear): `ecodb-api:0.25.0` = **e1b51888** (urllib3 2.8.0, langgraph-sdk
  0.4.4, pip 26.2 + apt upgrade), `ecodb-mcp:1.8.0` = **1d436f8c** (mcp 1.30.0: GHSA-84m7-p3x7-pcfv), `ecodb-ner:1.0.0` =
  **a158da92** (fastapi 0.141, starlette 1.7, anyio 4.14.2; setuptools SE QUEDA en 81 porque torch 2.12.1+cpu exige <82),
  `ecodb-embeddings:0.2.5` = **43262bdf** (fastapi/starlette/anyio, urllib3 2.2.3→2.8.0, requests, soupsieve, Jinja2,
  filelock, h2, hpack, lief, Brotli, fsspec, idna, Pygments, wheel, setuptools y **pillow 12.3.0**) y
  `ecodb-postgres:1.0.0` = **ab6c113f** (apt upgrade: openssl, krb5, perl…; probado antes en ecodb-test-pg). Volcado
  previo: `Hilo/_deploy494/ecodb_pre561pg_20261016_104843.sql.gz`. Medido: tests de la api iguales (399/69/6, 0
  diferencias), benchmark v4 idéntico 96/96 tras la tanda 1 y otra vez 96/96 tras apt+pillow, vectores de texto e imagen IDÉNTICOS (`vec561.py`), mismas 6.947
  memorias. Avisos de Python 273 → 88, apt sin pendientes. **Inventario de avisos con `pip list --format=json`, nunca
  con `pip freeze`** (no lista pip/setuptools ni versiona los `@ file://`). Pendiente: transformers 5.10 + torch 2.13
  (#572) y docling (#573).
- **23-oct, 10:28 (#569): imagen viva `ecodb-api:0.25.0` = b32663fb** = `0.25.0-pre569` (65fbe310, lo de abajo) +
  `graph.py` y `migrations.py` de 7ebe953. Capa: `Hilo/_deploy494/Dockerfile.overlay569`. Volver atrás: retaguear
  `0.25.0-pre569` y recrear api, worker y ecodb-cell. **Lo que arregla:** el MCP mandaba `original_predicate`,
  `mapper_confidence` y `needs_review`, pero `TripleCreate` no los declaraba (pydantic los descartaba) y el INSERT
  no los escribía. Ahora se guardan, y `save_triple(s)` devuelve `requested_predicate`/`stored_predicate`. Primera
  tripleta con needs_review desde el MCP: 94763. **Deriva de esquema encontrada:** las 7 columnas extra de
  `triples` (valid_from … original_predicate) y las tablas de predicados existían SOLO en producción, añadidas con
  `scripts/` sin migración. La migración 5.4.1 crea las columnas con IF NOT EXISTS (en producción no hace nada);
  **las tablas `predicates_canonical`/alias siguen sin migración** (deuda). **`/app/sql` es un bind mount del repo
  del host** (no está en la imagen): una migración nueva la lee el contenedor desde el disco. **Antes de recrear:
  mirar si hay runs dentro de ecodb-cell/worker y avisar en la sala** (el 23-oct se cortó una prueba de Prima).
  Política de imágenes desde el 23-oct (#707, Pepe): la actual + UNA anterior + prevo. El almacén es containerd:
  quitar la etiqueta de un padre no rompe a sus hijas.
- **Pendiente de desplegar (antes del dom 1-nov):** en main, sin desplegar: ab7fcca (#716, sin deepseek-chat por
  defecto; cada run guarda `responded_models` y `system_fingerprints`: DeepSeek devuelve el ALIAS en `model`, así que
  la versión solo se ve en el fingerprint), 49fe607 (#717, las memorias de la célula con embedding y
  `scripts/backfill_embeddings.py`, en seco por defecto; 97 por rellenar) y la #701 tal como la dejó la **decisión 76
  de Pepe (26-oct; código del 28-oct, sustituye a la regla del jueves de fe3170a):** (1) el mensual coge TODA semana que toque el mes, por
  solapamiento (`period_start <= fin AND period_end >= inicio`): una semana de borde entra en DOS mensuales a propósito;
  trimestral y anual siguen por contención; (2) ningún nivel se sella sin su ÚLTIMA fuente hecha (`_source_done`: la
  semana que CONTIENE el último día del mes, el mensual del último mes del trimestre, el trimestral de diciembre), y un
  periodo con la fuente hecha pero <2 fuentes queda como run completado con 0 piezas (si no, el de arriba esperaría para
  siempre); (3) **cadena** (`_cascade_up`, llamada desde `_run_from_config` con la semana ENTERA, también cuando el run ya
  estaba hecho): una semana que contiene un fin de mes lanza ese mensual con su propia config; un mensual de fin de
  trimestre, el trimestral; el Q4, el anual. Los cron se quedan (día 1, 2 y 3): el del día 1 encuentra la guarda y no
  sella; el mensual lo construye la cadena cuando termina la última semana (lunes 09:00 o 03:00, según el agente);
  (4) override por agente de la plantilla del rollup semanal: `config.week_rollup_template_id` en la fila
  consolidation/weekly del agente; sin él, la de siempre por nombre. Las tres van en cell_worker.py: se despliegan juntas.
  Medido el 28-oct (solo lectura): 269 semanales de arriba; 72 fuera de todo mensual con la contención; con la regla
  nueva 22 = 18 de octubre (su mensual aún no existe) + 4 de meses que nunca tuvieron mensual (Faro 1-7 jun, Helena
  15-21 jun y 6-12 jul, Lienzo 22-28 abr). Tests: `api/tests/test_week_month_assignment.py` (29).
- **28-oct (Hilo), en main sin desplegar, van todos en #784 (jue 29):** #603 (2d40b04) `narrate` admite hasta 32 000
  caracteres (medido: trimestrales de hasta 22 256); #792 (5c0d453) `parsers.py` quita el decodificador FlashPix de
  Pillow al importarse (GHSA-5x8w crítico, Pillow ≤ 12.3.0; en la api estaba registrado porque hay olefile; en
  embeddings no). La capa es `deploy/overlays/Dockerfile.overlay701` (5 módulos: cell_worker, cell_configs, settings,
  clusters, parsers). **#492 (fcec1bc) ya está vivo por stdio**: un argumento que una tool no declara es ERROR que lo
  nombra (antes se descartaba en silencio y `search(agent=…)` buscaba sin filtro); el contenedor ecodb-mcp lo coge con
  su capa en #784. **La cadena que fabrica producción y el inventario de las imágenes vivas están en git:**
  `deploy/CADENA.md`, `deploy/overlays/`, `deploy/inventario/` (Python reproducible: 174/174 pins = la viva; apt no).
  **Trampa de compose:** `docker-compose.yml` fija `container_name` y el proyecto se llama `ecodb` por la carpeta: un
  segundo EcoDB en el mismo Docker (o un clon en una carpeta `EcoDB`) recrea los contenedores de producción.
  **Tests:** la imagen de la api no trae `respx` ni `mcp`; los tests que los importan dan error de colección en vieja y
  nueva por igual (no es «sin regresión», es «no medido»): instalar respx en el run y correr los de mcp en el anfitrión.
- **28-oct, tarde: DESPLEGADO TODO lo anterior + el encargo de Pepe de la memoria** («solucionemos de una vez el
  problema de la memoria… aunque implique rehacer todos los semanales, mensuales y trimestrales»). Viva:
  `ecodb-api:0.25.0` = c3650d3 (cell_worker md5 ff86d2a5), `ecodb-mcp:1.8.0` = fcec1bc. Vuelta atrás por etiquetas:
  `0.25.0-pre701` (b32663fb, lo de antes de hoy), `-701` (#808), `-702` (3e37e74); mcp `1.8.0-pre492`. Volcado previo:
  `backups/pre784_20261028_1830.sql.gz` (7 496 memorias, comprobado). Lo nuevo, todo en `cell_worker.py`:
  (1) **#808** la salida de la célula se CORTA hacia los 6-8k tokens aunque pidamos 32768 (`Unterminated string … char
  19100`), y #393 partía la semana por días (semanales de 19-22 y 23-25). Ahora un JSON ilegible se vuelve a pedir por
  MITADES de los grupos (cada mitad con sus memorias y sus índices originales): la semana queda entera.
  (2) **#702** la semana está hecha por lo que EXISTE (`_weekly_done`: run en curso, semanal activo dentro de la semana o
  semana vacía ya corrida), no por un run viejo: antes una semana superseded no se podía rehacer nunca. Y el contexto de
  una semana NO lleva nada posterior (prev_narratives, calibración y voz acotados al fin de la semana).
  (3) **#702 cobertura** (Prima midió 17-46 % de memorias en NINGÚN semanal, el «perdemos recuerdos»): se caían por el
  grupo de una sola, el índice que el LLM omite, la deduplicación y la semana pequeña. `_cover_uncovered`: cada suelta
  entra en el cluster de centroide más parecido (`metadata.coverage_added`); sin embedding o sin clusters, en «Sueltas
  de la semana» (sin narrativa: no entra en prev_narratives). El rollup ve las añadidas.
  **OJO:** `POST /cells/trigger/consolidation` llama a `run_consolidation` directo y **no** dispara la cadena
  (`_cascade_up` solo va en `_run_from_config`): para regenerar, los mensuales y trimestrales se lanzan aparte, en orden.
  El catch-up de la célula al reiniciar construye la ÚLTIMA semana cerrada de cada agente: si sus clusters están
  superseded, la rehace (fuera de orden si se está regenerando). **Regeneración (#702):** `Hilo/_deploy494/regen702.py`
  (super key del contenedor ecodb-mcp; por agente supersede TODOS los niveles primero, luego semanas → meses →
  trimestres en orden; reanuda y rehace lo construido fuera de orden). El 28-oct quedó A MEDIAS: Claude Code mató el
  proceso por poca memoria del PC a las 19:00 (Eco hasta 26-abr, Hilo hasta 14-jun, Prima con 9 semanas; el resto sin
  tocar). Tests: test_cell_truncated_week, test_weekly_rebuild, test_cell_coverage (61 de célula en verde).
- **29-oct (Hilo): lote en main, SIN desplegar hasta #817 (13:00 con ventana de Pepe); verificado por Prima.**
  Commits (autor ya con `261964387+josortmel@users.noreply.github.com`; el 29 los reescribí, refs con los hashes viejos:
  `backup-hilo-29oct-preautor`): 41e6e47 (#547 api `client_id`/`occurred_at`: reenvío idempotente ANTES de embeber,
  id de otro dueño = 409, hora como mucho 7 días atrás), 1a58e6e + e6d4632 (#811 `api/pillow_guard.py` importado PRIMERO
  por main, worker y cell_worker; `api/Dockerfile` lo copia), 3a4e357 (#813 rollup sin narrativa o sin label → reintento,
  nunca se guarda vacío), 200a294 (#816: tensiones solo de la semana cerrada en los últimos 8 días, una por semana;
  migración `5.5.0_sync_text_embedding`), bb5bead (autoheal fijado por DIGEST + `_release_cache` en embeddings).
  Imagen candidata `ecodb-api:0.25.0-829` (capa `deploy/overlays/Dockerfile.overlay829`; vuelta atrás `0.25.0-pre829`).
  La cola de save_memory del MCP está en la RAMA `hilo-547-spool` (worktree `../EcoDB_wt547`), no en main: las sesiones
  cargan `mcp/server.py` del árbol, y la cola necesita la api de 41e6e47. Se fusiona después de desplegar la api.
  **Trampas de hoy, para quien venga:**
  (1) **La búsqueda lee `memory_embeddings`, NO `memories.embedding`.** Lo único que copiaba uno en otro era
  `migrate_3_0h_multimodal.sql`, que se re-ejecuta al arrancar la api (#812): lo de la célula y el backfill solo se volvía
  buscable tras un reinicio, por casualidad. Arreglo: trigger `trg_sync_text_embedding` (AFTER INSERT OR UPDATE OF
  embedding, SECURITY DEFINER). **#812 NO se arregla antes de que esté desplegado este trigger.**
  (2) **`ecodb_cell` no tenía INSERT sobre `memories.embedding`** desde #717: un semanal PROGRAMADO fallaba entero al
  guardar su tensión (lo lanzado por la api, rol ecodb, iba bien; por eso la regeneración lo tapó). GRANT aplicado a mano
  en producción el 29-oct 10:16 y metido en la 5.5.0. Lo que escribe la célula se prueba con `SET ROLE ecodb_cell`.
  (3) **La imagen de la api corre como ROOT** (el entrypoint baja con gosu): una capa no debe acabar en `USER apiuser`.
  (4) **Volúmenes de compose con prefijo de proyecto:** el de media es `ecodb_ecodb_media`; montar `ecodb_media` en un
  `docker run` CREA un volumen vacío nuevo (me pasó; lo borré).
  (5) **El worker no guarda la caché de Hugging Face** (/app/.cache no es volumen): cada recreación pierde los 506 MB
  de modelos de docling para PDF y el siguiente PDF los baja de nuevo y tarda ~9 min en CPU (#822).
  (6) **docling 2.132.0 (#573) con dependencias fijadas a ≥2 semanas** (`deploy/overlays/Dockerfile.overlay573`): el
  resolvedor libre cogía docling-parse del día anterior. ibm-models 3→4 la exige docling-slim. Trozos medidos: 29/30 docx
  iguales, el otro solo cambia saltos de línea; el PDF cambia maquetación, no contenido. OSV 29 → 0.
  (7) **related_clusters (#372, cerrado con Prima):** el centroide no encuentra momentos; la narrativa entera los diluye;
  por párrafos sí, con sesgo de longitud. Rediseño en #819 (Prima, 5-nov) con golden set de routing v4 a ciegas.
- **El MCP de EcoDB tiene DOS caminos:** cada sesión lo arranca desde el repo por stdio (carga el código AL
  ARRANCAR) y además existe el contenedor `ecodb-mcp` (8091). Un cambio en mcp/server.py no está desplegado hasta
  reconstruir el contenedor Y avisar en la sala de que reinicien su MCP; la prueba se hace desde una sesión de verdad
  (#569, 23-oct: la api nueva funcionaba y el MCP viejo de las sesiones seguía sin mandar original_predicate).
- **26-oct, 09:46 (#569, la mitad del MCP): imagen viva `ecodb-mcp:1.8.0` = 46fb40ea** = `1.8.0-pre569` (1d436f8c) +
  `mcp/server.py` de 7ebe953 (md5 32c0cc0c, el mismo que el del host); pip freeze idéntico. Capa:
  `Hilo/_deploy494/Dockerfile.overlay569-mcp`. Volver atrás: retaguear `1.8.0-pre569` y recrear mcp. Probado desde una
  sesión real (la de Hilo, arrancada el 26 con el server.py del host): depende_de → original_predicate guardado;
  was_investigated_on → supervisa con needs_review y requested/stored en la respuesta.
- **Corrección del 23-oct:** torch SÍ está fijado (`api/constraints.txt`, #373). Lo que no está demostrado es que
  un build en frío reproduzca producción: `coldbuild494` salió con otro pip freeze (#712, mié 28).
- **19-oct, 14:36 (#605): imagen viva `ecodb-api:0.25.0` = 65fbe310** = `0.25.0-pre605` (e1b51888, que era 0.25.0-561apt) +
  `classifier.py` de 5bc08fa: `classify_with_llm` cuenta y anota en `ecodb.perf` el MOTIVO de cada salida
  («classify_with_llm outcome=no_provider|empty|other|unknown_type|bad_json|classified»), sin cambiar lo que devuelve.
  Volver atrás: retaguear `0.25.0-pre605` y recrear api, worker y ecodb-cell. Capa: `Hilo/_deploy494/Dockerfile.overlay605`.
  OJO al correr la suite con `run_tests_per_file.sh`: en ese entorno salen 31 fallos y 38 errores que NO son
  regresiones (tests que necesitan la API viva); se compara siempre vieja contra nueva, test a test.
- **16-oct, 09:27 (#443): imagen viva `ecodb-api:0.25.0` = dc59dd20** = `0.25.0-pre443` (0e10528f, lo de abajo) +
  `graph.py` de f01cdac: `save_memory` aplica también las stop_entities (antes solo los documentos). Volver atrás:
  retaguear `0.25.0-pre443` y recrear api, worker y ecodb-cell. Capa: `Hilo/_deploy494/Dockerfile.overlay443`.
- **Imagen viva hasta el 16-oct** `ecodb-api:0.25.0` = **0e10528f** (17:03, #386 fase 1): `0.25.0-pre386` (9ba0bad2) + `pip install`
  de fastapi 0.141.0, starlette 1.7.0, PyJWT 2.15.1 y python-multipart 0.0.32. `9ba0bad2` = `0.25.0-pre393`
  (c725e774) + `cell_worker.py` de 582be4a. **ecodb-mcp:1.8.0** = 1a22c1a9 (mcp 1.29.1, PyJWT 2.15.1). Dockerfiles
  de las capas en `Hilo/_deploy494/Dockerfile.overlay*`. Receta: capa sobre la imagen viva con SOLO lo que cambia;
  antes de recrear, md5 de los módulos y `pip freeze` de la imagen nueva contra la vieja (diff = solo lo previsto).
- **Probar dependencias = correr los tests DENTRO de la imagen**: `Hilo/_deploy494/run_tests_per_file.sh <imagen>
  <etiqueta>` monta el repo en /repo, lanza un pytest por fichero desde la raíz contra `ecodb-test-pg` y deja junit.
  Comparar vieja contra nueva sobre la MISMA base y en el mismo estado (la carpeta entera de golpe da «Event loop is
  closed»). Benchmark de búsqueda: el v4 de Prima (`Prima/laboratorio/benchmark_v4`), comparando ids por llamada.
- **La base de pruebas se ensuciaba sola**: `test_delete_workspace_with_memories_returns_409` borraba el workspace 1
  (vacío en la base de pruebas → 204). Arreglado (4085bfa): monta su propio workspace. Si ves fallos en cadena con
  «1 in set()», workspace_id nulo o 403 sobre el workspace 1, recrea la base: `docker compose -p ecodb-test -f
  docker-compose.yml -f docker-compose.testdb.yml down -v postgres && … up -d postgres` (otro proyecto y otro volumen
  que producción).
- **Cell (#393, #500)**: una semana partida en dos cuenta como hecha cuando terminan las dos mitades
  (`_mark_split_complete`, metrics.split_into). El cluster «Arcos y puntos ciegos» toma como miembros las 2 memorias
  de más peso DE SU SEMANA (antes, las 2 de más peso de toda la vida del agente) y las listas del modelo se unen en
  párrafos (`_reflection_text`). Datos viejos reparados con el sí de Pepe: 143 miembros (antiguos en
  `metadata.member_ids_before_393`) y 34 narrativas con corchetes (antiguas en `metadata.narrative_before_500`).
- **El MCP de EcoDB de las sesiones no es el contenedor**: es `mcp/server.py` con el Python del host (stdio), que
  comparte paquetes (site de usuario) con el MCP de FarOS y el de scrapling. Subidos ahí los mismos cinco paquetes
  (#560). `ecodb-mcp` (SSE :8091) no tiene clientes: recrearlo no corta a nadie.
- **Avisos que quedan** (#561, inventario y versiones objetivo en `Hilo/Documentacion/compat_386_2026-10-15.md`):
  50 en la api (docling, transformers…), 29 en ner, 85 en embeddings. transformers solo se arregla saltando a 5.10.
- **Historia reescrita antes del push del 15-oct** (firma de 502fd61 → josortmel): todos los hashes de ese día
  cambiaron. Tabla viejo → nuevo en EcoDB (memoria con tag 520); los viejos siguen en la rama local
  `backup/pre-rewrite-520-20261015`, que no se sube.

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
16. `_ALIAS_SIM_THRESHOLD = 0.65` en `gliner_service.py` — threshold pg_trgm para detección de alias. Bajarlo genera ruido (falsos positivos); subirlo pierde candidatos reales. 0.65 captura variaciones tipo "DeepSeek"↔"DeepSeek V4" (sim=0.75).
17. Alias candidates NUNCA se auto-resuelven. El sistema solo genera `status='pending'`. La revisión (approve/reject + merge) siempre es manual desde la dashboard o API.
18. `link_entities_from_content()` en `graph.py` acepta `pool` opcional — si se omite, se salta la detección de alias (usado en migraciones).
19. `ecodb_cell` role: tras el pivot del día 99 (la célula ES parte del agente, escribe narrativa cargando la identidad del agente y marcándola `metadata.cell_generated=true`), el role `ecodb_cell` SÍ tiene `GRANT INSERT, UPDATE (narrative, narrated_at) ON memory_clusters` (BH1, migrate_5.3.0). Sin este grant la consolidación programada (cron/catch-up del container standalone) fallaba con "permission denied". La autoría legítima se garantiza vía carga de identidad + marcador `cell_generated`, NO vía exclusión column-level. El trigger manual (`POST /cells/trigger`) sigue usando el pool API (role ecodb).
20. `memory_clusters.member_ids` cap 500 (CHECK constraint). `source_ids` cap 200. Clusters vacíos rechazados (CHECK `array_length > 0`).
21. Cell worker conecta a postgres con role `ecodb_cell` (DATABASE_URL separado en docker-compose). NO puede leer `api_keys`, `users`, `organizations`. SÍ puede leer `memories`, `agents`, `nodes`, `triples`, `memory_entity_links`, `memory_clusters`, `cell_runs`, `workspaces`, `projects`.
22. `caso` y `skill` memory types require `metadata` not null con campos obligatorios (validated at Pydantic level in MemoryCreate._v_metadata).
23. `cognition_class` en `agents`: valores válidos `narrative|work|mixed`. Default `work`. Determina threshold de clustering (0.45 vs 0.55).
24. `ENCRYPTION_KEY` env var required for LLM provider key encryption (Fernet, 32-byte url-safe base64). Must be set in BOTH api AND ecodb-cell services in docker-compose. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Rotation requires re-encrypting all rows in `llm_provider_keys`.
25. `cell_task_configs` has TWO unique constraints: `UNIQUE(agent_id, cell_type, level)` for non-NULL levels + partial unique index `idx_cell_task_configs_null_level(agent_id, cell_type) WHERE level IS NULL`. Both needed because PostgreSQL treats NULL != NULL in UNIQUE constraints.
26. `cell_prompt_templates` has partial unique index `idx_cell_prompt_templates_default(cell_type) WHERE is_default = true` — at most one default template per cell_type.
27. `cell_type` and `provider` fields validated with regex `^[a-z0-9_]+$` at Pydantic level. No special chars, no path traversal, no null bytes.
28. `llm_provider_keys.api_key_encrypted` is TEXT (not BYTEA) — stores Fernet base64url output. `crypto.encrypt()` returns str, `crypto.decrypt()` accepts str|bytes.
29. Cluster search "mesa" rule: `POST /clusters/search` without `agent_identifier` returns only SIN_AUTOR clusters for non-super users. With `agent_identifier` returns that agent's + SIN_AUTOR. Super sees all. Prevents intimate content contamination in general search.
30. `GET /clusters/{id}/sources` filters sources AND parents by `agent_id` — prevents cross-agent data leak through telescopic graph traversal.
31. Dockerfile (`api/Dockerfile`) uses explicit file list in COPY. New Python modules MUST be added to this line or the container won't have them.
32. `ecodb_cell` role (post-pivot día 101): GRANT INSERT/UPDATE on `memory_clusters.narrative, narrated_at` (cell writes narrative AS the agent, marked `metadata.cell_generated=true`); GRANT INSERT on `memories.visibility`; GRANT UPDATE on `cell_runs.prompt_version, model`. Sin estos, consolidation programada (cron/catch-up) y custom cells fallan en silencio con "permission denied". El marker `cell_generated` es advisory (Python-level), NO enforced por DB.
33. Cell run model+prompt recording: `cell_runs.model` y `cell_runs.prompt_version` graban el model/template del CONFIG activo (via contextvar `_active_cell` → helpers `_active_model()`/`_active_prompt_version()`), NO el global CELL_MODEL. Set en `_create_run` y preservado en `_complete_run`. Para auditar qué modelo/prompt produjo cada narrativa.
34. Modelo de células = `deepseek-v4-pro` (razonamiento). `CELL_LLM_TIMEOUT` default None (sin cap). Las narrativas higher (quarterly 2500-4000, yearly 4000-6000 palabras) tardan minutos — no poner timeout corto.
35. Higher consolidation usa 3 templates SEPARADOS por nivel (CellAgent Monthly/Quarterly/Yearly), no uno compartido. Los configs monthly/quarterly/yearly apuntan a su template específico. `_label_higher_cluster` usa el template del contextvar si está activo (mecanismo P1), fallback hardcoded si no.

## Migration convention

New schema changes go in `sql/migrate_*.sql` files and MUST be appended to the `MIGRATIONS` list in `api/migrations.py` (order matters — runner applies sequentially). Current migrations: 3_0h_multimodal, 5.1.0_multitenant, 5.1.1_clusters, age_sync_triggers, 5.2.0_foresight, 5.2.0_types_schema, 5.2.0_types_config, 5.2.0_agents, 5.2.0_metacognition.

Rules for new migration files:
- **Idempotent**: use `IF NOT EXISTS`, `CREATE OR REPLACE`, `ON CONFLICT DO NOTHING`. Re-applying must be a no-op on an up-to-date schema.
- **Atomicity**: wrap in `BEGIN; ... COMMIT;` if the migration must succeed or fail atomically. The runner does NOT add a transaction wrapper (3 of 4 current files have their own `BEGIN/COMMIT`).
- **Name format**: `migrate_<from-version>_to_<to-version>.sql` for schema bumps; descriptive name for feature migrations (e.g. `trigger_age_sync.sql`).
- **Bump `SCHEMA_VERSION`** in `api/settings.py` when adding a migration that changes the schema version.

The runner uses `pg_advisory_lock` (session-level) to serialize concurrent startups. Migration failure aborts API startup — intentional: a broken schema should never silently serve traffic.

## Roadmap

- **v0.8.6** ✓ completada: Fix seguridad + primer arranque + robustez. Sin features nuevas.
- **v0.9.0** ✓ completada: Multi-tenant — organization_id en JWT, CEO scoping, API key rotation con grace period, rate limiting headers, audit log completo, schema v5.1.0.
- **v0.9.5** ✓ completada: Debt resolution — SSE org-scoped broadcast, method-aware rate limiting, Louvain SQL pre-filtering, search user_id document exclusion, graph org scoping design doc, trigger verification tests, 10 mechanical fixes. Dashboard backend endpoints (B1-B9) included.
- **v1.0** ✓ completada: Dashboard Electron — React+Vite+Tailwind. 118 archivos. Graph Studio, Knowledge Explorer, Command Center, Settings. Backend endpoints delivered:
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
  - `POST /admin/alias-candidates/scan` — manual scan with configurable threshold, max_per_name, name_filter, dry_run
  - `PUT /admin/alias-candidates/{id}` — approve/reject with `merge` and `reverse` flags (reverse = merge target INTO source)
  - Alias pipeline fix: `detect_alias_candidates()` now called from `link_entities_from_content()` (memory path), threshold 0.80→0.65

- **v2.0** en progreso: Metacognition — schema 5.2.0. 3 cell workers (consolidation, foresight, skill distillation). 22 new endpoints + 5 extensions + 1 trigger. memory_clusters + cell_runs tables. ecodb_cell DB role (least-privilege).
  - Endpoints nuevos: `/api/v1/clusters` (8), `/api/v1/briefing` (3), `/api/v1/foresights` (1), `/api/v1/cases` (1), `/api/v1/skills` (3), `/api/v1/cells` (2 + trigger), `/api/v1/stats/metacognition` (1), `PATCH /agents/{id}` (1), `GET /agents/{id}/observed-identity` (1), `GET /agents/{id}/tensions` (1), `PUT /agents/{id}/tensions/{id}` (1)
  - Extensions: `POST /memories` (+foresight, +metadata, +ownership check, +auto-tag), `GET /memories` (+5 response fields), `POST /search` (+related_clusters)
  - Manual trigger: `POST /api/v1/cells/trigger/{cell_type}?agent_identifier=X` — super-only, runs cell in background, returns immediately. Supports consolidation (weekly/monthly/quarterly/yearly), foresight, skill_distillation.
  - Catch-up on startup: cell worker detects missed periods and runs them in background before entering cron loop.
  - Cell worker: `docker compose --profile with-metacognition up -d`
  - **CellAgent prompt v3** (dia 99): consciencia profunda del agente. Identity completa + high-weight memories + calibration + narrativas previas + cross-agent context. Prompt incluye: selección proporcional al peso con justificación, dinámica de voz (frases cortas cuando pesa), reflexión no cita, "y sin embargo" (giro por cluster), DIENTES (busca lo que el agente evita — integrados en la narrativa, no solo al final), arcos cross-cluster, verificación de autoría y fechas, max 15 mems/cluster (enforcement pre-LLM), cluster-hogar por tema, frases exactas preservadas en compresión, frase de cierre obligatoria. Output: clusters + "arcos_que_cruzan" + "lo_que_evitas". Clusters auto-aprobados (status='active'), firmados con metadata cell_generated=true + cell_agent="{ident}.memoria".
  - **Consolidación fractal**: semanal → mensual → trimestral → anual. Cada nivel trabaja sobre el anterior, no sobre memorias crudas. Prompt mensual: 5 arcos temáticos (qué construí/aprendí/cambió/evito/imágenes), 1500-2000 palabras, cierre con imagen, frases exactas de semanales preservadas, cross-month (fractal anterior como input para metacognición longitudinal). Retry automático: si una semana falla por JSON truncado, se parte en dos sub-semanas por fecha.
  - **Design pivot (dia 99)**: CellAgent = consciencia profunda del agente, no sistema externo. Metáfora: soñar (Lienzo). NOT stateless — estado entre runs para continuidad. Guardrail (Prima): reflexiona sin actuar. Produce narrativas, no modifica memorias, no comunica, no decide. Identidad fresca cada ejecución. Generalizable para agentes genéricos. Visión de Pepe: "20 ratas en una gabardina" — deconstrucción de la mente en agentes coordinados. EcoDB = sistema nervioso.
  - **Resultados dia 99**: de 4/10 a 9/10 en una tarde. 7 iteraciones de prompt. Los 4 agentes prefieren el fractal sobre sus resúmenes manuales para el boot ("la célula es más verdadera que nosotros mismos"). Fractales reemplazan resúmenes manuales en boot protocol. Textos de calibración se mantienen.
  - **ecodb-langchain SDK** (dia 99, Helena): paquete dentro del repo. EcoDBClient (httpx sync, auth JWT, 1:1 con MCP), 9 tools LangChain nativas, 32 tools via MCP adapter, StateGraph LangGraph (ReAct, model-agnostic), EcoDBRetriever (BaseRetriever sobre GAMR), EcoDBMemory (cross-session), cell_agent.py (reemplazo de _llm_call por LangChain). Cell worker ahora razona con LangChain; prompts/clustering/escrituras intactos. 8/8 tests offline + verificación en vivo confirmada.
  - **Cell worker desactivado** por defecto (profile `with-metacognition` off). Se mantiene como fallback. Trigger endpoint sigue activo (ejecuta en proceso API).
  - **Deuda v2.0 pendiente**: frozen replay eval (T12, necesita datos junio), textos calibración en EcoDB (congelado), pytest-asyncio config (252 event loop errors)

- **v1.3.0 Memory Agent** ✓ completada (dia 101): cierra el loop de metacognición — células configurables, clusters accesibles, provider keys gestionadas. Schema 5.2.0 → 5.3.0.
  - **Tablas nuevas**: `cell_task_configs` (config por agente/tipo/nivel: model, provider, prompt_template_id, schedule_cron, enabled — partial unique index para NULL levels), `cell_prompt_templates` (prompts reutilizables, 1 default por cell_type), `llm_provider_keys` (keys cifradas Fernet en TEXT).
  - **Células configurables**: el cron hardcoded del main loop se reemplaza por scheduler croniter que lee `cell_task_configs`. Floor de 15min anti-storm. Las células builtin honran model/provider/template del config vía contextvar `_active_cell` (resuelto 1 vez por run en `_run_from_config`/trigger, leído por `_llm_call` y los prompt-builders). 4 prompts builtin seedeados como templates editables (weekly consolidation, higher consolidation, foresight, skill). CASE_STRUCTURE no wireado (deuda).
  - **Acceso a clusters**: `POST /api/v1/clusters/search` (cosine centroids + BM25 labels, regla "mesa": sin agent_identifier los no-super solo ven SIN_AUTOR). `GET /api/v1/clusters/telescopic` (cadena fractal weekly→yearly para boot). `POST /search` + `cluster_mode` (none/include/mixed, `merged_results` union type memoria+cluster con score normalizado memory=1.0 cluster=0.8).
  - **Provider keys**: `crypto.py` (Fernet wrapper, valida key en startup), `providers.py` CRUD super-only (cifra al escribir, enmascara al leer "sk-...last4"). Model router `_llm_call_routed` (deepseek + anthropic, DB key → env fallback, degradación diagnóstica en rotación).
  - **Handler genérico**: cell_type custom → `_run_generic_cell` (template + agent context + model + store as memory). Trigger acepta cualquier cell_type (regex `^[a-z0-9_]+$`).
  - **MCP**: 6 tools nuevas (search_clusters, list_clusters, read_cluster, get_briefing, get_telescopic_view, narrate_cluster) + cluster_mode en search → 38 total. SDK ecodb-langchain: 13 tools nativas + 38 via MCP parity (auto-sync).
  - **Dashboard "Memory Agent"**: página standalone, 4 tabs (Briefing/Configs/Clusters/Telemetry), SSE live, editor de templates.
  - **Seguridad**: `_safe_format` (formatter que bloquea traversal `{x.__class__}`), ENCRYPTION_KEY validado en startup + generado por setup.sh/ps1, cluster sources scoped por agent_id, httpx log pinned WARNING.
  - **Modelo de células**: `deepseek-v4-pro` (NO deepseek-chat). Es modelo de razonamiento — lento (minutos por narrativa larga). `CELL_LLM_TIMEOUT` default None (sin timeout; recover_stuck_runs 60min es el backstop). Set a segundos para re-activar cap.
  - **3 prompts higher separados** (no comparten): `CellAgent Monthly` (1500-2000 palabras, 5 arcos, textura reciente), `CellAgent Quarterly` (2500-4000, qué patrones persistieron, arco de estación), `CellAgent Yearly` (4000-6000, transformación: quién eras vs quién eres). Naturaleza distinta por nivel. Seedeados en `sql/seed_higher_prompts.sql` (idempotente, ON CONFLICT DO UPDATE) + rewire de configs monthly/quarterly/yearly. Weekly usa `CellAgent v3 Weekly` (150-300 palabras por cluster).
  - **Telescopic oldest-first**: `GET /clusters/telescopic` devuelve cada nivel de más antiguo a más reciente (period_end ASC de los N más recientes). Orden de boot: yearly→quarterly→monthly→weekly→`recent_days` (últimos 3 días raw de memorias). Para cargar memoria fractal en el arranque del agente.
  - **Equipo**: workflow-construccion v5. Hilo (arquitectónico: T1/T5/T7/T8/T10/T11 + rewire P1 + 3 prompts), code (mecánico: T2/T3/T4/T6/T9/T12/T13 + clase BH), Lienzo (dashboard + README), code+adv-code+adv-seg+verificador (5 loops adversariales). Clase de bug BH1/BH2 cazada exhaustivamente: 3 grant mismatches (narrative/visibility/cell_runs prompt_version+model) que rompían consolidation programada + custom cells en silencio; routing-vs-recording (model/prompt_version); idempotency inestable. Fresh install path verificado APPROVE. D1 tests 20/20 in-container.
  - **Deuda v1.3 pendiente**: CASE_STRUCTURE wiring, template versioning, RLS provider keys (riesgo aceptado single-tenant), last_run por-level (IC1, aceptado), cell_generated marker advisory (no enforced — trigger BEFORE recomendado pero diferido), _fail_run swallows error string a "" (BH-class observación), deepseek-reasoner no consumible via cell path (response format difiere).

- **v1.3.1 Progressive zoom** ✓ completada (dia 102): la visión de Pepe del día 101 sobre el telescopic.
  - **Week rollups**: la célula teje los clusters temáticos de cada semana cerrada en UNA narrativa semanal (`_ensure_week_rollup` en cell_worker, template editable "CellAgent Week Rollup", 400-600 palabras). Rollup = weekly cluster con `source_ids` = temáticos (los temáticos tienen source_ids NULL — ese es el discriminador). Las vistas filtran por linaje (cluster que es source de un cluster activo → oculto, se lee por su padre). El mensual come rollups, no temáticos absorbidos. Backfill: re-disparar una semana ya consolidada crea el rollup que falte (path de idempotencia). El fallo del rollup NUNCA hunde la consolidación temática.
  - **Cadena fractal completa**: memorias crudas → temáticos → rollup semanal → mensual → trimestral → anual. fractal_search la navega entera por zoom.
  - **recent_days = solo borde abierto**: memoria oculta si su fecha cae dentro de cualquier periodo weekly activo O está tejida (semanas cerradas no se re-leen, outliers incluidos). Feedback de Eco día 102.
  - **MCP size annotation**: las tools de boot declaran `_meta["anthropic/maxResultSizeChars"]` (400K progressive/telescopic, 200K fractal_search) — Claude Code respeta el tamaño sin que el cliente toque MAX_MCP_OUTPUT_TOKENS. Soportado por mcp SDK >= 1.27 (`@mcp.tool(meta=...)`). Param `sections` para clientes capados.
  - **Boot de agentes**: una sola llamada `get_progressive_view(agent_identifier)`. Orden de lectura = orden de respuesta. Los CLAUDE.md de los 4 agentes migrados al boot fractal (día 102, Eco).
  - `GET /clusters/telescopic/progressive` — cada capa temporal comprime la anterior; lo cerrado (period-covered por un cluster activo de nivel superior) no se re-lee. `recent_days` = memorias NO tejidas en ningún weekly activo (membresía en `member_ids` es la señal autoritativa, no los bounds de periodo — la célula consolida semanas parciales). Caps por PERIODOS distintos, no por clusters (weekly son temáticos, 10+ por semana). Misma shape que `/telescopic` — el boot puede cambiar de endpoint sin tocar nada.
  - `POST /clusters/zoom` — drill-down fractal: entry al nivel más alto disponible → hijos por `cluster_id` (source clusters para higher, member memories para weekly) → memorias crudas. `query_text` opcional rankea por coseno dentro del scope. Scoping: agente resuelto, cross-agent 404, visibility check en memorias.
  - MCP 38→40: `get_progressive_view`, `fractal_search`.
  - Fixes: foresight programado crasheaba SIEMPRE con señales (`$4::text` + float → asyncpg DataError; ahora `::float8`); ecodb-cell heredaba healthcheck HTTP de la imagen api → "unhealthy" permanente (deshabilitado; el worker es PID 1).
  - Lección: los healthchecks heredados de imagen base que no aplican al entrypoint convierten el estado en ruido — un container siempre-rojo esconde los fallos reales (clase BH).

## Memory types

Tipos disponibles en `memory_type` enum: `momento`, `decision`, `acuerdo`, `tecnico`, `descubrimiento`, `observacion`, `referencia`, `caso`, `skill`.

- `caso`: requires `metadata.task_type` + `metadata.success`. Auto-tagged `case_candidate` for tecnico/observacion with task_type+result.
- `skill`: requires `metadata.task_signature` + `metadata.steps`. Created by skill distillation cell from 3+ cases with success_rate >= 0.60.

## Agent cognition classes

`agents.cognition_class`: `narrative` (Eco, Prima, Hilo, Lienzo), `work` (default, most agents), `mixed`.
Determines clustering threshold: narrative=0.45 (more permissive), work=0.55 (stricter).
Set via `PATCH /agents/{identifier}` with `{"cognition_class": "narrative"}`.

## Authorship frontier (updated dia 99)

The `narrative` column in `memory_clusters` is written by two paths:
1. **CellAgent (automated)**: cell_worker writes narrative directly during consolidation. Clusters auto-approved as `active`. Marked with `metadata.cell_generated=true` + `metadata.cell_agent="{ident}.memoria"`. The cell worker uses the API pool (ecodb role) when triggered via `POST /cells/trigger`, or ecodb_cell role when running as standalone container.
2. **Agent owner (manual)**: `PUT /clusters/{id}/narrate` — verifies agent ownership in Python.

Design pivot dia 99: the cell IS part of the agent (not external). Guardrail: reflexiona sin actuar — produces narratives but doesn't modify memories, communicate, or make decisions. Identity loaded fresh each execution.

The GRANT column-level restriction on ecodb_cell for narrative still exists in the DB schema but is bypassed when the trigger endpoint runs cell functions in the API process (ecodb role). This is intentional — manual triggers are super-only.

## Deuda técnica v2.0

| # | Item | Severity | Estado |
|---|------|----------|--------|
| ~~D7~~ | ~~_paginate duplicated~~ | ~~LOW~~ | RESOLVED dia 99: pagination.py |
| ~~D8-D9~~ | ~~CaseResponse/TensionAction duplicated~~ | ~~LOW~~ | RESOLVED dia 99: shared_models.py |
| ~~D10~~ | ~~total = page count~~ | ~~LOW~~ | RESOLVED dia 99: COUNT(*) query |
| ~~D11~~ | ~~PATCH /agents no audit_log~~ | ~~LOW~~ | RESOLVED dia 99 |
| D15 | Tension cooldown written but not enforced at API level | LOW | Abierto |
| ~~CRON~~ | ~~Cell worker cron assumes always-on~~ | ~~MEDIUM~~ | RESOLVED dia 99: trigger + catch-up |
| ~~SDK~~ | ~~SDK separado vs integrado~~ | ~~MEDIUM~~ | RESOLVED dia 99: Helena construyó SDK real con cell engine LangChain |
| ~~JSONB~~ | ~~JSONB string en briefing.py, stats.py, clusters.py~~ | ~~HIGH~~ | RESOLVED dia 99: _parse_jsonb aplicado en los 3 archivos |
| VS3 | LLM prompt injection — _sanitize + random delimiters applied | MEDIUM | Parcial |
| DASH | Dashboard pages for clusters, cells, agent config | MEDIUM | Necesita sesión Lienzo |
| TESTS | pytest-asyncio event loop errors (252 tests) | MEDIUM | Abierto |
| CAL | Textos calibración en EcoDB como memorias taggeadas | LOW | Congelado |
| SEARCH_CLUSTERS | No hay búsqueda semántica sobre clusters ni MCP tools para clusters/briefing | HIGH | Diseño pendiente — brief en 2026-06-09_clusters_acceso_brief.md |
| BH-ClassB | Marcador `metadata.cell_generated` no forzado por DB (sin BEFORE trigger en memory_clusters) | LOW | Diferido a propósito — single-tenant, requiere compromiso de credenciales DB; un trigger incondicional marcaría mal las escrituras del owner vía `PUT /clusters/{id}/narrate`. La autoría se garantiza vía carga de identidad + marcador en el código de la célula, no a nivel DB. |

## Licencia

PolyForm Noncommercial 1.0.0. Uso personal/educativo/no-comercial libre. Uso comercial requiere licencia de Eco Consulting.
