---
workflow: design
fecha: 2026-05-12
proyecto: EcoDB
tipo: construction-brief
version: "4.1-final"
autor: the research lead (architecture) + the design lead (frontend design)
revision: v2 integrates contributions from 3 external consultancies
nivel: critical
input:
  - 2026-05-07_EcoDB_plan_maestro_construccion_v2.md (original phase)
  - 2026-05-12_EcoDB_fase4_plan_construccion.md
  - 2026-05-12_EcoDB_fase5_plan_construccion.md
  - Relay conversation the research lead↔the design lead 2026-05-12
tags:
  - workflow/design
  - project/ecodb
  - type/brief
  - status/v1
  - level/critical
---

# Brief — EcoDB Phase: Product (Electron Dashboard)

*the research lead + the design lead, May 12, 2026. v2 integrates contributions from DeepSeek+Gemini+ChatGPT.*

---

## 1. Context and motivation

After Phases 4-5, EcoDB has: episodic memories with dynamic weight and staleness, indexed documents with chunks and trust tiers, a governed graph with canonical predicates and soft merge, 8-stage GAMR with BM25 + document expansion + source resolution, cognitive governance with candidate aliases and deduplication. All this capability is accessible ONLY via MCP tools and REST API — there is no visual interface.

This phase builds the Electron dashboard: the visual governance tool where the platform owner sees everything and does everything EcoDB enables. It is not a monitor — it is the operations center of the knowledge system.

**Why now:** without a UI, the platform owner governs EcoDB blind. Candidate aliases accumulate without review, contradictions go unresolved, trust tiers go unassigned. Agents use the system but nobody SUPERVISES the system. The dashboard converts reactive governance (MCP when an agent queries) into proactive governance (the platform owner sees the inbox of pending decisions).

**Affected users:** the platform owner (sole dashboard user in this phase). Agents indirectly (better governance = better retrieval).

---

## 2. Design decisions (with traceability)

### D1: Stack — Electron + React + Vite + Tailwind

- Origin: [research] the design lead (direct evaluation of frontend ecosystems)
- Decision: Electron for installable desktop app. React for UI (most mature ecosystem for data dashboards). Vite for build (instant hot reload). Tailwind CSS for styling. electron-builder for packaging.
- Key libraries:
  - **react-force-graph-2d** for Canvas graph ([research] Gemini — SVG force-directed is a performance mistake even with 200 nodes). Canvas > SVG for continuous physics. D3 only as data layer, not renderer.
  - **TanStack Table** for dense tables with sorting/filtering/pagination
  - **TanStack Query** for API fetch with cache + invalidation + background refresh
  - **Recharts** or **Nivo** for /stats/* charts
  - **Zustand** for local UI state (lightweight, no Redux boilerplate)
- Rationale: React has the most mature ecosystem for data tables, interactive graphs, and charts. Svelte is more elegant but its component ecosystem for dashboards is insufficient.
- Trade-off: Electron is heavy (~150 MB installer). Acceptable for a single-user desktop app.

### D2: Architecture — renderer direct to REST API, no BFF

- Origin: [my-inference] + [research] the design lead
- Decision: no Backend-For-Frontend needed. The REST API was already designed for the dashboard (the design lead added stats, SSE, subgraph, onboarding endpoints in this phase). Single-tenant = no aggregation complexity.
- Architecture:
  - **Main Process**: auth (PIN storage in OS keychain), health check, window management, auto-reconnect.
  - **Renderer Process**: fetch() direct to localhost:8080 with JWT. EventSource for SSE.
  - **Electron security hardening** ([A1] adversarial — BLOCKER):
    ```js
    new BrowserWindow({
      webPreferences: {
        nodeIntegration: false,      // renderer does NOT access Node.js APIs
        contextIsolation: true,      // preload in isolated context
        preload: path.join(__dirname, 'preload.js'),  // minimal bridge
        sandbox: true
      }
    })
    ```
    Strict CSP: `default-src 'self'; connect-src 'self' http://localhost:8080; script-src 'self'`. Preload bridge exposes ONLY: `window.ecodb.fetch(url, opts)`, `window.ecodb.sse(url)`, `window.ecodb.getToken()`. Renderer does NOT have access to fs, child_process, or Node APIs.
- TanStack Query as cache layer: SSE events automatically invalidate relevant queries (`memory_created` → invalidate memories query, `document_indexed` → invalidate documents query). Real-time without polling.
- Trade-off: coupled to the API. If the API changes, the dashboard changes. Acceptable single-tenant.

### D3: Auth — local PIN day 1, Google OAuth in future phase

- Origin: [my-inference] + [research] the design lead
- Decision: this phase uses local PIN **alphanumeric 8+ characters** ([research] 3/3 consultancies — 4-6 digits is trivially brute-forceable). Hash with **bcrypt salt cost 10** stored in backend DB (not just keychain). **Backend-mandatory validation** ([research] Gemini — frontend-only leaves API exposed). Max **5 failed attempts → SERVER-SIDE lockout** ([research] the design lead C1 — client lockout bypassable via app restart). Backend stores `failed_attempts` + `locked_until` in DB. If `locked_until > now()` → 423 Locked with remaining_seconds. 15 min cooldown after 5 failures. **PIN recovery flow** ([L2] adversarial):
  - When creating/changing PIN, backend generates `recovery_key` (32 bytes random, base64). Shown ONCE on screen + downloaded as `ecodb_recovery.key` file.
  - Endpoint `POST /auth/pin/recover`: accepts recovery_key → resets PIN → returns temporary JWT (1h) → the platform owner sets new PIN immediately.
  - **IPC mechanism** ([research] DeepSeek v2): download recovery_key via `ipcRenderer.invoke('save-file')` → main process uses `dialog.showSaveDialog`. Recover via `<input type="file">` in renderer → main process reads file → sends to backend. Do NOT expose fs to renderer.
  - If the platform owner loses recovery_key AND forgets PIN: direct DB access (`UPDATE pin_hash`) as documented last resort.
- Future phase (VPS): migrate to Google OAuth (the platform owner uses Gmail). PKCE flow for Electron. PIN remains as offline fallback.
- Rationale: OAuth against Anthropic may not be available for third-party apps. Google OAuth is standard. But for day 1 on localhost, a PIN is sufficient and eliminates all auth complexity.
- Trade-off: without OAuth there is no external identity verification. Acceptable single-tenant localhost.

### D4: Screens — 8 screens + 2 transversal panels

- Origin: [research] the design lead (reorganization of the research lead's proposal)
- Decision:

**Main screens (sidebar navigation):**

1. **Command Center** — operational entry point. Summary stats + SSE activity feed. **Attention Inbox** grouped by **decision class** ([research] ChatGPT): `ontology` (aliases, merges, predicates), `knowledge_conflict` (tensions, contradictions), `document_governance` (duplicates, trust), `memory_lifecycle` (stale, dormant), (system_health goes to System Monitor panel, not to inbox — it is operational monitoring, not cognitive decision [research] the design lead M1). Semantic grouping, not chronological. Counters per class + detail on demand. "Knowledge Health" tab with /stats/knowledge metrics (orphaned entities, graph density, accumulated candidates) ([research] DeepSeek).

2. **Knowledge Explorer** — unified explorer for memories + documents. Tabs by source type. Integrated GAMR search. List view with preview. Filters: type, agent, project, tags, date, staleness, trust_tier. Side detail view. Contextual actions by type:
   - Memory: edit tags/type/weight, view linked entities, view in graph, validate auto-links, unarchive.
   - Document: trust tier, re-index, unlink, view chunks, view processing_metrics, confirm relationships.

3. **Graph Studio** — hero visual of the app. Interactive D3 force-directed with semantic zoom: zoom out = clusters by type, zoom in = individual relationships. Nodes colored by type (person=blue, org=green, tech=orange). Size by degree. Click node → side panel with neighbors, linked memories, triples, type, aliases. Actions: merge from graph, navigate to Knowledge Explorer.
   - **Render strategy** (corrected [research] 3/3 consultancies): **Canvas from day 1** via `react-force-graph-2d`. SVG discarded — force simulations + SVG DOM reflows degrade performance even with 200 nodes. Canvas handles 500+ nodes without issues. WebGL (3D) as future phase if needed.
   - **Simulation**: initial simulation → freeze → manual drag on demand → cached layout ([research] ChatGPT). No permanent continuous physics — causes visual fatigue and consumes CPU.
   - **Server-side clustering** ([research] Gemini): endpoint `GET /graph/clusters` with Louvain. Dashboard receives pre-calculated clusters. Do not calculate on client.
   - **Canvas interaction layer** ([research] the design lead H1): react-force-graph-2d as base. Custom layer needed: multi-select (Shift+click), right-click context menu, custom positioned tooltips, drag-to-select region. **+40% complexity over basic render**. Not "use lib and done".

4. **Ontology Console** — vocabulary governance. Two tabs:
   - **Entities**: pending candidate aliases (approve/reject), proposed merges, stop entities (manual + dynamic by frequency), node typing, pending reconciliation.
   - **Predicates**: canonicals with metadata (symmetric, inverse_of, transitive, domain/range), aliases, pending_predicates, states (experimental→approved→deprecated), inferred inverse view.

5. **Decisions** — human decisions inbox. "A contradiction is not a technical error, it is a moment for human decision" (the design lead). Categories by decision class. **Split view** ([research] Gemini): when resolving an item, side panel shows complete context (existing node + chunks where candidate was detected, both memories in tension, etc.). the platform owner does not need to navigate away to decide. Responsive layout within desktop range ([research] the design lead M2): ≥1440px horizontal split, 1280-1439px vertical stack. Each item: "why am I seeing this?" with explanation (similarity, shared entities, etc.) ([research] ChatGPT).

6. **Ingestion** — real-time ingestion queue. Documents in queued/processing/indexed/failed/deleted/superseded. Live SSE. Actions: re-index, unlink, change trust tier. Processing metrics per document. Watchdog status view.

7. **Templates** — guided forms for saving structured memories:
   - **Meeting**: date, participants, agreements, action items → generates memory type 'acuerdo' with appropriate tags.
   - **Technical decision**: context, evaluated alternatives, decision taken, rationale → generates memory type 'decision'.
   - **Discovery**: finding, source, implications → generates memory type 'descubrimiento'.
   - Each template pre-fills type, suggests tags, structures content.
   - **Flow** ([research] 3/3 consultancies): form → editable preview (markdown) → view suggested tags + detected entities + confidence → save only on confirm. Full pipeline (embedding + GLiNER + auto-link) executes on save. Never save directly without preview.
   - **Traceability** ([research] Gemini): memories created via template carry metadata `source: "template:{type}"` to distinguish from agent-created memories.

8. **Settings** — system configuration:
   - Trust tiers: assign per document
   - memory_type_config: base_weight and decay per type
   - Stop entities: manual CRUD
   - Entity dictionary: CRUD
   - Feature flags: ENABLE_BM25, ENABLE_AUTO_LINK
   - Watchdog: watched folders, extensions
   - PIN management

**Transversal panels:**

- **Cmd+K Search** — quick **launcher** ([research] the design lead H4). Type → 5-8 results → Enter → navigates to item. Like Spotlight/Raycast. No persistent filters. Different from Knowledge Explorer search which is deep-dive with filters, pagination, score_breakdown. Same GAMR engine, different UX.
- **System Monitor** — collapsible side/bottom bar. Live metrics: GPU, queue, throughput, active agents. Does not need its own screen — it is ambient information.

### D5: Visual design — the design lead's territory

- Origin: [research] the design lead
- Decision: EcoDB's visual identity (palette, typography, iconography, component design system) is defined by the design lead during implementation. the platform owner approves iterations.
- Brief constraints:
  - **Dark by default** — power tool for hours of use.
  - **Color encodes meaning** — entity types, memory states, trust tiers. Not decoration.
  - **The graph is art** — force-directed with soft physics, animated transitions, hover with glow.
  - **Keyboard-first** — Cmd+K, shortcuts, mouse as fallback.
  - **Window constraints**: minimum 1280x720, target 1920x1080. No mobile, no tablet, no responsive. Desktop app with uncompromised information density.
- References: Linear (density+beauty), Supabase Studio (DB management), Neo4j Bloom (graph viz), Grafana (monitoring), Raycast (Cmd+K UX).
- Palette proposed by the design lead: dark neutral (slate/zinc) + teal/cyan accent ("living knowledge"). Typography: JetBrains Mono (code/data) + Inter (text).

### D6: SSE as real-time engine

- Origin: [my-inference] based on previous phase (SSE already implemented)
- Decision: EventSource direct from renderer to GET /events/stream. TanStack Query invalidates cache automatically upon receiving events. Existing event types: memory_created, document_indexed, document_failed, source_updated, agent_connected/disconnected, contradiction_detected, system_alert, duplicate_detected, tension_detected. New for dashboard: stale_marked, dormant_marked.
- **Heartbeat** ([research] 3/3 consultancies): server sends `keepalive` every 30s. If client receives nothing for 60s → banner "Disconnected, data may be stale".
- **Reconnect strategy** (corrected [research] the design lead H2): on reconnect, `queryClient.invalidateQueries({refetchType: 'none'})` → **soft invalidation**. Visible data persists, refetch in background. No global visual flash. Data updates silently when components re-render or window re-focuses.
- **Event digest** ([research] ChatGPT + the design lead H3): windows by type:
  - **Immediate**: memory_created, document_indexed, agent_connected/disconnected (the platform owner wants to see them instantly)
  - **Batch 10s**: stale_marked, dormant_marked, duplicate_detected (background, not urgent)
  - **Debounce 3s**: attention_inbox_update (can fire in bursts when scheduler runs)
- Trade-off: SSE is unidirectional. Actions via fetch(). Acceptable.

### D7: Graceful degradation

- Origin: [research] the design lead (question #4)
- Decision: if EcoDB is not running when the platform owner opens the dashboard:
  - Status screen: "EcoDB API not responding at localhost:8080"
  - Automatic diagnostics: check if Docker is running, if containers are healthy
  - Automatic retry every 5 seconds with visual indicator
  - Last known state cached locally (TanStack Query persistent cache) — visible with banner "data from X minutes ago"
  - No silent crash, no white screen

### D8: Missing API endpoints for the dashboard

- Origin: [my-inference] auditing current API vs dashboard needs
- Decision: existing endpoints cover ~90% of needs. Identified gaps:
  - **GET /admin/attention-inbox/summary**: counters per decision class: `ontology`, `knowledge_conflict`, `document_governance`, `memory_lifecycle`. **No system_health** ([C1] adversarial — system_health is operational monitoring, goes to System Monitor panel via /stats/system, not to cognitive inbox). 1 min cache. SSE event `attention_inbox_update`.
  - **GET /admin/attention-inbox/details?class=X&limit=20&cursor=Y**: concrete items for a class, paginated. Detail on demand when the platform owner expands a class.
  - **PUT /memories/{id}/staleness**: manually change staleness (unarchive, force stale).
  - **GET /stats/timeline**: temporal activity for charts (memories created per day, documents indexed per day, searches per day). Configurable period.
  - **POST /auth/pin**: verify PIN against bcrypt hash in DB, return JWT. **JWT params** ([A3] adversarial): TTL **4 hours** (typical work session). No refresh token — on expiry, request PIN again (low friction single-tenant). Renderer stores JWT **only in memory** (not localStorage, not electron-store). On app close → token lost → PIN on reopen. Rate limit: 5 attempts, 423 Locked 15 min.
  - **PUT /auth/pin**: change PIN. Requires current PIN.
  - **POST /auth/pin/recover**: accepts recovery_key → resets PIN → returns temporary JWT (1h). ([G1] adversarial L2 — endpoint was in D3 but missing from D8).
  - **POST /memories/preview** ([research] the design lead C2): dry-run GLiNER on content draft. Returns {entities_detected, suggested_tags, confidence_scores}. No INSERT, no embedding, no side effects. Prerequisite for template preview with entities.
  - **GET /graph/clusters**: pre-calculated Louvain clusters. Ownership: backend task for this phase (the engineering lead). `cluster_updater` process in APScheduler hourly. Cache table ([SD1] adversarial L2 — full DDL):
    ```sql
    CREATE TABLE graph_clusters (
      node_id INT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      cluster_id INT NOT NULL,
      computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (node_id)
    );
    CREATE INDEX idx_gc_cluster ON graph_clusters (cluster_id);
    ```
    Louvain returns numeric cluster IDs (not labels — labels derived from the node with highest degree per cluster, calculated in application). Louvain timeout: 2 min — if exceeded, keep previous clusters. Response <200ms (cache read). Clusters >2h old: visual indicator + flat layout fallback.
- Rationale: the dashboard needs a single entry point for the governance inbox (attention-inbox) and management endpoints that MCP agents do not need.

---

## 3. Scope

### In scope:
- Electron app with React + Vite + Tailwind
- 8 screens + 2 transversal panels (D4)
- Canvas graph via react-force-graph-2d (no SVG)
- Server-side graph clustering (GET /graph/clusters)
- TanStack Query + SSE for real-time without polling
- TanStack Table for dense tables
- Recharts/Nivo for charts
- Zustand for UI state
- Local PIN auth 8+ chars alphanumeric, bcrypt backend, 5 attempt lockout (D3)
- SSE heartbeat 30s + reconnect invalidation + event digest
- Attention inbox split summary/details + decision classes
- Decisions split view with context
- Templates editable preview + full pipeline + traceability metadata
- Cmd+K universal GAMR search
- Ambient System Monitor
- Memory templates (meeting, decision, discovery)
- Graceful degradation when API unavailable (D7)
- 8 new API endpoints (D8 — including /memories/preview, /graph/clusters, inbox split)
- Vitest for data logic
- Louvain clustering backend (APScheduler hourly, graph_clusters table)
- Alias rejection check in ingestion pipeline: do not re-propose rejected aliases ([SD2] adversarial L2 — logic in pipeline, not in clusters endpoint)
- CE alias rejection: verify that rejected candidate is not re-proposed
- electron-builder for .exe packaging
- Visual identity defined by the design lead (dark theme, teal/cyan accent)

### Out of scope (conscious debt):
- Google OAuth (future phase — VPS)
- .exe auto-update (future phase)
- WebGL 3D for graphs (Canvas 2D sufficient day 1)
- .exe code signing (future phase — Windows Defender may block unsigned)
- Quiet modes / focus modes (ChatGPT — reduce noise per workflow type)
- Stateful investigation workspace (future phase)
- Mobile/tablet/responsive (not applicable — desktop app)
- Internationalization (single-user, no i18n)
- Advanced accessibility (basic ARIA yes, but not screen reader optimized)
- RRF as alternative to weighted sum (backend, deferred from previous phase)
- Cross-encoder reranking (backend)
- Cognitive Semantics Specification document (documentation, conceptual prerequisite but does not block construction)
- Explicit agent feedback (tool marcar_util — backend future phase debt)

---

## 4. Success criteria (verifiable)

- CE-1: `npm run build` generates installable .exe via electron-builder. the platform owner installs it on Windows 11.
- CE-2: App opens, requests PIN, verifies against API, shows Command Center with stats + attention inbox.
- CE-3: Command Center shows pending items (contradictions, aliases, stale, duplicates) in real-time via SSE.
- CE-4: Knowledge Explorer: search memory → view detail → edit tags → save. Search document → view chunks → change trust tier.
- CE-5: Graph Studio: interactive Canvas graph with **300 nodes** + 800 edges → 30+ FPS ([research] the design lead M3 — aligned with CE-18). Zoom, click node → side panel. Colors by type.
- CE-6: Ontology Console: view candidate aliases → approve/reject. View predicates → view states. Entity merge from UI.
- CE-7: Decisions inbox: view contradiction → resolve (discard/confirm). View candidate alias → approve.
- CE-8: Ingestion: view queue in real-time. Failed document → click re-index.
- CE-9: Templates: create meeting with guided form → memory type 'acuerdo' created with correct tags.
- CE-10: Cmd+K from any screen → GAMR search → click result → navigates to detail.
- CE-11: System Monitor: live metrics (GPU, queue, throughput) visible as ambient bar.
- CE-12: API unavailable → error screen with diagnostics + retry. Cached data via `persistQueryClient` + `electron-store` ([research] the design lead M4). Persist: stats, inbox summary, last Explorer view. TTL 24h. Do not persist: System Monitor metrics, SSE events.
- CE-13: SSE: create memory via MCP → appears in Knowledge Explorer without refreshing.
- CE-14: Minimum window 1280x720. Functional layout without horizontal scroll at 1920x1080.
- CE-15: PIN auth: 8+ chars alphanumeric, validated in backend. Incorrect PIN 5 times → lockout. Change PIN from Settings requires current PIN.
- CE-16: SSE heartbeat: 60s without keepalive → "Disconnected" banner. Reconnection → automatic invalidateQueries().
- CE-17: Attention inbox: counters per decision class loaded in <200ms (1 min cache). Paginated detail on demand.
- CE-18: Graph Studio: 300 nodes + 800 edges on Canvas → 30+ FPS interactive. Server-side clusters visible on zoom out.
- CE-19: Templates: meeting form → editable markdown preview → detected entities visible → save → memory type acuerdo with metadata source:"template:reunion".
- CE-20: Decisions split view: click item → side panel shows complete context without navigating away. "Why surfaced?" visible.
- CE-21: Electron security: nodeIntegration=false, contextIsolation=true verified. Renderer CANNOT access fs/child_process.
- CE-22: JWT expires after 4h → app requests PIN again. Token only in memory — closing app = token lost.
- CE-23: PIN recovery: create PIN → recovery_key generated. Use recovery_key → PIN reset → new PIN established.
- CE-24: attention-inbox/summary does NOT include system_health. Only 4 cognitive classes.
- CE-25: alias rejected in Ontology Console → new document with same entity → candidate is NOT re-proposed.
- CE-26: GET /graph/clusters responds <200ms (cache). Clusters >2h → "outdated" visual indicator.

---

## 5. Explicit debt

- **Google OAuth**: local PIN is sufficient for localhost single-tenant. OAuth needed when EcoDB lives on VPS (future phase).
- **WebGL 3D graph**: Canvas 2D handles 500+ nodes. 3D if immersion is needed.
- **Code signing**: without signature, Windows Defender may block .exe. Future phase.
- **Quiet modes**: focus mode that reduces irrelevant noise. Deferred but valuable.
- **Investigation workspace**: stateful space for complex multi-entity governance. Future phase.
- **Cognitive quality metrics**: auto-link approval rate, alias approval rate, retrieval clicks top-1. Future phase with explicit feedback.
- **Auto-update**: manual installation in this phase. electron-updater in future phase if needed.
- **Frontend testing**: **Vitest for data transformation logic** (score formatting, inbox categorization, event digest, colors by type) ([research] the design lead M5). No component tests or E2E day 1.
- **Finalized visual identity**: the design lead iterates during construction. No pre-approved mockups — the platform owner approves iterations in-situ.
- **Offline mode**: no real offline support. Only cache of last known state. If API goes down, dashboard is read-only over cache.

---

## 6. Questions the Adversarial should ask

1. **PIN storage security**: OS keychain (safeStorage) is secure, but if someone has physical access to the platform owner's PC, the PIN is trivially brute-forceable (4-6 digits). Is this acceptable single-tenant?
2. **TanStack Query cache invalidation**: if SSE briefly loses connection, are invalidations lost? Is there reconciliation on reconnect?
3. **D3 performance**: force-directed with 200 nodes + physics + animations in SVG inside Electron. Is there a benchmark? Does the Electron renderer (Chromium) handle this well?
4. **Attention inbox endpoint**: aggregating N queries in a single endpoint can be slow if each query is expensive. Is it cached? Refresh rate?
5. **Memory templates**: templates generate memories via POST /memories. Do they go through GLiNER/entity extraction? Or are they "raw" memories?
6. **electron-builder on Windows**: code signing? Without signature, Windows Defender may block the .exe.
7. **App size**: Electron (~150 MB) + React + D3 + dependencies. Estimated final installer size?
8. **Node/Electron versions**: pinned? Electron evolves fast, old versions have vulnerabilities.
9. **Graph Studio semantic zoom**: zoom out = clusters. How are clusters calculated? Server-side or client-side? With what algorithm?
10. **Templates as forms**: is the generated content editable before saving? Or do they save directly?
