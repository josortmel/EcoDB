# Review — #42 FB-EXP-SEARCH (KnowledgeExplorer.tsx)
Date: 2026-06-02 | Against: DESIGN.md + tokens.css | Product: EcoDB Dashboard

> Visual verification via Playwright no completada — app requiere auth en :5173.
> Todos los hallazgos están respaldados por análisis de código + cálculo WCAG manual.

---

## HIGH (fix before publishing)

- **[H1] Token semántico — retry button usa text-accent** → `src/pages/KnowledgeExplorer.tsx:437`
  ```tsx
  <button … className="font-mono text-[12px] text-accent">{t('exp.retry')}</button>
  ```
  §1.3: surgical orange reservado para señal live/active/critical — no para acciones. Patrón CC-H1 (Panel.tsx ya corregido a `text-ink-1 underline underline-offset-2`). Mismo fix aquí.

---

## MEDIUM (improve before publishing)

- **[M1] Token bypass — rgba hardcoded en 3 ubicaciones** → debería ser `color-mix(in srgb, var(--accent) X%, transparent)`

  | Ubicación | Código actual | Fix |
  |---|---|---|
  | `Chip` L57 background | `rgba(245,99,30,0.13)` | `color-mix(in srgb, var(--accent) 13%, transparent)` |
  | `Chip` L58 boxShadow | `rgba(245,99,30,0.4)` | `color-mix(in srgb, var(--accent) 40%, transparent)` |
  | `ScopeSelect` L88 boxShadow | `rgba(245,99,30,0.4)` | ídem |
  | `TagsFilter` L114 background | `rgba(245,99,30,0.13)` | `color-mix(in srgb, var(--accent) 13%, transparent)` |

  Precedente CC-M2 (CommandCenter.tsx): mismo patrón, mismo fix. Los tokens vars son la fuente de verdad; hardcodear rgba rompe el sistema cuando el acento cambia de tema.

- **[M2] text-accent en CTA "close" del modal** → `DocPreviewModal:208`
  ```tsx
  <button … className="flex-none font-mono text-[12px] text-accent">{t('exp.preview.close')}</button>
  ```
  "Close" es una acción de navegación, no una señal viva. §1.3: orange sólo marca live/active/critical. Fix: `text-ink-1` o `text-ink-2 hover:text-ink-1`.

---

## LOW (opcional / backlog)

- **[L1] TagsFilter inline tags — falta hairline de ring accent** → `TagsFilter:114`
  Los tag-chips activos del Chip component llevan `boxShadow: inset 0 0 0 1px rgba(245,99,30,0.4)`. Los inline chips en TagsFilter usan solo el background sin hairline. Inconsistencia visual menor entre los dos patrones de chip.

- **[L2] Modal scrim — negro sin tinte** → `DocPreviewModal:201`
  ```tsx
  style={{ background: 'rgba(0,0,0,0.45)' }}
  ```
  §1 principio 2: "Tint every neutral toward the brand hue." El midnight (bd-2 dark `#0c0f14`) es la referencia para fondos de overlay. Fix: `rgba(8,10,14,0.52)` (tinte midnight) o una var de scrim en tokens.

---

## Verificaciones PASS

| Check | Resultado |
|---|---|
| Floor 9.5px — ningún texto por debajo | ✅ mínimo encontrado 9.5px (labels select, section path modal) |
| ink-3 (#625c52) sobre inset (~#e8e6e2 efectivo) | ✅ 5.3:1 — WCAG AA para texto pequeño |
| ink-3 sobre card-bg (~#f2f0ec) | ✅ ~5.97:1 |
| accent sólo para señal activa (chips filter, scope indicator) | ✅ semántica correcta |
| Side-stripe borders | ✅ ninguno |
| Gradient text | ✅ ninguno |
| Identical card grids | ✅ ninguno |
| GlassCard modal — uso estructural no decorativo | ✅ |
| Jerarquía panel Advanced (row chips → grid selects) | ✅ agrupación clara, no satura |
| prefers-reduced-motion en GlassCard base | ✅ (AT3 en index.css cubierto) |
| DocRow: text-[13px] ink-1, meta text-[10.5px] ink-3 | ✅ |
| Modal title text-[14px] ink-1, subtitle text-[10.5px] ink-3 | ✅ |
| Chunk content text-[12.5px] leading-relaxed | ✅ §2 line-height |

---

## Score
Visual: 8/10 | Anti-slop: 9/10 | Total: 8.5/10

*(Voice no evaluada — no hay copy original en scope de esta tarea)*

## Verdict
**CHANGES NEEDED**

H1 + M1 + M2 bloquean publicación limpia. L1/L2 son backlog.
Correcciones: retry → `text-ink-1 underline`, close → `text-ink-1`/`text-ink-2`, rgba → color-mix en 4 puntos.
