// The window.ecodb bridge contract (Spec §13). The renderer programs against
// this; the MAIN process owns the API key and attaches it — the key never
// crosses into the renderer. There is deliberately NO getToken/getApiKey.

export interface EcodbFetchResult<T = unknown> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: 'no_api_key' | 'network' | 'invalid_path';
  /** Seconds from the Retry-After header on a 429, when present. */
  retryAfter?: number;
}

export interface EcodbFetchOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

export interface EcodbSseEvent {
  event: string;
  data: string;
}

export interface EcodbBridge {
  /** Main attaches `Authorization: Bearer <key>`. Renderer never sees the key. */
  fetch<T = unknown>(path: string, opts?: EcodbFetchOptions): Promise<EcodbFetchResult<T>>;
  /** Main opens the SSE stream with the Bearer header and forwards frames.
   *  Returns an unsubscribe that closes the stream. */
  sse(path: string, onEvent: (event: EcodbSseEvent) => void): () => void;
  /** Auth screen only (FB3). Trims + rejects empty. Stored encrypted in main. */
  setApiKey(key: string): Promise<boolean>;
  /** Pure boolean — never the key nor a hash of it. */
  hasApiKey(): boolean;
  /** For 401 / manual rotation. */
  clearApiKey(): Promise<void>;
  saveFile(content: string, filename: string): Promise<{ ok: boolean; path?: string; canceled?: boolean }>;
  /** Opens the native picker, reads the chosen file, and POSTs its content (multipart)
   *  to /documents/upload. The host path never crosses to the renderer. */
  uploadDocument(args: { project_id?: number; visibility?: 'public' | 'private' }): Promise<{
    ok: boolean;
    status?: number;
    data?: unknown;
    filename?: string;
    error?: string;
    canceled?: boolean;
  }>;
  /** App config (#41) — the configurable API base URL. */
  getConfig(): Promise<{ apiBaseUrl: string }>;
  setConfig(cfg: { apiBaseUrl: string }): Promise<{ ok: boolean; error?: string }>;
}

declare global {
  interface Window {
    ecodb: EcodbBridge;
  }
}
