import type { TFunction } from 'i18next';
import { ApiError } from './api';

// FastAPI 422 detail → "field: msg; field: msg". null if it isn't a 422 array.
function detail422(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const o = d as { loc?: (string | number)[]; msg?: string };
        const field = (o.loc ?? []).slice(-1)[0] ?? 'field';
        return `${field}: ${o.msg ?? ''}`;
      })
      .join('; ');
  }
  return null;
}

// Single shared error→message mapper for the mutation surfaces (MemoryDrawer,
// TemplateModal, DecisionsInbox). Surfaces real 422 field errors so schema drift
// stays visible, but NEVER echoes a server `detail` string for any other status —
// non-422 errors fall back to the generic message (info-disclosure guard,
// VS-DRAW-L1). Handles 429 (with Retry-After) and 403 from shared keys.
export function errMsg(err: unknown, t: TFunction, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return err.retryAfter != null ? t('errors.rateLimitedWait', { secs: err.retryAfter }) : t('errors.rateLimited');
    }
    if (err.status === 403) return t('errors.forbidden');
    if (err.status === 422) {
      const d = detail422(err.body);
      if (d) return d;
    }
  }
  return fallback;
}
