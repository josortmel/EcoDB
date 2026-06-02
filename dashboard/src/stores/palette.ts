import { create } from 'zustand';

// ⌘K command palette open/close. UI-only state (born FB-CMDK / 6.22). The global
// shortcut lives in AppShell; the AppBar search field opens it too.
interface PaletteState {
  open: boolean;
  openPalette: () => void;
  closePalette: () => void;
  toggle: () => void;
}

export const usePaletteStore = create<PaletteState>((set) => ({
  open: false,
  openPalette: () => set({ open: true }),
  closePalette: () => set({ open: false }),
  toggle: () => set((s) => ({ open: !s.open })),
}));
