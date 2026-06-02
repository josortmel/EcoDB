import { create } from 'zustand';
import type { ScoreBreakdown } from '../types/api';

// Full memory data for the right-side detail drawer (superset of the row data).
export interface MemoryDetail {
  id: string;
  content: string;
  type: string;
  tags: string[];
  agent: string | null;
  ts: string;
  visibility?: string;
  stale?: boolean;
  hot?: boolean;
  trustWarnings?: string[];
  scoreBreakdown?: ScoreBreakdown;
}

// Only the user-editable fields can be patched into the open memory.
export type MemoryPatch = Partial<Pick<MemoryDetail, 'content' | 'type' | 'visibility' | 'tags' | 'stale'>>;

interface DetailState {
  memory: MemoryDetail | null;
  open: (memory: MemoryDetail) => void;
  patch: (fields: MemoryPatch) => void;
  close: () => void;
}

export const useDetailStore = create<DetailState>((set) => ({
  memory: null,
  open: (memory) => set({ memory }),
  // Merge edited fields into the open memory so the drawer reflects a save
  // without waiting on the list refetch.
  patch: (fields) => set((s) => (s.memory ? { memory: { ...s.memory, ...fields } } : s)),
  close: () => set({ memory: null }),
}));
