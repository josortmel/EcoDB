import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { NavRail } from './NavRail';
import { AppBar } from './AppBar';
import { useViewStore, type ViewId } from '../stores/view';
import { usePaletteStore } from '../stores/palette';
import { CommandCenter } from '../pages/CommandCenter';
import { KnowledgeExplorer } from '../pages/KnowledgeExplorer';
import { GraphStudio } from '../pages/GraphStudio';
import { DecisionsInbox } from '../pages/DecisionsInbox';
import { OntologyConsole } from '../pages/OntologyConsole';
import { Ingestion } from '../pages/Ingestion';
import { Settings } from '../pages/Settings';
import { MemoryDrawer } from './MemoryDrawer';
import { CommandPalette } from './CommandPalette';
import { TemplateModal } from './TemplateModal';
import { SystemMonitor } from './SystemMonitor';
import { Toasts } from './Toasts';
import { GlassCard } from './GlassCard';
import { ErrorBoundary } from './ErrorBoundary';

// Fallback when a view throws — keeps the shell (nav + appbar) alive.
function ViewError() {
  const { t } = useTranslation();
  return (
    <div className="grid h-full place-items-center p-6">
      <GlassCard className="flex max-w-[420px] flex-col items-center gap-3 p-8 text-center">
        <span className="h-[9px] w-[9px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 8px rgba(222,70,48,0.5)' }} />
        <div className="font-mono text-[14px] text-ink-1">{t('shell.crashTitle')}</div>
        <div className="text-[12px] leading-relaxed text-ink-3">{t('shell.crashHint')}</div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-1 rounded-btn bg-btn-primary px-4 py-2 font-body text-[12.5px] font-semibold text-white"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
        >
          {t('shell.reload')}
        </button>
      </GlassCard>
    </div>
  );
}

// Per-view placeholder. The Command Center content lands in FB-CC part (b);
// the other screens are later tasks.
function ViewPlaceholder({ view }: { view: ViewId }) {
  const { t } = useTranslation();
  return (
    <div className="grid h-full place-items-center">
      <div className="text-center">
        <div className="font-mono text-[15px] text-ink-1">{t(`nav.${view}`)}</div>
        <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{t('shell.comingSoon')}</div>
      </div>
    </div>
  );
}

// The shell used by all 8 screens: glass nav rail + workzone (appbar + scrolling
// content). Desktop-first (Electron min 1280); the content grid handles the
// responsive bento.
export function AppShell() {
  const view = useViewStore((s) => s.view);

  // Global ⌘/Ctrl+K toggles the command palette (FB-CMDK).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        usePaletteStore.getState().toggle();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      {/* Unified 14px gutter: nav rail, top bar, status bar and the card area all
          float over the backdrop with the same margin + tray radius (§1/§3). */}
      <div className="grid h-screen w-screen gap-[14px] overflow-hidden p-[14px]" style={{ gridTemplateColumns: '222px 1fr' }}>
        <NavRail />
        <div className="flex min-h-0 min-w-0 flex-col gap-[14px]">
          <AppBar />
          <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-6 pb-4 pt-1.5">
            {/* key={view} remounts (and resets) the boundary on navigation. */}
            <ErrorBoundary key={view} fallback={<ViewError />}>
              {view === 'command' ? (
                <CommandCenter />
              ) : view === 'explorer' ? (
                <KnowledgeExplorer />
              ) : view === 'graph' ? (
                <GraphStudio />
              ) : view === 'decisions' ? (
                <DecisionsInbox />
              ) : view === 'ontology' ? (
                <OntologyConsole />
              ) : view === 'ingestion' ? (
                <Ingestion />
              ) : view === 'settings' ? (
                <Settings />
              ) : (
                <ViewPlaceholder view={view} />
              )}
            </ErrorBoundary>
          </main>
          {/* Its own boundary — the ambient bar must never take down the column. */}
          <ErrorBoundary fallback={null}>
            <SystemMonitor />
          </ErrorBoundary>
        </div>
      </div>
      <MemoryDrawer />
      <CommandPalette />
      <TemplateModal />
      <Toasts />
    </>
  );
}
