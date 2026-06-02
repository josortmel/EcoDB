import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useDetailStore } from '../stores/detail';
import { useToastStore } from '../stores/toast';
import {
  useUpdateStaleness,
  useUpdateMemory,
  useDeleteMemory,
  MEMORY_TYPES,
  type MemoryType,
  type Visibility,
  type MemoryUpdateInput,
} from '../hooks/memory';
import { errMsg } from '../lib/errMsg';
import { sameTags } from '../lib/sameTags';
import { asArray } from '../lib/asArray';

const SCORE_KEYS = ['semantic', 'graph', 'weight', 'freshness', 'bm25'] as const;

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={15} height={15}>
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-5 flex flex-col gap-2.5">
      <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{title}</div>
      {children}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="font-mono text-[15px] capitalize text-ink-1">{v}</div>
      <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{k}</div>
    </div>
  );
}

function Warn({ children, amber }: { children: ReactNode; amber?: boolean }) {
  const c = amber ? 'var(--kind-agent)' : 'var(--red)';
  return (
    <div
      className="mb-3 flex items-start gap-2 rounded-md px-3 py-2.5"
      style={{ background: `color-mix(in srgb, ${c} 10%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${c} 30%, transparent)` }}
    >
      <span className="mt-[3px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: c }} />
      <span className="text-[12px] leading-relaxed text-ink-1">{children}</span>
    </div>
  );
}

// Focus ring matches TemplateModal's field treatment (--ring doesn't exist; M2).
const fieldStyle = (focused: boolean) => ({
  background: 'var(--field-bg)',
  boxShadow: focused
    ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
    : 'inset 0 0 0 1px var(--card-hairline)',
});

interface Draft {
  content: string;
  type: MemoryType;
  visibility: Visibility;
  tags: string[];
}

// Right-side glass detail panel. Kicker is kind-colored (§2.8: memory → accent).
// Closes on ✕ / scrim / Esc. Slides via CSS transform; keeps the last memory
// rendered during the slide-out.
export function MemoryDrawer() {
  const { t } = useTranslation();
  const tx = t as (k: string) => string; // dynamic type-label keys
  const memory = useDetailStore((s) => s.memory);
  const close = useDetailStore((s) => s.close);
  const patchDetail = useDetailStore((s) => s.patch);
  const toast = useToastStore((s) => s.show);
  const staleness = useUpdateStaleness();
  const update = useUpdateMemory();
  const del = useDeleteMemory();
  const open = memory !== null;

  const [last, setLast] = useState(memory);
  useEffect(() => {
    if (memory) setLast(memory);
  }, [memory]);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [tagInput, setTagInput] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmPublic, setConfirmPublic] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [focusField, setFocusField] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset all transient action state whenever a different memory is shown.
  const shownId = memory?.id;
  useEffect(() => {
    setEditing(false);
    setDraft(null);
    setTagInput('');
    setConfirmDelete(false);
    setConfirmPublic(false);
    setConfirmDiscard(false);
    setFocusField(null);
    setError(null);
  }, [shownId]);

  // Closing while mid-edit with unsaved changes must not silently drop them (BH4).
  const m0 = last;
  const hasUnsavedChanges = (): boolean => {
    if (!editing || !draft || !m0) return false;
    if (draft.content.trim() !== m0.content) return true;
    if (draft.type !== m0.type) return true;
    if (draft.visibility !== (m0.visibility ?? 'public')) return true;
    if (!sameTags(draft.tags, m0.tags)) return true;
    return tagInput.trim() !== '';
  };
  const requestClose = () => {
    if (hasUnsavedChanges()) {
      setConfirmDiscard(true);
      return;
    }
    close();
  };
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') requestCloseRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus management (a11y): on open, remember the trigger and focus the first
  // control inside; on close, restore focus to the trigger (the MemoryRow).
  const panelRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement | null;
      requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>('button:not([disabled])')?.focus());
    } else {
      triggerRef.current?.focus?.();
    }
  }, [open]);

  // Trap Tab within the drawer while open.
  const onTrapKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;
    const f = panelRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input, textarea, select, [tabindex]:not([tabindex="-1"])',
    );
    if (f.length === 0) return;
    const first = f[0];
    const lastEl = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      lastEl.focus();
    } else if (!e.shiftKey && document.activeElement === lastEl) {
      e.preventDefault();
      first.focus();
    }
  };

  const m = last;
  const kicker = 'var(--kind-memory)';
  const busy = update.isPending || del.isPending || staleness.isPending;

  const toggleStale = () => {
    if (!m) return;
    const next = m.stale ? 'active' : 'stale';
    staleness.mutate(
      { id: m.id, staleness: next },
      {
        onSuccess: () => {
          toast(t(m.stale ? 'drawer.markedActive' : 'drawer.markedStale'));
          close();
        },
        onError: (e) => toast(errMsg(e, t, t('drawer.actionFailed'))),
      },
    );
  };

  // PUT a new visibility. Exposing (→public) is gated by a confirm; hiding
  // (→private) is one-click (hiding never leaks).
  const setVisibility = (next: Visibility) => {
    if (!m) return;
    setError(null);
    update.mutate(
      { id: m.id, patch: { visibility: next } },
      {
        onSuccess: () => {
          patchDetail({ visibility: next });
          toast(t('drawer.visibilitySet', { v: t(`drawer.vis.${next}`) }));
          setConfirmPublic(false);
        },
        onError: (e) => {
          setConfirmPublic(false);
          setError(errMsg(e, t, t('drawer.actionFailed')));
        },
      },
    );
  };
  const onVisibilityClick = () => {
    if (!m || busy) return;
    setConfirmDelete(false);
    const next: Visibility = m.visibility === 'private' ? 'public' : 'private';
    if (next === 'public') {
      setError(null);
      setConfirmPublic(true); // exposing → require confirmation (VS-DRAW-M1)
      return;
    }
    setVisibility('private'); // hiding → immediate
  };

  const startEdit = () => {
    if (!m) return;
    setError(null);
    setConfirmDelete(false);
    setConfirmPublic(false);
    const type = (MEMORY_TYPES as string[]).includes(m.type) ? (m.type as MemoryType) : 'observacion';
    const visibility: Visibility = m.visibility === 'private' ? 'private' : 'public';
    setDraft({ content: m.content, type, visibility, tags: [...m.tags] });
    setTagInput('');
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
    setFocusField(null);
    setError(null);
  };

  const commitTag = () => {
    const v = tagInput.trim();
    if (!v || !draft) return;
    if (!draft.tags.includes(v)) setDraft({ ...draft, tags: [...draft.tags, v] });
    setTagInput('');
  };

  const saveEdit = () => {
    if (!m || !draft) return;
    const content = draft.content.trim();
    if (!content) {
      setError(t('drawer.contentRequired'));
      return;
    }
    // Only send the fields that actually changed.
    const patch: MemoryUpdateInput = {};
    if (content !== m.content) patch.content = content;
    if (draft.type !== m.type) patch.type = draft.type;
    if (draft.visibility !== (m.visibility ?? 'public')) patch.visibility = draft.visibility;
    if (!sameTags(draft.tags, m.tags)) patch.tags = draft.tags;
    if (Object.keys(patch).length === 0) {
      cancelEdit();
      return;
    }
    setError(null);
    update.mutate(
      { id: m.id, patch },
      {
        onSuccess: () => {
          patchDetail({
            content: patch.content ?? m.content,
            type: patch.type ?? m.type,
            visibility: patch.visibility ?? m.visibility,
            tags: patch.tags ?? m.tags,
          });
          toast(t('drawer.saved'));
          cancelEdit();
        },
        onError: (e) => setError(errMsg(e, t, t('drawer.actionFailed'))),
      },
    );
  };

  const doDelete = () => {
    if (!m) return;
    setError(null);
    del.mutate(m.id, {
      onSuccess: () => {
        toast(t('drawer.binned'));
        close();
      },
      onError: (e) => {
        setConfirmDelete(false);
        setError(errMsg(e, t, t('drawer.actionFailed')));
      },
    });
  };

  return (
    <>
      <div
        onClick={requestClose}
        aria-hidden
        className={`fixed inset-0 z-[60] transition-opacity duration-300 ${open ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        style={{ background: 'rgba(18,14,10,0.34)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)' }}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
        onKeyDown={onTrapKeyDown}
        data-testid="memory-drawer"
        className="fixed right-0 top-0 z-[61] flex h-screen w-[408px] max-w-[92vw] flex-col transition-transform duration-300"
        style={{
          transform: open ? 'translateX(0)' : 'translateX(110%)',
          background: 'var(--card-bg)',
          backdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)',
          WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)',
          boxShadow: '-1px 0 0 var(--card-edge) inset, -40px 0 70px -26px rgba(0,0,0,0.5)',
        }}
      >
        {m && (
          <>
            <div className="flex items-start justify-between gap-3 border-b border-[var(--card-hairline)] px-6 pb-4 pt-[22px]">
              <div className="min-w-0">
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: kicker }}>
                  <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: kicker, boxShadow: `0 0 8px ${kicker}` }} />
                  {t('drawer.kindMemory')} · {tx(`drawer.type.${editing ? draft?.type ?? m.type : m.type}`)}
                </div>
                <div className="mt-2 line-clamp-2 text-[16px] font-semibold leading-tight text-ink-1">{m.content.slice(0, 80)}</div>
                <div className="mt-1.5 font-mono text-[11px] text-ink-3">
                  {m.ts} · {m.agent ?? '—'}
                </div>
              </div>
              <button
                type="button"
                onClick={requestClose}
                aria-label={t('drawer.close')}
                data-testid="drawer-close"
                className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1"
                style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
              >
                <CloseIcon />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 pb-6 pt-5">
              {m.stale && !editing && <Warn amber>{t('drawer.staleWarn')}</Warn>}
              {!editing &&
                asArray<string>(m.trustWarnings).map((w) => (
                  <Warn key={w}>{w}</Warn>
                ))}
              {error && <Warn>{error}</Warn>}

              {editing && draft ? (
                <>
                  <Section title={t('drawer.content')}>
                    <textarea
                      value={draft.content}
                      onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                      onFocus={() => setFocusField('content')}
                      onBlur={() => setFocusField(null)}
                      aria-label={t('drawer.content')}
                      rows={6}
                      className="w-full resize-y rounded-md px-3 py-2.5 text-[13.5px] leading-relaxed text-ink-1 outline-none"
                      style={fieldStyle(focusField === 'content')}
                    />
                  </Section>

                  <div className="mt-5 grid grid-cols-2 gap-2.5">
                    <label className="flex flex-col gap-1.5">
                      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('drawer.typeLabel')}</span>
                      <select
                        value={draft.type}
                        onChange={(e) => setDraft({ ...draft, type: e.target.value as MemoryType })}
                        onFocus={() => setFocusField('type')}
                        onBlur={() => setFocusField(null)}
                        className="rounded-md px-2.5 py-2 font-mono text-[12.5px] text-ink-1 outline-none"
                        style={fieldStyle(focusField === 'type')}
                      >
                        {MEMORY_TYPES.map((ty) => (
                          <option key={ty} value={ty}>
                            {tx(`drawer.type.${ty}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex flex-col gap-1.5">
                      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('drawer.visibility')}</span>
                      <div className="grid grid-cols-2 gap-1 rounded-md p-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                        {(['public', 'private'] as Visibility[]).map((v) => (
                          <button
                            key={v}
                            type="button"
                            onClick={() => setDraft({ ...draft, visibility: v })}
                            aria-pressed={draft.visibility === v}
                            className="rounded-sm py-1.5 font-mono text-[11px] capitalize transition-colors"
                            style={
                              draft.visibility === v
                                ? {
                                    background: 'color-mix(in srgb, var(--kind-memory) 18%, transparent)',
                                    boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-memory) 35%, transparent)',
                                    color: 'var(--kind-memory)',
                                  }
                                : { color: 'var(--ink-2)' }
                            }
                          >
                            {t(`drawer.vis.${v}`)}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <Section title={t('drawer.tags')}>
                    <div className="flex flex-wrap gap-1.5">
                      {draft.tags.map((tag) => (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => setDraft({ ...draft, tags: draft.tags.filter((x) => x !== tag) })}
                          aria-label={t('drawer.removeTag', { tag })}
                          className="flex items-center gap-1 rounded-sm px-2 py-0.5 font-mono text-[9.5px] text-ink-2 transition-colors hover:text-ink-1"
                          style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                        >
                          {tag}
                          <span aria-hidden className="text-ink-3">×</span>
                        </button>
                      ))}
                    </div>
                    <input
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onFocus={() => setFocusField('tags')}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ',') {
                          e.preventDefault();
                          commitTag();
                        }
                      }}
                      onBlur={() => {
                        commitTag();
                        setFocusField(null);
                      }}
                      placeholder={t('drawer.tagPlaceholder')}
                      aria-label={t('drawer.tags')}
                      className="mt-1 w-full rounded-md px-3 py-2 font-mono text-[11.5px] text-ink-1 outline-none placeholder:text-ink-4"
                      style={fieldStyle(focusField === 'tags')}
                    />
                  </Section>
                </>
              ) : (
                <>
                  <Section title={t('drawer.content')}>
                    <p className="text-[13.5px] leading-relaxed text-ink-1">{m.content}</p>
                  </Section>

                  <div className="mt-5 grid grid-cols-2 gap-2.5">
                    <Stat k={t('drawer.author')} v={m.agent ?? '—'} />
                    <Stat k={t('drawer.typeLabel')} v={tx(`drawer.type.${m.type}`)} />
                    <button
                      type="button"
                      onClick={onVisibilityClick}
                      disabled={busy}
                      data-testid="drawer-visibility"
                      title={t('drawer.cycleVisibility')}
                      aria-label={t('drawer.cycleVisibility')}
                      className="rounded-md p-3 text-left transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                      style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                    >
                      <div className="font-mono text-[15px] capitalize text-ink-1">{m.visibility ? tx(`drawer.vis.${m.visibility}`) : '—'}</div>
                      <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('drawer.visibility')}</div>
                    </button>
                    <Stat k={t('drawer.staleness.label')} v={t(m.stale ? 'drawer.staleness.stale' : 'drawer.staleness.active')} />
                  </div>

                  {m.scoreBreakdown && (
                    <Section title={t('drawer.score')}>
                      <div className="flex flex-col gap-2">
                        {SCORE_KEYS.map((k) => (
                          <div key={k} className="flex items-center gap-3">
                            <span className="w-[64px] flex-none font-mono text-[10px] text-ink-3">{k}</span>
                            <span className="h-[6px] flex-1 overflow-hidden rounded-full" style={{ background: 'var(--inset)' }}>
                              <span className="block h-full rounded-full" style={{ width: `${Math.round((m.scoreBreakdown?.[k] ?? 0) * 100)}%`, background: 'var(--chart-line)' }} />
                            </span>
                            <span className="w-[34px] flex-none text-right font-mono text-[10px] tabular-nums text-ink-2">
                              {(m.scoreBreakdown?.[k] ?? 0).toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </Section>
                  )}

                  {m.tags.length > 0 && (
                    <Section title={t('drawer.tags')}>
                      <div className="flex flex-wrap gap-1.5">
                        {m.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-sm px-2 py-0.5 font-mono text-[9.5px] text-ink-2"
                            style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </Section>
                  )}
                </>
              )}
            </div>

            <div className="border-t border-[var(--card-hairline)] px-6 py-4">
              {editing ? (
                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={saveEdit}
                    disabled={update.isPending}
                    data-testid="drawer-save"
                    className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
                    style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
                  >
                    {update.isPending ? t('drawer.saving') : t('drawer.save')}
                  </button>
                  <button
                    type="button"
                    onClick={cancelEdit}
                    disabled={update.isPending}
                    className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                    style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
                  >
                    {t('drawer.cancel')}
                  </button>
                </div>
              ) : confirmPublic ? (
                <div className="flex flex-col gap-2.5">
                  <span className="font-mono text-[12px] text-ink-1">{t('drawer.confirmPublicPrompt')}</span>
                  <div className="flex gap-2.5">
                    <button
                      type="button"
                      onClick={() => setVisibility('public')}
                      disabled={update.isPending}
                      data-testid="drawer-public-confirm"
                      className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
                      style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
                    >
                      {update.isPending ? t('drawer.saving') : t('drawer.makePublic')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmPublic(false)}
                      disabled={update.isPending}
                      className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                      style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
                    >
                      {t('drawer.cancel')}
                    </button>
                  </div>
                </div>
              ) : confirmDelete ? (
                <div className="flex flex-col gap-2.5">
                  <span className="font-mono text-[12px] text-ink-1">{t('drawer.confirmDeletePrompt')}</span>
                  <div className="flex gap-2.5">
                    <button
                      type="button"
                      onClick={doDelete}
                      disabled={del.isPending}
                      data-testid="drawer-delete-confirm"
                      className="flex-1 rounded-btn py-2.5 font-body text-[12.5px] font-semibold text-red transition-[filter] hover:brightness-110 disabled:opacity-50"
                      style={{ background: 'color-mix(in srgb, var(--red) 15%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 40%, transparent)' }}
                    >
                      {del.isPending ? t('drawer.deleting') : t('drawer.confirmDelete')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      disabled={del.isPending}
                      className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                      style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
                    >
                      {t('drawer.cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={toggleStale}
                    disabled={busy}
                    data-testid="drawer-stale"
                    className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
                    style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
                  >
                    {m.stale ? t('drawer.markActive') : t('drawer.markStale')}
                  </button>
                  <button
                    type="button"
                    onClick={startEdit}
                    disabled={busy}
                    data-testid="drawer-edit"
                    className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                    style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
                  >
                    {t('drawer.edit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setError(null);
                      setConfirmPublic(false);
                      setConfirmDelete(true);
                    }}
                    disabled={busy}
                    data-testid="drawer-delete"
                    className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-red transition-[filter] hover:brightness-110 disabled:opacity-50"
                    style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}
                  >
                    {t('drawer.bin')}
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* BH4: confirm before dropping unsaved edits (scrim / Esc / ✕). */}
        {confirmDiscard && (
          <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col gap-2.5 border-t border-[var(--card-hairline)] px-6 py-4" style={{ background: 'var(--card-bg)' }}>
            <span className="font-mono text-[12px] text-ink-1">{t('drawer.discardPrompt')}</span>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={() => {
                  setConfirmDiscard(false);
                  close();
                }}
                data-testid="drawer-discard"
                className="flex-1 rounded-btn py-2.5 font-body text-[12.5px] font-semibold text-red transition-[filter] hover:brightness-110"
                style={{ background: 'color-mix(in srgb, var(--red) 15%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 40%, transparent)' }}
              >
                {t('drawer.discard')}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDiscard(false)}
                className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)]"
                style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
              >
                {t('drawer.keepEditing')}
              </button>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
