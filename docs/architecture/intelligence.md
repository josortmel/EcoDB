---
workflow: diseño
fecha: 2026-05-12
proyecto: EcoDB
tipo: brief-construccion
version: "4.1-final"
autor: the research lead
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md (phase original)
  - 2026-05-12_EcoDB_fase4_plan_construccion.md (deuda heredada)
  - fase4_ingesta_brief.md v3.1-final (deuda explicita)
  - EcoDB_aportaciones_deepseek_F5.md
  - EcoDB_aportaciones_Gemini_F5.md
  - EcoDB_aportaciones_ChatGPT_F5.md
tags:
  - workflow/disenio
  - proyecto/ecodb
  - tipo/brief
  - estado/v2
  - nivel/critical
---

# Brief — EcoDB phase: Gobernanza Cognitiva (v2)

*the research lead, 12 de mayo de 2026. v4 integra adversarial Loop 1 + 2 rondas de 3 consultorias externas.*

---

## 1. Contexto y motivacion

EcoDB tras phase tiene: memorias episodicas, documentos indexados con chunks, grafo gobernado, GAMR 8 etapas con expansion documental y source resolution. El sistema indexa y busca. Pero todavia no GOBIERNA su propio conocimiento.

phase introduce gobernanza cognitiva: retrieval hibrido, vinculacion con confianza graduada, peso dinamico con decay, gobernanza de entidades con reversibilidad, trust tiers documentales, deduplicacion por deteccion (no por accion automatica), y observabilidad cognitiva.

**Principio rector de phase (nuevo, emergente de las 3 consultorias):** el sistema DETECTA y SUGIERE. El humano (o el agente supervisor) DECIDE y CONFIRMA. La automatizacion epistemica sin validacion produce deriva cognitiva que se detecta semanas despues, cuando ya contamino retrieval, expansion y decisiones.

**Cambio conceptual clave:** similitud ≠ relacion ≠ identidad ≠ reemplazo. phase no puede tratar estos conceptos como equivalentes.

---

## 2. Decisiones de diseno (con trazabilidad)

### D1: Retrieval hibrido — vector + BM25 + grafo con feature flag

- Origen: [my-inference] + [research] 3 consultorias (convergencia)
- Decision: BM25 como 5a senal GAMR. PostgreSQL ya tiene indice GIN fulltext en memorias. Anadir equivalente en document_chunks. Score compuesto pasa de 4 a 5 senales con pesos redistribuidos.
- **Feature flag** ([research] DeepSeek): `ENABLE_BM25=true` (env var). Desactivable sin reinicio. Cuando false, GAMR usa 4 senales originales. Permite rollback instantaneo si BM25 degrada retrieval.
- **Calibracion**: antes de activar en produccion, ejecutar smoke test con 20 queries tipicas. Verificar que top-3 mejoran subjetivamente. CE-17 formaliza esto.
- Filtros estructurales en buscar: `fecha_desde`, `fecha_hasta`, `doc_type`, `agent_identifier`, `tags`.
- Trade-off: redistribuir pesos sin dataset de test es riesgoso. Mitigado por feature flag + smoke test. Calibracion empirica post-despliegue.
- **Deuda phase**: RRF (Reciprocal Rank Fusion) como alternativa a suma ponderada. Cross-encoder reranking. Evaluar con the design lead para dashboard.

### D2: Vinculacion automatica con confianza graduada

- Origen: [user-brief] plan maestro + [research] 3 consultorias (convergencia: similitud ≠ relacion epistemica)
- **Cambio respecto v1**: auto-links NO entran con mismo peso que links manuales. Tienen peso reducido hasta validacion.
- **Feature flag** ([L3] adversarial): `ENABLE_AUTO_LINK=true` (env var). Desactivable sin reinicio. Cuando false, no se crean auto-links. Kill switch si el threshold genera falsos positivos masivos.
- Decision: al guardar memoria, si ENABLE_AUTO_LINK=true, buscar chunks similares. Si `cosine > AUTO_LINK_THRESHOLD` (default **0.78**, configurable, bajado de 0.85 por recomendacion DeepSeek):
  - Crear `memory_document_links` con `link_type='auto'`, `confidence=cosine_score`, `validated=false`.
  - Max 3 auto-links por memoria.
  - En GAMR Etapa 5, auto-links con `validated=false` reciben **0.5x** del source_score normal. Links manuales y validados reciben 1.0x.
  - **Auto-links no validados NO incrementan last_accessed_at** ([research] ChatGPT v2 — evitar feedback loops donde auto-links auto-refuerzan memorias no verificadas).
  - Validacion: el agente o admin puede confirmar con tool `validar_link(memory_id, document_id)` → `validated=true`.
- Columnas nuevas en memory_document_links: `confidence REAL`, `validated BOOLEAN DEFAULT false`.
- Razon: la consultorias coinciden — embedding similarity no es relacion epistemica. Auto-links pueden ser falsos. El peso reducido + validacion evita auto-refuerzo de links incorrectos.
- Trade-off: hasta que se validen, auto-links tienen menor impacto en source_score. Aceptable — mejor impacto reducido que contaminacion.

### D3: Weight dinamico con decay + access como senal auxiliar

- Origen: [user-brief] plan maestro + [research] ChatGPT (access_count peligroso) + DeepSeek (decay floor)
- Decision:
  ```
  effective_weight = weight_base * freshness_modifier
  freshness_modifier = max(0.0, 1 - decay_rate * days_since_creation)  -- floor 0.0, no 0.3
  ```
  `access_count` NO multiplica weight directamente. Es senal auxiliar para observabilidad.
  - **last_accessed_at** ([research] DeepSeek v2 + ChatGPT v2): nueva columna `memories.last_accessed_at TIMESTAMPTZ`. Se actualiza cada vez que una memoria es devuelta como resultado en `buscar` (no en operaciones admin/escritura). Reemplaza `access_count` como base para TODAS las condiciones temporales de staleness. `access_count` se mantiene como contador historico pero NO se usa para stale marking.
- **Condicion stale corregida [A1] adversarial L2**: la condicion de stale es `freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days` (o last_accessed_at IS NULL y created_at < now() - 60 days). NO usa access_count. **Cambio respecto v1**: eliminado access_boost multiplicativo. Razon ([research] ChatGPT): access_count mezcla relevancia real con sesgo de retrieval. Un documento accedido mucho puede simplemente ser central o facil de recuperar, no mejor.
- **Decay floor → 0.0** ([research] DeepSeek): el peso puede tender a cero. Pero **stale marking se activa antes**: si `freshness_modifier < 0.3` Y `last_accessed_at < now() - 60 days` → marcar como `stale` (no archivar automaticamente — ver D10).
- Decay por tipo (ya configurado en memory_type_config): acuerdos/decisiones decay_rate=0.0 (nunca decaen). Tecnicos decay_rate=0.10. Momentos 0.02. Observaciones 0.05.
- Trade-off: eliminar access_boost pierde la senal "memorias muy consultadas son probablemente utiles". Aceptable — la senal era ambigua y ChatGPT argumento convincentemente que produce auto-refuerzo.
- **Deuda**: decay exponencial (`e^(-λt)`) como alternativa si lineal resulta demasiado agresivo. Evaluar con datos reales.

### D4: Entity governance — candidatos, soft merge, reversibilidad

- Origen: [my-inference] + [research] 3 consultorias (convergencia total: reversibilidad obligatoria)
- **Cambio critico respecto v1**: NADA se fusiona o crea directamente. Todo pasa por candidatos.
- Decision:
  - **Aclaracion DDL [A3] adversarial**: la tabla `nodes` EXISTE como tabla PostgreSQL estandar desde phase (init.sql §1.6, `id SERIAL PRIMARY KEY, name TEXT UNIQUE`). EcoDB usa dual-write: SQL `nodes` + AGE `:Entity`. Las FK a `nodes(id)` son validas. El adversarial detecto un falso positivo por falta de contexto — pero este brief debe ser autocontenido, asi que se explicita aqui.
  - **Alias candidatos**: nueva tabla `entity_alias_candidates`:
    ```sql
    CREATE TABLE entity_alias_candidates (
      id SERIAL PRIMARY KEY,
      source_name TEXT NOT NULL,
      target_node_id BIGINT NOT NULL REFERENCES nodes(id),
      confidence REAL NOT NULL,
      occurrences INT DEFAULT 1,
      sample_contexts TEXT[],
      status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','archived')),
      first_seen TIMESTAMPTZ DEFAULT now(),
      last_seen TIMESTAMPTZ DEFAULT now(),
      reviewed_by INT REFERENCES users(id)
    );
    ```
    Cuando GLiNER detecta entidad con embedding >0.90 similar a nodo existente, se crea candidato. El admin revisa y aprueba/rechaza via tool `revisar_alias_candidato(id, decision)`. Aprobado → crea alias en predicate_aliases. Rechazado → marcado, no se vuelve a proponer.
    **Purga [L4] adversarial**: candidatos con status='pending' y last_seen > 90 dias → auto-archive. Candidatos con status='rejected' se mantienen indefinidamente (para no reproponerlos). Limite: max 500 candidatos pending simultaneos — si se excede, los de menor occurrences se purgan primero.
  - **Soft merge**: merge NO borra nodo. En su lugar:
    ```sql
    -- nodo absorbido
    UPDATE nodes SET status='merged', merged_into=target_id WHERE id=source_id;
    ```
    **Resolucion AGE** ([research] Gemini v2 blocker): AGE no sabe de la columna `status` en SQL. La resolucion se hace en la **capa de aplicacion ANTES de Cypher**: cuando GAMR Etapa 4 obtiene entity_node_ids de memory_entity_links/document_entity_links, primero resuelve merged_into via SQL, luego pasa los IDs finales a Cypher. El nodo AGE del merge source sigue existiendo pero nunca se consulta directamente.
    **Chain compression** ([research] ChatGPT v2): `merged_into` SIEMPRE apunta al root final (patron union-find). Tras cada merge, recomputar redirects para evitar cadenas A→B→C. Indice: `CREATE INDEX idx_nodes_merged ON nodes(merged_into) WHERE status='merged'`.
    Endpoint `deshacer_merge(source_node_id)` restaura el nodo a status activo.
    Tabla `entity_merge_log` para auditoria con fecha, actor, razon. **Columna target_original_id** ([A3] adversarial L2): guarda el target PRE-compresion, no el root comprimido. Si A→B y luego B→C (compresion hace A→C), el merge_log de A registra target_original_id=B. Asi, deshacer_merge(A) restaura A→B, no A→C.
  - **Stop entities dinamicas**: calcular `entity_document_frequency` periodicamente (background). Entidades con freq > 50% del corpus → peso atenuado en expansion (`weight / (1 + log10(doc_freq))`). Lista manual de phase sigue como override. Calculo background, no en tiempo real.
  - **Reconciliacion intra-documento**: asincrona, no bloquea indexacion ([research] DeepSeek v2). El documento se marca `indexed` al completar embedding+GLiNER. La reconciliacion corre en background (APScheduler) y actualiza una flag `reconciled BOOLEAN DEFAULT false` en documents. Configurable: param `reconcile_entities: bool = true` en registrar_documento. Con `false`, se salta reconciliacion. Timeout reconciliacion: 10s por documento — si excede, skip + log warning.
- Razon: las 3 consultorias coincidieron — merge irreversible, aliases directos y auto-archivado agresivo son los riesgos principales de phase. Candidatos + soft merge + reversibilidad eliminan el riesgo sin perder la capacidad.

### D5: Trust tiers documentales con decay lento en tier 3

- Origen: [research] ChatGPT v1 + [research] 3 consultorias v5 (convergencia: tier 3 no debe tener decay zero)
- Decision: misma tabla que phase (`documents.trust_tier SMALLINT DEFAULT 1`). Efecto:

  | Tier | base_weight multiplicador | Decay source_score |
  |------|--------------------------|-------------------|
  | 0 | ×0.5 | DECAY_DAYS=7 (rapido) |
  | 1 | ×1.0 | DECAY_DAYS=14 (normal) |
  | 2 | ×1.5 | DECAY_DAYS=28 (lento) |
  | 3 | ×2.0 | DECAY_DAYS=90 (muy lento, NO infinito) |

- **Cambio respecto v1**: tier 3 ya no tiene "freshness=1.0 siempre". Tiene decay muy lento (90 dias) pero NO infinito. Un plan maestro que cambio hace 90+ dias SI penaliza memorias basadas en la version anterior.
- **Cambio de version** ([research] Gemini): si un documento tier 3 tiene `supersedes_document_id` (es version nueva), solo la version mas reciente hereda tier 3. La anterior baja a tier 1.
- Columna nueva: `trust_origin TEXT DEFAULT 'manual'` (preparacion para phase: manual/inherited/inferred/system, solo manual en phase).
- Tool MCP: `clasificar_documento(document_id, trust_tier)`.

### D6: Deduplicacion por deteccion, no por accion automatica

- Origen: [my-inference] + [research] 3 consultorias (convergencia 3/3: detectar + notificar, no archivar)
- **Cambio critico respecto v1**: NO auto-superseder documentos. Separar similitud de reemplazo.
- Decision:
  - `content_fingerprint TEXT` en documents (hash del texto normalizado extraido).
  - **Fingerprint identico** (exactamente el mismo texto): no re-indexar, log "duplicate skipped". Unico caso automatico.
  - **Near-duplicate** (embedding promedio coseno > 0.92): crear entrada en nueva tabla `related_documents`:
    ```sql
    CREATE TABLE related_documents (
      source_id UUID REFERENCES documents(id),
      target_id UUID REFERENCES documents(id),
      relation_type TEXT CHECK (relation_type IN ('duplicate','near_duplicate','revision_of','supersedes','derived_from')),
      similarity REAL,
      detected_at TIMESTAMPTZ DEFAULT now(),
      confirmed_by INT REFERENCES users(id),
      PRIMARY KEY (source_id, target_id)
    );
    ```
  - SSE event `duplicate_detected` con los dos document_ids + similarity score.
  - El admin o agente decide: confirmar como supersedes (tool `confirmar_relacion_documento`) o ignorar.
  - `status='superseded'` solo por accion humana confirmada, nunca automatico.
  - **content_fingerprint formato** ([research] DeepSeek v2): normalizacion antes de hash: lowercase, strip whitespace multiple + saltos de linea, eliminar puntuacion. SHA-256 del texto normalizado.
  - **Limite related_documents** ([research] ChatGPT v2): max 20 relaciones por documento. Solo top-k por similaridad.
  - **Purga** ([research] DeepSeek v2): related_documents sin confirmed_by y detected_at > 90 dias → purga automatica. Confirmadas se mantienen indefinidamente.
- Razon: documentos similares no son necesariamente reemplazos. Dos guias de PostgreSQL pueden tener coseno 0.93 y ser documentos validos distintos. Auto-superseder elimina conocimiento legitimo.

### D7: Versionado documental minimo (Opcion A)

- Decision: sin cambio respecto v1. `document_version INT DEFAULT 1` + `supersedes_document_id UUID NULL`. Contador incrementado al re-indexar. Chunks anteriores no se preservan (pg_dump diario como snapshot).
- **Deuda explicita**: DELETE+INSERT chunks destruye trazabilidad chunk-granular. Opcion B (preservar chunks historicos) diferida.

### D8: Observabilidad — operacional + cognitiva

- Origen: [my-inference] + [research] 3 consultorias (convergencia: falta observabilidad cognitiva)
- Decision:
  - **Worker /metrics**: throughput, tiempos por etapa, cola, GPU peak (sin cambio de v1).
  - **Dashboard-ready aggregations**: GET /stats/documents, /stats/ingestion, /stats/search extendido.
  - **SSE alerts**: cola > 50, tasa fallo > 20%, GPU > 90% VRAM.
  - **Explainability por resultado** (NUEVO v4 — [research] ChatGPT v2 + Gemini v2): cada SearchResult incluye `score_breakdown` con los 5 scores individuales + multiplicadores aplicados (staleness, trust_tier, chunk_score_factor). Permite a the platform owner depurar "por que este resultado esta arriba".
  - **trust_warnings por resultado** (NUEVO v4 — [research] Gemini v2): si un resultado se basa en auto-link no validado o memoria stale, el campo `trust_warnings: string[]` lo senala. El agente puede advertir al usuario que la informacion es "de segunda clase".
  - **Observabilidad cognitiva** ([research] ChatGPT v1):
    - GET /stats/knowledge: entity_count, alias_candidate_count, merge_count, orphan_entity_count, stale_memory_count, duplicate_candidate_count, graph_density, top_entities_by_degree.
    - Estas metricas son la base del dashboard de phase. Sin ellas, the design lead diseña a ciegas.
  - **Deuda**: feedback explicito de agentes (tool marcar_util) diferido a phase.

### D9: Tags derivados del grafo con limite

- Decision: sin cambio conceptual de v1. Auto-tag por entidades tipadas.
- **Limite**: maximo **10 auto_tags** por memoria ([research] DeepSeek 15, Gemini 5, compromiso 10). Seleccionados por entity_confidence descendente.
- **Normalizacion**: lowercase, espacios eliminados (`auto_tag:proyecto:ecodb`).
- Trade-off: 10 puede ser mucho para memorias cortas. Aceptable — el GIN index maneja arrays largos sin degradacion.

### D10: Senales emergentes — tension semantica, stale marking

- Origen: [user-brief] plan maestro + [research] 3 consultorias (convergencia: reducir automatizacion)
- **Cambios criticos respecto v1**:
  1. **Renombrado**: "contradicciones cross-documento" → "tension semantica" ([research] ChatGPT). Embedding similarity no detecta contradiccion logica, detecta cercania semantica con diferencia temporal. El lenguaje importa.
  2. **Graph-guided, no brute force** ([research] Gemini): solo comparar memoria nueva con chunks que compartan al menos 2 entidades en el grafo. Reduce espacio de busqueda de O(N*M) a O(~100).
  3. **Auto-archivo → stale marking** ([research] ChatGPT + DeepSeek): NO mover automaticamente a archived_memories. En su lugar, marcar memorias como `stale`:
     - Condicion: freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days (o NULL y created_at < now() - 60 days).
     - Estado: nuevo campo `memories.staleness TEXT DEFAULT 'active'` CHECK IN ('active','stale','dormant','archived').
     - `stale`: peso reducido 50% adicional en GAMR. Visible en busqueda pero con indicador.
     - `dormant`: peso reducido 90%. Solo aparece con `include_dormant=true`.
     - `archived`: solo por accion admin explicita. Excluido de busqueda. Consultable via admin.
     - **Desarchivo**: tool `desarchivar_memoria(memory_id)` → vuelve a 'active'.
  - **Transiciones definidas [A2/L1] adversarial**:
     - active → stale: `freshness_modifier < 0.3 AND last_accessed_at < now() - 60 days` (o last_accessed_at IS NULL y created_at < now() - 60 days)
     - stale → dormant: `last_accessed_at < now() - 90 days` (30 dias adicionales sin acceso desde stale)
     - dormant → archived: solo por accion admin via `archivar_memoria(memory_id)`
     - cualquier estado → active: acceso o update resetea a active
  - Memorias tipo 'decision' o 'acuerdo' NUNCA se marcan stale automaticamente (independientemente de decay o access). Solo por accion admin.
  - **Concurrencia reconciliacion + auto-link [Q6]**: secuencial, no paralelo. Auto-link se ejecuta DESPUES de que reconciliacion intra-documento termine. Asi las entidades ya estan reconciliadas cuando se buscan memorias similares.
  - **Background intelligence [Q10]**: **dentro del worker Docker** ([research] Gemini v2 — cron host es anti-patron de portabilidad). Usar `APScheduler` integrado en el worker process. Cada hora ejecuta en orden: stop entities freq update → stale marking → tension detection → purga alias_candidates pending >90d → purga related_documents no confirmados >90d ([A4] adversarial L2). Serializado con ingesta via lock interno (no compiten por recursos). Cuando se migre a VPS (phase), no hay configuracion externa que replicar — todo vive en Docker. Eventual consistency documentada: las metricas background pueden tener hasta 1 hora de delay respecto al estado real.
- Razon: las 3 consultorias coincidieron — auto-archivar conocimiento es peligroso. Una decision critica de hace 6 meses sin accesos puede ser vital. El marking gradual (active→stale→dormant) da visibilidad sin destruir conocimiento.

---

## 3. Scope

### Dentro:
- BM25 como 5a senal GAMR con feature flag + filtros estructurales
- Vinculacion automatica con confidence + validated + peso reducido
- Weight dinamico con decay (floor 0.0) + access como senal auxiliar
- Entity governance: alias candidatos, soft merge reversible, merge_log, stop dinamicas background
- Trust tiers (0-3) con decay por tier (tier 3 = 90 dias, no infinito) + trust_origin
- Deduplicacion: content_fingerprint + related_documents table + detectar/notificar
- Versionado documental minimo (opcion A)
- Observabilidad operacional + cognitiva (GET /stats/knowledge)
- Tags derivados con limite 10
- Tension semantica graph-guided + stale marking gradual (active/stale/dormant/archived)
- Tools MCP nuevas: validar_link, clasificar_documento, revisar_alias_candidato, merge_entities, deshacer_merge, desarchivar_memoria, confirmar_relacion_documento
- Reconciliacion intra-documento configurable
- score_breakdown por SearchResult (explainability) + trust_warnings
- Background intelligence: stop entities freq, tension detection, stale marking, purga candidatos/related

### Fuera (deuda consciente):
- OCR PDF escaneados (phase)
- Chunking codigo fuente (sin caso de uso)
- Worker async hibrido (phase VPS)
- RRF como alternativa a suma ponderada (phase con the design lead)
- Cross-encoder reranking (phase)
- Decay exponencial (evaluar si lineal no encaja)
- Feedback explicito agentes / marcar_util (phase dashboard)
- Trust tiers dinamicos / inherited (phase)
- Resumenes generativos (requiere decision the platform owner sobre coste LLM)
- Consolidacion por subgrafos (phase)
- Versionado documental completo Opcion B (diferido)
- logical_chunk_id / stable_chunk_hash (diferido)
- parent_section_id (re-index aceptable)
- Retrieval multi-hop (research previo necesario)

---

## 4. Criterios de exito (verificables)

- CE-1: `buscar(query_text="plan maestro")` con ENABLE_BM25=true devuelve plan maestro como top result.
- CE-2: ENABLE_BM25=false → GAMR usa 4 senales originales. Resultados equivalentes a pre-phase.
- CE-3: **protocolo calibracion BM25** ([A1/L2] adversarial): 20 queries tipicas predefinidas. the platform owner + 1 agente evaluan cada query con veredicto binario "mejor/igual/peor" comparando top-3 con ENABLE_BM25=true vs false. Pass: ≥80% "mejor" o "igual" Y 0 queries "peor" en tipo factual/historical. Si falla: ENABLE_BM25=false + recalibrar pesos.
- CE-4: guardar memoria similar a documento → memory_document_links auto con link_type='auto', confidence, validated=false.
- CE-5: auto-link con validated=false → source_score × 0.5 en GAMR. Tras validar_link → × 1.0.
- CE-6: memoria tecnica creada hace 60 dias, last_accessed_at NULL o > 60 dias → freshness_modifier = 0.0, marcada stale. Memoria tecnica creada hace 60 dias PERO last_accessed_at hace 30 dias → NO stale.
- CE-7: memoria acuerdo 60 dias → freshness_modifier = 1.0 (decay_rate=0.0). Nunca stale automatica.
- CE-8: GLiNER detecta entidad similar a nodo existente → entity_alias_candidates creado (no alias directo).
- CE-9: admin aprueba candidato → alias creado en predicate_aliases. Rechaza → marcado, no se reproponea.
- CE-10: merge_entities → nodo source status='merged', merged_into=target. GAMR resuelve transparentemente.
- CE-11: deshacer_merge → nodo source restaurado a activo. References restauradas.
- CE-12: entidad con doc_freq > 50% corpus → peso atenuado automaticamente en expansion.
- CE-13: documento tier 3 → base_weight ×2.0, decay_days=90. Tier 3 que cambio hace 90+ dias SI penaliza.
- CE-14: documento con supersedes_document_id → solo version mas reciente hereda tier alto.
- CE-15: indexar PDF identico (fingerprint match) → no re-indexa, log "duplicate skipped".
- CE-16: near-duplicate detectado → related_documents entry + SSE duplicate_detected. NO auto-supersede.
- CE-17: GET /stats/knowledge devuelve entity_count, alias_candidates, merges, orphans, stale, duplicates, graph_density.
- CE-18: memoria con staleness='stale' → peso 50% reducido en GAMR. Con 'dormant' → 90% reducido, solo con include_dormant=true.
- CE-19: memoria tipo 'decision' → NUNCA marcada stale automaticamente.
- CE-20: desarchivar_memoria → vuelve a 'active', aparece en busqueda normal.
- CE-21: cada SearchResult incluye `score_breakdown` con las 5 senales + multiplicadores. the platform owner puede ver por que un resultado rankea arriba.
- CE-22: resultado basado en auto-link no validado → `trust_warnings: ["auto-link no validado"]` en SearchResult.
- CE-23: merge_entities con chain A→B→C → merged_into comprimido: A→C, B→C (union-find). GAMR resuelve merged_into en SQL antes de Cypher.
- CE-24: reconciliacion de documento largo → documento marcado `indexed` inmediatamente, `reconciled=false`. Reconciliacion corre en background. Si excede 10s → skip + log.
- CE-25: last_accessed_at se actualiza cuando memoria aparece en resultados de buscar. NO se actualiza por auto-links no validados.

---

## 5. Deuda explicita

- **RRF vs suma ponderada**: los pesos son heuristicos. RRF seria mas robusto pero mas complejo. Evaluar en phase.
- **Decay exponencial**: lineal puede ser demasiado agresivo para conocimiento historico. Monitorear con observabilidad cognitiva.
- **access_count infrautilizado**: relegado a senal auxiliar. Podria alimentar trust_tiers dinamicos en phase.
- **Aliases auto-learned false positives**: candidatos mitigan pero no eliminan. Revision periodica manual necesaria.
- **related_documents sin enforcement**: la tabla detecta pero no impide indexar duplicados. Es intencional — el sistema sugiere, no decide.
- **Reconciliacion costosa**: ~5s por documento grande. Configurable pero no desactivable globalmente.
- **Stale marking calibracion**: 60 dias + 0.3 threshold son estimados. Ajustar con datos reales.
- **Trust tier solo manual**: no escala a 500+ documentos. Inherited/inferred en phase.
- **BM25 solo español**: indice fulltext usa to_tsvector('spanish'). Documentos en ingles tendran BM25 degradado. Multiidioma en phase.

---

## 6. Formula GAMR consolidada (resolucion [L5] adversarial)

Todas las senales y multiplicadores en un solo lugar:

```
# Etapa 8 — Score compuesto (5 senales con feature flags)
if ENABLE_BM25:
    gamr_score = (
        semantic_score * W_semantic[query_type] +
        graph_score    * W_graph[query_type] +
        weight_signal  * W_weight[query_type] +
        freshness_score * W_freshness[query_type] +
        bm25_score     * W_bm25[query_type]
    )
else:
    gamr_score = (formula original 4 senales con pesos phase)

# Weight signal con decay y staleness
freshness_modifier = max(0.0, 1 - decay_rate * days_since_creation)
staleness_penalty = 1.0 if active, 0.5 if stale, 0.1 if dormant
weight_signal = weight_base * freshness_modifier * staleness_penalty

# Source resolution (Etapa 5, phase)
source_score = 0.5 + 0.5 * freshness_factor  # DOCUMENT_DECAY_DAYS=14-90 segun tier
effective_weight = weight_signal * source_score

# Auto-link modifier (phase)
if link.validated == false:
    source_score *= 0.5  # auto-links no validados pesan la mitad

# Document expansion (Etapa 4, phase)
doc_edge_weight = documents.base_weight  # default 0.3, configurable por doc
# Budget: MAX_MEMORY_EXPANSION=15, MAX_DOCUMENT_EXPANSION=5
# Max 2 chunks por documento via ROW_NUMBER

# Chunk score final (include_documents)
if source_type == 'document_chunk':
    final_score = gamr_score * CHUNK_SCORE_FACTOR  # default 0.7
```

---

## 7. Plan de migracion DDL atomica (resolucion [A5] adversarial)

```sql
BEGIN;

-- 1. Staleness + last_accessed_at en memories
ALTER TABLE memories ADD COLUMN staleness TEXT DEFAULT 'active'
  CHECK (staleness IN ('active','stale','dormant','archived'));
ALTER TABLE memories ADD COLUMN last_accessed_at TIMESTAMPTZ;

-- 2. Auto-link columns en memory_document_links
ALTER TABLE memory_document_links ADD COLUMN confidence REAL;
ALTER TABLE memory_document_links ADD COLUMN validated BOOLEAN DEFAULT false;

-- 3. Trust + dedup + reconciled en documents
ALTER TABLE documents ADD COLUMN trust_origin TEXT DEFAULT 'manual';
ALTER TABLE documents ADD COLUMN content_fingerprint TEXT;
ALTER TABLE documents ADD COLUMN document_version INT DEFAULT 1;
ALTER TABLE documents ADD COLUMN supersedes_document_id UUID REFERENCES documents(id);
ALTER TABLE documents ADD COLUMN reconciled BOOLEAN DEFAULT false;

-- 4. Indice BM25 en document_chunks
CREATE INDEX IF NOT EXISTS idx_dc_fulltext
  ON document_chunks USING gin (to_tsvector('spanish', content));

-- 5. Entity alias candidates
CREATE TABLE IF NOT EXISTS entity_alias_candidates (
  id SERIAL PRIMARY KEY,
  source_name TEXT NOT NULL,
  target_node_id BIGINT NOT NULL REFERENCES nodes(id),  -- nodes es tabla SQL standard (phase §1.6)
  confidence REAL NOT NULL,
  occurrences INT DEFAULT 1,
  sample_contexts TEXT[],
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','archived')),
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now(),
  reviewed_by INT REFERENCES users(id)
);

-- 6. Entity merge log
CREATE TABLE IF NOT EXISTS entity_merge_log (
  id SERIAL PRIMARY KEY,
  source_node_id BIGINT NOT NULL,
  target_node_id BIGINT NOT NULL,       -- root final post-compresion
  target_original_id BIGINT NOT NULL,   -- target directo pre-compresion (para undo)
  merged_by INT REFERENCES users(id),
  reason TEXT,
  merged_at TIMESTAMPTZ DEFAULT now(),
  undone_at TIMESTAMPTZ
);

-- 7. Soft merge columns en nodes
ALTER TABLE nodes ADD COLUMN status TEXT DEFAULT 'active'
  CHECK (status IN ('active','merged'));
ALTER TABLE nodes ADD COLUMN merged_into BIGINT REFERENCES nodes(id);
CREATE INDEX IF NOT EXISTS idx_nodes_merged ON nodes(merged_into) WHERE status='merged';

-- 8. Related documents
CREATE TABLE IF NOT EXISTS related_documents (
  source_id UUID REFERENCES documents(id),
  target_id UUID REFERENCES documents(id),
  relation_type TEXT CHECK (relation_type IN ('duplicate','near_duplicate','revision_of','supersedes','derived_from')),
  similarity REAL,
  detected_at TIMESTAMPTZ DEFAULT now(),
  confirmed_by INT REFERENCES users(id),
  PRIMARY KEY (source_id, target_id)
);
CREATE INDEX IF NOT EXISTS idx_related_source ON related_documents(source_id);
CREATE INDEX IF NOT EXISTS idx_related_target ON related_documents(target_id);

COMMIT;
```

pg_dump previo obligatorio. Rollback: script inverso DROP/ALTER disponible. Tablas nuevas vacias — sin riesgo de datos.

---

## 8. Preguntas que el Adversarial deberia preguntar (Loop 2)

1. **soft merge overhead**: GAMR tiene que resolver `merged_into` para cada nodo en expansion. Con 100 merges, son 100 redirects por busqueda. Impacto en latencia?
2. **staleness vs weight**: una memoria stale tiene freshness_modifier < 0.3 Y peso reducido 50%. La doble penalizacion es intencional o excesiva?
3. **related_documents sin accion**: la tabla detecta near-duplicates pero si nadie revisa, crece indefinidamente. Hay mecanismo de limpieza?
4. **BM25 en document_chunks**: el indice GIN fulltext no existe en document_chunks (solo en memories). Hay que crearlo. Migracion DDL?
5. **entity_alias_candidates volumen**: con 1000 documentos, GLiNER puede generar cientos de candidatos. Hay purga automatica de candidatos no revisados?
6. **Reconciliacion intra-doc + auto-link**: ambos crean relaciones automaticamente. Se ejecutan en secuencia o en paralelo? Pueden producir resultados contradictorios?
7. **trust_origin columna**: solo 'manual' en phase. Vale la pena crear la columna ahora o es YAGNI?
8. **feature flags multiples**: BM25 tiene flag. Deberian tenerlo tambien auto-link, decay, auto-tags?
9. **staleness field en memories**: otra migracion DDL. Atomica con el resto de cambios phase?
10. **Background intelligence**: reconciliacion, stop freq, tension detection, stale marking. Quien los ejecuta? El worker de ingesta o proceso separado?
