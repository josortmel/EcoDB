import { create } from 'zustand';

interface PresenceState {
  online: ReadonlySet<string>;
  connect: (identifier: string) => void;
  disconnect: (identifier: string) => void;
  reset: () => void;
}

// Live agent presence, fed by useSSE from agent_connected / agent_disconnected.
// /stats/agents.last_activity reflects the last memory/search, NOT a live link —
// so "online" must come from the event stream, never from last_activity.
// Ephemeral UI state, never persisted; cleared on stream teardown/reconnect.
export const useAgentPresence = create<PresenceState>((set) => ({
  online: new Set<string>(),
  connect: (identifier) =>
    set((s) => {
      if (!identifier || s.online.has(identifier)) return s;
      const next = new Set(s.online);
      next.add(identifier);
      return { online: next };
    }),
  disconnect: (identifier) =>
    set((s) => {
      if (!s.online.has(identifier)) return s;
      const next = new Set(s.online);
      next.delete(identifier);
      return { online: next };
    }),
  reset: () => set({ online: new Set<string>() }),
}));

// The agent_connected/disconnected `data` is a JSON string; the exact field name
// isn't pinned, so try the likely ones.
export function parseAgentId(raw: string): string | null {
  try {
    const p = JSON.parse(raw) as Record<string, unknown>;
    const id = p.agent_identifier ?? p.identifier ?? p.agent ?? p.name;
    return id != null ? String(id) : null;
  } catch {
    return raw || null;
  }
}
