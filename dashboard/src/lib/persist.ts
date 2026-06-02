import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import type { Query } from '@tanstack/react-query';

// localStorage (not electron-store): the renderer can't reach electron-store
// (main-only), and routing a kv-store through the bridge would add IPC surface.
// localStorage in the Electron renderer persists across launches and is the
// idiomatic TanStack persist target.
export const persister = createSyncStoragePersister({
  // Guard so importing this module in a pure node test env doesn't throw.
  storage: typeof window !== 'undefined' ? window.localStorage : (undefined as never),
  key: 'ecodb-qc-cache',
});

export const CACHE_MAX_AGE = 1000 * 60 * 60 * 24; // 24h TTL
// MUST bump whenever a persisted query's response shape in types/api.ts changes
// (a buster mismatch discards the stale-shaped cache on load).
export const CACHE_BUSTER = 'v0.1.0';

// Persist only non-sensitive, cheap-to-rehydrate read views: all stats
// (memories/graph/agents/search/system/knowledge/timeline), the inbox summary,
// and the last search / recent-memories (Explorer). NEVER auth/me, inbox details
// (large + paginated), or graph payloads. The API key is never a query result —
// it lives in safeStorage and never reaches the cache.
const PERSIST_PREFIXES: readonly (readonly string[])[] = [
  ['stats'],
  ['inbox', 'summary'],
  ['search'],
  ['memories', 'recent'],
];

const keyHasPrefix = (key: readonly unknown[], prefix: readonly string[]): boolean =>
  prefix.every((p, i) => key[i] === p);

export function shouldPersist(query: Query): boolean {
  if (query.state.status !== 'success') return false;
  return PERSIST_PREFIXES.some((p) => keyHasPrefix(query.queryKey, p));
}
