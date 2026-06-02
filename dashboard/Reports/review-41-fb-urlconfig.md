# Review — #41 FB-URLCONFIG (Settings.tsx — ConnectionPanel)
Date: 2026-06-02 | Against: DESIGN.md + tokens.css | Product: EcoDB Dashboard

> Visual verification via Playwright no completada — app requiere auth en :5173.
> Hallazgos por análisis de código + cálculo WCAG manual.

---

## MEDIUM (fix before publishing)

- **[M1] Focus ring ausente en input URL** → `ConnectionPanel:162`
  ```tsx
  className="… focus:outline-none"
  ```
  `focus:outline-none` elimina el focus indicator del browser sin reemplazo. WCAG 2.4.7 (Focus Visible — AA) requiere un indicador visible para navegación por teclado. SearchField sí tiene el patrón correcto (JS onFocus/onBlur + boxShadow condicional en el wrapper). El URL input debería seguir el mismo patrón o añadir `focus-visible:ring-2 focus-visible:ring-accent` como mínimo.
  
  **Nota sistémica**: mismo patrón en ScopeSelect:87 y TagsFilter:133 — candidatos a la misma corrección.

---

## Verificaciones PASS (ConnectionPanel)

| Check | Resultado |
|---|---|
| Label `text-[10px]` — sobre floor 9.5px | ✅ |
| `rounded-md` = `var(--r-md)` = 13px (tailwind.config.ts) | ✅ correcto, no 6px default |
| `rounded-btn` = `var(--r-btn)` = 11px | ✅ |
| CTA `bg-btn-primary` = terracota gradient `#d5704a→#c45d38→#b6502f` | ✅ §3 correcto |
| No `var(--accent)` en CTA (naranja = señal, no acción) | ✅ |
| Disabled `!valid \|\| !dirty` — semántica correcta | ✅ |
| `transition-[filter]` no anima propiedades de layout | ✅ |
| Field: `field-bg` + `card-edge` top inset + `card-hairline` outline | ✅ §2.5 correcto |
| ink-3 (#625c52) sobre field-bg efectivo (~#f9f8f6) | ✅ ~6.2:1 WCAG AA |
| ink-3 sobre inset (~#e8e6e2) — labels 10px | ✅ ~5.3:1 WCAG AA |
| Hint: `text-[11px] leading-relaxed` body font — apropiado para descripción | ✅ §2.2 |
| Restart note: mono 10.5px ink-3 | ✅ |
| Spacing ascendente: label→input 6px / input→hint 8px / hint→button 12px | ✅ ritmo claro |
| Button specular `rgba(255,255,255,0.3)` — top inset, no toca tokens de texto | ✅ |
| Button border `rgba(150,62,32,0.45)` — sin token equivalente (gradient no admite color-mix), aceptable | ✅ |
| Sin side-stripe borders | ✅ |
| Sin gradient text | ✅ |
| Sin glassmorphism decorativo | ✅ |

---

## Observaciones fuera de scope (no puntúan)

- **OBS-1 — ApiKeyManagement:70,75**: `rgba(245,99,30,0.08/0.13/0.3)` hardcoded — mismo patrón CC-M2/EXP-M1. Candidato a corrección en el siguiente batch.
- **OBS-2 — SearchField:57**: `text-white` sobre `bg-accent` (`#F5631E`) a 10px = **3.14:1** — falla WCAG AA (mín. 4.5:1 para texto normal). El badge de result-count del Explorer tiene contraste insuficiente. Requiere review dedicado.

---

## Score
Visual: 9/10 | Anti-slop: 10/10 | Total: 9.5/10

## Verdict
**CHANGES NEEDED**

M1 (focus ring) antes de publicar. El ConnectionPanel visual está bien ejecutado en todos los demás aspectos — terracota CTA correcta, spacing con ritmo, tokens correctos, jerarquía clara.
