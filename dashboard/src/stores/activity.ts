import { create } from 'zustand';

export interface ActivityItem {
  id: string;
  event: string;
  ts: number;
}

interface ActivityState {
  items: ActivityItem[];
  push: (event: string) => void;
}

const MAX = 12;

// Ring buffer of the most recent SSE events, for the Command Center live feed.
// Fed by useSSE; this is ephemeral UI state, never persisted.
export const useActivityStore = create<ActivityState>((set) => ({
  items: [],
  push: (event) =>
    set((s) => ({
      items: [{ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, event, ts: Date.now() }, ...s.items].slice(0, MAX),
    })),
}));
