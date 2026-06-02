import { describe, it, expect } from 'vitest';
import type { Query } from '@tanstack/react-query';
import { shouldPersist } from '../lib/persist';

const q = (queryKey: unknown[], status: 'success' | 'error' | 'pending' = 'success') =>
  ({ queryKey, state: { status } }) as unknown as Query;

// Requirement: cache only non-sensitive read views; never auth/me, inbox
// details, graph, or non-success queries.
describe('shouldPersist (dehydration allowlist)', () => {
  it('persists stats, inbox summary, search, recent memories', () => {
    expect(shouldPersist(q(['stats', 'memories']))).toBe(true);
    expect(shouldPersist(q(['stats', 'timeline', 30]))).toBe(true);
    expect(shouldPersist(q(['inbox', 'summary']))).toBe(true);
    expect(shouldPersist(q(['search', { query_text: 'x' }]))).toBe(true);
    expect(shouldPersist(q(['memories', 'recent', 20]))).toBe(true);
  });

  it('does NOT persist auth/me, inbox details, or graph', () => {
    expect(shouldPersist(q(['auth', 'me']))).toBe(false);
    expect(shouldPersist(q(['inbox', 'details', 'stale_memories', 20, 0]))).toBe(false);
    expect(shouldPersist(q(['graph', 'subgraph', 'EcoDB', 2]))).toBe(false);
  });

  it('does NOT persist non-success queries', () => {
    expect(shouldPersist(q(['stats', 'memories'], 'error'))).toBe(false);
    expect(shouldPersist(q(['stats', 'memories'], 'pending'))).toBe(false);
  });
});
