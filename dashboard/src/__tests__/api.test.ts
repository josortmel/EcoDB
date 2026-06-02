import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiGet, ApiError } from '../lib/api';
import { useAuthStore } from '../stores/auth';
import type { EcodbBridge, EcodbFetchResult } from '../types/electron';

const setFetch = (fn: () => Promise<EcodbFetchResult>) => {
  (window as unknown as { ecodb?: Partial<EcodbBridge> }).ecodb = { fetch: fn as EcodbBridge['fetch'] };
};

// Requirement: the wrapper must normalize bridge results and react to auth /
// rate-limit / transport failures correctly.
describe('api request wrapper', () => {
  beforeEach(() => {
    (window as unknown as { ecodb?: unknown }).ecodb = undefined;
    vi.restoreAllMocks();
  });

  it('returns data on ok', async () => {
    setFetch(async () => ({ ok: true, status: 200, data: { hello: 'world' } }));
    await expect(apiGet('/x')).resolves.toEqual({ hello: 'world' });
  });

  it('401 → ApiError(401) and signs out', async () => {
    const signOut = vi.spyOn(useAuthStore.getState(), 'signOut').mockResolvedValue();
    setFetch(async () => ({ ok: false, status: 401, data: null }));
    await expect(apiGet('/x')).rejects.toMatchObject({ status: 401 });
    expect(signOut).toHaveBeenCalledOnce();
  });

  it('429 → ApiError carries retryAfter', async () => {
    setFetch(async () => ({ ok: false, status: 429, data: null, retryAfter: 7 }));
    await expect(apiGet('/x')).rejects.toMatchObject({ status: 429, retryAfter: 7 });
  });

  it('network failure → ApiError(0)', async () => {
    setFetch(async () => ({ ok: false, status: 0, data: null, error: 'network' }));
    await expect(apiGet('/x')).rejects.toMatchObject({ status: 0 });
  });

  it('no bridge → ApiError', async () => {
    await expect(apiGet('/x')).rejects.toBeInstanceOf(ApiError);
  });
});
