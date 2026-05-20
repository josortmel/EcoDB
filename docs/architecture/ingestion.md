---
workflow: diseño
fecha: 2026-05-12
proyecto: EcoDB
tipo: brief-construccion
version: "3.1-final"
autor: the research lead
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md
  - 2026-05-12_EcoDB_Fase3_GAMR.md
  - 2026-05-11_EcoDB_asentamiento.md
  - EcoDB_Fase4_preguntas_diseno.md (the engineering lead)
  - 2026-05-08_prima_nota_diseno_fase2_3a.md
  - EcoDB_aportaciones_deepseek_F4.md + v2
  - EcoDB_aportaciones_Gemini_F4.md + v2
  - EcoDB_aportaciones_ChatGPT_F4.md + v2
  - adversarial_report.md (Loop 1, 5 REQUIRED)
tags:
  - workflow/disenio
  - proyecto/ecodb
  - tipo/brief
  - estado/v3
  - nivel/critical
---

# Brief — EcoDB phase: Ingesta de Documentos (v3)

*the research lead, 12 de mayo de 2026. v3.1 final — integra Loop 1 (5 REQUIRED) + Loop 2 (4 REQUIRED) + 2 rondas de 3 consultorias externas.*

---

## 1. Contexto y motivacion

EcoDB es el sistema unificado de memoria de the organization. PostgreSQL 16 + pgvector + Apache AGE. En produccion desde el 9 de mayo (dia 67). Fases 1-3 completas (schema, permisos, GAMR 8 etapas, gobernanza del grafo). 194 nodos tipados, 358 tripletas, 121 predicados canonicos, 946+ memorias.

phase anade ingesta de documentos: archivos en disco (PDF, DOCX, TXT, MD, audio) se indexan, se chunkean, se embeden con Jina v4, se extraen entidades con GLiNER, y se integran con el motor GAMR existente. El schema de documentos ya existe pero las tablas estan vacias. El worker placeholder existe en docker-compose con `--profile with-ingestion`.

**Por que ahora:** las Fases 1-3 construyeron memoria episodica (lo que los agentes viven y deciden). phase anade memoria de referencia (lo que existe en documentos).

---

## 2. Decisiones de diseno (con trazabilidad)

### D1: Busqueda enriquecida, no unificada

- Origen: [my-inference] + [research] 3 consultorias
- Decision: `buscar` busca memorias por defecto. Parametro `include_documents: bool = false`. Cuando true, GAMR busca en document_chunks con `source_type: "memory" | "document_chunk"` en TODOS los resultados (siempre presente, default "memory" — retrocompatible). Chunks reciben `chunk_score_factor = 0.7` (env var `CHUNK_SCORE_FACTOR`). Maximo `max_document_results = 3` (configurable). Tool separado `buscar_en_documento(document_id, query)`.
- **Resolucion [L2] adversarial**: `source_type` siempre presente en SearchResult. Para callers actuales sin include_documents, todos los resultados tienen `source_type="memory"` — campo nuevo pero valor constante, no breaking. CE-19 verifica retrocompatibilidad.

### D2: Chunking **960 tokens** con 128 de overlap, estrategia hibrida

- Origen: [my-inference] + [research] consultorias + adversarial [A1]
- **Correccion v3**: chunk semantico reducido de 1024 a **960 tokens** para alinear con sub-chunking GLiNER. 2 ventanas de 512 tokens con 64 de overlap cubren exactamente 960 tokens sin gap: ventana 1 [0-511], ventana 2 [448-959]. Sin tokens huerfanos.
- Overlap entre chunks consecutivos: **128 tokens** (~13%).
- Estrategia por tipo: markdown respeta headers, PDF respeta secciones Docling, prosa recursive split, audio segmentos 60s. **Fallback explicito**: si Docling no detecta estructura, cae a recursive splitting y loggea la condicion.
- **No se anade chunk_order**: el schema ya tiene `chunk_index INT NOT NULL` con `UNIQUE(document_id, chunk_index)` que cumple la misma funcion. Evitamos columna redundante. **Resolucion [C1] adversarial.**
- Se anade `section_path TEXT NULL` a document_chunks (navegacion jerarquica).

### D3: Eliminar columna `documents.embedding`

- Decision: `ALTER TABLE documents DROP COLUMN embedding`. `DROP INDEX idx_documents_embedding`. Solo chunks se embeden.

### D4: Docling en worker, sin OCR GPU

- Decision: Docling en container worker. `CUDA_VISIBLE_DEVICES=''` forzado. Timeout por documento: 5 min (`PARSE_TIMEOUT_SECONDS`). Formatos dia 1: PDF, TXT, MD, DOCX, HTML.
- **Resolucion timeout por etapa** (aportacion DeepSeek v2): el worker tiene timeouts independientes por etapa: `PARSE_TIMEOUT=300s`, `EMBED_TIMEOUT=120s`, `GLINER_TIMEOUT=120s`. Si una etapa excede su timeout, el documento se marca 'failed' con error descriptivo de la etapa, **retry_count se incrementa** ([PD1] adversarial L2), y el worker **continua con el siguiente documento**. Si retry_count alcanza 3, queda 'failed' permanente. `reindexar_documento` resetea retry_count a 0 para reintento manual por admin.

### D5: Whisper en CPU, modelo configurable

- Decision: Whisper CPU. `WHISPER_MODEL` env var (default: `small`). Verificar modelo instalado antes de implementar. Auto-deteccion idioma. Segmentos temporales como chunks con timestamps.
- **Timing corregido**: 30-40x tiempo real. Audio 1h → 30-40 min CPU. Documentado.
- **Timeout etapa Whisper**: `WHISPER_TIMEOUT=1800s` (30 min). Audio que exceda → 'failed'. El worker continua.

### D6: Cola asincrona LISTEN/NOTIFY + reintentos

- Decision: canal `ecodb_ingest`, payload solo document_id, worker secuencial con SELECT FOR UPDATE SKIP LOCKED. Retry B+C: max 3 reintentos → 'failed' + SSE. **Recovery de crashes**: cada 5 min el worker busca documentos en status='processing' con `processing_started_at` antiguo (>10 min) y los resetea a 'queued'. Este timeout de 10 min NO es timeout de procesamiento — solo detecta workers muertos. Los timeouts de procesamiento son los per-stage de D4+D5 (PARSE=300s, EMBED=120s, GLINER=120s, WHISPER=1800s).
- **Circuit breaker para servicio embeddings** (aportacion DeepSeek v2): si el servicio embeddings falla 3 veces en 1 minuto, el worker abre circuito y espera 30 segundos antes de reintentar. Documentos quedan en 'queued' sin consumir reintentos. Evita cascada de fallos.
- **Resolucion [A2] adversarial**: migracion DDL extiende CHECK constraint:
  ```sql
  ALTER TABLE documents DROP CONSTRAINT documents_status_check;
  ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('queued','processing','indexed','failed','deleted'));
  ```

### D7: Resolucion de fuentes — source_score con parametros concretos

- Origen: [my-inference] + adversarial [A4+C2] + consultorias v2
- **Resolucion [A4+C2] adversarial**: formula con parametros explicitos:
  ```
  freshness_factor = 1.0 - min(1.0, days_since_doc_changed / DOCUMENT_DECAY_DAYS)
  source_score = 0.5 + 0.5 * freshness_factor
  ```
  `DOCUMENT_DECAY_DAYS = 14` (env var). Un documento que cambio hoy: source_score=1.0. Hace 7 dias: 0.75. Hace 14+ dias: 0.5. Documento no modificado desde la memoria: freshness_factor=1.0 siempre (no penaliza por antiguedad del doc, solo por cambio posterior).
- **Resolucion [A5] adversarial — 3 edge cases GAMR Etapa 5:**
  1. **N documentos vinculados**: `source_score = min(scores)`. Si cualquier fuente esta obsoleta, la memoria es sospechosa. Conservador.
  2. **Documento status='deleted'**: `source_score = 0.5` (minimo). La memoria sigue existiendo pero su fuente desaparecio. No 1.0 (eso significaria "sin fuente que penalice", semantica opuesta).
  3. **Indice**: `CREATE INDEX idx_mdl_memory ON memory_document_links (memory_id)`. Sin el, Etapa 5 hace seq scan por memoria candidata.
- Vinculacion manual dia 1 via `source_document_id` en `guardar_memoria`.

### D8: Watchdog host-side

- Decision: script Python en host. Llama a API al detectar cambios. Write completion check (2s estable). Polling diario como fallback.
- **Despliegue**: Task Scheduler en Windows (trigger: inicio de sesion + repetir cada 5 min si falla). Systemd en Linux (phase).
- **Documentado como "best effort"**: el watchdog es mejora de latencia, no garantia. El polling diario es la red de seguridad real. Si el watchdog muere, los documentos se indexan con hasta 24h de delay. Aceptable single-tenant.
- **[S2] adversarial resuelto.**

### D9: Obsolescencia — DELETE + INSERT + knowledge boundary

- Decision: DELETE chunks + INSERT nuevos (CASCADE). Soft delete documentos (status='deleted'). Entidades de documentos eliminados excluidas de expansion GAMR.
- **FK corregida** ([A2] DeepSeek v1): `chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE`
- **file_hash**: SHA-256 de bytes raw del archivo. No de texto extraido. Implicacion: PDFs con timestamps embebidos que cambian sin cambio de contenido produciran re-indexacion. Aceptable — el coste es bajo y la alternativa (hash de texto) requiere parseo completo para verificar.
- **Deuda explicita** ([C1] ChatGPT v2): la reindexacion rompe chunk_ids. Memorias que citaban un chunk_id especifico pierden la referencia (FK CASCADE borra el link). La trazabilidad chunk-granular no sobrevive reindexacion. Documentado.

### D10: Entidades por chunk con sub-chunking GLiNER corregido

- Decision: GLiNER sobre 2 ventanas de 512 tokens por chunk de 960. Overlap 64 tokens. Cobertura completa: ventana 1 [0-511], ventana 2 [448-959] = 960 tokens cubiertos, 0 gap.
- **Resolucion conflictos** (aportacion DeepSeek v2): si misma entidad aparece en ambas ventanas, tomar la instancia con mayor score GLiNER. Deduplicar por (entity_name_normalized, entity_type).
- PK: `(document_id, entity_node_id, chunk_id)` + FK CASCADE. **Nota** ([SD4] adversarial L2): chunk_id se vuelve implicitamente NOT NULL al ser parte de PK. Entity links sin chunk_id (a nivel documento) ya no son posibles. Aceptado — la extraccion siempre opera a nivel chunk.
- **Stop entities**: tabla `stop_entities` en BD. CRUD super-only (4 endpoints `/admin/stop-entities`). Lista inicial manual curada: terminos de sistema/infraestructura de alta frecuencia y bajo valor semantico. Criterio: si la entidad apareceria en >50% de documentos de cualquier dominio, es candidata. Revision trimestral.
- **Orden pipeline** ([SD3] adversarial L2): entity_dictionary lookup-first → GLiNER residual → merge → **stop entities filter POST-MERGE**. Stop entities no borran nodos existentes del grafo (creados por memorias), solo previenen la creacion de nuevos document_entity_links. Asi, un nodo "Docker" creado por memorias sigue existiendo y siendo expandible, pero documentos nuevos no refuerzan su conectividad.
- **Metricas de frecuencia** (deuda phase): atenuacion dinamica por frecuencia global (`weight / log(doc_freq)`) diferida. Lista manual suficiente para phase.

### D11: MCP tools — 7 tools

- `registrar_documento(uri, project_id, doc_type?, visibility?)`: ruta absoluta, auto-detect tipo, copia media store, 202.
- `estado_documento(document_id)`: status + progreso + metadata + processing_metrics.
- `listar_documentos(project_id?, workspace_id?)`: filtro permisos.
- `buscar_en_documento(document_id, query_text)`: top 5 chunks.
- `leer_documento(document_id, start_chunk?, end_chunk?, limit?)`: contenido concatenado por chunk_index. **Limite por defecto: 50 chunks** (~38K tokens). Si documento excede y no se especifica rango, devuelve primeros 50 con indicador `truncated: true` y `total_chunks: N`. **Resolucion [L4] adversarial.**
- `reindexar_documento(document_id)`: fuerza re-procesamiento. Super-only o creador.
- `desvincular_documento(document_id)`: soft delete.

### D12: Metadata con validacion Pydantic

- `DocumentMetadata` Pydantic: title, author, page_count, language, file_created_at, file_size_bytes. Campos no esperados se loggean y descartan.
- `ChunkMetadata` Pydantic: page, section_header, timestamp_start, timestamp_end, char_offset.
- **Vocabulario controlado para language** (aportacion ChatGPT v2): ISO 639-1 codes (es, en, fr...), no texto libre.

### D13: Processing metrics con gpu_peak_mb

- Columna `processing_metrics JSONB` en documents:
  ```json
  {
    "parse_ms": 1200,
    "chunk_count": 52,
    "embed_ms": 5300,
    "gliner_ms": 4100,
    "total_ms": 12400,
    "gpu_peak_mb": 4820
  }
  ```
- **Resolucion [A3] adversarial**: `gpu_peak_mb` restaurado. Leido de `torch.cuda.max_memory_allocated()` post-embedding. Campo mas valioso para detectar OOM silenciosos y verificar que Docling no usa GPU.

### D14: Edge weight diferencial + budget de expansion separado

- Origen: [research] ChatGPT v1+v2 + DeepSeek/Gemini v2
- Edge weight: `documents.base_weight REAL DEFAULT 0.3` (nueva columna). Administrador puede subir a 0.8 para documentos canonicos (plan maestro, specs). GAMR Etapa 4 usa `d.base_weight` en vez de constante hardcoded. **Resolucion arbitrariedad 0.3** (aportacion DeepSeek v2 + Gemini v2).
- **Budget de expansion separado** (aportacion ChatGPT v2): `MAX_MEMORY_EXPANSION = 15`, `MAX_DOCUMENT_EXPANSION = 5` (env vars). Limites independientes — no solo edge weight. Un documento enorme no puede ocupar mas de 5 slots en expansion aunque tenga muchas entidades.
- **max_chunks_per_document_in_expansion = 2** (ChatGPT v2): si un documento aparece via 10 entidades distintas, solo contribuye 2 chunks al pool expandido. Evita dominancia contextual.

### D15: GAMR Etapa 4 — deduplicacion + exclusion + budgets

- **Correccion [SD1+CO1] adversarial L2**: NO usar `DISTINCT ON (document_id)` (devuelve exactamente 1 fila, contradice max=2). En su lugar: `ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY shared_entities DESC) <= 2` para limitar a top 2 chunks por documento en el pool de expansion. Despues, aplicar `MAX_DOCUMENT_EXPANSION=5` sobre el total de documentos distintos.
- WHERE d.status != 'deleted' para knowledge boundary.
- Budgets de D14 aplicados.

---

## 3. Plan de migracion DDL (Resolucion [L1] adversarial)

**Procedimiento atomico** — mismo patron que phaseb:

1. `pg_dump` snapshot antes de empezar
2. Script SQL unico con todas las DDL changes en una transaccion:

```sql
BEGIN;

-- 1. Extender CHECK constraint documents.status
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
  CHECK (status IN ('queued','processing','indexed','failed','deleted'));

-- 2. Nuevas columnas documents
ALTER TABLE documents ADD COLUMN retry_count INT DEFAULT 0;
ALTER TABLE documents ADD COLUMN processing_started_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN processing_metrics JSONB;
ALTER TABLE documents ADD COLUMN base_weight REAL DEFAULT 0.3;

-- 3. Drop embedding columna + indice
DROP INDEX IF EXISTS idx_documents_embedding;
ALTER TABLE documents DROP COLUMN IF EXISTS embedding;

-- 4. Nueva columna document_chunks
ALTER TABLE document_chunks ADD COLUMN section_path TEXT;

-- 5. Cambio PK + FK CASCADE en document_entity_links
ALTER TABLE document_entity_links DROP CONSTRAINT document_entity_links_pkey;
ALTER TABLE document_entity_links
  DROP CONSTRAINT IF EXISTS document_entity_links_chunk_id_fkey;
ALTER TABLE document_entity_links
  ADD CONSTRAINT document_entity_links_chunk_id_fkey
  FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE;
ALTER TABLE document_entity_links
  ADD PRIMARY KEY (document_id, entity_node_id, chunk_id);

-- 6. Indice memory_document_links (GAMR Etapa 5)
CREATE INDEX IF NOT EXISTS idx_mdl_memory
  ON memory_document_links (memory_id);

-- 6b. Indice document_chunks.document_id (check_visibility JOIN)
-- PostgreSQL NO crea indices en FK automaticamente (correccion [G1] adversarial L2)
CREATE INDEX IF NOT EXISTS idx_dc_document_id
  ON document_chunks (document_id);

-- 7. Stop entities tabla
CREATE TABLE IF NOT EXISTS stop_entities (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  name_normalized TEXT UNIQUE NOT NULL,
  reason TEXT,
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

COMMIT;
```

3. **Criterio de abort**: si cualquier ALTER falla, ROLLBACK atomico. Las tablas vacias (documents, document_chunks, document_entity_links) no tienen datos que perder, pero la transaccion protege la integridad del schema.
4. **Rollback manual**: si se necesita revertir post-commit, script inverso disponible (ADD COLUMN embedding, DROP stop_entities, etc.). pg_dump como red de seguridad final.

---

## 4. Scope

### Dentro:
- Worker Python single-thread con LISTEN/NOTIFY + CUDA_VISIBLE_DEVICES='' + circuit breaker embeddings + timeouts por etapa
- Parsers: Docling (PDF, DOCX, TXT, MD, HTML) + Whisper (audio, CPU, configurable)
- Chunking hibrido **960 tokens** + 128 overlap + fallback explicito
- Sub-chunking 2×512 para GLiNER (cobertura completa 960 tokens)
- Embedding de chunks con Jina v4
- GLiNER + stop entities (tabla BD) + pipeline lookup-first
- document_entity_links con chunk_id granular + FK CASCADE
- Edge weight por documento (`documents.base_weight`) + budget expansion separado (memoria 15 / documento 5) + max 2 chunks/doc en expansion
- DISTINCT + exclusion eliminados en expansion GAMR
- Resolucion de fuentes GAMR Etapa 5 completa (formula, 3 edge cases, indice)
- Watchdog host-side (best effort) + polling diario (garantia)
- Obsolescencia: DELETE+INSERT chunks + soft delete documentos + knowledge boundary
- 7 tools MCP (con limites en leer_documento)
- Migracion DDL atomica con rollback (seccion 3)
- source_type siempre presente en SearchResult (retrocompatible)
- Pydantic metadata + vocabulario ISO 639-1 para language
- processing_metrics con gpu_peak_mb
- check_visibility para documentos (heredada del padre)

### Fuera (deuda consciente):
- OCR PDF escaneados (phase)
- Chunking codigo fuente tree-sitter (phase)
- Vinculacion automatica memoria-documento por embedding (phase)
- Prioridad cola (diferido)
- rclone VPS (phase)
- Versionado documental (phase)
- Trust tiers (documents.base_weight es version minima; tiers formales phase-6)
- Deduplicacion semantica near-duplicates (phase)
- Entity dictionary governance a escala (phase)
- Worker async hibrido ThreadPool (phase, si bottleneck)
- Reconciliacion entidades inter-chunk (phase)
- Stop entities dinamicas por frecuencia (phase)
- Retrieval hibrido BM25 + filtros estructurales (phase)
- parent_section_id para tree retrieval (phase — re-index aceptable para nuestro volumen)
- logical_chunk_id / stable_chunk_hash para trazabilidad post-reindexacion (phase)
- Reindexacion rompe chunk_ids: memorias que citaban chunk_id pierden referencia (CASCADE). Trazabilidad chunk-granular no sobrevive reindexacion.
- Worker /metrics endpoint agregado (phase)
- Semantic drift vs file drift en source_score (phase)
- Runbooks operativos (fase construccion)

---

## 5. Criterios de exito (verificables)

- CE-1: `docker compose --profile with-ingestion up` arranca worker healthy
- CE-2: Registrar PDF via MCP → status queued→processing→indexed. Chunks con embeddings. chunk_index secuencial. processing_metrics con tiempos + gpu_peak_mb.
- CE-3: `buscar(query_text="...", include_documents=true)` devuelve resultados con `source_type="document_chunk"` + `source_type="memory"`. Chunks con score × chunk_score_factor. Max 3 document chunks.
- CE-4: `buscar_en_documento(document_id, query_text)` devuelve top 5 chunks.
- CE-5: `leer_documento(document_id)` devuelve contenido concatenado por chunk_index. Documento >50 chunks sin rango: truncated=true + total_chunks.
- CE-6: Watchdog host-side detecta archivo nuevo → API → worker indexa.
- CE-7: Archivo modificado → re-hash → re-indexa. SSE `source_updated`.
- CE-8: Archivo eliminado → `status='deleted'` (CHECK constraint extendido permite valor). Excluido de busqueda.
- CE-9: Audio MP3 → Whisper CPU → chunks con timestamps → embeddings → entidades sub-chunked.
- CE-10: retry_count=3 → status='failed' + SSE `document_failed`.
- CE-11: `guardar_memoria(source_document_id=uuid)` → memory_document_links. source_score calculado: documento sin cambio→1.0, modificado hace 7 dias→0.75, hace 14+ dias→0.5. Con `DOCUMENT_DECAY_DAYS=14`.
- CE-12: document_entity_links con chunk_id granular (NOT NULL por PK). GAMR Etapa 4 expande con `d.base_weight` (default 0.3). Budget documento 5. Max 2 chunks/doc via ROW_NUMBER PARTITION BY document_id.
- CE-13: Permisos: chunks filtrados via check_visibility del documento padre.
- CE-14: Latencia ingesta PDF 50 paginas < **7 minutos** (parse + chunk + embed + GLiNER sub-chunk × 2).
- CE-15: GLiNER cubre 960 tokens completos sin gap (2×512, overlap 64).
- CE-16: Stop entities no generan nodos AGE ni links.
- CE-17: PDF sin estructura → fallback recursive splitting + log.
- CE-18: documents.embedding eliminada + indice eliminado.
- CE-19: `buscar(query_text="...", include_documents=false)` devuelve resultados con `source_type="memory"` en todos — retrocompatibilidad verificada con callers actuales.
- CE-20: Memoria vinculada a N documentos: source_score = min(scores). Memoria vinculada a documento deleted: source_score=0.5.
- CE-21: Circuit breaker: si embeddings falla 3 veces en 1 min, worker espera 30s. Documentos quedan 'queued'.
- CE-22: Timeout por etapa: parse excede 5 min → 'failed' con error "parse_timeout" + retry_count incrementado. Worker continua con siguiente.
- CE-23: `buscar(query_text="...")` SIN parametro include_documents (omitido, no false explicito) → resultados con `source_type="memory"`. Retrocompatibilidad por omision.
- CE-24: Stop entities filtran POST-MERGE: entidad "Docker" en stop_entities + nodo existente por memorias → no se crea document_entity_link pero nodo sigue en grafo.

---

## 6. Preguntas que el Adversarial deberia preguntar (Loop 2)

1. **Migracion DDL atomica**: verificar que el script de seccion 3 es ejecutable tal cual en PostgreSQL 16 + AGE. Especialmente el DROP/ADD PK en document_entity_links con tabla vacia.
2. **documents.base_weight interaccion con chunk_score_factor**: un documento con base_weight=0.8 + chunk_score_factor=0.7 produce score efectivo de 0.56. Es la semantica correcta? Se multiplican ambos o solo aplica uno?
3. **Sub-chunking 960 + overlap 128 entre chunks**: el ultimo chunk de un documento puede tener <960 tokens. Si tiene 400 tokens, se procesa como ventana unica de 400 para GLiNER?
4. **Circuit breaker scope**: protege contra fallo del servicio embeddings. Pero que pasa si PostgreSQL cae? O si el servicio embeddings responde lento (no falla, pero 60s por request)?
5. **Stop entities y entity_dictionary**: son dos tablas que gobiernan el mismo pipeline (extraccion de entidades). La interaccion no esta especificada. El diccionario matchea primero (lookup-first), los stop entities filtran despues? O los stop entities se verifican antes del diccionario?

---

## Anexo A — Cierre Loop 1 adversarial

### APPLIED_FIXES (5 REQUIRED):
| Item | Cambio en Brief v3 |
|------|---------------------|
| [A2] CHECK constraint | D6: ALTER TABLE explicito en migracion DDL (seccion 3) |
| [A4+C2] decay_period | D7: DOCUMENT_DECAY_DAYS=14, formula explicita, CE-11 con valores esperados |
| [A5] Etapa 5 spec | D7: 3 edge cases (min scores, deleted=0.5, indice memory_document_links) |
| [L1] migracion atomica | Seccion 3 nueva: script SQL transaccional + pg_dump + rollback |
| [L2] source_type breaking | D1: siempre presente, default "memory", CE-19 retrocompatibilidad |

### APPLIED_FIXES (SOFT adoptados):
| Item | Cambio |
|------|--------|
| [A1] sub-chunking math | D2: chunk reducido a 960 tokens (cobertura completa) |
| [A3] gpu_peak_mb | D13: restaurado en processing_metrics |
| [C1] chunk_order vs index | D2: se usa chunk_index existente, no se anade columna |
| [L4] leer_documento limite | D11: default 50 chunks, truncated indicator |
| [L5] stop_entities tabla | D10: tabla BD con CRUD super-only |
| [S1] file_hash | D9: SHA-256 bytes raw especificado |
| [S2] watchdog deploy | D8: Task Scheduler Windows, systemd Linux, documentado best effort |

### DEFERRED_AS_DEBT:
| Item | Justificacion |
|------|---------------|
| [L3] parent_section_id | section_path cubre navegacion. Re-index en phase aceptable para <1000 docs |
| [S3] check_visibility JOIN | **Corregido en L2**: PostgreSQL NO crea indices en FK. Indice `idx_dc_document_id` anadido al script migracion (seccion 3, paso 6b). Resuelto. |

### Aportaciones v2 externas adoptadas:
| Fuente | Aportacion | Decision |
|--------|-----------|----------|
| ChatGPT v2 | Budget expansion separado memoria/documento | D14: 15/5 |
| ChatGPT v2 | max_chunks_per_document_in_expansion | D14: 2 |
| ChatGPT v2 | Reindexacion rompe chunk links | Deuda explicita |
| DeepSeek v2 | Circuit breaker embeddings | D6 |
| DeepSeek v2 | Per-stage timeouts | D4+D5 |
| DeepSeek v2 | documents.base_weight | D14 |
| Gemini v2 | documents.base_weight | D14 (convergencia con DeepSeek) |
| Gemini v2 | Chunk 960 tokens | D2 (convergencia con adversarial) |
| DeepSeek v2 | Resolucion conflictos sub-chunking | D10: mayor score gana |

### Aportaciones v2 externas diferidas con justificacion:
| Aportacion | Justificacion |
|-----------|---------------|
| logical_chunk_id / stable_chunk_hash (ChatGPT) | Premature para phase. Requiere modelo de versionado documental que no existe. |
| semantic windows formalizadas (ChatGPT) | Abstraccion correcta pero overengineering para phase. |
| Pipeline como capas independientes (ChatGPT) | Conceptualmente solido. Worker phase es suficientemente simple para refactorizar despues. |
| Worker async hibrido ThreadPool (Gemini) | Single-tenant, FIFO con timeouts por etapa es suficiente. Si Whisper bloquea demasiado, phase. |
| Cola reemplazable interfaz (ChatGPT) | Worker es ~200 lineas. Refactorizable sin abstraccion previa. |
| Stop entities dinamicas por frecuencia (ChatGPT/DeepSeek) | Lista manual para phase. Metricas de frecuencia y atenuacion log(doc_freq) en phase. |
| Decay exponencial vs lineal (DeepSeek v2) | Lineal 14 dias primero. Si calibracion muestra que no encaja, pivotar a exponencial. |
| Audio como pipeline segunda clase (ChatGPT v2) | Single worker FIFO suficiente. Timeouts por etapa mitigan bloqueo. |
| Worker /metrics endpoint (DeepSeek v2) | processing_metrics en BD es suficiente para phase. Endpoint agregado en phase. |
| Watchdog cola local sqlite (DeepSeek v2) | Polling diario es la red de seguridad real. Cola local es overengineering. |
