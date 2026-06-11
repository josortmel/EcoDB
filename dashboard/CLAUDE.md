# EcoDB Dashboard — guía del proyecto

Dashboard de escritorio (Electron + React + TypeScript) para **EcoDB**, la memoria unificada de Eco Consulting. GUI de búsqueda, gestión y gobernanza del conocimiento sobre el backend EcoDB. Construido con el workflow-frontend (Faro: Lienzo). Lenguaje visual **Liquid Glass**, portado del prototipo en `../design_system/`.

## Stack

React 18 · Vite 6 · TypeScript · Tailwind 3.4 · TanStack Query 5 · Zustand 5 · Electron 42 (Node 24, Chromium 148) · react-i18next · react-force-graph-2d · electron-store **@8.2.0** (NO v9 — ESM rompe el main CJS) · electron-builder 26.

## Comandos

```bash
npm run dev      # Electron + Vite dev (:5173) → backend en localhost:8080
npm run build    # vite build + tsc (renderer + electron)
npm run test     # vitest
npm run package  # electron-builder → release/*.exe (sin firmar)
```

**Typecheck — correr SIEMPRE LOS DOS** (el renderer NO cubre main.ts):
```bash
npx tsc -p tsconfig.json --noEmit           # renderer
npx tsc -p tsconfig.electron.json --noEmit  # main process (electron)
```
⚠ Saltarse el tsc electron deja pasar bugs en main.ts (ya ocurrió: un caller de `resolveApiUrl` con args incompletos compiló "verde" en el renderer y rompía el SSE).

## Arquitectura

- `src/main.ts` — Electron main: ventana, CSP, IPC bridge handlers (`ecodb:fetch/sse/uploadDocument/getConfig/setConfig/...`).
- `src/preload.ts` + `src/types/electron.d.ts` — el contrato `window.ecodb` (bridge).
- `src/secure-store.ts` — API key cifrada (safeStorage/DPAPI). `src/config-store.ts` — config no cifrada (URL base).
- `src/lib/` — api (wrapper bridge), api-url (`resolveApiUrl(path, base)` origin-check), sse, helpers (asArray/assertUuid/assertNodeId/errMsg/displayStatus).
- `src/hooks/` — TanStack Query por dominio (search/documents/stats/settings/inbox/ontology/auth + `useMemoryAgent` v1.3).
- `src/stores/` — Zustand (auth/view/detail/ingestion/toast/presence).
- `src/pages/` + `src/components/` — pantallas y UI. `src/locales/en.json` — i18n (EN ahora, ES drop-in; nombres de marca exentos de t()).
- `src/pages/MemoryAgentPage.tsx` + `src/components/memory-agent/` — **Memory Agent (v1.3)**, ver sección dedicada abajo.

## Memory Agent (v1.3 — metacognición)

Página standalone (9º item del nav, grupo Governance, icono Brain, color `--sec-memory-agent` #7a6bc7 índigo-violeta). 6 tabs (roving-tabindex APG, ←/→ nav): **Briefing** (default — foresights urgency-sorted + tensions observed/declared + telescopic preview), **Configs** (LLM providers collapsible + agentes expandibles → cell configs con cron-builder + trigger + prompt-template editor en drawer, Gate B3), **Clusters** (lista/search + drawer narrativa/members/sources telescópicos + approve/reject/narrate), **Foresights** (Gate F3 — vista per-agent: AgentSelect compartido + filtro status active/expired/dismissed + lista ForesightItem urgency-sorted, urgency como dot), **Skills** (Gate F3 — per-agent: AgentSelect + filtro active/stale/candidate/deprecated + lista SkillCard con barra success_rate + SkillDrawer steps/tools/failure_modes/checklist/source_cases + PUT status), **Telemetry** (cell runs table + health).

- **AgentSelect compartido** (Foresights + Skills): los endpoints `/foresights` y `/skills` EXIGEN `agent_identifier` → el estado del agente se eleva a `MemoryAgentPage` (se elige una vez, persiste entre ambas tabs). `AgentSelect` auto-selecciona el primer agente al cargar. `StatusChips` es el filtro tint-selected compartido por ambas vistas.
- **Data layer**: `src/hooks/useMemoryAgent.ts` — todos contra `/api/v1` (schema 5.3.0): briefing, cells/configs|templates|runs|health|trigger, clusters (list/detail/members/sources/search/telescopic/narrate/status), agents, providers, foresights (per-agent), skills (list/detail/status PUT, per-agent). `GET /cells/runs` devuelve `id` (NO `run_id`). El evento SSE de runs usa `run_id` en el payload (irrelevante — eventDigest invalida por nombre de evento). `GET /foresights` devuelve `ForesightItem[]` tipado (mismo wrap que briefing). Skill ids son UUID → `assertUuid`; numeric ids (templates) → `assertIntId` (`lib/assertUuid.ts`). Providers `api_key_masked` — la cleartext NUNCA vuelve del GET ni del POST.
- **SSE**: `cell.run.started|completed|failed` + `cluster.created` + `foresight.triggered` van por el `/events/stream` EXISTENTE (auth del bridge, sin endpoint nuevo) → registrados en `eventDigest.ts` (immediate/debounce). No hay EventSource nuevo.
- **Cron builder**: el usuario elige freq/día/hora; emite el cron string internamente, NUNCA expone "0 3 * * 0" (escape hatch "advanced" con regex guard `/^[\d\s*/,\-#]+$/`). El scheduler backend usa croniter (no shell) — VS_CF2 safe.
- **CronBuilder/provider model select**: nunca uses un separador compuesto con espacio (`'\0'`/`' '`) para encode provider+model → corrompe nombres con espacio. Selects independientes.

## Seguridad (NO regresar)

- **La API key NUNCA cruza al renderer.** El main la lee (`decryptApiKey`) solo para adjuntar `Authorization: Bearer` dentro de los handlers fetch/sse/upload.
- **`resolveApiUrl(path, base)`** valida que el path resuelva al origin configurado (anti SSRF/exfil del Bearer). Toda URL pasa por ahí.
- CSP exacta en prod (sin unsafe-eval), `connect-src` sigue la URL configurada. contextIsolation + sandbox + devTools:false en prod.
- Uploads: dialog + read + POST ocurren EN MAIN; el path del host nunca llega al renderer. Allowlist de extensión + cap de tamaño (100MB) en main. Filename escapado en el Content-Disposition.

## Gotchas críticos

- **Electron main `fetch` NO serializa un FormData/Blob global (undici)** → el part llega vacío. Para multipart, construir el body MANUAL como Buffer con boundary explícito (ver `ecodb:uploadDocument` en main.ts). El fetch JSON sí funciona (body string).
- **`app.setName('ecodb-dashboard')` al top de main.ts + stores LAZY** (Store creado en primera llamada, no en import). Si no, `app.getName()` varía entre arranques → userData distinto → la API key no persiste.
- **Patrón endpoint-availability:** acciones sin endpoint REST quedan DISABLED (no fake-success). El contrato REAL es `curl http://localhost:8080/openapi.json`, NO el backend guide (estaba incompleto).
- **i18n:** cero literales en JSX, todo por `t()`. Floor de texto **9.5px** (legibilidad = prioridad absoluta de Pepe).
- **Scroll en tabs con listas densas (cazado 3×):** un hijo flex de un root `flex flex-col overflow-y-auto` tiene `flex-shrink:1` por defecto → se comprime a la altura del root en vez de crecer, y el `overflow-hidden` del GlassCard clipa la lista → NO scrollea. Fix: `flex-none` en el hijo (GlassCard/Panel/grid). Aplicado en Configs, Clusters, Telemetry, Briefing; Foresights/Skills nacieron con él. El bug solo se ve en runtime con datos densos, no por lectura.

## Decisiones firmes (no re-litigar)

Prototipo (`../design_system/`) gobierna sobre design.md si difieren · CTA **terracota** (`--btn-primary`) ≠ naranja señal (`--accent` #F5631E, solo live/active/critical) · anti-slop: selección por **tint**, nunca side-stripe izquierdo · GlassCard con specular cursor-tracked (hover-gated) + lift hover -2px · §2.9 color por sección en el nav · clusters del grafo descartados · hop del grafo [1,2,Full] · ink-3 light #625c52 (WCAG-tuned, no tocar) · ingesta = multipart upload (el backend en Docker no ve paths del host).

**Regla WCAG signal-colors (DESIGN.md §1.3, cazada 3× en v1.3):** los signal colors (`--accent`, `--red`, `--grn`) Y los section accents de baja lightness (`--sec-memory-agent` #7a6bc7, L≈0.19) NO alcanzan 4.5:1 sobre fondo claro → SOLO como **dot/glow/border/tint**, NUNCA como fill de texto pequeño (<18px) en light. Estado/urgencia/error en texto = dot de color + texto ink-1/ink-2. Excepción: affordances de acción destructiva (botón reject/delete con red tint) no son indicadores.

## NO tocar

- `../api/`, `../mcp/`, `../sql/`, `../docker/` — backend (dominio de Hilo).
- El cifrado de `secure-store.ts` (safeStorage, sin encryptionKey, sin fallback plaintext).

## Contexto

Repo: el dashboard vive DENTRO del repo EcoDB (`../`). Spec+Plan, DESIGN.md y los informes de sesión están en el vault de Obsidian (Faro/). Backend por Hilo-DeepSeek.
