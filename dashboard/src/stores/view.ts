import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ViewId =
  | 'command'
  | 'explorer'
  | 'graph'
  | 'decisions'
  | 'ingestion'
  | 'ontology'
  | 'memory-agent'
  | 'settings'
  | 'insights';

export type Density = 'comfortable' | 'compact';

export interface DrawerTarget {
  kind: 'memory' | 'node' | 'document' | 'agent';
  id: string;
}

// UI / view state only — NEVER server state (that's TanStack Query). Born with
// the app shell (FB9 / 6.10).
interface ViewState {
  view: ViewId;
  density: Density;
  drawer: DrawerTarget | null;
  /** One-shot seed for the Explorer (e.g. ⌘K → document result carries its query). */
  explorerSeed: { query: string; tab: 'memories' | 'documents' } | null;
  /** System Monitor bottom bar expanded/collapsed (persisted, like density). */
  sysExpanded: boolean;
  setView: (view: ViewId) => void;
  setDensity: (density: Density) => void;
  toggleDensity: () => void;
  openDrawer: (target: DrawerTarget) => void;
  closeDrawer: () => void;
  seedExplorer: (query: string, tab: 'memories' | 'documents') => void;
  consumeExplorerSeed: () => void;
  toggleSys: () => void;
}

export const useViewStore = create<ViewState>()(
  persist(
    (set) => ({
      view: 'command',
      density: 'comfortable',
      drawer: null,
      explorerSeed: null,
      sysExpanded: false,
      setView: (view) => set({ view }),
      setDensity: (density) => set({ density }),
      toggleDensity: () => set((s) => ({ density: s.density === 'comfortable' ? 'compact' : 'comfortable' })),
      openDrawer: (drawer) => set({ drawer }),
      closeDrawer: () => set({ drawer: null }),
      seedExplorer: (query, tab) => set({ explorerSeed: { query, tab } }),
      consumeExplorerSeed: () => set({ explorerSeed: null }),
      toggleSys: () => set((s) => ({ sysExpanded: !s.sysExpanded })),
    }),
    // Only UI preferences persist (density + monitor expanded); the active view,
    // drawer and seeds are ephemeral (always start on the command view).
    { name: 'ecodb-view', partialize: (s) => ({ density: s.density, sysExpanded: s.sysExpanded }) },
  ),
);
