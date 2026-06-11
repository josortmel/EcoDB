import type { TFunction } from 'i18next';

// Shared helpers for the Memory Agent tabs.

export const MA_ACCENT = 'var(--sec-memory-agent)'; // §2.9 memory-agent indigo-violet

// ISO timestamp → YYYY-MM-DD (or em dash when absent).
export const day = (iso?: string | null): string => (iso ? iso.slice(0, 10) : '—');

// Skill status enum → localized label (ma.skills.status{Active|Stale|…}). Keeps
// the chips, row tags, drawer header and status picker consistent.
export const skillStatusLabel = (status: string, t: TFunction): string =>
  (t as (k: string) => string)(`ma.skills.status${status.charAt(0).toUpperCase()}${status.slice(1)}`);

// Skill status → dot color (dot only, status text stays ink — §1.3). Shared by
// the Skills list row and the drawer.
export const SKILL_STATUS_DOT: Record<string, string> = {
  active: 'var(--grn)',
  stale: 'var(--kind-agent)',
  candidate: 'var(--accent)',
  deprecated: 'var(--ink-3)',
};
