import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore, type AuthUser } from '../stores/auth';
import type { EcodbBridge, EcodbFetchResult } from '../types/electron';

// Non-generic fetch so concrete mock results are assignable in tests.
type MockBridge = Omit<EcodbBridge, 'fetch'> & { fetch: () => Promise<EcodbFetchResult<AuthUser>> };

const baseUser: AuthUser = {
  user_id: 1,
  email: 'pepe@eco.dev',
  name: 'Pepe',
  is_super: false,
  is_ceo: false,
  organization_id: 1,
  lead_workspaces: [],
};

function bridge(overrides: Partial<MockBridge>): MockBridge {
  return {
    hasApiKey: () => true,
    setApiKey: async () => true,
    clearApiKey: async () => {},
    fetch: async () => ({ ok: false, status: 401, data: null }),
    sse: () => () => {},
    saveFile: async () => ({ ok: false }),
    uploadDocument: async () => ({ ok: false, canceled: true }),
    getConfig: async () => ({ apiBaseUrl: 'http://localhost:8080' }),
    setConfig: async () => ({ ok: true }),
    ...overrides,
  };
}

const setBridge = (b: MockBridge | undefined) => {
  (window as unknown as { ecodb?: EcodbBridge }).ecodb = b as EcodbBridge | undefined;
};

// FB3/FB4 requirement: the boot check must route to the RIGHT screen — a 401
// (bad key) and a transport failure (server down) are different problems.
describe('auth store routing', () => {
  beforeEach(() => {
    useAuthStore.setState({ status: 'checking', user: null, error: null, submitting: false });
    setBridge(undefined);
  });

  it('no bridge → unauthenticated', async () => {
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().status).toBe('unauthenticated');
  });

  it('network error → unreachable, and the key is kept', async () => {
    const clearApiKey = vi.fn(async () => {});
    setBridge(bridge({ fetch: async () => ({ ok: false, status: 0, data: null, error: 'network' }), clearApiKey }));
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().status).toBe('unreachable');
    expect(clearApiKey).not.toHaveBeenCalled();
  });

  it('401 → unauthenticated, and the key is dropped', async () => {
    const clearApiKey = vi.fn(async () => {});
    setBridge(bridge({ fetch: async () => ({ ok: false, status: 401, data: null }), clearApiKey }));
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().status).toBe('unauthenticated');
    expect(clearApiKey).toHaveBeenCalledOnce();
  });

  it('200 → authenticated with the user', async () => {
    setBridge(bridge({ fetch: async () => ({ ok: true, status: 200, data: baseUser }) }));
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().status).toBe('authenticated');
    expect(useAuthStore.getState().user?.email).toBe('pepe@eco.dev');
  });

  it('connect: network during validation → error network, key kept', async () => {
    const clearApiKey = vi.fn(async () => {});
    setBridge(
      bridge({ setApiKey: async () => true, fetch: async () => ({ ok: false, status: 0, data: null, error: 'network' }), clearApiKey }),
    );
    await useAuthStore.getState().connect('a-key');
    expect(useAuthStore.getState().error).toBe('network');
    expect(clearApiKey).not.toHaveBeenCalled();
  });

  it('connect: 401 → error invalid, key cleared, stays unauthenticated', async () => {
    const clearApiKey = vi.fn(async () => {});
    setBridge(bridge({ setApiKey: async () => true, fetch: async () => ({ ok: false, status: 401, data: null }), clearApiKey }));
    await useAuthStore.getState().connect('a-key');
    expect(useAuthStore.getState().error).toBe('invalid');
    expect(useAuthStore.getState().status).not.toBe('authenticated');
    expect(clearApiKey).toHaveBeenCalledOnce();
  });

  it('connect: keychain unavailable (setApiKey throws) → noSecureStorage', async () => {
    setBridge(
      bridge({
        setApiKey: async () => {
          throw new Error('encryption_unavailable');
        },
      }),
    );
    await useAuthStore.getState().connect('a-key');
    expect(useAuthStore.getState().error).toBe('noSecureStorage');
  });
});
