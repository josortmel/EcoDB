import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewStore, type ViewId } from '../stores/view';
import { useAuthStore } from '../stores/auth';
import { BrandMark } from './BrandMark';

type IconProps = { className?: string };
const icon = (path: ReactNode) =>
  function NavIcon({ className }: IconProps) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} width={17} height={17} className={className}>
        {path}
      </svg>
    );
  };

const ICONS: Record<ViewId, (p: IconProps) => ReactNode> = {
  command: icon(
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>,
  ),
  explorer: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
    </>,
  ),
  graph: icon(
    <>
      <circle cx="6" cy="17" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="17" cy="17" r="2" />
      <circle cx="9" cy="7" r="2" />
      <path d="M8 16l8-8M9 9l7 7" />
    </>,
  ),
  decisions: icon(
    <>
      <path d="M3 13l3-8h12l3 8v5a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      <path d="M3 13h5l1 2h6l1-2h5" />
    </>,
  ),
  ingestion: icon(
    <path d="M12 3v10m0 0l-4-4m4 4l4-4M5 17v2a2 2 0 002 2h10a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round" />,
  ),
  ontology: icon(
    <>
      <circle cx="12" cy="6" r="3" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M10 8l-3.5 7M14 8l3.5 7" />
    </>,
  ),
  settings: icon(
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
    </>,
  ),
  insights: icon(<path d="M4 19V5M4 19h16M8 16l3-4 3 2 4-6" strokeLinecap="round" strokeLinejoin="round" />),
};

// §2.9 per-section color — the active item reads as a legend entry.
const SECTION_COLOR: Record<ViewId, string> = {
  command: 'var(--sec-command)',
  explorer: 'var(--sec-explorer)',
  graph: 'var(--sec-graph)',
  decisions: 'var(--sec-decisions)',
  ingestion: 'var(--sec-ingestion)',
  ontology: 'var(--sec-ontology)',
  settings: 'var(--sec-settings)',
  insights: 'var(--sec-insights)',
};

const GROUPS: { key: 'workspace' | 'governance'; items: ViewId[] }[] = [
  { key: 'workspace', items: ['command', 'explorer', 'graph', 'decisions'] },
  { key: 'governance', items: ['ingestion', 'ontology', 'settings'] },
];

function NavItem({ id }: { id: ViewId }) {
  const { t } = useTranslation();
  const active = useViewStore((s) => s.view === id);
  const setView = useViewStore((s) => s.setView);
  const Icon = ICONS[id];
  const color = SECTION_COLOR[id];

  return (
    <button
      type="button"
      data-testid={`nav-${id}`}
      onClick={() => setView(id)}
      aria-current={active ? 'page' : undefined}
      className={`relative flex w-full items-center gap-[11px] rounded-[11px] px-[11px] py-[9px] text-left font-body text-[13px] transition-colors ${
        active ? 'font-semibold text-ink-1' : 'text-ink-2 hover:text-ink-1'
      }`}
      style={
        active
          ? {
              background: 'var(--card-bg)',
              boxShadow: 'inset 0 0 0 1px var(--card-hairline), 0 1px 2px rgba(0,0,0,0.12)',
            }
          : undefined
      }
    >
      {active && (
        <span
          className="absolute -left-3 top-1/2 h-[18px] w-[3px] -translate-y-1/2 rounded-[3px]"
          style={{ background: color, boxShadow: `0 0 8px ${color}` }}
        />
      )}
      <span className="grid flex-none place-items-center" style={active ? { color } : undefined}>
        <Icon />
      </span>
      <span className="min-w-0 flex-1 truncate">{t(`nav.${id}`)}</span>
      {active && (
        <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      )}
    </button>
  );
}

function NavUser() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);
  const initial = user?.name?.[0]?.toUpperCase() ?? '?';

  return (
    <div
      className="mt-2 flex items-center gap-2.5 rounded-xl p-2.5"
      style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <span
        className="grid h-7 w-7 flex-none place-items-center rounded-md font-mono text-[12px]"
        style={{ background: 'var(--ink-4)', color: 'var(--ink-2)' }}
      >
        {initial}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12.5px] text-ink-1">{user?.name ?? '—'}</div>
        <div className="truncate font-mono text-[9.5px] text-ink-2">{user?.email ?? ''}</div>
      </div>
      <button
        type="button"
        data-testid="nav-signout"
        onClick={() => void signOut()}
        aria-label={t('commandCenter.signOut')}
        className="flex-none text-ink-3 transition-colors hover:text-ink-1"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} width={16} height={16}>
          <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}

// Active item gets the section color on its icon (via currentColor) + left bar +
// LED dot. Inactive items stay ink. Glass tray (not a card).
export function NavRail() {
  const { t } = useTranslation();

  return (
    <nav
      aria-label={t('nav.label')}
      className="z-[2] flex min-h-0 flex-col gap-[6px] overflow-y-auto rounded-xl p-4"
      style={{
        background: 'var(--tray-bg)',
        backdropFilter: 'blur(22px) saturate(1.3)',
        WebkitBackdropFilter: 'blur(22px) saturate(1.3)',
        boxShadow: 'var(--tray-shadow)',
      }}
    >
      <div className="flex items-center gap-[11px] px-2 pb-4 pt-1.5 text-ink-1">
        <BrandMark size={28} />
        <span className="font-mono text-[14px] text-ink-1">EcoDB</span>
      </div>

      {GROUPS.map((group) => (
        <div key={group.key} className="flex flex-col gap-[6px]">
          <div className="px-2.5 pb-1.5 pt-3.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">
            {t(`nav.group.${group.key}`)}
          </div>
          {group.items.map((id) => (
            <NavItem key={id} id={id} />
          ))}
        </div>
      ))}

      <div className="flex-1" />
      <NavItem id="insights" />
      <NavUser />
    </nav>
  );
}
