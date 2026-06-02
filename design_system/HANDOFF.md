# EcoDB Dashboard — Handoff (Design → Build)

**From:** Design (prototype + design system)
**To:** Engineering (Lienzo · frontend)
**One line:** *The design is done. Now we build the app.*

This document is the **bridge** between three things: (1) the design + prototype produced today, (2) the EcoDB system itself, and (3) **Prima's construction plan** (*EcoDB Dashboard — Spec + Plan v2*), which remains the authoritative build bible. Read this first, then build from Prima's plan using the prototype + design system as the visual/UX source of truth.

**Status at a glance**
- ✅ **Design** — complete (tokens, components, all 8 screens, light/dark). This package.
- ✅ **Backend** — complete (Hilo). All endpoints live; the frontend wires directly, no backend wait.
- ▶ **Frontend build** — the remaining work: port the prototype to the real stack and wire it to the live API (Prima's plan).

---

## TL;DR for the team

This package is the **visual + UX source of truth** for the EcoDB v1.0 Dashboard. Everything here is *design-final and interaction-final*, running on **mock data**. Your job (Phase 3) is to **wire it to the real EcoDB backend and ship it as the Electron app** — the look, the components and the flows are already decided, so you don't re-design, you re-implement.

**Open `EcoDB-Dashboard-prototype.html` (double-click) to see exactly what you're building.**

---

## What's in this box

| Folder / file | What it is | Use it to… |
|---|---|---|
| `EcoDB-Dashboard-prototype.html` | The full clickable prototype, one self-contained file (offline) | See & demo the target. 8 views, light/dark, real interactions on mock data |
| `design.md` | The design system (tokens, colors, type, rules, color-coded signal) | The single source of visual truth. Mirror these tokens in Tailwind |
| `component-kit/` | Every UI component in isolation, all states, documented | Reference for building each component (props + states + contracts) |
| `prototype-source/` | The prototype's raw source (HTML + CSS + JSX) | Lift markup, structure, exact styles and interaction logic |

> The prototype is **no-build** (React UMD + in-browser Babel) on purpose — it's a reference, not the shippable codebase. Phase 3 ports it to the real stack.

---

## The 8 views (all present in the prototype)

1. **Command Center** — operative home: stat cards, attention inbox (actionable), live activity feed, knowledge health, ingestion snapshot.
2. **Knowledge Explorer** — memories/documents tabs, GAMR search + filters, trust/visibility badges, row actions (edit, visibility, bin), memory drawer with 10-stage score breakdown.
3. **Decisions Inbox** — split view, "why surfaced?", resolve / dismiss / defer (alias candidates, contradictions, stale).
4. **Graph Studio** — Apache AGE graph, click-to-inspect node panel, Louvain cluster legend.
5. **Ingestion** — Docling queue, lifecycle status, re-index / unlink actions, metrics.
6. **Ontology Console** — entities (aliases, merge, stop, retype) + canonical predicates.
7. **Settings** — trust tiers, feature flags, entity dictionary CRUD, API-key management.
8. **Insights** — engine metrics (GAMR pipeline, Recall@5, latency) — kept aside, for presentations/launch reel, not daily work.

---

## Phase 3 — "make it functional" (the brief)

This follows the internal Spec+Plan (Prima, *EcoDB Dashboard — Spec + Plan v2*). Summary so the team can start:

### Stack (target)
`React + Vite + Tailwind + TanStack Query + Zustand + Electron`. Monorepo: `EcoDB/dashboard/`.

### Step 1 — tokens & components
- Port `design.md` tokens into `tailwind.config.ts` (CSS variables + a JSON mirror), light/dark themes.
- Rebuild each component from `component-kit/` as real React components (props/states already documented there). Keep: 3-layer depth, surgical orange, per-section color, DM Mono for data / Hanken Grotesk for copy.

### Step 2 — app shell & data layer (can start with mocks, in parallel with backend)
- Electron shell + security (`contextIsolation`, `sandbox`, CSP, preload bridge — API key never in the renderer).
- **API-key auth flow** (electron-store + safeStorage, auto-auth on launch, first-run diagnostic).
- TanStack Query wrappers + **SSE** (`/events/stream`) + Zustand stores + offline cache.

### Step 3 — wire the screens to real endpoints
Replace mock data with the real API. **The backend is complete (Hilo) — all endpoints are live**, so the frontend connects directly (no backend blocking). See `DASHBOARD_BACKEND_GUIDE.md` and Prima's plan for the contracts: `/search`, `/api/v1/stats/*`, `/graph/subgraph`, `/graph/clusters`, `/admin/attention-inbox/*`, `/memories/preview`, `/auth/me`, etc. Run a **wiring smoke-test** to reconcile mock shapes ↔ real payloads.

### Step 4 — package & verify
- `electron-builder` → Windows `.exe` (min 1280×720).
- `check-contrast` (WCAG) PASS on every screen · Vitest suite green.

### Phasing (from Prima's plan)
- **Alpha (~25h):** shell, auth, data layer, Command Center, Knowledge Explorer, Settings, ⌘K.
- **Beta (~12h):** Decisions Inbox, Ontology Console, Ingestion, Templates, System Monitor.
- **v1.0 (~18h):** Graph Studio (react-force-graph-2d, 300 nodes @ 30+ FPS), packaging.
- **Backend:** ✅ complete (Hilo) — all endpoints live; frontend wires directly.

### Guiding principle (keep it)
> The dashboard maximises **operational clarity and decision quality**, not visible information. Every element justifies its cognitive cost.

---

## What is *not* your job
Re-deciding the visual language, layouts, component states, colors, or interaction patterns — those are settled here. If something needs a design change, flag it back; don't improvise it.

---

*Light mode is the primary theme for this app. Dark mode is fully supported via the theme toggle.*
