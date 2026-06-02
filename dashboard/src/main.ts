import { app, BrowserWindow, ipcMain, dialog, session } from 'electron';
import path from 'node:path';
import { writeFile, readFile, stat } from 'node:fs/promises';
import { hasApiKey, setApiKey, clearApiKey, decryptApiKey } from './secure-store';
import { getApiBase, setApiBase } from './config-store';
import { resolveApiUrl } from './lib/api-url';
import { parseSseFrame, nextBoundary } from './lib/sse';

// Pin the app name BEFORE any electron-store is instantiated (the stores are
// lazy for this reason). Otherwise app.getName() can resolve to "Electron" on
// some dev launches and "ecodb-dashboard" on others → two different userData
// dirs → the persisted API key saved under one isn't found under the other, so
// the app keeps asking for the key on every start.
app.setName('ecodb-dashboard');

const APP_ROOT = path.join(__dirname, '..');
process.env.APP_ROOT = APP_ROOT;
const RENDERER_DIST = path.join(APP_ROOT, 'dist');
const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL;
const IS_DEV = Boolean(VITE_DEV_SERVER_URL);

let win: BrowserWindow | null = null;

// Extensions the backend can ingest — single source of truth for both the dialog
// filters and the allowlist gate (defense-in-depth: never read a .env/.key/etc.).
const UPLOAD_DOC_EXT = ['pdf', 'docx', 'html', 'htm', 'md', 'txt'];
const UPLOAD_AUDIO_EXT = ['mp3', 'wav', 'm4a', 'ogg', 'flac'];
const UPLOAD_ALLOWED_EXT = new Set([...UPLOAD_DOC_EXT, ...UPLOAD_AUDIO_EXT]);
// Fail fast before slurping a huge file into main memory (PF-1).
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB

// ── Content-Security-Policy ──────────────────────────────────────────────
// Prod is the exact policy from Spec §4 (no 'unsafe-eval'). Dev relaxes only
// what Vite HMR needs (ws: + 'unsafe-eval'), gated on VITE_DEV_SERVER_URL.
function cspFor(dev: boolean): string {
  if (dev) {
    return [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "connect-src 'self' ws://localhost:* http://localhost:*",
      "img-src 'self' data:",
      "font-src 'self' data:",
    ].join('; ');
  }
  // connect-src follows the configured API base (#41) — default localhost:8080,
  // or whatever the user set in Settings. Applied at boot; a URL change needs a
  // restart to re-issue the policy.
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    `connect-src 'self' ${getApiBase()}`,
    "img-src 'self' data:",
  ].join('; ');
}

function installSessionSecurity(): void {
  const csp = cspFor(IS_DEV);
  session.defaultSession.webRequest.onHeadersReceived((details, cb) => {
    const headers = { ...details.responseHeaders };
    for (const k of Object.keys(headers)) {
      if (k.toLowerCase() === 'content-security-policy') delete headers[k];
    }
    headers['Content-Security-Policy'] = [csp];
    cb({ responseHeaders: headers });
  });
  // Deny every permission request (camera, geolocation, notifications, …).
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, done) => done(false));
}

// SSE frame parsing lives in ./lib/sse (unit-tested for LF/CRLF/CR).

// ── IPC bridge handlers ──────────────────────────────────────────────────
// The key is read here (decryptApiKey) only to attach the Bearer header. It
// never crosses to the renderer.
function registerIpc(): void {
  ipcMain.handle(
    'ecodb:fetch',
    async (_e, args: { path: string; opts?: { method?: string; body?: unknown; headers?: Record<string, string> } }) => {
      // SSRF guard (FB2-H1): the path must resolve to the API origin — never
      // off-host. Otherwise the Bearer key could be sent to an attacker.
      const target = resolveApiUrl(args.path, getApiBase());
      if (!target) return { ok: false, status: 400, data: null, error: 'invalid_path' };
      const key = decryptApiKey();
      if (!key) return { ok: false, status: 401, data: null, error: 'no_api_key' };
      try {
        const res = await fetch(target, {
          method: args.opts?.method ?? 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...(args.opts?.headers ?? {}),
            Authorization: `Bearer ${key}`,
          },
          body:
            args.opts?.body == null
              ? undefined
              : typeof args.opts.body === 'string'
                ? args.opts.body
                : JSON.stringify(args.opts.body),
        });
        const text = await res.text();
        let data: unknown = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch {
            data = text;
          }
        }
        const result: { ok: boolean; status: number; data: unknown; retryAfter?: number } = {
          ok: res.ok,
          status: res.status,
          data,
        };
        if (res.status === 429) {
          // Only honor a finite, positive Retry-After. A missing header
          // (Number(null) === 0) or "Infinity" must fall back to the backoff.
          const raw = res.headers.get('Retry-After');
          if (raw !== null) {
            const secs = Number(raw);
            if (Number.isFinite(secs) && secs > 0) result.retryAfter = secs;
          }
        }
        return result;
      } catch {
        return { ok: false, status: 0, data: null, error: 'network' };
      }
    },
  );

  const sseStreams = new Map<string, AbortController>();

  ipcMain.handle('ecodb:sse:start', (e, args: { id: string; path: string }) => {
    const send = (payload: { event: string; data: string }) => {
      if (!e.sender.isDestroyed()) e.sender.send(`ecodb:sse:${args.id}`, payload);
    };
    const target = resolveApiUrl(args.path, getApiBase());
    if (!target) {
      send({ event: 'error', data: 'invalid_path' });
      return;
    }
    const key = decryptApiKey();
    if (!key) {
      send({ event: 'error', data: 'no_api_key' });
      return;
    }
    const controller = new AbortController();
    sseStreams.set(args.id, controller);
    // BC3: stop the stream if the renderer is destroyed.
    const onDestroyed = () => controller.abort();
    e.sender.once('destroyed', onDestroyed);
    void (async () => {
      try {
        const res = await fetch(target, {
          headers: { Authorization: `Bearer ${key}`, Accept: 'text/event-stream' },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          send({ event: 'error', data: String(res.status) });
          return;
        }
        const decoder = new TextDecoder();
        let buf = '';
        for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
          buf += decoder.decode(chunk, { stream: true });
          let b: ReturnType<typeof nextBoundary>;
          while ((b = nextBoundary(buf)) !== null) {
            const ev = parseSseFrame(buf.slice(0, b.index));
            buf = buf.slice(b.index + b.length);
            if (ev) send(ev);
          }
        }
      } catch (err) {
        if ((err as Error)?.name !== 'AbortError') send({ event: 'error', data: 'stream_closed' });
      } finally {
        if (!e.sender.isDestroyed()) e.sender.removeListener('destroyed', onDestroyed);
        sseStreams.delete(args.id);
      }
    })();
  });

  ipcMain.handle('ecodb:sse:stop', (_e, args: { id: string }) => {
    sseStreams.get(args.id)?.abort();
    sseStreams.delete(args.id);
  });

  ipcMain.handle('ecodb:setApiKey', (_e, key: unknown) => setApiKey(typeof key === 'string' ? key : ''));
  ipcMain.handle('ecodb:clearApiKey', () => {
    clearApiKey();
  });
  // Sync so the renderer can gate on it cheaply; returns a pure boolean.
  ipcMain.on('ecodb:hasApiKey', (e) => {
    e.returnValue = hasApiKey();
  });

  // App config (#41) — the API base URL. Plain config (no secret). A change needs
  // an app restart to re-issue the CSP/connect-src for the new origin.
  ipcMain.handle('ecodb:getConfig', () => ({ apiBaseUrl: getApiBase() }));
  ipcMain.handle('ecodb:setConfig', (_e, cfg: { apiBaseUrl?: unknown }) => setApiBase(cfg?.apiBaseUrl));

  ipcMain.handle('ecodb:saveFile', async (_e, args: { content: string; filename: string }) => {
    if (!win) return { ok: false, canceled: true };
    const r = await dialog.showSaveDialog(win, {
      defaultPath: args.filename,
      filters: [
        { name: 'JSON', extensions: ['json'] },
        { name: 'Text', extensions: ['txt'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (r.canceled || !r.filePath) return { ok: false, canceled: true };
    await writeFile(r.filePath, args.content, 'utf8');
    return { ok: true, path: r.filePath };
  });

  // Multipart upload — the backend runs in Docker and cannot read host paths, so we
  // stream the file's CONTENT (not its path) to POST /documents/upload. The whole flow
  // (dialog → read → POST) lives in main: the host path never crosses to the renderer,
  // and the renderer only supplies project_id/visibility.
  ipcMain.handle('ecodb:uploadDocument', async (_e, args: { project_id?: number; visibility?: 'public' | 'private' }) => {
    if (!win) return { ok: false, canceled: true };
    const r = await dialog.showOpenDialog(win, {
      properties: ['openFile'],
      filters: [
        { name: 'Documents', extensions: UPLOAD_DOC_EXT },
        { name: 'Audio', extensions: UPLOAD_AUDIO_EXT },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (r.canceled || r.filePaths.length === 0) return { ok: false, canceled: true };
    const filePath = r.filePaths[0];
    const filename = path.basename(filePath);
    // Allowlist by extension even via "All Files" — never read/upload a .env/.key/etc.
    const ext = path.extname(filename).slice(1).toLowerCase();
    if (!UPLOAD_ALLOWED_EXT.has(ext)) return { ok: false, status: 0, data: null, error: 'unsupported_type' };
    const key = decryptApiKey();
    if (!key) return { ok: false, status: 401, data: null, error: 'no_api_key' };
    const pid = Number.isInteger(args?.project_id) ? args.project_id : 1;
    const vis = args?.visibility === 'private' ? 'private' : 'public';
    const target = resolveApiUrl(`/documents/upload?project_id=${pid}&visibility=${vis}`, getApiBase());
    if (!target) return { ok: false, status: 400, data: null, error: 'invalid_path' };
    try {
      const st = await stat(filePath);
      if (st.size > MAX_UPLOAD_BYTES) return { ok: false, status: 0, data: null, error: 'file_too_large' };
      const buf = await readFile(filePath);
      // Build the multipart body manually as a Buffer. Electron's main-process
      // fetch does NOT reliably serialize a global (undici) FormData/Blob — the
      // part comes through empty, so the backend never receives the file. A raw
      // Buffer body with an explicit boundary works with any fetch impl.
      const boundary = `----ecodb${Date.now().toString(16)}`;
      const safeName = filename.replace(/["\r\n]/g, '_');
      const head = Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${safeName}"\r\n` +
          `Content-Type: application/octet-stream\r\n\r\n`,
      );
      const tail = Buffer.from(`\r\n--${boundary}--\r\n`);
      const body = Buffer.concat([head, buf, tail]);
      const res = await fetch(target, {
        method: 'POST',
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': `multipart/form-data; boundary=${boundary}` },
        body,
      });
      const text = await res.text();
      let data: unknown = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
      }
      return { ok: res.ok, status: res.status, data, filename };
    } catch {
      return { ok: false, status: 0, data: null, error: 'network' };
    }
  });
}

// ── window ───────────────────────────────────────────────────────────────
function createWindow(): void {
  win = new BrowserWindow({
    width: 1380,
    height: 860,
    minWidth: 1280, // Spec 6.26
    minHeight: 720,
    show: false,
    // #49 — Win11 Mica: a subtle wallpaper-tinted window base. show:false +
    // ready-to-show already prevents the white flash, so a transparent base lets
    // Mica show through at the window chrome. Non-Win32 keeps the opaque bd-2.
    ...(process.platform === 'win32' ? { backgroundMaterial: 'mica' as const, backgroundColor: '#00000000' } : { backgroundColor: '#ddd9d1' }),
    title: 'EcoDB',
    icon: path.join(APP_ROOT, 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      // Primary guard: DevTools cannot open at all in prod (the renderer holds
      // vault data — memories, search, governance — that must not be inspectable).
      devTools: IS_DEV,
    },
  });

  win.once('ready-to-show', () => win?.show());

  // Surface renderer console (incl. any CSP violations) in the terminal — dev only.
  if (IS_DEV) {
    win.webContents.on('console-message', (e) => console.log('[renderer]', e.message));
  }

  // Defense-in-depth alongside devTools:false — if DevTools is ever re-enabled,
  // shut it immediately in prod (adv-seg FB1-M1).
  if (!IS_DEV) {
    win.webContents.on('devtools-opened', () => win?.webContents.closeDevTools());
  }

  // No popups, no external navigation. shell.openExternal is intentionally
  // not wired (no allowlisted external links yet).
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e, url) => {
    // SPA: client-side routing uses the history API (no will-navigate). In prod
    // deny ALL navigation — a controlled file:// path could otherwise read local
    // files (FB2-M1). In dev, allow only the vite dev origin (HMR full reloads).
    if (IS_DEV && VITE_DEV_SERVER_URL && url.startsWith(VITE_DEV_SERVER_URL)) return;
    e.preventDefault();
  });

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'));
  }
}

app.whenReady().then(() => {
  installSessionSecurity();
  registerIpc();
  createWindow();
});

app.on('window-all-closed', () => {
  win = null;
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
