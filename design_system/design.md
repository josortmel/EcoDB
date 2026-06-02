# EcoDB — Design System
*Knowledge-management UI · Apple Liquid Glass × Teenage Engineering · midnight + ivory, surgical orange, color-coded signal*

Source of truth for the EcoDB visual language. **Phases 1 & 2 are built and approved** — this doc documents the *shipped* system, not a wishlist. Use it to (a) reproduce the look exactly and (b) re-implement the dashboard on the real stack (Phase 3 handoff).

**Primary theme is LIGHT** (ivory + bright white frosted glass). Dark (midnight) is fully supported via the theme toggle but is the secondary mode for this app.

**Reference files (live):** `EcoDB App.html` (the full 8-view dashboard — THE current target) + its source: `ecodb-app.jsx/.css`, `ecodb-data.jsx`, `ecodb-command.jsx`, `ecodb-explorer.jsx`, `ecodb-views2.jsx`. Shared foundation: `styles.css` (tokens + base components), `components.jsx`, `graph.jsx`, `kit-parts.jsx`, `kit-overlays.jsx`. Component gallery: `EcoDB Kit.html`. Self-contained exports: `ecodb-app-standalone.html`, `ecodb-kit-standalone.html`. Handoff bundle: `handoff/`. Prior explorations: `v1/`, `v2/`, `kit-v1/`, `kit-v2/`.

---

## 0 · Phases

| Phase | Goal | Status |
|---|---|---|
| **0 — Language** | Lock tokens, primitives, motion, color norms | ✅ this doc |
| **1 — Component kit** | Every element isolated, all variants/states, copy-pasteable | ✅ `EcoDB Kit.html` |
| **2 — Dashboard prototype** | All 8 views, real interactions on mock data, light/dark | ✅ `EcoDB App.html` |
| **3 — Build (functional app)** | Port to React+Vite+Tailwind+Electron, wire to live API | ▶ engineering (backend ✅ done by Hilo) |

---

## 1 · Principles

1. **Three depth layers, always.** Backdrop (content for glass to refract) → liquid-glass *tray* → floating frosted *cards*. Cards are **raised** (elevation shadow + bright top edge), **never sunken/inset**. The single exception is the **GraphViewport** (a dark recessed screen, in both themes). This depth hierarchy is the core of the look.
2. **Two temperatures — LIGHT is primary.** Light = clean **ivory + bright white frosted glass** (a Braun product in morning light) — the default and main mode for this app. Dark = **midnight blue-black** with cool slate glass (Mission Control at night) — *not* brown, *not* blue-cold-gray — fully supported as the secondary mode.
3. **Surgical orange (`#F5631E`) for signal; terracotta for action.** Orange marks *only* live/active/critical signal: live sparklines, the active agent, the highlighted graph node, status dots, chart "now" markers, the **on** toggle, section accent lights. The **primary button** is a warmer **terracotta** gradient (see §3) so CTAs feel grounded, not neon — the bright signal-orange is reserved for indicators. Never decorative.
4. **Color-coded signal as identity.** Beyond orange, entity *kinds* and memory *types* carry a quiet, consistent accent (see §2.8). This is what gives the system character without noise — applied as small touches (an icon glyph, a drawer kicker, a row dot), never as fills or panels.
5. **Monochrome data, restrained chrome.** Charts and numbers are graphite (light) / cool ivory (dark). Instrument feel comes from precision, tabular numerals, and spacing — not color.
6. **Real dashboard primitives only.** Time-series (area/line), distributions (bars), KPIs+sparkline, tables, lists, graph viewport, search, command palette, segmented controls, toggles, indicator dots, drawers. **No gauges/dials. No skeuomorphic transport buttons.**
7. **Quiet motion.** Values tick, lines settle, the active agent blinks, graph pulses travel edges, drawers slide. Nothing bounces.

---

## 2 · Tokens

CSS custom properties scoped to `[data-theme="light"]` / `[data-theme="dark"]`. Names below are the **real** ones in `styles.css`.

### 2.1 Brand / semantic (theme-independent)
```
--accent:   #F5631E   /* primary signal orange */
--accent-2: #FF8A4C   /* lighter orange (hover) */
--grn:      #4E9E6A   /* positive / ok */
--red:      #DE4630   /* alert / negative */
```

### 2.2 Type
```
--font-mono: 'DM Mono'         → labels, tags, ALL numbers/data (tabular-nums), chrome
--font-body: 'Hanken Grotesk'  → titles, descriptions, body, button labels
```
- `font-variant-numeric: tabular-nums` on every number, always.
- Section titles: 11px / `letter-spacing:.14em` / uppercase / 600 / `--ink-2`.
- KPI value 32px mono 500 · chart big value 30px mono 500 · tags/meta 9.5–11px mono.
- (No display/pixel font — the old `Doto` is gone.)

### 2.3 Ink (text on glass) — tuned for contrast
| Token | Light | Dark | Use |
|---|---|---|---|
| `--ink-1` | `#1f1d1a` | `#eef1f7` | primary text / values |
| `--ink-2` | `#5e584f` | `#b6bdca` | titles, secondary, small captions |
| `--ink-3` | `#625c52` | `#868e9c` | labels, meta, ticks (kept dark enough to read on glass) |
| `--ink-4` | `#a9a397` | `#4a505c` | idle / disabled |

> Contrast note: small grey mono text must use `--ink-2` for captions and never go lighter than `--ink-3`. This was a real legibility fix — don't regress it.
> ink-3 light bumped to ≥4.5:1 (was #6f695e = 3.87 on bd-2) — legibility, WCAG AA for small text. Now #625c52 = 4.70 on bd-2 / 5.97 on card; still lighter than ink-2 (5.00), so ink-1 > ink-2 > ink-3 holds.

### 2.4 Backdrop (must stay non-flat — it's what the glass refracts)
```
light  --bd-1 #ece9e3  --bd-2 #ddd9d1  --bd-3 #d2cdc3      (warm ivory)
dark   --bd-1 #12151b  --bd-2 #0c0f14  --bd-3 #07080c      (midnight blue-black)
--blob-warm : faint orange radial, top-right (brand warmth)
--blob-cool : faint blue radial, bottom-left (dark: rgba(72,116,182,.11))
grain: SVG fractalNoise, opacity --grain (.035 light / .05 dark), mix-blend soft-light
```

### 2.5 Liquid glass
```
TRAY (bg panel):  --tray-bg, --tray-edge, --tray-shadow · backdrop-filter: blur(22px) saturate(1.3)
CARD (floating):  --card-bg, --card-edge / --card-edge-lo (rim), --card-spec (specular),
                  --card-hairline (1px divider) · backdrop-filter: blur(28px) saturate(1.6)
   light --card-bg = linear-gradient(155deg, rgba(255,255,255,.74), rgba(252,252,250,.55))  ← frosted (lets backdrop read through)
   dark  --card-bg = linear-gradient(155deg, rgba(48,56,70,.46),   rgba(20,24,32,.33))       ← cool slate, translucent
   dark  --card-spec = rgba(214,228,252,.20)  ← cool, SOFT top highlight (a harsh warm edge reads wrong)
   dark  --card-spec = rgba(214,228,252,.20)  ← cool, SOFT top highlight (a harsh warm edge reads wrong)
ELEVATION: --elev (rest) / --elev-hi (hover) — layered: soft inset top hairline + 2 ambient shadows.
           Dark top inset is intentionally low (~.09 alpha, cool) so the edge whispers, not shouts.
```
**Cursor-tracked specular:** every GlassCard's `::before` is a radial highlight at `var(--mx) var(--my)` (updated on `pointermove`) + a diagonal rim gradient. This "light follows the cursor" is the Liquid-Glass signature — keep it on every card.

### 2.6 Geometry
```
radii: --r-xl 26 (tray) · --r-lg 20 (card) · --r-md 13 (screen/inset) · --r-sm 8 (chip/slot)
grid gap 16 · card padding 16–18 · tray padding 22 · inset wells: --inset + --inset-edge
```

### 2.7 Charts (the graph screen is always dark)
```
--chart-grid, --chart-line, --chart-fill-1/2 (area gradient), --chart-bar
--screen-bg (dark in both themes), --node, --node-hot #FF7A3C, --edge, --screen-grid
   light --chart-line #45413a · dark --chart-line #cdd4e0
Graph node glow is deliberately restrained (gradient radius ≈ 2.1× core, ≈3.2× for the hot node) — nodes read as crisp points, not blooms.
```

### 2.8 Color-coded signal — THE identity layer (norm)
A quiet, consistent palette beyond orange. Apply as **small touches only** (glyph, kicker text + its dot, row dot), never fills/borders/panels.

**Entity kind** — used on **CmdK result icons** and the **Drawer kicker** (the small top-left label + its dot), plus a 7%-opacity header wash of the same hue:
```
memory   → orange  var(--accent)
document → blue     #6e9ecf
node     → green    var(--grn)
agent    → amber    #c4a86a
```
**Memory type** — used on the **MemoryRow** type dot:
```
decision → orange · tecnico → blue #6e9ecf · momento → green var(--grn)
observacion → amber #c4a86a · referencia → var(--ink-3)
```

### 2.9 Section color & panel accents (app-level identity)
Variety **by meaning, not decoration**. Two mechanisms, both subtle:

**Per-section nav colors** — each nav item + its active state (LED dot, left bar, icon) carries its own hue. The nav reads as a colour legend:
```
command #F5631E · explorer #5C8FC9 · graph #4E9E6A · decisions #C98A3C
ingestion #4FA0A0 · ontology #8E78BC · settings #8A8F9C · insights #D98C4A
```
**Per-panel accent** — `GlassCard accent="<hue>"` adds a small colored dot beside the title + a ~7%-opacity corner glow (top-right), keyed to what the panel *shows* (e.g. activity=blue, health=green, attention=amber, ingestion=teal, dictionary=blue, api-key=violet). Never a fill or border — just the dot + whisper of glow.

### 2.10 Brand mark
Eco Consulting logo: a square outline with three horizontal bars; the **middle bar is signal-orange**, the outer two use `currentColor` so they adapt — espresso/ink in light, cream in dark. Sits bare (no chip) next to the **EcoDB** wordmark in the nav.

---

## 3 · Component inventory (built — `EcoDB Kit.html`)

All ship isolated, all states, light+dark, with prop contracts in the gallery.

### Primitives
- **GlassCard** — `variant: default|compact|flush`, `accent?: <hue>` (§2.9), `state: rest|hover|loading|empty|error`, `head{title, tag|control}`. Loading = shimmer skeleton in glass; empty/error = quiet centered message (error has a red dot + retry). The container everything sits in.
- **Dot** — `s: on(orange)|ok(green)|alert(red)|idle` + memory-type variants `t-decision|t-tecnico|t-momento|t-observacion|t-referencia`; `anim: pulse|blink|none`. Recessed well — the one inset element.
- **Chip** — mono micro-label; `tone?: hot`.
- **Button** — `variant: default | primary | tint | danger`, plus `loading`, `disabled`, `pressed`. **default** = frosted glass + hairline (tactile, has presence). **primary** = warm **terracotta** gradient (`#D5704A→#C45D38→#B6502F`) with a top specular sheen — grounded, *not* neon. **tint** = orange-tinted glass + orange text (soft, on-brand CTA option). **danger** = muted red tint (not a bright fill). Compact size only.
- **Toggle** — `on:boolean`. **Orange gradient track when ON** (white knob), neutral recessed well when OFF.
- **SegmentedControl** — `options:string[]`, `value`. e.g. `1h / 24h / 7d`.
- **ThemeToggle** — recessed flat button, sun (in dark) / moon (in light).

### Data viz
- **AreaChart** — `data:number[]`, `min/max?`, `band?:[lo,hi]` (target zone), `unit`, `tipFmt`. Smooth Catmull-Rom, gradient fill, grid, orange "now" marker, **hover crosshair + tooltip**. `vector-effect:non-scaling-stroke`. States: data/loading/empty.
- **BarChart** — `data:number[]`; most-recent bar orange.
- **Sparkline** — `data:number[]`, `accent?` (orange). Fixed-size; for KpiTile / AgentRow.
- **KpiTile** — `label, value, unit?, series, delta, trend, accent?`. States rest/hover/loading/empty/error.
- **GraphViewport** — animated canvas constellation; `onPick(nodeId)`, hover labels, one hot node, traveling edge pulses, stats bar. Dark inset screen in both themes. States data/loading/empty/error. (Built to scale to full-screen in Phase 2's Graph view.)

### Lists / surfaces / chrome
- **MemoryRow** — `ts, text, type, tags[], hot?, query?`. type dot colored per §2.8; `hot` = orange left accent; `query` highlights matches with `<mark>`. Click → Drawer.
- **AgentRow** — `name, role, status, task, sparkline, on, hot?`. Active agent = orange name. Toggle inline (stops row click). Click → Drawer.
- **AttentionInbox** (item + summary) — decision-class checklist with counts; `count>0` = orange dot + hot badge, `0` = idle. **All-clear is a good empty state.**
- **SearchField** *(hero)* — `value, placeholder, resultCount?, loading?, focus?, disabled?, onClear`. Generous 44–48px height, orange focus ring, `⌘K` badge when idle, count badge + clear when typing.
- **CmdK** — ⌘K palette over heavy glass blur. Results carry kind-colored icons (§2.8). States results/empty/no-results/loading. ↑↓ select · ↵ open · esc close.
- **Drawer** — right-side glass panel; `kind: agent|memory|node|document` (kicker + dot colored per §2.8, header gets a 7% hue wash). Header (kicker+title+desc+close) · stat grid · section charts/lists · action buttons (primary stays orange CTA). Closes on ✕ / scrim / Esc.
- **StatusPill** — `services, healthy, latency`; green when all healthy.
- **TopBar** — glass *tray* (not a card): logo + version · SearchField · StatusPill + Clock + ThemeToggle. Optional thin orange status-accent line.

---

## 4 · Data contracts (real API shapes — bind in Phase 2)

```ts
type SystemStat = { memories:{total,today}; documents:{total,today};
                    graph:{nodes,triples,predicates}; search:{p50_ms,p95_ms,queries_per_min};
                    services:{total,healthy} }
type KPI        = { label; value:string|number; unit?; delta; trend:'up'|'down'; series:number[] }
type TimeSeries = { points:{t:number;v:number}[]; unit; band?:[number,number] }
type Agent      = { id; name; role; status:'active'|'ok'|'idle'|'error'; task?; load;
                    throughput:number[]; uptime_sec; queueDepth; error_rate; actions:{lt;x}[] }
type Memory     = { id; ts; text; type:'decision'|'tecnico'|'momento'|'observacion'|'referencia';
                    tags:string[]; salience; sourceId? }
type GraphNode  = { id; label; type:'Entity'|'Document'|'Decision'|'Topic'; cluster; degree;
                    centrality; updatedAt; linkedMemoryIds:string[] }
type GraphEdge  = { a; b; weight; kind:'intra'|'bridge' }
type AttentionInbox = { classes:{stale_memories;pending_alias_candidates;
                                 unconfirmed_relations;low_trust_documents}; total }
type SearchResult = { id; content; type; tags:string[]; agent_identifier; score; created_at }
```
**Backend is complete (Hilo)** — all endpoints live (`/search`, `/api/v1/stats/*`, `/graph/subgraph`, `/graph/clusters`, `/admin/attention-inbox/*`, `/memories/preview`, `/auth/me`). The prototype ships a mock data layer (`ecodb-data.jsx`); at build time, swap it for an api adapter against the live endpoints. Demo data uses real names (agents **Lienzo / Hilo / Prima / Eco**) and plausible scale (~1,847 memories · 142 docs · 1,247 nodes · 3,291 triples · p95 48ms).

---

## 5 — Phase 2 · the dashboard (BUILT — `EcoDB App.html`)

The full prototype: app shell (colour-coded nav rail + appbar with global search, StatusPill, clock, theme toggle) and **8 views**, all interactive on mock data, light default.

1. **Command Center** — operative home: clickable stat cards, actionable attention inbox (merge / keep / resolve / defer), live SSE-style activity feed, knowledge-health meters, ingestion snapshot.
2. **Knowledge Explorer** — memories/documents tabs, GAMR search + filters (type, visibility, stale), trust/visibility badges, row actions (edit, cycle visibility, bin w/ undo), memory drawer with 10-stage GAMR score breakdown + trust/contradiction warnings.
3. **Decisions Inbox** — split view, “why surfaced?”, context cards, resolve / dismiss / defer.
4. **Graph Studio** — full-screen GraphViewport, click-to-inspect node panel, Louvain cluster legend, hop control.
5. **Ingestion** — Docling queue, lifecycle metrics, re-index / unlink actions.
6. **Ontology Console** — entities (alias, merge, stop, retype) + canonical predicates tabs.
7. **Settings** — trust tiers, feature-flag toggles, entity-dictionary CRUD, API-key show/rotate/revoke.
8. **Insights** — engine metrics (GAMR pipeline, Recall@5, latency) kept aside for presentations/launch reel, not daily work.

State patterns (loading shimmer / empty / error) come from the kit. Actions mutate real local state with toast confirmations (incl. undo).

---

## 5b — Phase 3 · build notes (engineering)
- **Target stack:** React + Vite + Tailwind + TanStack Query + Zustand + Electron (Prima's plan). Port `design.md` tokens → `tailwind.config.ts` (CSS vars + JSON mirror).
- **Backend is complete (Hilo)** — wire directly: `/search`, `/api/v1/stats/*`, `/graph/subgraph`, `/graph/clusters`, `/admin/attention-inbox/*`, `/memories/preview`, `/auth/me`. Run a wiring smoke-test (mock shapes ↔ real payloads).
- **Responsive:** prototype is desktop-first; add the responsive grid (≥1280 bento · 768–1280 two-col · <768 single + drawer→sheet) at build time.
- **A11y:** focus rings, `aria` on toggle/drawer/search/cmdk, ≥4.5:1 (ink scale tuned), keyboard nav, `prefers-reduced-motion` stops ambient motion, `check-contrast` PASS.
- Authoritative build bible: **Prima's *EcoDB Dashboard — Spec + Plan v2***. Handoff bridge: `handoff/HANDOFF.md`.

---

## 6 · Caveats / cleanup before production
- **No-build stack:** prototype runs React 18 UMD + in-browser Babel + `.jsx` files. The build ports to Vite and drops Babel-in-browser.
- **Drawer slide is JS rAF, not a CSS transition** — the preview harness stalled CSS transitions on `transform`. In the real app use a CSS transition or framer-motion; keep the rAF only if the stall recurs.
- **Fonts:** confirm DM Mono / Hanken Grotesk licensing or self-host equivalents.
- **Mock data layer** (`ecodb-data.jsx`) is client-side; swap for the live API adapter.
- Keep the deliberate corrections: **light is primary**, **dark = midnight, not brown**, **ink contrast** (§2.3), **terracotta CTA vs signal-orange** (§3), and **colour-by-meaning, not decoration** (§2.9).

---

*Built and approved with Lienzo (Design Lead) through the Phase 2 dashboard prototype + fine-tuning (light-primary, terracotta CTAs, frosted panels, per-section colour, real brand mark). The prototype `EcoDB App.html` is the canonical visual/UX target; this doc tracks it. Backend complete (Hilo); next is the engineering build (Phase 3).*
