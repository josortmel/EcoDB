import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StatusPill } from './StatusPill';
import { ThemeToggle } from './ThemeToggle';
import { usePaletteStore } from '../stores/palette';
import { useComposeStore } from '../stores/compose';
import { cmdKBadge } from '../lib/platform';

// "New memory" — opens the guided-template modal (FB-TPL).
function NewMemoryButton() {
  const { t } = useTranslation();
  const openCompose = useComposeStore((s) => s.openCompose);
  return (
    <button
      type="button"
      onClick={openCompose}
      data-testid="new-memory"
      className="flex h-11 flex-none items-center gap-2 rounded-md px-3.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105"
      style={{ background: 'var(--btn-primary)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={15} height={15}><path d="M12 5v14M5 12h14" strokeLinecap="round" /></svg>
      {t('tpl.title')}
    </button>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const time = now.toLocaleTimeString('en-US', { hour12: false });
  const date = now.toLocaleDateString('en-US', { weekday: 'short', day: '2-digit', month: 'short' });
  return (
    <div className="flex flex-col gap-0.5 text-right font-mono text-[11px] leading-none text-ink-3">
      <span className="tabular-nums tracking-[0.04em]">{time}</span>
      <span className="text-ink-2">{date}</span>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} width={16} height={16}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
    </svg>
  );
}

// Global search field. Opens the ⌘K command palette (FB-CMDK).
function GlobalSearch() {
  const { t } = useTranslation();
  const openPalette = usePaletteStore((s) => s.openPalette);
  return (
    <button
      type="button"
      onClick={openPalette}
      aria-label={t('appbar.searchPlaceholder')}
      className="flex h-11 min-w-0 max-w-[540px] flex-1 items-center gap-[11px] rounded-md px-4 text-left transition-colors hover:text-ink-2"
      style={{
        background: 'var(--field-bg)',
        boxShadow: 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline), 0 1px 0 var(--inset-edge)',
      }}
    >
      <span className="flex-none text-ink-3">
        <SearchIcon />
      </span>
      <span className="min-w-0 flex-1 truncate font-body text-[13.5px] text-ink-3">{t('appbar.searchPlaceholder')}</span>
      <span
        className="flex-none rounded-md px-[7px] py-[3px] font-mono text-[10.5px] text-ink-3"
        style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
      >
        {cmdKBadge}
      </span>
    </button>
  );
}

// Floating glass tray (not a card). Sits across the top of the workzone, inset
// by the shell's 14px gutter and rounded to the tray radius (matches the rail).
export function AppBar() {
  return (
    <header
      className="flex flex-none items-center gap-4 overflow-hidden rounded-xl px-6 py-4"
      style={{
        background: 'var(--tray-bg)',
        backdropFilter: 'blur(22px) saturate(1.3)',
        WebkitBackdropFilter: 'blur(22px) saturate(1.3)',
        boxShadow: 'var(--tray-shadow)',
      }}
    >
      <GlobalSearch />
      <div className="flex-1" />
      <NewMemoryButton />
      <StatusPill />
      <Clock />
      <ThemeToggle />
    </header>
  );
}
