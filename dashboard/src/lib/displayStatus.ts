import type { TFunction } from 'i18next';

// REST document `status` → localized label, falling back to the raw value for
// unseen codes (the field has no declared enum; the SSE queue already uses t()).
export function displayStatus(status: string, t: TFunction): string {
  return (t as (k: string, o?: Record<string, unknown>) => string)(`ing.statusValue.${status}`, { defaultValue: status });
}
