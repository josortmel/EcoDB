---
workflow: diseño
fecha: 2026-05-12
proyecto: EcoDB
tipo: brief-construccion
version: "4.1-final"
autor: the research lead (arquitectura) + the design lead (diseño frontend)
revision: v2 integra aportaciones 3 consultorias externas
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md (phase original)
  - 2026-05-12_EcoDB_fase4_plan_construccion.md
  - 2026-05-12_EcoDB_fase5_plan_construccion.md
  - Conversacion relay the research lead↔the design lead 2026-05-12
tags:
  - workflow/disenio
  - proyecto/ecodb
  - tipo/brief
  - estado/v1
  - nivel/critical
---

# Brief — EcoDB phase: Producto (Dashboard Electron)

*the research lead + the design lead, 12 de mayo de 2026. v2 integra aportaciones DeepSeek+Gemini+ChatGPT.*

---

## 1. Contexto y motivacion

EcoDB tras Fases 4-5 tiene: memorias episodicas con weight dinamico y staleness, documentos indexados con chunks y trust tiers, grafo gobernado con predicados canonicos y soft merge, GAMR 8 etapas con BM25 + expansion documental + source resolution, gobernanza cognitiva con alias candidatos y deduplicacion. Toda esta capacidad es accesible SOLO via MCP tools y API REST — no hay interfaz visual.

phase construye el dashboard Electron: la herramienta visual de gobernanza donde the platform owner ve todo y hace todo lo que EcoDB permite. No es un monitor — es el centro de operaciones del sistema de conocimiento.

**Por que ahora:** sin UI, the platform owner gobierna EcoDB a ciegas. Los alias candidatos se acumulan sin revisar, las contradicciones sin resolver, los trust tiers sin asignar. Los agentes usan el sistema pero nadie SUPERVISA el sistema. El dashboard convierte gobernanza reactiva (MCP cuando un agente pregunta) en gobernanza proactiva (the platform owner ve el inbox de decisiones pendientes).

**Usuarios afectados:** the platform owner (unico usuario del dashboard en phase). Agentes indirectamente (mejor gobernanza = mejor retrieval).

---

## 2. Decisiones de diseno (con trazabilidad)

### D1: Stack — Electron + React + Vite + Tailwind

- Origen: [research] the design lead (evaluacion directa de ecosistemas frontend)
- Decision: Electron para app de escritorio instalable. React para UI (ecosistema mas maduro para dashboards de datos). Vite para build (hot reload instantaneo). Tailwind CSS para styling. electron-builder para empaquetado.
- Librerias clave:
  - **react-force-graph-2d** para grafo Canvas ([research] Gemini — SVG force-directed es error de rendimiento incluso con 200 nodos). Canvas > SVG para fisicas continuas. D3 solo como data layer, no render.
  - **TanStack Table** para tablas densas con sorting/filtering/pagination
  - **TanStack Query** para fetch API con cache + invalidation + background refresh
  - **Recharts** o **Nivo** para charts de /stats/*
  - **Zustand** para estado UI local (lightweight, sin boilerplate Redux)
- Razon: React tiene el ecosistema mas maduro para tablas de datos, grafos interactivos, y charts. Svelte es mas elegante pero su ecosistema de componentes para dashboards es insuficiente.
- Trade-off: Electron es pesado (~150 MB instalador). Aceptable para app de escritorio de un solo usuario.

### D2: Arquitectura — renderer directo a API REST, sin BFF

- Origen: [my-inference] + [research] the design lead
- Decision: no se necesita Backend-For-Frontend. La API REST ya fue disenada para el dashboard (the design lead anadio los endpoints de stats, SSE, subgraph, onboarding en phase). Single-tenant = sin complejidad de aggregation.
- Arquitectura:
  - **Main Process**: auth (PIN storage en OS keychain), health check, window management, auto-reconnect.
  - **Renderer Process**: fetch() directo a localhost:8080 con JWT. EventSource para SSE.
  - **Electron security hardening** ([A1] adversarial — BLOCKER):
    ```js
    new BrowserWindow({
      webPreferences: {
        nodeIntegration: false,      // renderer NO accede Node.js APIs
        contextIsolation: true,      // preload en contexto aislado
        preload: path.join(__dirname, 'preload.js'),  // bridge minimo
        sandbox: true
      }
    })
    ```
    CSP estricta: `default-src 'self'; connect-src 'self' http://localhost:8080; script-src 'self'`. Preload bridge expone SOLO: `window.ecodb.fetch(url, opts)`, `window.ecodb.sse(url)`, `window.ecodb.getToken()`. Renderer NO tiene acceso a fs, child_process, ni APIs Node.
- TanStack Query como capa de cache: SSE events invalidan queries relevantes automaticamente (`memory_created` → invalidar query memorias, `document_indexed` → invalidar query documentos). Real-time sin polling.
- Trade-off: acoplado a la API. Si la API cambia, el dashboard cambia. Aceptable single-tenant.

### D3: Auth — PIN local day 1, Google OAuth en phase

- Origen: [my-inference] + [research] the design lead
- Decision: phase usa PIN local **alfanumerico 8+ caracteres** ([research] 3/3 consultorias — 4-6 digitos es trivial de forzar). Hash con **bcrypt salt cost 10** almacenado en backend DB (no solo keychain). Validacion en **backend obligatoria** ([research] Gemini — frontend-only deja API expuesta). Max **5 intentos fallidos → lockout SERVER-SIDE** ([research] the design lead C1 — client lockout bypassable via app restart). Backend almacena `failed_attempts` + `locked_until` en DB. Si `locked_until > now()` → 423 Locked con remaining_seconds. Cooldown 15 min tras 5 fallos. **PIN recovery flow** ([L2] adversarial):
  - Al crear/cambiar PIN, backend genera `recovery_key` (32 bytes random, base64). Se muestra UNA vez en pantalla + se descarga como archivo `ecodb_recovery.key`.
  - Endpoint `POST /auth/pin/recover`: acepta recovery_key → resetea PIN → devuelve JWT temporal (1h) → the platform owner establece PIN nuevo inmediatamente.
  - **IPC mechanism** ([research] DeepSeek v2): descargar recovery_key via `ipcRenderer.invoke('save-file')` → main process usa `dialog.showSaveDialog`. Recuperar via `<input type="file">` en renderer → main process lee archivo → envia a backend. NO exponer fs al renderer.
  - Si the platform owner pierde recovery_key Y olvida PIN: acceso directo a DB (`UPDATE pin_hash`) como ultimo recurso documentado.
- phase (VPS): migrar a Google OAuth (the platform owner usa Gmail). PKCE flow para Electron. El PIN se mantiene como fallback offline.
- Razon: OAuth contra Anthropic puede no estar disponible para apps terceras. Google OAuth es estandar. Pero para day 1 en localhost, un PIN es suficiente y elimina toda complejidad de auth.
- Trade-off: sin OAuth no hay verificacion de identidad externa. Aceptable single-tenant localhost.

### D4: Pantallas — 8 pantallas + 2 paneles transversales

- Origen: [research] the design lead (reorganizacion de propuesta the research lead)
- Decision:

**Pantallas principales (navegacion lateral):**

1. **Command Center** — punto de entrada operativo. Stats resumen + activity feed SSE. **Attention Inbox** agrupado por **decision class** ([research] ChatGPT): `ontology` (aliases, merges, predicados), `knowledge_conflict` (tensiones, contradicciones), `document_governance` (duplicados, trust), `memory_lifecycle` (stale, dormant), (system_health va al System Monitor panel, no al inbox — es monitoreo operacional, no decision cognitiva [research] the design lead M1). Agrupacion semantica, no cronologica. Contadores por clase + detalle bajo demanda. Tab "Salud del Conocimiento" con metricas /stats/knowledge (entidades huerfanas, densidad grafo, candidatos acumulados) ([research] DeepSeek).

2. **Knowledge Explorer** — explorador unificado memorias + documentos. Tabs por tipo de fuente. Busqueda GAMR integrada. Vista lista con preview. Filtros: tipo, agente, proyecto, tags, fecha, staleness, trust_tier. Vista detalle lateral. Acciones contextuales por tipo:
   - Memoria: editar tags/tipo/weight, ver entidades vinculadas, ver en grafo, validar auto-links, desarchivar.
   - Documento: trust tier, re-indexar, desvincular, ver chunks, ver processing_metrics, confirmar relaciones.

3. **Graph Studio** — hero visual de la app. D3 force-directed interactivo con zoom semantico: zoom out = clusters por tipo, zoom in = relaciones individuales. Nodos coloreados por tipo (persona=azul, org=verde, tech=naranja). Tamano por grado. Click en nodo → panel lateral con vecinos, memorias vinculadas, tripletas, tipo, aliases. Acciones: merge desde el grafo, navegar a Knowledge Explorer.
   - **Render strategy** (corregido [research] 3/3 consultorias): **Canvas desde day 1** via `react-force-graph-2d`. SVG descartado — force simulations + SVG DOM reflows degradan rendimiento incluso con 200 nodos. Canvas maneja 500+ nodos sin problemas. WebGL (3D) como phase si se necesita.
   - **Simulation**: initial simulation → freeze → drag manual puntual → layout cacheado ([research] ChatGPT). No fisicas continuas permanentes — producen fatiga visual y consumen CPU.
   - **Clustering server-side** ([research] Gemini): endpoint `GET /graph/clusters` con Louvain. Dashboard recibe clusters pre-calculados. No calcular en cliente.
   - **Canvas interaction layer** ([research] the design lead H1): react-force-graph-2d como base. Custom layer necesario: multi-select (Shift+click), right-click context menu, custom tooltips posicionados, drag-to-select region. **Complejidad +40% sobre render basico**. No es "usar lib y ya".

4. **Ontology Console** — gobernanza del vocabulario. Dos tabs:
   - **Entidades**: alias candidatos pendientes (aprobar/rechazar), merges propuestos, stop entities (manual + dinamicas por freq), tipado de nodos, reconciliacion pendiente.
   - **Predicados**: canonicos con metadata (symmetric, inverse_of, transitive, domain/range), aliases, pending_predicates, estados (experimental→approved→deprecated), vista inversos inferidos.

5. **Decisions** — inbox de decisiones humanas. "Una contradiccion no es un error tecnico, es un momento de decision humana" (the design lead). Categorias por decision class. **Split view** ([research] Gemini): al resolver un item, panel lateral muestra contexto completo (nodo existente + chunks donde se detecto candidato, ambas memorias en tension, etc.). the platform owner no necesita navegar fuera para decidir. Layout responsive dentro del rango desktop ([research] the design lead M2): ≥1440px split horizontal, 1280-1439px stack vertical. Cada item: "why am I seeing this?" con explicacion (similaridad, entidades compartidas, etc.) ([research] ChatGPT).

6. **Ingestion** — cola de ingesta en tiempo real. Documentos en queued/processing/indexed/failed/deleted/superseded. SSE live. Acciones: re-indexar, desvincular, cambiar trust tier. Processing metrics por documento. Vista de watchdog status.

7. **Templates** — formularios guiados para guardar recuerdos estructurados:
   - **Reunion**: fecha, participantes, acuerdos, action items → genera memoria tipo 'acuerdo' con tags apropiados.
   - **Decision tecnica**: contexto, alternativas evaluadas, decision tomada, razon → genera memoria tipo 'decision'.
   - **Descubrimiento**: hallazgo, fuente, implicaciones → genera memoria tipo 'descubrimiento'.
   - Cada template pre-llena type, sugiere tags, estructura el contenido.
   - **Flujo** ([research] 3/3 consultorias): formulario → preview editable (markdown) → ver tags sugeridos + entidades detectadas + confidence → solo guardar al confirmar. Pipeline completo (embedding + GLiNER + auto-link) se ejecuta al guardar. Nunca guardar directamente sin preview.
   - **Trazabilidad** ([research] Gemini): memorias creadas via template llevan metadata `source: "template:{tipo}"` para distinguir de memorias de agentes.

8. **Settings** — configuracion del sistema:
   - Trust tiers: asignar por documento
   - memory_type_config: base_weight y decay por tipo
   - Stop entities: CRUD manual
   - Entity dictionary: CRUD
   - Feature flags: ENABLE_BM25, ENABLE_AUTO_LINK
   - Watchdog: carpetas vigiladas, extensiones
   - PIN management

**Paneles transversales:**

- **Cmd+K Search** — **launcher** rapido ([research] the design lead H4). Escribir → 5-8 resultados → Enter → navega al item. Como Spotlight/Raycast. Sin filtros persistentes. Distinto de Knowledge Explorer search que es deep-dive con filtros, paginacion, score_breakdown. Mismo motor GAMR, distinta UX.
- **System Monitor** — barra lateral/inferior colapsable. Metricas en vivo: GPU, cola, throughput, agentes activos. No necesita pantalla propia — es informacion ambiental.

### D5: Diseno visual — territorio de the design lead

- Origen: [research] the design lead
- Decision: la identidad visual de EcoDB (paleta, tipografia, iconografia, component design system) la define the design lead durante implementacion. the platform owner aprueba iteraciones.
- Constraints del brief:
  - **Dark by default** — power tool para horas de uso.
  - **Color codifica significado** — tipos de entidad, estados de memoria, trust tiers. No decoracion.
  - **El grafo es arte** — force-directed con fisica suave, transiciones animadas, hover con glow.
  - **Keyboard-first** — Cmd+K, atajos, raton como fallback.
  - **Window constraints**: minimum 1280x720, target 1920x1080. No mobile, no tablet, no responsive. App de escritorio con densidad de informacion sin compromiso.
- Referencias: Linear (densidad+belleza), Supabase Studio (DB management), Neo4j Bloom (graph viz), Grafana (monitoring), Raycast (Cmd+K UX).
- Paleta propuesta por the design lead: dark neutral (slate/zinc) + acento teal/cyan ("conocimiento vivo"). Tipografia: JetBrains Mono (code/data) + Inter (texto).

### D6: SSE como motor de real-time

- Origen: [my-inference] basada en phase (SSE ya implementado)
- Decision: EventSource directo desde renderer a GET /events/stream. TanStack Query invalida cache automaticamente al recibir eventos. Tipos de evento existentes: memory_created, document_indexed, document_failed, source_updated, agent_connected/disconnected, contradiction_detected, system_alert, duplicate_detected, tension_detected. Nuevos para dashboard: stale_marked, dormant_marked.
- **Heartbeat** ([research] 3/3 consultorias): servidor envia `keepalive` cada 30s. Si cliente no recibe 60s → banner "Desconectado, datos pueden estar obsoletos".
- **Reconnect strategy** (corregido [research] the design lead H2): al reconectar, `queryClient.invalidateQueries({refetchType: 'none'})` → **soft invalidation**. Datos visibles se mantienen, refetch en background. Sin flash visual global. Datos se actualizan silenciosamente cuando componentes re-renderizan o window re-focus.
- **Event digest** ([research] ChatGPT + the design lead H3): ventanas por tipo:
  - **Inmediato**: memory_created, document_indexed, agent_connected/disconnected (the platform owner quiere verlos al momento)
  - **Batch 10s**: stale_marked, dormant_marked, duplicate_detected (background, no urgentes)
  - **Debounce 3s**: attention_inbox_update (puede disparar en rafaga cuando scheduler ejecuta)
- Trade-off: SSE unidireccional. Acciones via fetch(). Aceptable.

### D7: Graceful degradation

- Origen: [research] the design lead (pregunta #4)
- Decision: si EcoDB no esta corriendo cuando the platform owner abre el dashboard:
  - Pantalla de estado: "EcoDB API no responde en localhost:8080"
  - Diagnostico automatico: verificar si Docker esta corriendo, si los containers estan healthy
  - Retry automatico cada 5 segundos con indicador visual
  - Ultimo estado conocido cacheado localmente (TanStack Query persistent cache) — visible con banner "datos de hace X minutos"
  - No crash silencioso, no pantalla blanca

### D8: Endpoints API que faltan para el dashboard

- Origen: [my-inference] auditando API actual vs necesidades del dashboard
- Decision: endpoints existentes cubren ~90% de las necesidades. Gaps identificados:
  - **GET /admin/attention-inbox/summary**: contadores por decision class: `ontology`, `knowledge_conflict`, `document_governance`, `memory_lifecycle`. **Sin system_health** ([C1] adversarial — system_health es monitoreo operacional, va al System Monitor panel via /stats/system, no al inbox cognitivo). Cache 1 min. SSE event `attention_inbox_update`.
  - **GET /admin/attention-inbox/details?class=X&limit=20&cursor=Y**: items concretos para una clase, paginado. Detalle bajo demanda cuando the platform owner expande una clase.
  - **PUT /memories/{id}/staleness**: cambiar staleness manualmente (desarchivar, forzar stale).
  - **GET /stats/timeline**: actividad temporal para charts (memorias creadas por dia, documentos indexados por dia, searches por dia). Periodo configurable.
  - **POST /auth/pin**: verificar PIN contra hash bcrypt en DB, devolver JWT. **JWT params** ([A3] adversarial): TTL **4 horas** (sesion de trabajo tipica). Sin refresh token — al expirar, pedir PIN de nuevo (baja friccion single-tenant). Renderer almacena JWT **solo en memoria** (no localStorage, no electron-store). Al cerrar app → token perdido → PIN al reabrir. Rate limit: 5 intentos, 423 Locked 15 min.
  - **PUT /auth/pin**: cambiar PIN. Requiere PIN actual.
  - **POST /auth/pin/recover**: acepta recovery_key → resetea PIN → devuelve JWT temporal (1h). ([G1] adversarial L2 — endpoint estaba en D3 pero faltaba en D8).
  - **POST /memories/preview** ([research] the design lead C2): dry-run GLiNER sobre content draft. Devuelve {entities_detected, suggested_tags, confidence_scores}. Sin INSERT, sin embedding, sin side effects. Prerequisito para template preview con entidades.
  - **GET /graph/clusters**: clusters pre-calculados Louvain. Ownership: tarea backend phase (the engineering lead). Proceso `cluster_updater` en APScheduler cada hora. Cache table ([SD1] adversarial L2 — DDL completo):
    ```sql
    CREATE TABLE graph_clusters (
      node_id INT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      cluster_id INT NOT NULL,
      computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (node_id)
    );
    CREATE INDEX idx_gc_cluster ON graph_clusters (cluster_id);
    ```
    Louvain devuelve cluster IDs numericos (no labels — labels derivados del nodo con mayor grado por cluster, calculado en aplicacion). Timeout Louvain: 2 min — si excede, mantener clusters anteriores. Response <200ms (cache read). Clusters >2h antiguos: indicador visual + fallback flat layout.
- Razon: el dashboard necesita un punto de entrada unico para el inbox de gobernanza (attention-inbox) y endpoints de gestion que los agentes MCP no necesitan.

---

## 3. Scope

### Dentro:
- Electron app con React + Vite + Tailwind
- 8 pantallas + 2 paneles transversales (D4)
- Canvas graph via react-force-graph-2d (no SVG)
- Graph clustering server-side (GET /graph/clusters)
- TanStack Query + SSE para real-time sin polling
- TanStack Table para tablas densas
- Recharts/Nivo para charts
- Zustand para estado UI
- PIN local auth 8+ chars alphanumeric, bcrypt backend, 5 attempt lockout (D3)
- SSE heartbeat 30s + reconnect invalidation + event digest
- Attention inbox split summary/details + decision classes
- Decisions split view with context
- Templates preview editable + pipeline completo + trazabilidad metadata
- Cmd+K busqueda GAMR universal
- System Monitor ambiental
- Templates de recuerdos (reunion, decision, descubrimiento)
- Graceful degradation cuando API no disponible (D7)
- 8 endpoints API nuevos (D8 — incluyendo /memories/preview, /graph/clusters, inbox split)
- Vitest para logica de datos
- Louvain clustering backend (APScheduler hourly, table graph_clusters)
- Alias rejection check en pipeline ingesta: no re-proponer alias rechazados ([SD2] adversarial L2 — logica en pipeline, no en endpoint clusters)
- CE alias rejection: verificar que candidato rechazado no se re-propone
- electron-builder para empaquetado .exe
- Identidad visual definida por the design lead (dark theme, teal/cyan acento)

### Fuera (deuda consciente):
- Google OAuth (phase — VPS)
- Auto-update del .exe (phase)
- WebGL 3D para grafos (Canvas 2D sufficient day 1)
- Code signing .exe (phase — Windows Defender puede bloquear sin firma)
- Quiet modes / focus modes (ChatGPT — reduce noise per workflow type)
- Investigation workspace stateful (phase)
- Mobile/tablet/responsive (no aplica — app de escritorio)
- Internacionalizacion (single-user, sin i18n)
- Accessibility avanzada (ARIA basico si, pero no screen reader optimizado)
- RRF como alternativa a suma ponderada (backend, diferida desde phase)
- Cross-encoder reranking (backend)
- Cognitive Semantics Specification document (documentacion, pre-requisito conceptual pero no bloquea construccion)
- Feedback explicito de agentes (tool marcar_util — backend phase deuda)

---

## 4. Criterios de exito (verificables)

- CE-1: `npm run build` genera .exe instalable via electron-builder. the platform owner lo instala en Windows 11.
- CE-2: App abre, pide PIN, verifica contra API, muestra Command Center con stats + attention inbox.
- CE-3: Command Center muestra items pendientes (contradicciones, alias, stale, duplicados) en tiempo real via SSE.
- CE-4: Knowledge Explorer: buscar memoria → ver detalle → editar tags → guardar. Buscar documento → ver chunks → cambiar trust tier.
- CE-5: Graph Studio: grafo Canvas interactivo con **300 nodos** + 800 edges → 30+ FPS ([research] the design lead M3 — alineado con CE-18). Zoom, click nodo → panel lateral. Colores por tipo.
- CE-6: Ontology Console: ver alias candidatos → aprobar/rechazar. Ver predicados → ver estados. Merge de entidades desde UI.
- CE-7: Decisions inbox: ver contradiccion → resolver (descartar/confirmar). Ver alias candidato → aprobar.
- CE-8: Ingestion: ver cola en tiempo real. Documento failed → click re-indexar.
- CE-9: Templates: crear reunion con formulario guiado → memoria tipo 'acuerdo' creada con tags correctos.
- CE-10: Cmd+K desde cualquier pantalla → busqueda GAMR → click resultado → navega a detalle.
- CE-11: System Monitor: metricas en vivo (GPU, cola, throughput) visibles como barra ambiental.
- CE-12: API no disponible → pantalla de error con diagnostico + retry. Datos cacheados via `persistQueryClient` + `electron-store` ([research] the design lead M4). Persistir: stats, inbox summary, ultima vista Explorer. TTL 24h. No persistir: System Monitor metrics, SSE events.
- CE-13: SSE: crear memoria via MCP → aparece en Knowledge Explorer sin refrescar.
- CE-14: Minimum window 1280x720. Layout funcional sin scroll horizontal en 1920x1080.
- CE-15: PIN auth: 8+ chars alfanumerico, validado en backend. PIN incorrecto 5 veces → lockout. Cambiar PIN desde Settings requiere PIN actual.
- CE-16: SSE heartbeat: 60s sin keepalive → banner "Desconectado". Reconexion → invalidateQueries() automatico.
- CE-17: Attention inbox: contadores por decision class cargados en <200ms (cache 1 min). Detalle paginado bajo demanda.
- CE-18: Graph Studio: 300 nodos + 800 edges en Canvas → 30+ FPS interactivo. Clusters server-side visibles en zoom out.
- CE-19: Templates: formulario reunion → preview markdown editable → entidades detectadas visibles → guardar → memoria tipo acuerdo con metadata source:"template:reunion".
- CE-20: Decisions split view: click item → panel lateral muestra contexto completo sin navegar fuera. "Why surfaced?" visible.
- CE-21: Electron security: nodeIntegration=false, contextIsolation=true verificado. Renderer NO puede acceder fs/child_process.
- CE-22: JWT expira tras 4h → app pide PIN de nuevo. Token solo en memoria — cerrar app = token perdido.
- CE-23: PIN recovery: crear PIN → recovery_key generado. Usar recovery_key → PIN reseteado → nuevo PIN establecido.
- CE-24: attention-inbox/summary NO incluye system_health. Solo 4 classes cognitivas.
- CE-25: alias rechazado en Ontology Console → nuevo documento con misma entidad → NO se re-propone candidato.
- CE-26: GET /graph/clusters responde <200ms (cache). Clusters >2h → indicador visual "desactualizados".

---

## 5. Deuda explicita

- **Google OAuth**: PIN local es suficiente para localhost single-tenant. OAuth necesario cuando EcoDB viva en VPS (phase).
- **WebGL 3D grafo**: Canvas 2D maneja 500+ nodos. 3D si se necesita inmersion.
- **Code signing**: sin firma, Windows Defender puede bloquear .exe. phase.
- **Quiet modes**: modo foco que reduce ruido no relevante. Diferido pero valioso.
- **Investigation workspace**: espacio stateful para gobernanza compleja multi-entidad. phase.
- **Cognitive quality metrics**: auto-link approval rate, alias approval rate, retrieval clicks top-1. phase con feedback explicito.
- **Auto-update**: instalacion manual en phase. electron-updater en phase si se necesita.
- **Testing frontend**: **Vitest para logica de transformacion de datos** (formateo scores, categorizacion inbox, event digest, colores por tipo) ([research] the design lead M5). No component tests ni E2E day 1.
- **Identidad visual finalizada**: the design lead itera durante construccion. No hay mockups pre-aprobados — the platform owner aprueba iteraciones in-situ.
- **Offline mode**: sin soporte offline real. Solo cache de ultimo estado. Si API cae, dashboard es read-only sobre cache.

---

## 6. Preguntas que el Adversarial deberia preguntar

1. **PIN storage seguridad**: OS keychain (safeStorage) es seguro, pero si alguien tiene acceso fisico al PC de the platform owner, el PIN es trivial de forzar (4-6 digitos). ¿Es aceptable single-tenant?
2. **TanStack Query cache invalidation**: si SSE pierde conexion brevemente, ¿se pierden invalidaciones? ¿Hay reconciliacion al reconectar?
3. **D3 performance**: force-directed con 200 nodos + fisicas + animaciones en SVG dentro de Electron. ¿Hay benchmark? ¿El renderer de Electron (Chromium) maneja bien?
4. **Attention inbox endpoint**: agregar N queries en un solo endpoint puede ser lento si cada query es costosa. ¿Se cachea? ¿Refresh rate?
5. **Templates de recuerdos**: los templates generan memorias via POST /memories. ¿Pasan por GLiNER/entity extraction? ¿O son memorias "crudas"?
6. **electron-builder en Windows**: ¿code signing? Sin firma, Windows Defender puede bloquear el .exe.
7. **Tamaño de la app**: Electron (~150 MB) + React + D3 + dependencias. ¿Tamaño final estimado del instalador?
8. **Versiones de Node/Electron**: ¿pinned? Electron evoluciona rapido, versiones viejas tienen vulnerabilidades.
9. **Graph Studio zoom semantico**: zoom out = clusters. ¿Como se calculan los clusters? ¿Server-side o client-side? ¿Con que algoritmo?
10. **Templates como formularios**: ¿el contenido generado es editable antes de guardar? ¿O guardan directamente?
