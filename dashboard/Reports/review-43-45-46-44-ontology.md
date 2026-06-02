# Review — #43/#45/#46/#44 OntologyConsole.tsx
Date: 2026-06-02 | Against: DESIGN.md + tokens.css | Product: EcoDB Dashboard

> Visual verification via Playwright no completada — auth requerida. Análisis código + cálculo WCAG.

---

## HIGH (fix before publishing)

- **[ONT-H1] StateWrap retry button usa text-accent** → `OntologyConsole.tsx:92`
  ```tsx
  <button … className="font-mono text-[12px] text-accent">{t('ont.retry')}</button>
  ```
  Tercer caso del mismo patrón: CC-H1 (Panel.tsx), EXP-H1 (KnowledgeExplorer.tsx) → ahora StateWrap. El retry en estado de error es una acción de navegación, no señal live. §1.3: naranja reservado para live/active/critical signal.
  StateWrap es compartido: el fix cierra la regresión en los 4 tabs (Entities, Predicates, Aliases, Dictionary) en un único punto.
  Fix: `className="font-mono text-[12px] text-ink-1 underline underline-offset-2"`

---

## Verificaciones PASS

### Floor y legibilidad

| Elemento | Tamaño | Resultado |
|---|---|---|
| Entity type label / status label | 9.5px | ✅ floor exacto |
| Marker badge | 9.5px | ✅ |
| Similarity / occurrences meta | 9.5px | ✅ |
| Type filter chips / shown count | 10px | ✅ |
| Predicate edit/delete buttons | 10.5px | ✅ |
| Alias meta (confidence/occurrences) | 10px | ✅ |
| SearchInput | 12px | ✅ |
| Entity name (detail panel) | 18px bold | ✅ §2.2 body font para título |
| Merge confirm prompt / keepAlias | 11px–11.5px | ✅ |
| ink-3 sobre card-bg | ~5.97:1 (calc. anterior) | ✅ WCAG AA |

Sin texto por debajo del floor 9.5px en todo el archivo.

### Tokens y semántica de color

| Check | Resultado |
|---|---|
| CTAs merge/approve/add/update/save → `bg-btn-primary text-white` | ✅ terracota §3 |
| Danger (delete/reject) → `color-mix(var(--red) 12%/38%)` tint, NO fill sólido | ✅ §3 componente danger |
| Section color `--sec-ontology` (#8E78BC) → chips activos, dots, kicker, active row | ✅ §2.9 correcto |
| `accentColor: var(--sec-ontology)` en checkbox keepAlias | ✅ theme-aware |
| `var(--grn)` approved / `var(--red)` rejected en AliasesTab markers | ✅ §2.1 semántica |
| InlineWarn: `color-mix(var(--red) 10%/30%)` | ✅ token-safe |
| Marker: `color-mix(in srgb, ${color} 12%/32%)` dinámico | ✅ |
| Active entity/dict row: `color-mix(var(--sec-ontology) 12%)` subtle | ✅ §2.9 |
| Alias status chips, entity type chips: `color-mix(var(--sec-ontology) 14%/38%)` | ✅ |
| SearchInput focus ring: accent ring + halo (patrón establecido en codebase) | ✅ consistente |

### Anti-slop

| Check | Resultado |
|---|---|
| Side-stripe borders | ✅ ninguno |
| Gradient text | ✅ ninguno |
| Identical card grids | ✅ — EntitiesTab: split list+detail / PredicatesTab: single card / AliasesTab: list con flow / DictionaryTab: split list+detail |
| Glassmorphism decorativo | ✅ — GlassCard uso estructural únicamente |
| Hero-metric template | ✅ ninguno |
| Naranja señal en CTAs | ✅ — terracota en todos, signal orange ausente de acciones |

### A11y (DESIGN.md §5b)
- `role="tablist"` + `role="tab"` + `role="tabpanel"` + `aria-selected` + `aria-controls` + `aria-labelledby` en OntologyConsole ✅
- `aria-pressed` en entity type chips y alias status chips ✅
- `role="option"` + `aria-selected` en entity listbox ✅
- `role="listbox"` + `aria-label` en entity y dictionary lists ✅
- Two-step delete confirmation (confirmName/confirmId) ✅

---

## Score
Visual: 9/10 | Anti-slop: 10/10 | Total: 9.5/10

## Verdict
**CHANGES NEEDED**

ONT-H1 = única corrección requerida: StateWrap:92 `text-accent` → `text-ink-1 underline underline-offset-2`. Fix de un punto cierra la regresión en los 4 tabs. Todo el resto del componente está limpio.
