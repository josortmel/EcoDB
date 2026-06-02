import { create } from 'zustand';
import type { EcodbBridge, EcodbFetchResult } from '../types/electron';

// Shape of GET /auth/me (backend guide §3).
export interface AuthUser {
  user_id: number;
  email: string;
  name: string;
  is_super: boolean;
  is_ceo: boolean;
  organization_id: number;
  lead_workspaces: number[];
}

export type AuthStatus = 'checking' | 'unauthenticated' | 'unreachable' | 'authenticated';
export type AuthError = 'invalid' | 'noSecureStorage' | 'network';

interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  error: AuthError | null;
  submitting: boolean;
  /** Boot: validate any stored key; route to CC / auth / first-run. */
  checkAuth: () => Promise<void>;
  /** Auth screen submit: store the key, then validate against /auth/me. */
  connect: (rawKey: string) => Promise<void>;
  /** First-run "Retry" — re-run the boot check. */
  retry: () => Promise<void>;
  signOut: () => Promise<void>;
}

// window.ecodb only exists inside Electron. In a plain browser it is undefined.
const getBridge = (): EcodbBridge | undefined => window.ecodb;

// The API is unreachable (server down / ECONNREFUSED) vs. a real HTTP response.
// The bridge reports a transport failure as status 0 + error 'network'.
const isNetworkError = (res: EcodbFetchResult): boolean => res.status === 0 || res.error === 'network';

// Best-effort: a failed clear must never strand the state machine.
const safeClear = async (b: EcodbBridge | undefined): Promise<void> => {
  try {
    await b?.clearApiKey();
  } catch {
    /* ignore */
  }
};

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'checking',
  user: null,
  error: null,
  submitting: false,

  checkAuth: async () => {
    const bridge = getBridge();
    if (!bridge || !bridge.hasApiKey()) {
      set({ status: 'unauthenticated' });
      return;
    }
    const res = await bridge.fetch<AuthUser>('/auth/me');
    if (res.ok && res.data) {
      set({ status: 'authenticated', user: res.data, error: null });
    } else if (isNetworkError(res)) {
      // Server is down — keep the key (it may be fine) and show first-run help.
      set({ status: 'unreachable' });
    } else {
      // 401/403/etc — the key is bad. Drop it and ask for a new one.
      await safeClear(bridge);
      set({ status: 'unauthenticated' });
    }
  },

  connect: async (rawKey) => {
    if (get().submitting) return; // atomic guard against double-submit
    const bridge = getBridge();
    if (!bridge) {
      set({ submitting: false, error: 'network' });
      return;
    }
    set({ submitting: true, error: null });

    let stored: boolean;
    try {
      stored = await bridge.setApiKey(rawKey);
    } catch {
      set({ submitting: false, error: 'noSecureStorage' });
      return;
    }
    if (!stored) {
      set({ submitting: false, error: 'invalid' });
      return;
    }

    const res = await bridge.fetch<AuthUser>('/auth/me');
    if (res.ok && res.data) {
      set({ status: 'authenticated', user: res.data, submitting: false, error: null });
    } else if (isNetworkError(res)) {
      // Server down: keep the just-stored key, surface a reachability error.
      set({ submitting: false, error: 'network' });
    } else {
      await safeClear(bridge);
      set({ submitting: false, error: 'invalid' });
    }
  },

  retry: async () => {
    if (get().status === 'checking') return; // already re-checking
    set({ status: 'checking', error: null });
    await get().checkAuth();
  },

  signOut: async () => {
    if (get().status === 'unauthenticated') return; // concurrent 401s collapse to one
    await safeClear(getBridge());
    set({ status: 'unauthenticated', user: null, error: null });
  },
}));
