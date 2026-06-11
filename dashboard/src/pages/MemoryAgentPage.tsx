import { useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { BriefingTab } from '../components/memory-agent/BriefingTab';
import { TelemetryTab } from '../components/memory-agent/TelemetryTab';
import { ClustersTab } from '../components/memory-agent/ClustersTab';
import { ConfigsTab } from '../components/memory-agent/ConfigsTab';
import { ForesightsTab } from '../components/memory-agent/ForesightsTab';
import { SkillsTab } from '../components/memory-agent/SkillsTab';

const ACCENT = 'var(--sec-memory-agent)'; // §2.9 memory-agent #7a6bc7 (indigo-violet, cognition)

export type MaTab = 'briefing' | 'configs' | 'clusters' | 'foresights' | 'skills' | 'telemetry';

const TABS: { id: MaTab; labelKey: `ma.tab.${MaTab}` }[] = [
  { id: 'briefing', labelKey: 'ma.tab.briefing' },
  { id: 'configs', labelKey: 'ma.tab.configs' },
  { id: 'clusters', labelKey: 'ma.tab.clusters' },
  { id: 'foresights', labelKey: 'ma.tab.foresights' },
  { id: 'skills', labelKey: 'ma.tab.skills' },
  { id: 'telemetry', labelKey: 'ma.tab.telemetry' },
];

function TabButton({
  id,
  active,
  label,
  onClick,
  btnRef,
}: {
  id: MaTab;
  active: boolean;
  label: string;
  onClick: () => void;
  btnRef: (el: HTMLButtonElement | null) => void;
}) {
  return (
    <button
      ref={btnRef}
      type="button"
      role="tab"
      id={`ma-tabbtn-${id}`}
      aria-selected={active}
      aria-controls={`ma-panel-${id}`}
      // roving tabindex (APG tablist pattern): only the active tab is in the
      // tab order; ←/→ move between tabs (handled on the tablist).
      tabIndex={active ? 0 : -1}
      data-testid={`ma-tab-${id}`}
      onClick={onClick}
      className={`rounded-btn px-3.5 py-2 font-body text-[13px] transition-colors ${
        active ? 'font-semibold text-ink-1' : 'text-ink-2 hover:text-ink-1'
      }`}
      style={
        active
          ? {
              // anti-slop: selection by TINT, never a left side-stripe (§ decisiones firmes)
              background: 'color-mix(in srgb, var(--sec-memory-agent) 14%, transparent)',
              boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)',
            }
          : undefined
      }
    >
      {label}
    </button>
  );
}

// Placeholder while the per-tab content lands (built by frontend-builder, T13.3–T13.6).
function TabStub({ tab }: { tab: MaTab }) {
  const { t } = useTranslation();
  return (
    <div className="grid h-full min-h-[260px] place-items-center">
      <div className="text-center">
        <div className="font-mono text-[14px] text-ink-1">{t(`ma.tab.${tab}`)}</div>
        <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{t('ma.comingSoon')}</div>
      </div>
    </div>
  );
}

// "Memory Agent" — the metacognition control surface (EcoDB v1.3). Four tabs:
// Briefing (default — what's happening), Configs (cell workers + providers),
// Clusters (browse/read/approve), Telemetry (runs + health). Standalone page,
// not a Settings subsection — this is the nervous system, not a toggle.
export function MemoryAgentPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<MaTab>('briefing');
  // Shared agent selection for the per-agent views (Foresights + Skills both
  // require agent_identifier). Picked once, persists across the two tabs.
  // Starts undefined; the AgentSelect auto-selects the first agent on load.
  const [agent, setAgent] = useState<string | undefined>(undefined);
  // Cross-tab hand-off: a telescopic row in Briefing opens the Clusters tab
  // focused on that cluster. Held in a ref (no re-render needed — the parent
  // stays mounted across tab switches) so the id survives the switch. The
  // Clusters tab reads focusClusterRef.current on entry (T13.5).
  const focusClusterRef = useRef<string | null>(null);

  const openCluster = (clusterId: string) => {
    focusClusterRef.current = clusterId;
    setTab('clusters');
  };

  // Roving focus across the tablist (APG keyboard pattern): ←/→ wrap, Home/End jump.
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const onTablistKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const idx = TABS.findIndex((tb) => tb.id === tab);
    let next = -1;
    if (e.key === 'ArrowRight') next = (idx + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = TABS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    setTab(TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  let content: ReactNode;
  switch (tab) {
    case 'briefing':
      content = <BriefingTab onOpenCluster={openCluster} />;
      break;
    case 'telemetry':
      content = <TelemetryTab />;
      break;
    case 'clusters':
      // initialClusterId comes from a Briefing telescopic click (ref survives the
      // tab switch); the Clusters tab auto-opens that cluster's drawer on entry.
      content = <ClustersTab initialClusterId={focusClusterRef.current ?? undefined} />;
      break;
    case 'configs':
      content = <ConfigsTab />;
      break;
    case 'foresights':
      content = <ForesightsTab agent={agent} onAgentChange={setAgent} />;
      break;
    case 'skills':
      content = <SkillsTab agent={agent} onAgentChange={setAgent} />;
      break;
    default:
      content = <TabStub tab={tab} />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <header className="flex flex-col gap-1">
        <div className="flex items-center gap-2.5">
          <span className="h-[10px] w-[10px] rounded-full" style={{ background: ACCENT, boxShadow: `0 0 8px ${ACCENT}` }} />
          <h1 className="font-body text-[20px] font-semibold text-ink-1">{t('ma.title')}</h1>
        </div>
        <p className="text-[12.5px] text-ink-3">{t('ma.subtitle')}</p>
      </header>

      <div role="tablist" aria-label={t('ma.title')} onKeyDown={onTablistKeyDown} className="flex flex-wrap gap-1.5">
        {TABS.map((tb, i) => (
          <TabButton
            key={tb.id}
            id={tb.id}
            active={tab === tb.id}
            label={t(tb.labelKey)}
            onClick={() => setTab(tb.id)}
            btnRef={(el) => (tabRefs.current[i] = el)}
          />
        ))}
      </div>

      <div role="tabpanel" id={`ma-panel-${tab}`} aria-labelledby={`ma-tabbtn-${tab}`} tabIndex={0} className="min-h-0 flex-1 outline-none">
        {content}
      </div>
    </div>
  );
}
