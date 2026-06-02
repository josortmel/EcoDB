# EcoDB — Design System
*Knowledge-management UI · Apple Liquid Glass × Teenage Engineering · midnight + ivory, surgical orange, color-coded signal*

Source of truth for the EcoDB visual language. **Phase 1 (the component kit) is built and approved** — this doc now documents the *shipped* system, not a wishlist. Use it to (a) reproduce the look exactly and (b) assemble the real, data-backed dashboard (Phase 2) from the existing parts.

**Reference files (live):** `EcoDB Kit.html` (component gallery — every part, all states, light+dark), `EcoDB Console.html` (assembled dashboard mockup), `styles.css` (tokens + base components), `components.jsx` (charts/primitives), `graph.jsx` (graph viewport), `kit-parts.jsx` + `kit-overlays.jsx` (kit components), `kit-gallery.jsx` (gallery). Self-contained exports: `ecodb-kit-standalone.html`, `ecodb-dashboard-standalone.html`. Prior explorations: `v1/` (mission-control), `v2/` (TE aluminium), `kit-v1/`, `kit-v2/`.

---

## 0 · Phases

| Phase | Goal | Status |
|---|---|---|
| **0 — Language** | Lock tokens, primitives, motion, color norms | ✅ this doc |
| **1 — Component kit** | Every element isolated, all variants/states, copy-pasteable | ✅ `EcoDB Kit.html` |
| **2 — Real dashboard** | Multi-view shell, real data, loading/empty/error/offline, responsive, a11y, density | ▶ next |
| **3 — Handoff** | Framework components + tokens (CSS vars + JSON) + documented contracts | later |

---

## 1 · Principles

1. **Three depth layers, always.** Backdrop (content for glass to refract) → liquid-glass *tray* → floating frosted *cards*. Cards are **raised** (elevation shadow + bright top edge), **never sunken/inset**. The single exception is the **GraphViewport** (a dark recessed screen, in both themes). This depth hierarchy is the core of the look.
2. **Two temperatures, both committed.** Light = clean **ivory + bright white glass** (a Braun product in morning light). Dark = **midnight blue-black** with cool slate glass (Mission Control at night) — *not* brown, *not* blue-cold-gray; a true neutral-blue night.
3. **Surgical orange (`#F5631E`).** Orange marks *only* live/active/critical signal: live sparklines, the one active agent, the highlighted graph node, status dots, chart "now" markers, the **on** toggle, the primary action. Never decorative. Two oranges fighting in one card → remove one.
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
| `--ink-3` | `#6f695e` | `#868e9c` | labels, meta, ticks (kept dark enough to read on glass) |
| `--ink-4` | `#a9a397` | `#4a505c` | idle / disabled |

> Contrast note: small grey mono text must use `--ink-2` for captions and never go lighter than `--ink-3`. This was a real legibility fix — don't regress it.

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
                  --card-hairline (1px divider) · backdrop-filter: blur(22px) saturate(1.5)
   light --card-bg = linear-gradient(155deg, rgba(255,255,255,.85), rgba(253,253,251,.67))  ← bright, whiter
   dark  --card-bg = linear-gradient(155deg, rgba(46,54,68,.52),   rgba(21,25,33,.40))       ← cool slate
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

---

## 3 · Component inventory (built — `EcoDB Kit.html`)

All ship isolated, all states, light+dark, with prop contracts in the gallery.

### Primitives
- **GlassCard** — `variant: default|compact|flush`, `state: rest|hover|loading|empty|error`, `head{title, tag|control}`. Loading = shimmer skeleton in glass; empty/error = quiet centered message (error has a red dot + retry). The container everything sits in.
- **Dot** — `s: on(orange)|ok(green)|alert(red)|idle` + memory-type variants `t-decision|t-tecnico|t-momento|t-observacion|t-referencia`; `anim: pulse|blink|none`. Recessed well — the one inset element.
- **Chip** — mono micro-label; `tone?: hot`.
- **Button** — `variant: default | primary | tint | danger`, plus `loading`, `disabled`, `pressed`. **default** = frosted glass + hairline (tactile, has presence). **primary** = warm orange gradient (`#F4742F→#DE5316`) with a top specular sheen — confident, *not* neon. **tint** = orange-tinted glass + orange text (the soft, on-brand CTA option). **danger** = muted red tint (not a bright fill). Compact size only.
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
Real endpoints exist (`/search`, `/api/v1/stats/*`, `/graph/clusters`, `/admin/attention-inbox/*`, `/memories/preview`). Provide a **mock ↔ api adapter** so the same components run on either. Demo data uses real names (agents **Lienzo / Hilo / Prima / Eco**) and plausible scale (~1,847 memories · 142 docs · 1,247 nodes · 3,291 triples · p95 48ms).

---

## 5 · Phase 2 — assembling the serious dashboard

Components are done; layout and wiring are next (frontend team directs).
- **Every data surface gets** loading (shimmer) / empty (quiet) / error (red dot + retry) / stale-offline (dim + "last updated"). The kit already provides these states.
- **Views / routing:** Overview · Graph Studio (full-screen GraphViewport + inspector Drawer) · Agents · Memory Search (results, facets, pagination, CmdK).
- **Responsive:** the mockup's fixed 1380 tray *scaled to fit* is a mockup trick — replace with a real grid: ≥1280 bento · 768–1280 two-column · <768 single column + Drawer becomes a full-screen sheet.
- **Density:** comfortable / compact toggle.
- **A11y:** visible focus rings, `aria` on toggle/drawer/search/cmdk, ≥4.5:1 text contrast (ink scale already tuned), keyboard nav for rows + graph picks, `prefers-reduced-motion` stops ambient motion.
- **Wiring:** search filters memories *and* graph; clicking a node focuses its cluster (dim the rest); segmented range drives all time-series + KPIs together; toggles persist.

---

## 6 · Caveats / cleanup before production
- **No-build stack:** React 18 UMD + in-browser Babel + `.jsx` files. For handoff move to Vite (or similar) and drop Babel-in-browser.
- **Drawer slide is JS rAF, not a CSS transition** — the preview harness stalled CSS transitions on `transform`/`right`. In a normal app use a CSS transition or framer-motion; keep the rAF only if the stall recurs.
- **Fonts:** confirm DM Mono / Hanken Grotesk licensing or self-host equivalents.
- **Graph data** is generated client-side; bind to `GraphNode/GraphEdge`.
- Keep the **ink contrast** (§2.3) and the **dark = midnight, not brown** rule — both were deliberate corrections.

---

*Built and approved through v4 with Lienzo (Design Lead). The kit is the canonical reference; this doc tracks it.*
