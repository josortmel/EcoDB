import { create } from 'zustand';

// "New memory" guided-template modal open state (FB-TPL). UI-only; opened from
// the AppBar "+" action.
interface ComposeState {
  open: boolean;
  openCompose: () => void;
  closeCompose: () => void;
}

export const useComposeStore = create<ComposeState>((set) => ({
  open: false,
  openCompose: () => set({ open: true }),
  closeCompose: () => set({ open: false }),
}));
