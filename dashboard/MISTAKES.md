# MISTAKES — EcoDB Dashboard

Running log of what broke during implementation, the real cause, and the fix.
Lienzo mines this for rules. One entry per real failure.

---

## FB1 — Scaffold + token port (2026-06-01)

### 1. `tsc --noEmit` failed with TS6306 / TS6310 (project references)
- **Symptom**: `npm run build` failed — `Referenced project 'tsconfig.node.json'
  must have setting "composite": true` and `may not disable emit`.
- **Real cause**: the root `tsconfig.json` listed `tsconfig.node.json` under
  `references`. TypeScript project references require the referenced project to
  be `composite: true` and emit-capable, which conflicts with a plain
  `tsc --noEmit` typecheck. The Vite starter shape assumes `tsc -b` (build
  mode); I was running `tsc --noEmit`.
- **Fix**: removed `references` from `tsconfig.json`. `tsc --noEmit` now
  typechecks `src/` only; `vite.config.ts` / `tailwind.config.ts` are validated
  by Vite/esbuild at load time, which is sufficient. `tsconfig.node.json` stays
  for editor support but is no longer referenced.

### 2. Console error: 404 on `/favicon.ico`
- **Symptom**: renderer console showed 1 error — `Failed to load resource: 404
  (favicon.ico)`. Fails the "clean console" criterion even though it is cosmetic.
- **Real cause**: `index.html` declared no icon, so the browser auto-requested
  `/favicon.ico`, which does not exist.
- **Fix**: added an inline SVG data-URI favicon (the brand accent dot, `#F5631E`)
  in `index.html`. No external asset, no extra request, on-brand. The real app
  icon (`.ico` for electron-builder) is still pending from Lienzo (FB2+).

---

## Gotchas worth remembering (not failures, but cost thought)

- **Sandboxed preload must be CommonJS.** Spec §4 requires `sandbox: true`, and
  a sandboxed Electron preload cannot be an ES module. `vite-plugin-electron`
  defaults preload to `.mjs`, which would silently fail under sandbox. Forced
  preload output to `format: 'cjs'` + `entryFileNames: 'preload.js'` in
  `vite.config.ts`. Verified in the built bundle: `require("electron")`, not
  `import`.
- **Electron dev shows an "Insecure Content-Security-Policy" warning.** Expected
  in FB1 — the CSP session header is FB2 (task 6.3). The warning is dev-only
  ("will not show up once the app is packaged") and is a *warning*, not an error.
  Do NOT add a static strict CSP `<meta>` to kill it: it would break `vite` dev
  HMR (needs `unsafe-eval` + ws `connect-src`). The correct fix is a dev-vs-prod
  session header in FB2.

---

## FB2 — Shell + security hardening + bridge (2026-06-01)

### 3. Prod CSP refused the (vite-inlined) `data:` fonts
- **Symptom**: under the prod CSP, the Electron renderer logged many
  `Refused to load the font 'data:font/woff2;base64,…' because it violates
  "default-src 'self'"`. Fonts silently fell back to system fonts.
- **Real cause**: the exact Spec §4 CSP has no `font-src`, so fonts fall back to
  `default-src 'self'`. Vite inlines assets below `assetsInlineLimit` (4 KB
  default) as `data:` URIs — several font subset files got inlined, and `data:`
  is not `'self'`.
- **Fix**: `build.assetsInlineLimit: 0` in `vite.config.ts` → every font emits
  as a same-origin file, covered by `'self'`. The CSP stays EXACTLY per Spec §4
  (no font-src added — the asset pipeline was wrong, not the policy).
- **Caught by**: running the built app under the *prod* CSP (file://) and
  grepping the renderer console — not visible in dev (dev CSP is permissive).

### 4. `vitest/config` in `vite.config.ts` → duplicate-vite type clash
- **Symptom**: once the build typechecked the config files (BC1), TS errored
  with `Type 'Plugin<any>' is not assignable…` between
  `vitest/node_modules/vite` and the hoisted `vite`.
- **Real cause**: importing `defineConfig` from `vitest/config` pulls vitest's
  bundled vite types, which conflict with the electron plugin typed against the
  hoisted vite.
- **Fix**: `vite.config.ts` uses `defineConfig` from `vite`; the Vitest `test`
  block moved to a standalone `vitest.config.ts` (no plugins → no clash).

### 5. `process.env.APP_ROOT` is `string | undefined` inside nested functions
- **Symptom**: TS2345 at the `BrowserWindow` `icon:` — `string | undefined` not
  assignable to `string`, even though it was assigned at module top.
- **Real cause**: assignment-narrowing (`process.env.APP_ROOT = …`) holds only
  in the same scope; it does not carry into a nested function body.
- **Fix**: a module-level `const APP_ROOT = path.join(__dirname, '..')` used
  everywhere (and mirrored into `process.env.APP_ROOT`).

### Decision (not a failure): electron-store stayed at @8.2.0, not @10
- @10 is ESM-only and cannot be `require()`d by the CJS main process (CJS is
  required because the sandboxed preload must be CJS). @8.2.0 is CJS and works.
- Security is identical either way: the key is encrypted with **manual
  `safeStorage`** (`encryptString`/`decryptString`), the store has **no
  `encryptionKey`** option (a static bundle key would be false security), the
  decrypted key never leaves main and is never logged.

### 6. FOUC fix shipped UNWIRED — script created but never referenced
- **Symptom**: the FB2 report claimed the FOUC fix was verified. Lienzo found
  `index.html` referenced only the module, never `theme-init.js`. The pre-paint
  script never ran.
- **Real cause**: `public/theme-init.js` was created but the
  `<script src="./theme-init.js">` was never added to `index.html`. The
  verification was **fooled**: App's `useEffect` sets `data-theme` *post-paint*
  from the same store, producing the identical visible result (dark), so the
  screenshot looked correct even though the pre-paint script was absent.
- **Lesson**: a downstream effect that produces the same *visible* outcome can
  mask a missing fix. Verify the **mechanism** (script present in the built
  `index.html`, loads 200, executes), not just the visible end state.
- **Fix**: added the blocking classic `<script src="./theme-init.js">` in
  `<head>` (before the module). Verified: present in `dist/index.html`, fetches
  200, reads the persisted store, applies the theme on load. Also set
  `<html lang="en">` (was `es`) and sync it from i18n on `languageChanged`.

### 7. SSRF in the fetch/sse bridge — URL built by string concatenation
- **Symptom**: adv-seg + verificador flagged HIGH. `fetch(API_BASE + args.path)`
  with a renderer-supplied path like `@evil.com/steal` produces
  `http://localhost:8080@evil.com/steal`, whose host (per the WHATWG parser) is
  `evil.com` — the `Authorization: Bearer <key>` header would be sent there.
- **Real cause**: building a URL by concatenating a trusted base with untrusted
  input. The `@` lands in the authority and redirects the host. `startsWith('/')`
  alone also misses `//evil.com` and `/\evil.com`.
- **Fix**: `resolveApiUrl()` — `new URL(path, API_BASE)` + require
  `path.startsWith('/')` + `url.origin === API_ORIGIN`. Rejects `@host`,
  `//host`, `/\host`, and absolute off-origin URLs. Applied to both
  `ecodb:fetch` and `ecodb:sse:start`. Unit-tested (`api-url.test.ts`, 5 cases)
  and runtime-verified (`@evil.com` → 400 `invalid_path`).
- **Lesson**: never build a request URL from a trusted base + untrusted string by
  concatenation. Resolve with the `URL` constructor and verify the origin.

### Decision (not a failure): query cache persists to plain localStorage
- FB10 persists the TanStack query cache with `createSyncStoragePersister` over
  `window.localStorage` (key `ecodb-qc-cache`), NOT electron-store — the renderer
  can't reach electron-store and a kv bridge would add IPC surface.
- The cache holds non-sensitive read views only (stats, inbox summary, last
  search / recent memories) via a `shouldDehydrateQuery` allowlist; auth/me,
  inbox details and graph are excluded. The **API key is never a query result**
  (it lives in safeStorage), so it never reaches the cache.
- Accepted risk: vault data (stats/inbox/search) sits in plain localStorage.
  Mitigated by devTools being off in prod. If adv-seg objects, the fallback is
  to encrypt the persisted blob or move it behind the bridge.

---

## FB-CMDK — Command palette / ⌘K (2026-06-02)

### No build/runtime failures — went clean on the first pass
- Reused established patterns: focus-trap + restore from `MemoryDrawer`, the
  `searchToRow` mapping from `KnowledgeExplorer`, and the `useSearch` hook
  (passed `limit: 8` to override its default 20 — the spread order in the hook
  puts `params` last, so the override lands).
- Combobox a11y done properly: input `role="combobox"` +
  `aria-activedescendant` pointing at the selected `role="option"` row inside a
  `role="listbox"`. ↑↓ moves selection (wrap), `aria-activedescendant` follows;
  Enter activates; Esc closes. Verified in the browser, not just by reading.

### Gotcha worth remembering: focus-restore target depends on the trigger
- During verification, opening the palette via ⌘K right after closing the drawer
  restored focus to `<body>`, not the AppBar field. **Not a bug**: the palette
  restores focus to whatever was focused when it opened (its trigger). In that
  test sequence the trigger genuinely was `<body>` because the just-closed
  drawer's own restore had no valid target (its trigger row no longer existed).
  Clean path verified separately: focus the AppBar field → ⌘K → Esc returns
  focus to the AppBar field. Lesson for testing modals: control what holds focus
  *before* you open, or you'll misread the restore target.

### Reminder (carried from Settings): the web-preview bridge mock body is an OBJECT
- The Playwright `window.ecodb` mock receives `opts.body` as a JS object; the
  real `main.ts` JSON-stringifies it. The palette only issues `POST /search`, so
  this didn't bite here, but the mock router still must not `JSON.parse` the body.

---

## Settings-fix + Cmd+K polish (2026-06-02)

### BC4 — optional chaining doesn't guard a chained promise method
- **Symptom (potential)**: `navigator.clipboard?.writeText(x).then(...)` throws
  `TypeError: ... .then is not a function` on a platform where
  `navigator.clipboard` is undefined.
- **Real cause**: `?.` short-circuits the *whole* call to `undefined`, but the
  following `.then(...)` is then invoked on that `undefined`. Optional chaining
  only protects the access immediately to its left, not the next link.
- **Fix**: chain the optional through every hop —
  `navigator.clipboard?.writeText(x)?.then(...)?.catch(...)`. Same for the
  dismiss handler's `writeText('')?.catch(...)`.

### IC1 — the ⌘ badge was a macOS symbol on a Windows target
- **Symptom**: the AppBar / hero search "⌘K" badge shows the Cmd glyph, but the
  app ships as a Windows `.exe` (Electron) where the modifier is Ctrl.
- **Fix**: `lib/platform.ts` derives the badge from `navigator.platform`
  (`/mac/i` → `⌘K`, else `Ctrl K`). Verified at runtime: `navigator.platform`
  is `Win32` → badge reads `Ctrl K`. The global listener already accepted both
  `metaKey || ctrlKey`, so only the label was wrong.

### BC1 — disabled affordances must not look interactive
- Feature-flag toggles had no write endpoint yet, so toggling persisted nothing
  while *looking* like it saved. Made them `disabled` + a "Requires backend"
  tooltip — same rule already applied to the Drawer's edit/bin and the key
  revoke button. A control that can't do anything must look like it can't.

### BC2 — the bridge mock body is an object (reconfirmed)
- The Settings delete-confirm and the api-keys 403 paths were verified with the
  Playwright `window.ecodb` mock. Reminder still applies: the mock receives
  `opts.body` as a JS object (the real `main.ts` stringifies it), so the mock
  router reads `opts.body.name` directly — never `JSON.parse`.

---

## FB-DEC — Decisions Inbox (2026-06-02, Beta opens)

### No failures — clean first pass. One gate decision + one test gotcha.

### Gate: resolve/dismiss/defer have NO REST endpoint
- The backend guide (DASHBOARD_BACKEND_GUIDE.md) lists only two attention-inbox
  routes: `GET /admin/attention-inbox/summary` and
  `GET /admin/attention-inbox/details`. The MCP `review_alias_candidate` /
  `confirm_document_relation` are MCP tools, not REST. So the read path (list +
  why-surfaced context) works; the write actions do not.
- Decision (per Lienzo's brief): render Resolve / Defer / Dismiss **disabled** +
  "Requires backend" tooltip — same rule as the Drawer's edit/bin, the flags,
  and key revoke. Flagged to Hilo (via Lienzo) so a REST action endpoint can be
  added. A button that can't act must look like it can't.

### Test gotcha: innerText returns CSS-transformed text
- A Playwright check for `'Why surfaced?'` failed even though the label rendered.
  Cause: the label uses `uppercase` (CSS `text-transform`), and
  `element.innerText` returns the *rendered* (uppercased) text — `WHY SURFACED?`.
  `textContent` would return the original casing. Lesson: assert against
  `textContent` for case-sensitive checks, or match case-insensitively, when the
  element is styled `uppercase`/`lowercase`/`capitalize`.

### Selection without an effect
- The detail panel auto-selects the first item with a pure derive —
  `items.find(i => i.id === selectedId) ?? items[0] ?? null` — instead of a
  `useEffect` that calls `setState` on data load. No effect, no extra render, and
  it naturally re-falls-back when the class/page changes and the old id is gone.

---

## FB-ONT Ontology Console + Decisions-fix (2026-06-02)

### Gate: merge/alias/retype have NO REST endpoint
- `/admin/graph-vocabulary` (entities + predicates) and `/admin/entity-dictionary`
  are GETs; the mutations `merge_entities` / `review_alias_candidate` are MCP
  tools, not REST. So the Ontology Console reads/lists vocabulary fully, but
  Merge / Alias / Retype render disabled + "Requires backend". Flagged to Hilo.
- The Console is the *rich* ontology view (vocabulary by type, dictionary/stop
  cross-reference, predicate catalog). The basic entity-dictionary CRUD stays in
  Settings — not duplicated here, just the same data read differently.

### Gotcha: a 403 doesn't surface when react-query has stale cached data
- Testing the "non-admin → limitedAccess" path by flipping the mock to 403 and
  *remounting* did NOT show the limited state. Cause: TanStack Query keeps the
  previously cached (success) data and a background-refetch failure does not flip
  the observer into the error branch while stale data is present — so
  `error`/`isError` don't drive `is403`.
- The real scenario is a **fresh** load with no prior cache: a non-admin's first
  `/admin/*` fetch 403s with no cached data → error state → `is403` true →
  limitedAccess. Verified two correct ways: (1) Decisions — click a class tab
  whose details were *never* cached → fresh 403 → limited; (2) Ontology — point
  `/auth/me` at a non-admin so `isAdmin` is false → the StateWrap gate renders
  limited without needing the query at all.
- Lesson for verifying error/empty states under react-query: don't mutate a
  server mock *after* a success is cached and expect a remount to surface it —
  exercise an un-cached key, or clear the cache (sign out), or drive the gate
  via a different signal.

### a11y: toggle vs. single-select semantics (Decisions adv-code IC2)
- ClassTabs and result rows were `aria-pressed` (button-toggle semantics). For a
  single-select group a screen reader should hear tab/option semantics: tabs →
  `role="tablist"` + `role="tab"` + `aria-selected`; the row list →
  `role="listbox"` + `role="option"` + `aria-selected`. `aria-pressed` is for
  independent toggles, not mutually-exclusive selection.

---

## FB-ING Ingestion + Ontology-fix (2026-06-02)

### Clean first pass. Gate + one verification trick worth recording.

### Gate: re-index / unlink / trust-tier have NO REST endpoint
- The queue is fed by the live document SSE events (document_indexed /
  document_failed / duplicate_detected). The per-document actions
  `reindex_document` / `unlink_document` are MCP tools — no REST — so Re-index /
  Unlink / Trust-tier render disabled + "Requires backend". Flagged to Hilo.
- There's also no historical doc-list endpoint, so the queue is **live-only**:
  events that arrive while the app is open. The empty state says so explicitly
  instead of pretending a backlog will load.

### useSSE feeds a second ring-buffer store
- `useSSE` already pushed event *names* to the activity store; it dropped the
  event *data*. Ingestion needs the document payload, so the handler now also
  parses `ev.data` and feeds `useIngestionStore` for the 3 doc events. One
  surgical block; the digest/activity behavior is untouched.
- `useSSE()` lives in App.tsx's `Authed` component (mounts only when
  authenticated), so the SSE subscription happens *after* the bridge exists.
  That matters for the web-preview verification.

### Verification trick: emit SSE events through the mock bridge
- The web-preview `window.ecodb` mock's `sse(path, onEvent)` captures `onEvent`
  into `window.__sseEmit` and returns a no-op unsub. Because `Authed` mounts
  post-auth, the real `useSSE` subscribes against the mock — so calling
  `window.__sseEmit({ event, data })` drives the live queue exactly like the
  server would. Verified: 4 emitted events → 4 newest-first rows, counts
  incremented, `heartbeat` ignored.

### react-query: disabled query stays `pending` — gate the UI before the skeleton
- IC1 added `enabled: isAdmin` to the 3 admin hooks so a non-admin doesn't fire
  3 pointless 403s. A disabled query reports `isPending: true` (fetchStatus
  idle), so the Ontology `StateWrap` must check `!isAdmin` *before* the
  `isPending` branch — otherwise a non-admin would see a stuck skeleton instead
  of the access note. (It already did; worth remembering when ordering states.)

---

## BUG-1 (blocker) + Ingestion-fix + FB-TPL Templates (2026-06-02)

### BUG-1 A: `?? []` does NOT guard a non-array
- `(query.data ?? []).map(...)` crashes if `data` is a truthy non-array (a
  backend error object, a wrapped payload). `??` only catches null/undefined.
- Fix: `lib/asArray.ts` — `asArray<T>(v) = Array.isArray(v) ? v : []` — applied to
  every list rendered straight from a response (api-keys, entity-dictionary,
  stop-entities, graph-vocabulary entities/predicates, inbox details, search
  results, recent memories, palette results, drawer trust-warnings). Verified:
  Settings with a non-array `/auth/api-keys` → empty list, no crash.

### BUG-1 B: ErrorBoundary is the safety net for field-level type violations
- A class `ErrorBoundary` wraps the AppShell view router with `key={view}` so a
  crashing screen shows a glass "Something went wrong" + Reload instead of a
  blank app, and navigating away (key change) remounts/resets it.
- Verified by forcing a real throw: a predicate with `description: null` makes
  `p.description.toLowerCase()` throw during render → boundary caught it, nav
  stayed alive, nav-away recovered. NOTE: this proves the boundary also catches
  per-field type violations that `asArray` (array-shape only) doesn't — that's by
  design; we don't guard every field, the boundary is the backstop.
- The 1 console error during that test is the *deliberate* throw, not a feature
  bug. In production React does not log boundary-caught errors with a stack the
  way the raw TypeError surfaced here under the preview build.

### Cross-session bleed isn't just the query cache (Ingestion-fix BC1)
- The signOut subscriber cleared queryClient + persister + palette, but the
  Zustand session stores (ingestion queue, activity ring buffer, open detail)
  would survive into the next login. Reset them in the same subscriber. Verified:
  emit events → counts > 0 → signOut → re-auth → queue empty, counts 0.

### Templates: assemble → preview → edit → re-preview → create
- The modal builds `content` from guided fields, runs `POST /memories/preview`
  (GLiNER), shows entities + suggested_triples, lets you edit the content
  (dirty → "Re-preview"), then `POST /memories`. 429 reads `Retry-After`
  (ApiError.retryAfter → "try again in Ns"); 422 → validation message. Real
  endpoints, so nothing disabled. Numeric ids from SSE are `String()`-coerced.

---

## FB-SYS System Monitor + Templates-fix (2026-06-02) — Beta closes

### System Monitor: ambient bottom bar, not a nav view
- Mounted in AppShell at the bottom of the workzone column (flex-none), below
  <main>. Collapsed = thin handle strip (services + agents indicators);
  expanded = metric tiles. State `sysExpanded` in the view store, persisted
  alongside `density`.
- Real data: services (healthy/total) + db_size from /stats/system; active agents
  from /stats/agents — and it updates **live** because the event digest already
  invalidates ['stats','agents'] on agent_connected/disconnected (immediate
  policy). GPU / queue / throughput have no field yet → "—" (6.25b). Agent
  kill/restart have no REST endpoint → disabled.
- IC-2: the bar sits OUTSIDE the `key={view}` boundary (which only wraps <main>),
  so it gets its OWN `<ErrorBoundary fallback={null}>` — a throw in the ambient
  bar collapses silently instead of taking down the whole workzone column.
- BC-1: the "online" dot color must derive from `online.length`, not total
  `agents.length` — otherwise all-offline shows a green dot next to "0 agents".

### Templates-fix: don't repopulate content on re-preview (BC-1)
- `runPreview` originally `setContent(text)` on every success, including
  re-preview. If the user keeps typing while the re-preview request is in flight,
  the response overwrites their edits. Fix: a `populateContent` flag — true only
  on the first compose→preview, false on re-preview (which only updates the
  "previewed" snapshot used for the dirty check).
- AU-1: the Create button also disables while a re-preview is in flight
  (`preview.isPending`), so you can't create content the backend hasn't seen.
- L1: the suggested-triple predicate is a *detected* label (data), not a live
  signal — so it's neutral, not orange (design.md §1.3: orange = live signal only).

### Cross-session privacy, final sweep (VS-BC2a)
- The signOut subscriber now also `useViewStore.setState({ drawer: null,
  explorerSeed: null })` — the previous user's open drawer target and ⌘K Explorer
  seed are in-memory (not persisted) but would otherwise survive into the next
  login on a shared machine.

---

## FB-GRAPH1 Graph Studio base (2026-06-02, v1.0 opens)

### GlassCard's base `relative` overrode an `absolute` passed via className
- The node inspector was `<GlassCard className="absolute right-4 top-4 bottom-4 …">`.
  GlassCard's own base class is `glass-card relative …`, and Tailwind emits
  `relative` after `absolute` in the generated CSS, so `relative` won → the
  inspector rendered **in document flow** (measured x:244 y:750, below the graph)
  instead of floating right.
- Fix: wrap GlassCard in an absolutely-positioned div and let GlassCard fill it
  (`<div className="absolute right-4 top-4 bottom-4 w-[300px]"><GlassCard className="h-full …">`).
  Lesson: never override a component's own `position` utility by passing a
  conflicting one through `className` — wrap it instead. Caught it because the
  Playwright check measured the inspector's bounding rect, not just "is it in the DOM".

### Canvas can't read CSS vars — resolve once, never per frame
- `nodeCanvasObject`/`linkColor` run per node/link per frame; reading
  `getComputedStyle(...).getPropertyValue('--edge')` there would be catastrophic.
  Resolved `--edge`/`--node-hot` once via `useMemo` keyed on the theme; node TYPE
  colours are fixed hex (the graph screen is dark in both themes, so they don't
  change with the app theme).

### Perf confirmed on the real screen (with glow + labels)
- Re-measured at hop 3 (280 nodes) with labels rendering (zoomed past the 1.6
  threshold) + active zoom/pan: **p50 60 / min 59 FPS** — labels didn't degrade
  it (fewer nodes painted when zoomed). Full-graph view tracks the spike (~p50 56).
  Labels are gated above zoom 1.6 (spike caveat) and the glow follows the
  prototype recipe (radius 2.1×/3.2× core, restrained, crisp dot).

### Mock adapter, swap at 6.25b
- `useGraphMock(depth)` is a `useQuery` with a mock `queryFn` (350ms delay →
  exercises loading). At 6.25b swap the queryFn to `apiGet('/graph/subgraph')` +
  `/graph/clusters` merge; the `MockGraph` shape already matches the inspector
  (design.md §4 GraphNode + centrality/linkedMemories).

---

## GRAPH-WIRE — Graph Studio on the live API (2026-06-02)

### The backend guide was incomplete — the OpenAPI is the contract
- Real /graph/subgraph node = {id:<number>, name, type, degree} — NO cluster_id;
  type is the 12 domain categories (persona/concepto/tecnologia/agente_ia/…) and
  ~17% are **null** → a fallback colour is mandatory, not optional.
- /graph/clusters is EMPTY (Louvain not computed, no trigger endpoint) → cluster
  colouring/legend/last_computed were dropped (Pepe's call: clusters are a
  pseudo-feature). Colour-by-type is the primary view.
- /api/v1/stats/graph is {nodes_total, triples_total, daily[]} (NOT nodes/triples)
  — the CC graph card needs remapping (P1).

### CORS blocks the web preview from the live API
- ECODB_CORS_ORIGINS = :8080,:8091 only. The web preview (:4173) can't fetch
  :8080 directly. The real Electron app is fine (request goes through the main
  process — no CORS). To smoke-test the wiring I curled the real shape, then drove
  a **real-shaped** mock (numeric ids, the 12 types incl. null, predicate edges,
  truncated case) through the Playwright bridge. The live numbers (1409 nodes;
  EcoDB depth-2 = 365 nodes / 2375 edges) come from curl with the .env key.

### The inspector must FOLLOW the focal node, not be cleared on re-center
- Click = re-center (new /graph/subgraph?center=node). The dataset-change effect
  was `setSelected(null)`, so the inspector flashed and vanished. Fix: a one-shot
  effect auto-selects the center node when its subgraph loads (`autoSelectedFor`
  ref guards it), so the inspector tracks the focal point through navigation.

---

## 6.25b real wiring — Decisions actions + New-memory create (2026-06-02)

### MemoryCreate requires workspace_id + project_id (the guide omitted them)
- POST /memories 422'd because the body lacked workspace_id/project_id (both
  required; content_type/visibility have defaults). Fix: useCreateMemory defaults
  `{workspace_id: 1, project_id: 1, content_type: 'text', ...body}` — the
  general/system pair the MCP save_memory uses, so dashboard memories land with
  the agents'. Verified live: 201 + the created memory.

### Surface FastAPI 422 detail, don't hide it
- `ApiError` now carries the parsed error `body` (main.ts already returns it in
  `res.data` for any status). For 422, errMsg reads `body.detail[].loc/.msg` and
  shows "field: message" instead of a generic line — the next schema mismatch is
  visible, not swallowed. Applied in both the Templates modal and Decisions.

### The alias-candidate inbox class has its own endpoint + shape
- pending_alias_candidates is NOT the generic inbox item. Use
  GET /admin/alias-candidates (bare list of {id, source_name, target_node_name,
  confidence, occurrences, status}) for the tab, and PUT
  /admin/alias-candidates/{id} {status:'approved', merge:true} (approve) /
  {status:'rejected'} (reject). The list has no offset → no pagination for that
  tab. stale_memories uses PUT /memories/{id}/staleness (active/dormant/archived).
- unconfirmed_relations + low_trust_documents are EMPTY live, and their actions
  need fields the generic inbox item doesn't carry (source_id/target_id;
  document_id + trust_tier) — left structured/disabled, flagged for when they
  have items and the list endpoint/shape can be verified.

---

## CC stat cards + Knowledge Health real shapes + Decisions/Templates hardening (2026-06-02)

### Several /api/v1/stats/* shapes differ from the dashboard types
- graph: {nodes_total, triples_total, daily[]} (NOT nodes/triples/predicates).
- memories: {data:[{label,count}], total} (NO `today`). Card now shows total +
  the top type as sub.
- agents: {period, agents:[{identifier, memories_created, searches,
  last_activity}]} — NOT a bare list. Card/SystemMonitor read `.agents`;
  "active" = last_activity != null (no `status` field).
- search: {total_queries, p95_latency_ms (null when 0 queries), ...} — show
  "No searches in 7d" when total_queries===0 instead of a bare "—".
- knowledge: {entity_count, orphan_entity_count, stale_memory_count,
  dormant_memory_count, duplicate_candidate_count, graph_density,
  top_entities_by_degree[{id,name,type,degree}]} — Knowledge Health rebuilt
  around these.
- **system: {embeddings, db, media} — NO `services`.** StatusPill + SystemMonitor
  still target the old `{services, db_size_bytes}` shape → they show "—".
  FLAGGED for follow-up (needs a real mapping: embeddings.status / db counts).

### Destructive graph action needs a confirm (adv-seg VS-MERGE-M1)
- Alias Approve runs merge:true (entity merge in the graph — undo-merge to
  revert). Gated behind an explicit Confirm/Cancel showing "merges X → Y in the
  graph. Continue?". Reject (no merge) stays one-click. The confirm resets per
  item via a `key` on the detail.

### Templates: validate required fields before preview (adv-code BC-1)
- FieldDef.required was decorative. onPreview now checks every required field is
  non-empty and, if not, errors with the missing field names ("Required: …") and
  the labels show an asterisk. Closes the "what's wrong?" confusion on a 422.

---

## SYSTEM mapping — StatusPill + SystemMonitor (2026-06-02)

### 1. StatusPill/SystemMonitor targeted a `services`/`db_size_bytes` shape that doesn't exist
- **Symptom**: appbar pill + bottom-bar tiles showed "—" on every screen.
- **Real cause**: both targeted an invented `/stats/system = {services:{total,healthy}, db_size_bytes}`.
  The live shape (curl) is `{embeddings:{status,model_loaded,quantization,cpu_percent,vram_*},
  db:{memories_count,nodes_count,triples_count}, media:{files_count}}` — no `services`, no byte count.
- **Fix**: SystemStats retyped to the real shape. StatusPill dot now keys on
  `embeddings.status==='ok' && model_loaded` (green/amber/red), label Online/Degraded/Offline,
  no "X/Y services". Latency segment shown ONLY when `/stats/search.p95_latency_ms` is present
  (>0) — otherwise omitted, not a fake "—". SystemMonitor tiles = memories/nodes/triples
  (db), embeddings (status+quant), cpu_percent, media files_count. Dropped GPU/queue/throughput
  (no datum in this backend).

### 2. Agent "online" can't come from /stats/agents.last_activity
- **Symptom**: needed a live online roster; last_activity is a 7d-window timestamp, not a link state.
- **Real cause**: `last_activity` = last memory/search; an agent with a recent memory is NOT
  necessarily connected now. Driving the dot off it lies.
- **Fix**: new `stores/presence.ts` (useAgentPresence: Set<identifier>) fed by useSSE from
  `agent_connected`/`agent_disconnected` (parseAgentId tries agent_identifier/identifier/agent/name).
  Roster comes from /stats/agents; the green dot + the "N active" count come from presence only.
  Presence is reset on stream teardown/reconnect — never claim online without a live link.
  Verified: Prima has last_activity but renders OFFLINE; Eco/Hilo render ONLINE only after their
  SSE agent_connected fired. That divergence is the proof the wiring is correct.

### DEVIATION — removed the disabled Restart/Kill agent buttons
- The SystemMonitor agent row had permanently-disabled Restart/Kill placeholders (no REST
  endpoint exists). Lienzo's "real data" mapping didn't mention them; dropped them rather than
  ship dead UI. Flagged to Lienzo for veto. Unused i18n keys sys.restart/kill/requiresBackend +
  sys.metric.gpu/queue/throughput/services/db removed. → APPROVED by Lienzo (no dead UI without endpoint).

---

## GRAPH-PALETTE-FIX + StatusPill/adv-code LOW folds (2026-06-02)

### Palette + legend (GraphStudio)
- M1: agente_ia #F5631E → #D4723A. L1: metodologia #B57EDC → #C079E0 (both verified in the
  legend swatches at runtime: rgb(212,114,58) / rgb(192,121,224)).
- L3: legend was hard-capped at .slice(0,8) — silently hid types. Now caps at 12 rows: ≤12
  shows all, else top 11 + a "+N more" row. Verified: 13 distinct types (12 + ∅) → 11 rows +
  "+2 more".
- L2/AU-1: the reset-center control was a bare "↺" glyph (no a11y name). Replaced with an SVG
  + aria-label/title `t('gph.resetCenter',{center})`.
- IC-1 (inspector): relations used `key={i}` (index key → bad reconciliation on reorder). Now
  `key={predicate-other-i}` (content-composite + index tiebreaker). No dup-key warnings at runtime.
- IC-2 (types): removed the dead `clusters?` field from SubgraphResponse (clusters feature was
  DESCARTADO). NOTE: `useClusters`/`ClustersResponse`/`ClusterGroup` are now also dead — left in
  place (out of this brief's scope), flagged to Lienzo.

### Couldn't trigger node re-center headlessly to capture the reset button live
- **Symptom**: 4 approaches to click a graph node in the web preview all failed (random canvas
  clicks, wheel-zoom+click, tiny-graph re-inject blocked by RQ cache, React-fiber coord read).
- **Real cause**: react-force-graph (kapsule) appends its <canvas> imperatively OUTSIDE React's
  tree, so the canvas fiber has no graphData/instance to read node screen coords from; and node
  hit-radius at fit-zoom is ~5px so blind clicks miss. The reset button only shows when
  center≠default, which requires a node click.
- **Resolution**: reset button is source-verified + compiles against the typed i18n key; the
  glyph→SVG swap is purely presentational. Real Electron app handles node clicks normally.
  Lesson: for force-graph interaction tests, drive via the app's own handlers, not canvas pixels.

### StatusPill adv-visual LOWs (folded)
- L1: degraded dot '#c4a86a' hardcoded → var(--kind-agent). L3: "ms" suffix hardcoded →
  t('appbar.latency',{ms}) key "{{ms}}ms".
- L2: dots now glow ONLY in signal states (green/red); neutral "awaiting" dot is var(--ink-4)
  with no glow (convention: no-signal dots = ink-4, no glow).

### adv-code LOWs (folded)
- IC-1: eventDigest agent_connected/disconnected 'immediate' → 'debounce'. Dots come from the
  presence store (no query), so /stats/agents only refreshes the roster — debounce collapses a
  connect/disconnect burst into one refetch. Zero functional change to the dots.
- AU-1: commented the useSSE() call in Authed() — mounted once at shell level, no singleton
  guard, so a second mount would open a second SSE connection.

---

## 2ª ola #1 — EXP MemoryDrawer: edit / delete / cycle visibility (2026-06-02)

### Wired the three disabled drawer actions against the live contract
- Edit was a permanently-disabled placeholder. Now an inline edit mode (content textarea, type
  select over the 7 enum types, public/private toggle, tag chip editor) → PUT /memories/{id}.
- Bin → DELETE /memories/{id} behind an explicit confirm ("Delete this memory?" → Delete/Cancel).
- Visibility stat → clickable, cycles public↔private in one PUT {visibility}.

### Send only the changed fields, not the whole memory
- **Why it matters**: MemoryUpdate accepts a partial body; the backend leaves omitted fields
  untouched (verified live: PUT {visibility:'private'} on a memory left content/type/tags intact).
  Sending the full object on every edit would risk clobbering a field if the local copy were
  stale. saveEdit diffs draft vs original and sends ONLY changed keys; if nothing changed it
  just closes (no request). Verified at runtime: visibility-only edit → {visibility}, content-only
  edit → {content}.

### 422 detail surfaced (not a generic "couldn't update")
- errMsg() extracts FastAPI 422 detail (loc[-1] + msg). Live PUT {type:'not_a_type'} returns
  422 with the literal-enum error; rendered as "type: Input should be 'momento'…". On 422 the
  drawer stays in edit mode so the user can fix the field (verified).

### Verification approach
- Live curl smoke-test (create throwaway → partial PUT → GET-confirms-unchanged → 422 → DELETE
  204 → cleaned up) proved the contract. Playwright against a live-shaped mock that captures the
  PUT/DELETE bodies on window proved the UI diff + confirm gating + 422 rendering. Web preview
  can't hit :8080 (CORS) — curl (no CORS) is how we test the real endpoint.
- Removed orphaned i18n keys drawer.editSoon + drawer.requiresBackend (dead after wiring).

---

## Floating TopBar + StatusBar (2026-06-02)

### TopBar/StatusBar were full-bleed flex siblings with sharp corners
- **Symptom** (Pepe, live): the TopBar (SearchField) and bottom StatusBar had pico corners and
  touched the viewport edges + the content panel, breaking the floating-panel language the nav
  rail + cards already use.
- **Cause**: AppBar + SystemMonitor were edge-to-edge flex children of the right column (no
  margin, no radius). The nav rail floated via m-[14px] + rounded-xl, but the bars didn't.
- **Fix**: unified the gutter at the shell level — grid `p-[14px] gap-[14px]`, cols `222px 1fr`,
  right column `flex flex-col gap-[14px]`. Dropped the nav rail's own m-[14px] (grid handles it).
  AppBar + SystemMonitor → `rounded-xl` (--r-xl = 26, matches the rail) + full tray glass
  (--tray-bg + blur(22) saturate(1.3) + --tray-shadow) + overflow-hidden so the backdrop blur
  clips to the radius. SystemMonitor's old `0 -1px 0 hairline` separator → --tray-shadow.
- **Verified** (1440×900): nav/topbar/statusbar all inset 14px from the viewport, radius 26px;
  the "Settings" h1 now sits 26px below the floating TopBar (the gap-14 + main pt makes every
  view's title breathe — no overlap). Light + dark both clean (tray tokens have both variants).
- No overlap risk: the bars are flex SIBLINGS of the scroll <main>, not overlaid — the 14px gap
  separates them, content scrolls between. Kept main's px-6 to avoid reflowing 8 screens'
  card layouts (flagged to Lienzo as a deliberate scope decision).

### DON'T `taskkill //IM node.exe //F` to clean up zombie preview servers
- **What happened**: to kill leftover `vite preview` servers I ran `taskkill //IM node.exe //F`.
  It kills EVERY node.exe — which took down the node-based MCP servers (playwright, mcpvault,
  youtube all disconnected mid-session) and could disrupt OTHER agents' node MCP children too.
- **Lesson**: never kill by image name. Kill the specific process: `pkill -f "vite preview"`
  (POSIX) or by PID/port (`netstat -ano | findstr :4173` → `taskkill /PID <pid> /F`). The broad
  kill is a blast-radius mistake — exactly the kind of destructive shortcut to avoid.

---

## EXP MemoryDrawer — iteration 2 fix-list (2026-06-02)

### errMsg duplicated 3× → single lib/errMsg.ts (IC-1, closes VS-DRAW-L1)
- MemoryDrawer, TemplateModal and DecisionsInbox each had their own error→message mapper with
  drifting behavior (the drawer's even echoed a `detail` string for ANY status — info disclosure).
- Extracted `lib/errMsg(err, t, fallback)`: 429 → rate-limit msg (w/ Retry-After), 403 → forbidden,
  422 array → "field: msg", and CRUCIALLY a non-422 `detail` string is NEVER echoed (falls to the
  generic fallback) — closes the schema-hint leak (VS-DRAW-L1). Shared `errors.*` i18n keys. Also
  repaired the drawer's missing 429 handling (it previously fell straight to the generic message).
- Covered by a new vitest suite (errMsg.test.ts, 7 cases) since Playwright was down — the
  info-disclosure guard (422-string and 404-string both → fallback) is asserted there.

### VS-DRAW-M1 — one-click private→public was a data-exposure window
- cycleVisibility fired the PUT immediately; an accidental click on the visibility cell could
  expose a private memory org-wide before the user noticed. Now: exposing (→public) is gated by a
  confirm ("Make this memory public?" → Make public / Cancel, footer pattern shared with delete);
  hiding (→private) stays one-click (hiding never leaks). confirmPublic resets per memory.

### Other folds
- VS-DRAW-L2: assert id matches a UUID before the update/delete request (catches schema drift early).
- M2 [a11y]: the edit fields used `focus:ring-[var(--ring)]` — but `--ring` doesn't exist, so the
  ring never rendered. Switched to TemplateModal's focused-boxShadow pattern (accent inset + halo).
- M1/L1 visual: destructive/active surfaces are TINTS not solid fills — delete-confirm = red tint
  (was solid var(--red)); visibility toggle active = kind-memory tint (was solid orange, violated
  §1.3 "orange is signal-only").
- L2/L3: staleness value + type-select options now route through t() (drawer.staleness.*, drawer.type.*).
- BC-1: tag diff compares as a SET — reordering tags is no longer a phantom edit.
- DC-1: removed the dead `toast.undo` affordance entirely (store field + Toasts button + drawer.undo/
  restored keys). Nothing ever passed an undo callback, and there's no real restore — the button
  would have promised an undo that didn't exist.

### FLOAT follow-ups (adversarial-visual)
- FLOAT-M1 (SystemMonitor rounded-xl + overflow-hidden) was already applied in the floating pass.
- FLOAT-L1: AppBar py-3 → py-4 to match the nav rail's 16px vertical weight (removes the 4px asymmetry).

---

## Ingestion — historical list + chunks + reindex/delete (2026-06-02)

### Live SSE queue and the REST document list are DIFFERENT vocabularies — two sections, not one
- The SSE pipeline emits `document_indexed`/`document_failed`/`duplicate_detected`; GET /documents
  persists a `status` field whose live value is `"indexed"` (different words). A processing doc is
  NOT in GET /documents yet. So combining them into one list would HIDE in-flight docs until they
  finished — losing the "processing now" feedback. Structure is two sections: live SSE activity on
  top (transient), the indexed library (GET /documents) below (persistent, selectable). When an
  SSE doc finishes, eventDigest invalidates ['documents'] and it appears in the historical list.
- REST `status` has no declared enum (just `string`), only `"indexed"` observed live. Colored it
  with a loose `statusColor()` (substring match index/fail/dup/process) + an ink-3 fallback, so an
  unseen value still renders sensibly instead of breaking.

### trust_tier is write-only → kept OUT of Ingestion
- PUT /admin/documents/{id}/trust-tier sets a tier 0-3, but GET never returns it. A setter you
  can't read-back lies about state (user sets blind, can't tell the current tier). Per design call
  it lives in the Decisions Inbox (low_trust_documents, where a flagged item gives context), NOT in
  the general Ingestion view. The hook was deliberately not written.

### reindex / trust-tier responses are opaque
- PUT reindex and trust-tier return `{additionalProperties:true}` (no defined success shape).
  Treat HTTP 200 as success → toast + invalidate ['documents']. DELETE → 204 (no body).

### Verification (Playwright still down)
- Contract audited against the live OpenAPI; GET /documents + /{id}/chunks confirmed live (1 doc,
  status indexed, 82 chunks). Reindex/DELETE NOT run against the real production doc (destructive) —
  hooks + contract source/openapi-verified; full mutation runtime pass deferred to Playwright on a
  throwaway. Adding ['documents'] to the doc events required updating eventDigest.test.ts
  (document_failed now invalidates 2 keys, not 1).

---

## Ontology — merge / undo / alias review (2026-06-02)

### The vocabulary has no node ids, but merge/undo need them
- /admin/graph-vocabulary returns entities as {name, type} (601 of them) — NO node id. But
  POST /admin/merge-entities and /admin/undo-merge take INTEGER node ids. Bridge: GET /graph/search
  ?q=NAME (q≥3 chars) → { matches:[{id, name, similarity}] }. So the manual merge resolves both the
  source (the selected entity's name) and the target (picked from a search) to ids at confirm time.
  Live: q=Pepe → [{id:3, name:'Pepe', similarity:1.0}].
- Merge UX: Merge → search a target (shows similarity per match) → 2-step confirm "Merge X → Y?" →
  resolve ids → POST. Destructive but reversible: undo is CONTEXTUAL (stash the just-merged
  source_node_id → POST /admin/undo-merge). There's no merge-history endpoint, so a persistent/global
  undo is impossible — contextual is the honest affordance. The detail is keyed by entity so all
  merge/undo state resets when you select a different entity.

### Aliases is a second VIEW, not duplicated logic
- The new Aliases tab reuses the Decisions Inbox hooks verbatim (useAliasCandidates /
  useReviewAliasCandidate) — single source of truth. Ontology is the conceptual home of aliases;
  Decisions surfaces them as an inbox class. Approving with merge:true is gated behind a per-row
  confirm; reject is one-click.

### Contracts
- merge body {source_node_id:int>0, target_node_id:int>0, reason?} → opaque. undo {source_node_id}.
  alias PUT {status:'approved'|'rejected', merge?} → returns the candidate row. retype → NO endpoint
  exists, rendered disabled. Merge/undo NOT executed against real nodes (destructive) — contract +
  UI source-verified; runtime mutation pass deferred to Playwright on throwaway nodes.

---

## Ingestion fix-list + cross-screen folds (2026-06-02)

### An open detail panel went stale after an SSE event (BC-1)
- The doc SSE events invalidated ['documents'] (the list) but not ['document'] (the open detail +
  chunks). A detail panel left open would keep showing the pre-event state. Added ['document']
  (prefix-match covers ['document',id] + chunks) to all three doc events. Each addition shifts the
  eventDigest test key-counts — updated them (document_failed now invalidates 3 keys).

### Reindex needs a cooldown, not a confirm (VS-ING-L2)
- adv-seg flagged chained reindexes (the keyed remount resets `busy` across docs). A confirm would
  contradict the design (reindex = one-click terracotta). Resolution per Lienzo: a 6s cooldown
  after a successful reindex disables the button — keeps the one-click feel, blocks the pile-up.

### assertUuid was duplicated verbatim (DC-1)
- memory.ts and documents.ts each had their own UUID_RE + assertUuid. Extracted lib/assertUuid.ts;
  both import it.

### Other folds
- ING-H1 [HIGH]: dropped the DocRow active left side-stripe (anti-slop) — the tint already signals
  selection; bumped the tint 9%→12% to compensate.
- ING-M1: the initial Delete button used hardcoded rgba(222,70,48,…) → color-mix(var(--red)), matching
  the confirm button (theme-token consistent).
- ING-M2: {status} raw → displayStatus(s,t) — localizes known REST codes, falls back to the raw value
  for unseen ones (i18next defaultValue), since the status field has no declared enum.
- ING-L2: MetricTile big value → font-medium. ING-L3: detail-load error uses its own ing.loadFailed,
  not the mutation key.
- BH4 [verificador]: closing the drawer (scrim/Esc/✕) mid-edit with unsaved changes now routes through
  requestClose → a "Discard unsaved changes?" overlay. No changes → closes directly. Esc handler reads
  the latest requestClose via a ref so the effect doesn't churn on every keystroke.
- VS-TPL-ENUM [verificador, FIX A]: TemplateModal offered visibility 'workspace' but
  MemoryCreate.visibility (curl-confirmed) is only public/private → choosing it would 422. Removed
  'workspace' from the type + VIS array.

---

## Ontology fix-list (2026-06-02)

### A fuzzy fallback on a resolve-by-name merge = silent wrong-node corruption (VS-ONT-H1 / BC-1)
- doMerge resolved the source node id by name (via /graph/search) AFTER the user confirmed, and
  fell back to `?? src[0]?.id` if no exact match. If the entity's name didn't exactly match a search
  result (Unicode/normalization diff, a since-renamed node, a near-name ranking first), it would
  merge a DIFFERENT node than the confirm dialog showed — silently, and the graph corruption is
  hard to recover (the undo affordance is contextual and vanishes on navigation). Triple-flagged
  (adv-seg HIGH + adv-code + verificador). Fix: require EXACTLY ONE exact name match; 0 or >1 → abort
  with the noSource error. NEVER fall back to a fuzzy result. **Lesson: when you resolve an id by a
  human label for a destructive op, an ambiguous/missing match must abort, never guess.**

### The async resolve window let a double-click fire two merges (IC-1)
- The Confirm button was disabled on `merge.isPending`, but doMerge has an async phase (searchNodes)
  BEFORE the mutation starts where isPending is false — so a fast double-click fired doMerge twice.
  Fixed with a `submitting` flag set at the top of doMerge (guarded `if (submitting) return`) and
  cleared on settle, driving the button's disabled + a dedicated "Merging…" label.

### Other folds
- BC-2: merge/undo onSuccess now also invalidate ['inbox'] — a manual merge can resolve a pending
  alias candidate, so the Aliases tab must refresh.
- VS-ONT-L1: int>0 guard (assertNodeId) in the merge/undo hooks — the integer analogue of assertUuid.
- ONT-H1: dropped the entity-list active side-stripe (anti-slop, same as ING-H1) → 12% tint.
- ONT-M1: alias Approve (step 1) → terracotta primary (approve is the primary action). ONT-M2: merge
  search uses the shared SearchInput (correct focus ring; added an optional onKeyDown). ONT-L2:
  similarity shows a "sim" label. ONT-L3: alias confirm-merge got the missing ambient glow.
- VS-ONT-L2 (undo 1-click) + VS-ONT-L3 (reject 1-click): ACCEPTED per Lienzo — fast undo IS the
  recovery (a confirm would be counterproductive), and reject doesn't corrupt the graph + matches the
  Decisions pattern (approve = primary 2-step / reject = neutral 1-click).

---

## FB-GRAPH3 — canvas interaction (2026-06-02)

### Testing kapsule-canvas interactions: a DEV-only window hook beats pixel-clicks
- react-force-graph (kapsule) renders its <canvas> outside React's tree and hit-tests via an
  offscreen color buffer, so Playwright pixel-clicks on nodes are unreliable (proven repeatedly).
  The interaction LOGIC, though, is plain React state. Solution: expose a DEV-gated
  `window.__graph` (import.meta.env.DEV) with the same actions the handlers call — toggleSelect,
  selectVisible, openNodeMenu, expand, etc. The Playwright pass runs against `npm run dev` (DEV true)
  and drives the DOM overlays (context menu, selection box, merge confirm) through that hook; the
  production `preview`/packaged build never exposes it. The REAL canvas trigger (right-click → menu,
  shift-drag box) still needs human eyes — that's Pepe's manual check.

### Box-select vs the canvas's own pan: a Shift-gated overlay
- ForceGraph pans on background drag. To add a rubber-band box without fighting it, an absolute
  overlay sits over the canvas with `pointerEvents: shiftHeld ? 'auto' : 'none'`. While Shift is
  held the overlay intercepts all pointer events (box-select mode, pan disabled via
  enablePanInteraction={!shiftHeld}); otherwise it's transparent and the canvas works normally. A
  tiny drag (<4px) is treated as a Shift-click → toggle the nearest node (hit-tested by mapping each
  node's x/y through fgRef.graph2ScreenCoords). The ref methods ARE reachable (unlike reading node
  coords via the fiber, which failed) because we call them imperatively, not via React.

### Merge-from-here in the graph is safe (no VS-ONT-H1)
- Graph nodes carry integer ids directly, so merge uses node.id with no name→id resolution — the
  fuzzy-match corruption risk that hit the Ontology console doesn't exist here. Enabled only when
  the right-click source has exactly ONE other selected node (the target); 0 or >1 → disabled.

### Hop control capped at [1, 2]
- /graph/subgraph?depth=3 returns only the center node (0 edges) — but this is an INTENTIONAL
  backend 2-hop security cap, not a bug. The control is [1, 2]; FB-GRAPH4 will add a "Full graph"
  option instead of restoring 3.

### FB-GRAPH3 fix-list (4 reviews)
- VS-GSTUD-M1: GraphStudio had no admin gate — the merge-from-here item (a POST /admin/* action)
  was visible to non-admins. Now gated on isAdmin (useAuthMe) and hidden entirely for non-admins,
  matching OntologyConsole. Verified: non-admin sees only Inspect/Re-center/Expand.
- GPH3-M1: the multi-select ring can't be --sec-graph (#4E9E6A) — it collides with TYPE_COLOR.proyecto
  AND --grn, so the ring vanishes on a proyecto node. It also can't be white (= the focal ring).
  Chose ice-blue #a0c8ff: outside the 12-type palette, ≠ green, ≠ orange. A select-ring color must be
  distinct from every node fill AND the focal ring.
- IC-1: expandNeighbors appended neighbors unconditionally → `extra` grew N×k on repeat expands and the
  data useMemo re-processed ever-growing arrays. Now deduped against base + existing extra (Sets of
  node id / link key) + an in-flight guard. Verified: expand same node twice → 7 nodes, not 9.
- BC-1: Escape now closes the context-menu / merge confirm (was backdrop/action only).

### FB-ING3 close-out: openFile is path-only + real doc-type filters
- The native picker (main.ts ecodb:openFile) used to readFile(path,'utf8') and return the content.
  Tested on a 200KB binary: utf8 read does NOT throw — it returns a same-length garbage string. So
  it "handled clean", but with the dialog now filtering PDF/audio (large binaries), slurping a
  multi-MB file as a utf8 string and serializing it over IPC on every "Add document" is a UX-hang /
  memory hazard. Made openFile PATH-ONLY (no read; the backend ingests from the path). Dropped the
  now-unused readFile import + `content` from the bridge type — only consumer (FB-ING3) uses path.
- Dialog filters → Documents [pdf docx html htm md txt] + Audio [mp3 wav m4a ogg flac] + All. JSON
  removed as a featured type (it lands on the backend's weak _chunk_txt fallback).

## FB-GRAPH4

### Full graph (stage 2) is blocked — no endpoint
- There is NO full-graph endpoint: /graph/subgraph REQUIRES `center` (422 without), /graph/full and
  /graph/all are 404, /graph/clusters is empty (0 clusters computed). The whole graph is 1414 nodes
  / 3293 triples (/api/v1/stats/graph) — NOT 601 (that was the vocab entity_count). Faking "Full"
  client-side (aggregating subgraph calls from hubs) = N calls + incomplete + slow → not viable. And
  1414 nodes / 3293 edges on Canvas 2d is past the spike's comfortable ≥30 FPS → WebGL territory.
  Deferred: needs a backend endpoint (Hilo) + a Canvas→WebGL decision. Hop control stays [1, 2].

### Tune sliders (stage 3): re-apply forces on dataset change
- ForceGraph REBUILDS its d3 forces when graphData changes — so any imperative override
  (fgRef.d3Force('charge').strength(...), d3Force('link').distance(...)) is lost on a new subgraph.
  The apply effect therefore depends on [charge, linkDist, data] so it re-applies after every dataset
  swap, then d3ReheatSimulation(). node-size + label-zoom aren't forces — they're draw inputs
  (drawNode opts), so they only need the useCallback dep, not the reheat.
- The panel is collapsed by default (a "Tune" toggle) to avoid clutter on the viewport. nodeRelSize
  is ineffective here because we custom-draw via nodeCanvasObject, so "node size" is a multiplier on
  our nodeRadius (applied in both drawNode and nodePointerAreaPaint), not the nodeRelSize prop.

---

## FB-POLISH (specular bug + GRAPH4 review fold) — 2026-06-02

### GlassCard specular "flashlight" was permanently visible on every panel
- **Symptom**: the cursor-tracked specular highlight (§2.5) showed on all GlassCards even with no
  pointer over them, and was too intense (light theme washed out).
- **Real cause**: `.glass-card::before` packed BOTH the radial specular AND the static diagonal rim
  into one pseudo with a constant `opacity: 0.5`. With `--mx/--my` defaulting to 50%/0% (tokens.css),
  the radial painted at top-center with zero hover. Light `--card-spec` was `rgba(255,255,255,0.95)`.
- **Fix**: split into two pseudos — `::before` = static rim (always on), `::after` = radial specular,
  `opacity:0` at rest, CSS `:hover::after { opacity:0.25 }` with a 0.15s transition. Gate via `:hover`
  (no JS state needed; the existing pointermove handler only matters while hovered). Intensity halved
  (0.5→0.25). Added `@media (prefers-reduced-motion: reduce){ ::after{ transition:none } }`.

### "ink-3 over glass is safe" is FALSE for the nav TRAY (vs a card)
- **Symptom**: GRAPH4-C1 audit — most ink-3 body text passes AA, but the NavRail user email
  (text-ink-3, 9.5px) measured 4.34:1 in light theme → fails AA for small text.
- **Real cause**: the design assumption "ink-3 on glass = ~5.97:1" holds for a CARD (`--card-bg`
  ~0.74 alpha) but NOT for the TRAY (`--tray-bg` ~0.32 alpha). At the bottom of the screen the base
  backdrop is bd-3 (#d2cdc3, only 4.18:1 with ink-3), and the thin tray doesn't lighten it enough.
  The page subtitles pass only because they sit in the TOP bd-1↔bd-2 zone (~5.0:1).
- **Fix**: bumped that ONE component (NavRail email) text-ink-3 → text-ink-2 (→ 4.62:1). Token
  left untouched. Lesson: contrast over translucent glass depends on the panel's alpha AND the
  backdrop region underneath — measure the composited pixel, don't assume "on glass = safe".
