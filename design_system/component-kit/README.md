# EcoDB Component Kit

Reusable building blocks ("legos") for the EcoDB knowledge-management UI.
Aesthetic: Apple Liquid Glass × Teenage Engineering — midnight + ivory, surgical orange, color-coded signal.

## Open it
- **`EcoDB Kit (standalone).html`** — self-contained gallery, works offline. Double-click to open. Every component, all states, light + dark.
- **`EcoDB Kit.html`** — same gallery, but loads the source files below (edit these to change components).

## The legos (source)
| File | What's inside |
|---|---|
| `styles.css` | Design tokens (`--*` for light/dark) + base component styles (card, dot, toggle, chip, button, search, segmented, charts, agent/memory rows, drawer, screen). **Start here.** |
| `kit.css` | Gallery chrome + extra component styles/states (skeletons, focus rings, CmdK, StatusPill, attention inbox, memory-type colors, inline drawer). |
| `components.jsx` | Charts & primitives: `AreaChart`, `BarChart`, `Sparkline`, `Dot`, `Toggle`, `useSize`. |
| `graph.jsx` | `KnowledgeGraph` / GraphViewport (animated canvas, hover labels, `onPick`). |
| `kit-parts.jsx` | `GlassCard`, `Chip`, `Button`, `Segmented`, `KpiTile`, `MemoryRow`, `AgentRow`, `AttentionInbox`, `StatusPill`, `ThemeToggle`, icons, `highlight()`. |
| `kit-overlays.jsx` | `SearchField`, `CmdK`, `Drawer` (kind: agent/memory/node/document), `TopBar`, `Clock`. |
| `kit-gallery.jsx` | The gallery page + real EcoDB mock data (Lienzo/Hilo/Prima/Eco). |
| `design.md` | The full design system: tokens, principles, color norms, component contracts, data shapes. **The spec.** |

## How to compose
Components are plain React (UMD + Babel, no build step). To use one elsewhere:
1. Include `styles.css` (+ `kit.css` for the extra components) and the two fonts (DM Mono, Hanken Grotesk).
2. Put `data-theme="light"` or `"dark"` on a wrapping element (tokens re-scope per subtree).
3. Drop components on the 3-layer surface: backdrop → glass tray → raised cards. Keep cards raised (never inset) and orange surgical.

## Rules that matter (don't regress)
- 3-layer depth; cards raised, GraphViewport is the only dark inset screen.
- Orange = live/active/critical only. Kind colors (memory=orange, document=blue, node=green, agent=amber) as *small touches* only.
- DM Mono for all data/numbers (`tabular-nums`); Hanken Grotesk for copy.
- Dark = midnight blue-black (not brown); keep ink contrast as tuned.

## Production note
This is a no-build reference (in-browser Babel). For shipping, port to a real build (Vite) and self-host fonts — see `design.md` §6.
