import { useAuthStore } from '../stores/auth';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly retryAfter?: number,
    public readonly body?: unknown, // the parsed error payload (e.g. FastAPI 422 {detail:[...]})
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

// All API traffic goes through the main-process bridge (which attaches the
// Bearer key). This wrapper normalizes the result: data on success, a typed
// ApiError otherwise. A 401 means the session is dead → sign out.
async function request<T>(path: string, opts?: RequestOptions): Promise<T> {
  // window.ecodb is always present in Electron (preload runs first). The guard
  // stays only so tests / a plain-browser preview fail cleanly.
  const bridge = window.ecodb;
  if (!bridge) throw new ApiError(0, 'bridge_unavailable');

  const res = await bridge.fetch<T>(path, opts);
  if (res.ok) return res.data as T;

  if (res.status === 401) {
    void useAuthStore.getState().signOut();
    throw new ApiError(401, 'unauthorized');
  }
  if (res.status === 429) throw new ApiError(429, 'rate_limited', res.retryAfter, res.data);
  if (res.error === 'network' || res.status === 0) throw new ApiError(0, 'network');
  throw new ApiError(res.status, `http_${res.status}`, undefined, res.data);
}

export const apiGet = <T>(path: string): Promise<T> => request<T>(path);
export const apiPost = <T>(path: string, body: unknown): Promise<T> => request<T>(path, { method: 'POST', body });
export const apiPut = <T>(path: string, body: unknown): Promise<T> => request<T>(path, { method: 'PUT', body });
export const apiDelete = <T>(path: string): Promise<T> => request<T>(path, { method: 'DELETE' });
