import { contextBridge, ipcRenderer } from 'electron';
import type { EcodbBridge, EcodbSseEvent } from './types/electron';

// The renderer talks to the API only through this bridge. The MAIN process
// owns the API key and attaches the Bearer header inside fetch/sse — the key
// is never sent to the renderer. There is deliberately NO getToken/getApiKey
// (Spec §13; contradicts DASHBOARD_BACKEND_GUIDE.md §1, which is wrong).
let sseSeq = 0;

const bridge: EcodbBridge = {
  fetch: (path, opts) => ipcRenderer.invoke('ecodb:fetch', { path, opts }),

  sse: (path, onEvent) => {
    const id = `sse_${Date.now()}_${sseSeq++}`;
    const channel = `ecodb:sse:${id}`;
    const listener = (_e: unknown, payload: EcodbSseEvent) => onEvent(payload);
    ipcRenderer.on(channel, listener);
    void ipcRenderer.invoke('ecodb:sse:start', { id, path });
    return () => {
      ipcRenderer.removeListener(channel, listener);
      void ipcRenderer.invoke('ecodb:sse:stop', { id });
    };
  },

  setApiKey: (key) => ipcRenderer.invoke('ecodb:setApiKey', key),
  // Sync so an auth gate can read it without awaiting; returns a pure boolean.
  hasApiKey: () => ipcRenderer.sendSync('ecodb:hasApiKey') as boolean,
  clearApiKey: () => ipcRenderer.invoke('ecodb:clearApiKey'),
  saveFile: (content, filename) => ipcRenderer.invoke('ecodb:saveFile', { content, filename }),
  uploadDocument: (args) => ipcRenderer.invoke('ecodb:uploadDocument', args),
  getConfig: () => ipcRenderer.invoke('ecodb:getConfig'),
  setConfig: (cfg) => ipcRenderer.invoke('ecodb:setConfig', cfg),
};

contextBridge.exposeInMainWorld('ecodb', bridge);
