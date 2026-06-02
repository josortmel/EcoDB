import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { highlight } from '../lib/highlight';
import { asArray } from '../lib/asArray';
import { usePaletteStore } from '../stores/palette';
import { useDetailStore, type MemoryDetail } from '../stores/detail';
import { useViewStore } from '../stores/view';
import { useSearch } from '../hooks/search';
import type { SearchResult } from '../types/api';

// §2.8 kind palette. /search only returns memory + document_chunk today, but the
// icon/colour map covers all four signal kinds.
type Kind = 'memory' | 'document' | 'node' | 'agent';
const KIND_COLOR: Record<Kind, string> = {
  memory: 'var(--kind-memory)',
  document: 'var(--kind-document)',
  node: 'var(--kind-node)',
  agent: 'var(--kind-agent)',
};
const kindOf = (r: SearchResult): Kind => (r.source_type === 'document_chunk' ? 'document' : 'memory');

// Module-level (GlassCard pattern): the entrance translate is skipped under
// prefers-reduced-motion; the opacity fade stays (acceptable).
const reduceMotionQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

const day = (iso?: string) => (iso ? iso.slice(0, 10) : '');
const toDetail = (r: SearchResult): MemoryDetail => ({
  id: r.id,
  content: r.content,
  type: r.type,
  tags: r.tags,
  ts: day(r.created_at),
  agent: r.agent_identifier,
  visibility: r.visibility,
  trustWarnings: r.trust_warnings,
  scoreBreakdown: r.score_breakdown,
  stale: false,
});

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} width={17} height={17}>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
    </svg>
  );
}

function KindIcon({ kind }: { kind: Kind }) {
  const color = KIND_COLOR[kind];
  if (kind === 'document') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.7} width={14} height={14}>
        <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" />
        <path d="M14 3v5h5" />
      </svg>
    );
  }
  return <span className="h-[8px] w-[8px] rounded-full" style={{ background: color, boxShadow: `0 0 7px ${color}` }} />;
}

function Hk({ keys, label }: { keys: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <kbd
        className="rounded px-[5px] py-[2px] text-[10px] text-ink-2"
        style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
      >
        {keys}
      </kbd>
      <span>{label}</span>
    </span>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="grid place-items-center py-10 font-mono text-[12px] text-ink-3">{children}</div>;
}

function Shimmer() {
  return (
    <div className="flex flex-col gap-2.5 p-3">
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className="h-[14px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${90 - i * 9}%` }} />
      ))}
    </div>
  );
}

function PaletteInner({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const openDetail = useDetailStore((s) => s.open);
  const setView = useViewStore((s) => s.setView);
  const seedExplorer = useViewStore((s) => s.seedExplorer);
  const reduce = reduceMotionQuery?.matches ?? false;

  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [sel, setSel] = useState(0);
  const [shown, setShown] = useState(false);

  // Debounce input → query so the GAMR call lands well under 500ms (≈220ms + fetch).
  useEffect(() => {
    const id = setTimeout(() => setDebounced(q), 220);
    return () => clearTimeout(id);
  }, [q]);

  const search = useSearch({ query_text: debounced, limit: 8, include_documents: true });
  const results = useMemo<SearchResult[]>(() => asArray<SearchResult>(search.data?.results).slice(0, 8), [search.data]);
  const searching = debounced.trim().length > 0;
  const loading = searching && search.isPending;

  useEffect(() => setSel(0), [results]);

  // Entrance fade (self-contained, no global keyframe).
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Focus management (a11y): capture the trigger, focus the input, restore on close.
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    triggerRef.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => triggerRef.current?.focus?.();
  }, []);

  // Keep the active row in view during keyboard navigation.
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${sel}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [sel]);

  const activate = (r: SearchResult) => {
    if (kindOf(r) === 'memory') {
      openDetail(toDetail(r));
    } else {
      // Carry the query so the Explorer opens pre-filled on the documents tab (BC2).
      seedExplorer(debounced, 'documents');
      setView('explorer');
    }
    onClose();
  };

  const onInputKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSel((s) => (results.length ? (s + 1) % results.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSel((s) => (results.length ? (s - 1 + results.length) % results.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const r = results[sel];
      if (r) activate(r);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  // Trap Tab within the palette while open.
  const onTrapKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;
    const f = panelRef.current.querySelectorAll<HTMLElement>('input, button:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (f.length === 0) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center" onKeyDown={onTrapKeyDown}>
      <div
        onClick={onClose}
        aria-hidden
        className="absolute inset-0 transition-opacity duration-150"
        style={{
          background: 'rgba(18,14,10,0.42)',
          backdropFilter: 'blur(4px)',
          WebkitBackdropFilter: 'blur(4px)',
          opacity: shown ? 1 : 0,
        }}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('cmdk.title')}
        data-testid="command-palette"
        className="relative mt-[16vh] flex max-h-[64vh] w-[640px] max-w-[92vw] flex-col overflow-hidden rounded-xl transition-[opacity,transform] duration-150"
        style={{
          background: 'var(--card-bg)',
          backdropFilter: 'blur(var(--drawer-blur)) saturate(var(--palette-saturate))',
          WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(var(--palette-saturate))',
          boxShadow: 'inset 0 0 0 1px var(--card-edge), 0 30px 80px -24px rgba(0,0,0,0.6)',
          opacity: shown ? 1 : 0,
          transform: reduce ? undefined : shown ? 'translateY(0)' : 'translateY(-8px)',
        }}
      >
        <div className="flex items-center gap-3 border-b border-[var(--card-hairline)] px-4 py-3.5">
          <span className="flex-none text-ink-3">
            <SearchIcon />
          </span>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder={t('cmdk.placeholder')}
            aria-label={t('cmdk.placeholder')}
            role="combobox"
            aria-expanded={true}
            aria-controls="cmdk-listbox"
            aria-activedescendant={results[sel] ? `cmdk-opt-${sel}` : undefined}
            aria-autocomplete="list"
            className="min-w-0 flex-1 bg-transparent font-body text-[15px] text-ink-1 outline-none placeholder:text-ink-3"
          />
          <kbd
            className="flex-none rounded-md px-[7px] py-[3px] font-mono text-[10px] text-ink-3"
            style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
          >
            esc
          </kbd>
        </div>

        <div ref={listRef} id="cmdk-listbox" role="listbox" aria-label={t('cmdk.title')} className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {!searching ? (
            <Hint>{t('cmdk.idle')}</Hint>
          ) : loading ? (
            <Shimmer />
          ) : results.length === 0 ? (
            <Hint>{t('cmdk.empty')}</Hint>
          ) : (
            results.map((r, i) => {
              const kind = kindOf(r);
              return (
                <button
                  key={r.id}
                  type="button"
                  id={`cmdk-opt-${i}`}
                  data-idx={i}
                  data-testid="cmdk-row"
                  role="option"
                  aria-selected={i === sel}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => activate(r)}
                  className="grid w-full grid-cols-[18px_1fr_auto] items-center gap-3 rounded-md px-3 py-2.5 text-left"
                  style={i === sel ? { background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' } : undefined}
                >
                  <span className="grid h-[18px] place-items-center">
                    <KindIcon kind={kind} />
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-1 block text-[13px] leading-snug text-ink-1">{highlight(r.content, debounced)}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 font-mono text-[10px] text-ink-3">
                      <span style={{ color: KIND_COLOR[kind] }}>{t(`cmdk.kind.${kind}`)}</span>
                      <span>·</span>
                      <span>{r.type}</span>
                      <span>·</span>
                      <span className="truncate">{r.agent_identifier ?? '—'}</span>
                    </span>
                  </span>
                  <span className="flex-none font-mono text-[9.5px] tabular-nums text-ink-3">{r.score.toFixed(2)}</span>
                </button>
              );
            })
          )}
        </div>

        <div className="flex items-center gap-4 border-t border-[var(--card-hairline)] px-4 py-2.5 font-mono text-[10px] text-ink-3">
          <Hk keys="↑↓" label={t('cmdk.nav')} />
          <Hk keys="↵" label={t('cmdk.open')} />
          <Hk keys="esc" label={t('cmdk.close')} />
          {searching && results.length > 0 && <span className="ml-auto">{t('cmdk.count', { count: results.length })}</span>}
        </div>
      </div>
    </div>
  );
}

export function CommandPalette() {
  const open = usePaletteStore((s) => s.open);
  const close = usePaletteStore((s) => s.closePalette);
  if (!open) return null;
  return <PaletteInner onClose={close} />;
}
