# Brief — Phase 1: EcoDB Component Kit

**From**: Lienzo (Design Lead, Eco Consulting)
**To**: Design agent
**Date**: 1 June 2026
**Scope**: Component kit only. No dashboard layout, no page assembly, no routing.

---

## What we're asking

Build every UI component from design.md §3 **in isolation** on a gallery page (`EcoDB Kit.html`). Each component shows all variants and states, light+dark, with documented props. The gallery is the deliverable — a page where I can scroll through every piece, see every state, and copy any component into the real dashboard when we build it.

**You own the components. We own the layout.** Don't assemble a dashboard. Don't decide what goes where on a page. That's Phase 2 and we direct it with our frontend team. Your job here is to give us perfect, composable pieces.

---

## Source of truth

- **Visual language**: `design_system/design.md` — your tokens, your spec, unchanged. Follow it exactly.
- **Data contracts**: this brief §4 below — real response shapes from the live API, not placeholder data.
- **Component list**: design.md §3 + additions in this brief §3.

---

## Rules (non-negotiable)

1. **Three-layer depth**: backdrop → tray → floating cards. Cards are RAISED (elevation shadow + bright top edge). Never sunken/inset. Only exception: graph viewport (dark inset screen).
2. **Surgical orange (#F5631E)**: marks ONLY live/active/critical signal. Never decorative. If two oranges fight in one card, remove one.
3. **Tokens from design.md §2**: use the exact CSS custom properties. No new colors, no new fonts.
4. **DM Mono** for all data/numbers/labels/tags. **Hanken Grotesk** for titles/descriptions/body. No exceptions.
5. **Every component gets ALL these states**: rest, hover, active/focused, loading (shimmer skeleton in glass), empty (quiet mono message), error (red dot + retry), disabled. Light+dark for each.
6. **Cursor-tracked specular highlight** on glass cards (the `--mx/--my` technique from the mockup). This is the Liquid Glass signature — keep it on every GlassCard.
7. **`font-variant-numeric: tabular-nums`** on all numbers. Always.
8. **No gauges, no dials, no skeuomorphic transport buttons.** Real dashboard primitives only.

---

## §3 Component list (build in this order)

### Batch A — Containers & primitives (build first — everything else sits inside these)

**A1. GlassCard**
- The container for everything. All other components live inside GlassCards.
- Variants: `default` | `compact` (less padding) | `flush` (no padding, for tables/lists)
- Optional header: `{ title: string, tag?: string, control?: ReactNode }` — title in DM Mono uppercase 11px, tag as Chip, control as SegmentedControl or other.
- States: rest (default elevation), hover (elevated shadow), loading (entire card = shimmer skeleton), error (card with red dot + "retry" link), empty (card with centered mono message like "no data").
- The `::before` specular highlight follows cursor on hover.
- Both themes.

**A2. Dot (indicator)**
- States: `on-accent` (orange, pulsing glow), `ok` (green, steady), `alert` (red, blinking), `idle` (muted, no glow).
- Recessed well housing (inset shadow + outer rim) — this is the ONE element that's inset, not raised.
- Animation: `pulse` (gentle scale 1→1.15→1), `blink` (opacity), `none`.
- Size: 6px default, 8px large.

**A3. Chip**
- Mono micro-label. Background: subtle fill from `--inset`. Text: `--ink-3`.
- No border. Rounded `--r-sm`.
- Use for: memory type tags, agent roles, status labels.

**A4. Button**
- Variants: `default` (ghost, subtle border), `primary` (orange fill, dark text), `danger` (red fill).
- States: rest, hover, active/pressed, disabled, loading (spinner replacing label).
- Size: compact only (no big buttons in this UI).

**A5. Toggle**
- `on: boolean`. Track is neutral graphite when on (NOT orange — per design.md §1.5).
- Thumb moves with ease-out transition.
- Show both states side by side in gallery.

**A6. SegmentedControl**
- `options: string[]`, `value: string`.
- Example: `['1h', '24h', '7d']`.
- Active segment: subtle fill + `--ink-1` text. Inactive: `--ink-3`.
- Transition between segments is smooth.

### Batch B — Search & navigation (the most-used interactions)

**B1. SearchField**
- This is the HERO component of the app. Build it generously.
- `value: string`, `placeholder: string`, `resultCount?: number`, `onClear: () => void`.
- States: empty (placeholder visible), typing (value visible + clear button), focused (orange focus ring), loading (spinner in right side while searching), has-results (count badge).
- Keyboard shortcut badge: `⌘K` chip on the right when not focused.
- Size: full-width, generous height (44-48px). This is not a small input.
- DM Mono for the input text.

**B2. CmdK Modal**
- Overlay modal triggered by Cmd+K.
- SearchField at top (same component as B1 but inside modal).
- Results list below: 5-8 items, each with icon + title + subtitle + type chip.
- Keyboard navigation: ↑/↓ to select, Enter to navigate, Esc to close.
- Glass backdrop with heavy blur.
- Show states: empty (no query), results, no-results ("nothing found"), loading.

**B3. Drawer**
- Right-side glass panel that slides in from the right.
- `kind: 'agent' | 'memory' | 'node' | 'document'` — header changes per kind.
- Header: kicker label (kind) + title + description + close button.
- Body: scrollable content area for stats, charts, lists, actions.
- Footer: action buttons (e.g., "Mark as stale", "Open in Explorer").
- States: closed, open, loading (skeleton inside), transitioning.
- Closes on: ✕ button, click outside (scrim), Esc key.
- Width: 400px default.

### Batch C — Data display (what the user reads)

**C1. KpiTile**
- `label: string`, `value: string | number`, `unit?: string`, `series: number[]`, `delta: number`, `trend: 'up' | 'down'`, `accent?: boolean`.
- Shows: label (DM Mono uppercase), big value (32px mono), sparkline (Sparkline component), delta with arrow.
- If `accent: true`, sparkline is orange. Otherwise warm graphite.
- Compact: fits in a grid cell, not a hero block.
- States: rest, hover (slight elevation), loading (shimmer), error, empty.

**C2. AreaChart**
- `data: { t: number, v: number }[]`, `unit: string`, `band?: [lo: number, hi: number]` (target zone), `tipFmt?: (v) => string`.
- Smooth Catmull-Rom interpolation, gradient fill (from accent to transparent).
- Grid lines, "now" marker (orange vertical line at right edge).
- **Hover crosshair + tooltip** — shows value at cursor position.
- `vector-effect: non-scaling-stroke` for clean scaling.
- Axis labels: DM Mono `--ink-3`.
- States: data, loading (shimmer area), empty ("no data for this period"), error.

**C3. BarChart**
- `data: { label: string, value: number }[]`.
- Horizontal bars. Last bar (most recent) = orange. Rest = `--chart-bar`.
- Hover: tooltip with exact value.
- States: data, loading, empty, error.

**C4. Sparkline**
- `data: number[]`, `accent?: boolean`.
- Tiny inline chart, no axes, no labels. For embedding in KpiTile and AgentRow.
- If accent: orange stroke. Else: `--chart-line`.
- SVG, height ~24px.

**C5. GraphViewport**
- The dark inset screen for the knowledge graph.
- This is the ONE component that uses a dark recessed look (even in light theme).
- Animated constellation: nodes with edges, traveling pulses on edges.
- `onPick: (nodeId) => void` — clicking a node fires callback.
- Hover: node label appears.
- One "hot" node (orange, larger, glowing) — the currently selected/focused node.
- Cluster coloring: nodes in same cluster share a subtle hue.
- Stats bar below: connected %, avg degree, clusters, density (DM Mono, `--ink-3`).
- States: loading (pulsing dots), data (animated graph), empty ("no graph data"), error.
- NOTE: in Phase 2 this becomes full-screen in Graph Studio view. Build it so it can scale.

### Batch D — Lists & rows (the content the user scans)

**D1. MemoryRow**
- `ts: string`, `text: string`, `tags: string[]`, `type: string`, `hot?: boolean`.
- Layout: timestamp (DM Mono) | type dot (colored by type) | text (Hanken, truncated) | tags (Chip array).
- If `hot`: left orange accent line (2px), slightly elevated background.
- Hover: subtle background fill.
- Click: opens Drawer with memory detail.
- Text supports **search highlight** (wrap matched substring in `<mark>` with orange background).
- Type colors: decision=orange, tecnico=blue (#6e9ecf), momento=green, observacion=amber (#c4a86a), referencia=`--ink-3`.

**D2. AgentRow**
- `name: string`, `status: 'active' | 'ok' | 'idle' | 'error'`, `task?: string`, `sparkline: number[]`, `on: boolean`, `hot?: boolean`.
- Layout: Dot (status color) | name (DM Mono 600) | task description (Hanken, `--ink-3`) | sparkline | toggle.
- If `hot`: name in orange (the one active agent).
- Click: opens Drawer with agent detail.

**D3. AttentionInboxItem**
- `class: 'stale_memories' | 'pending_alias_candidates' | 'unconfirmed_relations' | 'low_trust_documents'`, `count: number`, `label: string`.
- Layout: Dot (orange if count > 0, idle if 0) | label (DM Mono) | count badge.
- Click: navigates to filtered view (this will be wired in Phase 2).
- Show as a compact list, not big cards. This is a checklist, not a hero section.

**D4. AttentionInboxSummary**
- Container GlassCard holding 4× AttentionInboxItem.
- Header: "attention inbox" + total count badge.
- Shows the 4 decision classes with their counts.
- States: loading, data, empty ("nothing needs attention" — this is a GOOD state), error.

### Batch E — Chrome & system (build last)

**E1. TopBar**
- Fixed top. Glass tray (not a card — uses tray tokens).
- Left: logo mark (orange rounded square with EcoDB icon) + "ecodb" text (DM Mono 600) + version chip.
- Center: SearchField (B1).
- Right: Clock (DM Mono, time + date) + system status dots (services healthy count) + theme toggle button.
- The orange strip concept from my v3 prototype: consider incorporating the service status indicators as a thin orange accent line or subtle orange section in the topbar — but it should feel integrated, not boxy. Optional — show both with and without in the gallery so we can decide.

**E2. StatusPill**
- System status indicator. `services: number`, `healthy: number`, `latency: string`.
- Layout: Dot (green if all healthy) + "6/6 services" + "48ms p95" (DM Mono, `--ink-3`).
- Compact. Lives in TopBar.

**E3. ThemeToggle**
- Button that switches light/dark.
- Icon: moon (dark) / sun (light).
- Recessed button style (inset shadow, like my v3 knobs but as a flat button, not 3D).

---

## §4 Data contracts (real shapes from the live API)

Use these for the mock data in each component. These are the ACTUAL response shapes from the running backend.

### Attention Inbox
```json
// GET /admin/attention-inbox/summary
{
  "classes": {
    "stale_memories": 118,
    "pending_alias_candidates": 18,
    "unconfirmed_relations": 0,
    "low_trust_documents": 0
  },
  "total": 136
}

// GET /admin/attention-inbox/details?decision_class=stale_memories
{
  "class": "stale_memories",
  "total": 118,
  "items": [{ "id": "uuid", "content": "...", "created_at": "iso", "tags": [] }],
  "limit": 20,
  "offset": 0
}
```

### Stats Timeline
```json
// GET /api/v1/stats/timeline?period=30
{
  "period_days": 30,
  "timeline": [
    { "date": "2026-06-01", "memories": 11, "documents": 0, "searches": 3 }
  ]
}
```

### Memory Preview (for Templates screen)
```json
// POST /memories/preview
{
  "entities": [
    { "text": "Eco Consulting", "label": "organizacion", "score": 1.0, "source": "dictionary" }
  ],
  "entity_count": 3,
  "suggested_triples": [
    { "subject": "Eco Consulting", "predicate": "is_a", "object": "organizacion" }
  ]
}
```

### Graph Clusters
```json
// GET /graph/clusters
{
  "clusters": [
    { "cluster_id": 0, "node_count": 15, "nodes": [{ "node_id": 1, "name": "Eco" }] }
  ],
  "cluster_count": 8,
  "total_nodes": 120,
  "last_computed": "2026-06-01T12:00:00Z"
}
```

### Search (for SearchField + CmdK)
```json
// POST /search
{
  "query": "multi-tenant",
  "query_type": "contextual",
  "results": [
    {
      "id": "uuid",
      "content": "...",
      "type": "decision",
      "tags": ["ecodb", "v0.9"],
      "agent_identifier": "Lienzo",
      "score": 0.92,
      "semantic_score": 0.73,
      "graph_score": 0.5,
      "freshness_score": 0.99,
      "created_at": "2026-06-01T14:33:47Z"
    }
  ],
  "count": 10,
  "warnings": []
}
```

### System Stats (for KpiTiles)
```json
// GET /api/v1/stats/*
{
  "memories": { "total": 1847, "today": 23 },
  "documents": { "total": 142, "today": 4 },
  "graph": { "nodes": 1247, "triples": 3291, "predicates": 98 },
  "search": { "p50_ms": 44, "p95_ms": 48, "queries_per_min": 297 },
  "services": { "total": 6, "healthy": 6 }
}
```

### Agent (for AgentRow)
```json
{
  "id": 4,
  "name": "Lienzo",
  "role": "Design Lead",
  "status": "active",
  "task": "Building dashboard components",
  "load": 0.72,
  "throughput": [12, 15, 8, 22, 18, 14, 9],
  "uptime_sec": 3600,
  "error_rate": 0.0
}
```

---

## §5 Mock data guidelines

- Use REAL names from our system: agents are Lienzo, Hilo, Prima, Eco. Not "archivist", "cartographer", "sentinel."
- Memory content examples should reference real EcoDB work: "Reestructura README v0.9", "Multi-tenant spec aprobado", "GAMR 10 etapas verificado". Not generic "Vendor contract renewal."
- Tags should be real: "ecodb", "v0.9", "readme", "multi-tenant", "workflow-frontend". Not "contracts", "planning."
- Numbers should be plausible for our scale: ~1800 memories, ~140 documents, ~3300 triples, ~1200 nodes. Not 15,000+.

---

## §6 Gallery layout

The gallery page itself should be clean and scannable:
- One component per section, with a heading showing the component name.
- Show all states side by side (rest | hover | active | loading | empty | error | disabled).
- Show light theme, then dark theme for each component.
- Props/data contract documented as a small code block beside each component.
- Background: use the three-layer backdrop from design.md so the glass reads correctly (not on a flat white page).

---

## §7 What NOT to do

- Don't assemble a dashboard layout. Gallery of isolated components only.
- Don't introduce new colors, fonts, or design elements not in design.md.
- Don't use generic placeholder data. Use our real system names and plausible numbers.
- Don't build routing, state management, or API integration. Components receive props, that's it.
- Don't skip any state. Loading and error states are as important as the happy path.
- Don't make the SearchField small. It's the hero of the app.
- Don't use gauges or dials. Real dashboard primitives only.

---

## Deliverable

One HTML file: `EcoDB Kit.html` — a scrollable gallery with every component, every state, both themes, documented props. Self-contained, openable in a browser.

When this is done, send it to me (Lienzo) for review. I'll evaluate against design.md compliance, component completeness, and state coverage. After approval, we proceed to Phase 2 (real dashboard assembly) which I direct with my frontend team.
