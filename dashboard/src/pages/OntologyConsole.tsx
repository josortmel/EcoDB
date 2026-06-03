import { useMemo, useState, type ReactNode, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../components/GlassCard';
import { ApiError } from '../lib/api';
import { errMsg } from '../lib/errMsg';
import { asArray } from '../lib/asArray';
import { useToastStore } from '../stores/toast';
import { useAuthMe } from '../hooks/auth';
import { useGraphVocabulary, useEntityDictionary, useStopEntities, useSaveEntity, useDeleteEntity, useCreatePredicate, useUpdatePredicate, useDeletePredicate, PREDICATE_STATES, type VocabEntity, type VocabPredicate, type DictEntity, type StopEntity, type GraphVocabulary, type PredicateState } from '../hooks/settings';
import { useMergeEntities, useUndoMerge, searchNodes, type NodeMatch } from '../hooks/ontology';
import { useAliasCandidates, useReviewAliasCandidate, useScanAliasCandidates, type AliasItem, type AliasStatus, type AliasScanResponse } from '../hooks/inbox';

const ACCENT = 'var(--sec-ontology)'; // §2.9 ontology #8E78BC

function SearchInput({ value, onChange, placeholder, onKeyDown, testid = 'ont-search', ariaLabel }: { value: string; onChange: (v: string) => void; placeholder: string; onKeyDown?: (e: ReactKeyboardEvent<HTMLInputElement>) => void; testid?: string; ariaLabel?: string }) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      aria-label={ariaLabel}
      data-testid={testid}
      className="w-full rounded-md px-3 py-2 font-mono text-[12px] text-ink-1 outline-none placeholder:text-ink-3"
      style={{
        background: 'var(--field-bg)',
        boxShadow: focused
          ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
          : 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline)',
      }}
    />
  );
}

// Retype has no REST endpoint → rendered disabled (never a no-op).
function DisabledBtn({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      disabled
      aria-disabled
      title={t('ont.noEndpoint')}
      className="rounded-btn px-4 py-2 font-body text-[12px] font-semibold text-ink-1 opacity-40"
      style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
    >
      {children}
    </button>
  );
}

function InlineWarn({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-start gap-2 rounded-md px-3 py-2" style={{ background: 'color-mix(in srgb, var(--red) 10%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 30%, transparent)' }}>
      <span className="mt-[3px] h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--red)' }} />
      <span className="text-[11.5px] leading-relaxed text-ink-1">{children}</span>
    </div>
  );
}

function StateWrap({
  query,
  isAdmin,
  children,
}: {
  query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => Promise<unknown> };
  isAdmin: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const is403 = query.error instanceof ApiError && query.error.status === 403;
  if (!isAdmin || is403) {
    return <div className="grid place-items-center py-16 font-mono text-[12.5px] text-ink-3">{t('ont.limitedAccess')}</div>;
  }
  if (query.isPending) {
    return (
      <div className="flex flex-col gap-2.5 py-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className="h-[13px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${90 - i * 8}%` }} />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
        <span className="font-mono text-[12px] text-ink-2">{t('ont.error')}</span>
        <button type="button" onClick={() => void query.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">
          {t('ont.retry')}
        </button>
      </div>
    );
  }
  return <>{children}</>;
}

function Marker({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px]"
      style={{ color, background: `color-mix(in srgb, ${color} 12%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 32%, transparent)` }}
    >
      {label}
    </span>
  );
}

// Detail panel. Keyed by entity in the list so merge/undo state resets per entity.
function EntityDetail({ entity, inDict, isStop }: { entity: VocabEntity; inDict: boolean; isStop: boolean }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const merge = useMergeEntities();
  const undo = useUndoMerge();
  const qc = useQueryClient();

  const [mode, setMode] = useState<'view' | 'pick' | 'confirm'>('view');
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<NodeMatch[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [target, setTarget] = useState<NodeMatch | null>(null);
  const [keepAlias, setKeepAlias] = useState(false);
  const [mergedId, setMergedId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const status = isStop ? t('ont.stopStatus') : inDict ? t('ont.curated') : t('ont.auto');
  const busy = merge.isPending || undo.isPending;

  const runSearch = async () => {
    if (query.trim().length < 3) {
      setError(t('ont.mergeFlow.searchHint'));
      return;
    }
    setError(null);
    setSearching(true);
    try {
      const res = await searchNodes(query, 8);
      setMatches(res.filter((m) => m.name.toLowerCase() !== entity.name.toLowerCase()));
    } catch {
      setMatches([]);
    } finally {
      setSearched(true);
      setSearching(false);
    }
  };

  // #46b — entering pick mode auto-loads the top similar nodes (by similarity)
  // so the user sees candidates immediately instead of an empty search box.
  const startMerge = async () => {
    setError(null);
    setMode('pick');
    setQuery('');
    setTarget(null);
    setKeepAlias(false);
    setMatches([]);
    setSearched(false);
    setSearching(true);
    try {
      const res = await searchNodes(entity.name, 6);
      setMatches(res.filter((m) => m.name.toLowerCase() !== entity.name.toLowerCase()));
    } catch {
      setMatches([]);
    } finally {
      setSearched(true);
      setSearching(false);
    }
  };
  const cancelMerge = () => {
    setMode('view');
    setTarget(null);
    setKeepAlias(false);
    setError(null);
  };

  const doMerge = async () => {
    if (!target || submitting) return; // guard the async window (searchNodes) against a double-fire (IC-1)
    setError(null);
    setSubmitting(true);
    let sourceId: number | undefined;
    try {
      const src = await searchNodes(entity.name, 8);
      // Require EXACTLY one exact name match. Never fall back to a fuzzy result —
      // a near-name (or a since-renamed node) would merge a different node than the
      // one the confirm showed. 0 or >1 exact matches → abort (VS-ONT-H1).
      const exact = src.filter((m) => m.name.toLowerCase() === entity.name.toLowerCase());
      if (exact.length === 1) sourceId = exact[0].id;
    } catch {
      /* handled by the null check */
    }
    if (sourceId == null) {
      setError(t('ont.mergeFlow.noSource'));
      setSubmitting(false);
      return;
    }
    if (sourceId === target.id) {
      setError(t('ont.mergeFlow.sameNode'));
      setSubmitting(false);
      return;
    }
    const src = sourceId;
    merge.mutate(
      { source_node_id: src, target_node_id: target.id, keep_as_alias: keepAlias },
      {
        onSuccess: () => {
          // #46a — drop the absorbed source from the vocab list immediately. The
          // graph merge is eventually-consistent, so the hook's invalidate alone
          // can refetch stale data; this optimistic edit makes the row disappear now.
          qc.setQueryData<GraphVocabulary>(['admin', 'graph-vocabulary'], (old) =>
            old
              ? {
                  ...old,
                  // Match name AND type — names repeat across types (Person:John ≠ Organization:John).
                  entities: old.entities.filter((e) => !(e.name.toLowerCase() === entity.name.toLowerCase() && e.type === entity.type)),
                  entity_count: Math.max(0, old.entity_count - 1),
                }
              : old,
          );
          setMergedId(src);
          toast(t('ont.mergeFlow.done', { source: entity.name, target: target.name }));
          cancelMerge();
          setSubmitting(false);
        },
        onError: (e) => {
          setError(errMsg(e, t, t('ont.mergeFlow.failed')));
          setSubmitting(false);
        },
      },
    );
  };

  const doUndo = () => {
    if (mergedId == null) return;
    undo.mutate(mergedId, {
      onSuccess: () => {
        toast(t('ont.mergeFlow.undone'));
        setMergedId(null);
      },
      onError: (e) => toast(errMsg(e, t, t('ont.mergeFlow.failed'))),
    });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: ACCENT }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: ACCENT, boxShadow: `0 0 8px ${ACCENT}` }} />
        {entity.type}
      </div>
      <div className="mt-2 break-words text-[18px] font-semibold leading-tight text-ink-1">{entity.name}</div>

      <div className="mt-4 grid grid-cols-1 gap-2.5">
        <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <div className="font-mono text-[12.5px] text-ink-1">{entity.type}</div>
          <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ont.typeLabel')}</div>
        </div>
        <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <div className="font-mono text-[12.5px] text-ink-1">{status}</div>
          <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ont.status')}</div>
        </div>
      </div>

      {/* Target picker — only in pick mode, fills the middle. */}
      {mode === 'pick' && (
        <div className="mt-4 flex min-h-0 flex-1 flex-col">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('ont.mergeFlow.pickTitle', { source: entity.name })}</div>
          <div className="flex gap-2">
            <div className="min-w-0 flex-1">
              <SearchInput
                value={query}
                onChange={setQuery}
                placeholder={t('ont.mergeFlow.searchPlaceholder')}
                testid="ont-merge-search"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    void runSearch();
                  }
                }}
              />
            </div>
            <button
              type="button"
              onClick={() => void runSearch()}
              disabled={searching}
              className="flex-none rounded-md px-3 py-2 font-mono text-[11px] text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
              style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
            >
              {searching ? t('ont.mergeFlow.searching') : t('ont.mergeFlow.search')}
            </button>
          </div>
          <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
            {searched && matches.length === 0 ? (
              <div className="px-1 py-3 font-mono text-[11.5px] text-ink-3">{t('ont.mergeFlow.noMatches')}</div>
            ) : (
              matches.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  data-testid="ont-merge-match"
                  onClick={() => {
                    setTarget(m);
                    setMode('confirm');
                  }}
                  className="flex w-full items-center gap-2 border-b border-[var(--card-hairline)] px-2.5 py-2 text-left transition-colors last:border-0 hover:bg-[var(--inset)]"
                >
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-1">{m.name}</span>
                  {m.similarity != null && <span className="flex-none font-mono text-[9.5px] tabular-nums text-ink-3">{t('ont.mergeFlow.similarity')} {m.similarity.toFixed(2)}</span>}
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {mode !== 'pick' && <div className="flex-1" />}

      {error && <InlineWarn>{error}</InlineWarn>}

      {/* Footer: confirm / merged / pick-cancel / view actions */}
      {mode === 'confirm' && target ? (
        <div className="flex flex-col gap-2.5">
          <span className="font-mono text-[11.5px] leading-relaxed text-ink-1">{t('ont.mergeFlow.confirmPrompt', { source: entity.name, target: target.name })}</span>
          <label className="flex cursor-pointer items-start gap-2 font-mono text-[11px] leading-relaxed text-ink-2">
            <input
              type="checkbox"
              checked={keepAlias}
              onChange={(e) => setKeepAlias(e.target.checked)}
              data-testid="ont-merge-keepalias"
              className="mt-0.5 flex-none"
              style={{ accentColor: 'var(--sec-ontology)' }}
            />
            <span>{t('ont.mergeFlow.keepAlias', { source: entity.name, target: target.name })}</span>
          </label>
          <div className="flex gap-2.5">
            <button
              type="button"
              onClick={() => void doMerge()}
              disabled={submitting}
              data-testid="ont-merge-confirm"
              className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
            >
              {submitting ? t('ont.mergeFlow.merging') : t('ont.mergeFlow.confirmMerge')}
            </button>
            <button
              type="button"
              onClick={() => setMode('pick')}
              disabled={submitting}
              className="rounded-btn px-4 py-2.5 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
              style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
            >
              {t('ont.mergeFlow.back')}
            </button>
          </div>
        </div>
      ) : mode === 'pick' ? (
        <button
          type="button"
          onClick={cancelMerge}
          className="mt-2 rounded-btn px-4 py-2 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)]"
          style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
        >
          {t('ont.mergeFlow.cancel')}
        </button>
      ) : mergedId != null ? (
        <div className="flex items-center gap-2.5">
          <span className="flex-1 font-mono text-[11.5px] text-ink-2">{t('ont.mergeFlow.mergedNote')}</span>
          <button
            type="button"
            onClick={doUndo}
            disabled={undo.isPending}
            data-testid="ont-merge-undo"
            className="rounded-btn px-4 py-2.5 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
          >
            {undo.isPending ? t('ont.mergeFlow.undoing') : t('ont.mergeFlow.undo')}
          </button>
        </div>
      ) : (
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => void startMerge()}
            disabled={busy}
            data-testid="ont-merge"
            className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
            style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
          >
            {t('ont.merge')}
          </button>
          <DisabledBtn>{t('ont.retype')}</DisabledBtn>
        </div>
      )}
    </div>
  );
}

const entityKey = (e: VocabEntity): string => `${e.type}:${e.name}`;

function EntitiesTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const vocab = useGraphVocabulary(isAdmin);
  const dict = useEntityDictionary(isAdmin);
  const stop = useStopEntities(isAdmin);
  const [type, setType] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const entities = asArray<VocabEntity>(vocab.data?.entities);
  const types = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of entities) m.set(e.type, (m.get(e.type) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [entities]);
  const dictSet = useMemo(() => new Set(asArray<DictEntity>(dict.data).map((d) => d.name.toLowerCase())), [dict.data]);
  const stopSet = useMemo(() => new Set(asArray<StopEntity>(stop.data).map((s) => s.name.toLowerCase())), [stop.data]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return entities.filter((e) => (!type || e.type === type) && (!needle || e.name.toLowerCase().includes(needle)));
  }, [entities, type, q]);

  // Match by composite type:name key — names can repeat across types (BC1).
  const selected = filtered.find((e) => entityKey(e) === selectedKey) ?? filtered[0] ?? null;

  return (
    <StateWrap query={vocab} isAdmin={isAdmin}>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        {/* LIST */}
        <GlassCard className="flex max-h-[calc(100vh-250px)] flex-col p-3">
          <SearchInput value={q} onChange={setQ} placeholder={t('ont.searchEntities')} />
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setType(null)}
              aria-pressed={type === null}
              className="rounded-[20px] px-2.5 py-1 font-mono text-[10px] transition-colors"
              style={type === null ? { color: ACCENT, background: 'color-mix(in srgb, var(--sec-ontology) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ontology) 38%, transparent)' } : { color: 'var(--ink-3)', background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
            >
              {t('ont.allTypes')}
            </button>
            {types.map(([ty, n]) => (
              <button
                key={ty}
                type="button"
                data-testid="ont-typechip"
                onClick={() => setType(type === ty ? null : ty)}
                aria-pressed={type === ty}
                className="rounded-[20px] px-2.5 py-1 font-mono text-[10px] transition-colors"
                style={type === ty ? { color: ACCENT, background: 'color-mix(in srgb, var(--sec-ontology) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ontology) 38%, transparent)' } : { color: 'var(--ink-3)', background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
              >
                {ty} <span className="text-ink-3">{n}</span>
              </button>
            ))}
          </div>
          <div className="mt-2 px-1 font-mono text-[10px] text-ink-3">{t('ont.shown', { count: filtered.length })}</div>
          <div role="listbox" aria-label={t('ont.tab.entities')} className="mt-1 min-h-0 flex-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="grid place-items-center py-10 font-mono text-[12px] text-ink-3">{t('ont.empty')}</div>
            ) : (
              filtered.map((e) => {
                const inDict = dictSet.has(e.name.toLowerCase());
                const isStop = stopSet.has(e.name.toLowerCase());
                const active = !!selected && entityKey(selected) === entityKey(e);
                return (
                  <button
                    key={entityKey(e)}
                    type="button"
                    role="option"
                    aria-selected={active}
                    data-testid="ont-entity"
                    onClick={() => setSelectedKey(entityKey(e))}
                    className="flex w-full items-center gap-2.5 border-b border-[var(--card-hairline)] px-2.5 py-2.5 text-left transition-colors last:border-0 hover:bg-[var(--inset)]"
                    style={active ? { background: 'color-mix(in srgb, var(--sec-ontology) 12%, transparent)' } : undefined}
                  >
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-1">{e.name}</span>
                    {inDict && <Marker label={t('ont.inDictionary')} color="var(--sec-explorer)" />}
                    {isStop && <Marker label={t('ont.stopEntity')} color="var(--red)" />}
                    <span className="flex-none font-mono text-[9.5px] text-ink-3">{e.type}</span>
                  </button>
                );
              })
            )}
          </div>
        </GlassCard>

        {/* DETAIL */}
        <GlassCard className="flex max-h-[calc(100vh-250px)] flex-col p-[18px]">
          {selected ? (
            <EntityDetail key={entityKey(selected)} entity={selected} inDict={dictSet.has(selected.name.toLowerCase())} isStop={stopSet.has(selected.name.toLowerCase())} />
          ) : (
            <div className="grid h-full place-items-center px-6 text-center font-mono text-[12px] text-ink-3">{t('ont.selectPrompt')}</div>
          )}
        </GlassCard>
      </div>
    </StateWrap>
  );
}

// Predicate CRUD (#44). The list (graph-vocabulary) returns state + cluster per
// predicate, so editing pre-fills the current state.
function PredicatesTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const vocab = useGraphVocabulary(isAdmin);
  const create = useCreatePredicate();
  const update = useUpdatePredicate();
  const del = useDeletePredicate();

  const [q, setQ] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [pstate, setPstate] = useState<PredicateState>('approved');
  const [confirmName, setConfirmName] = useState<string | null>(null);

  const predicates = asArray<VocabPredicate>(vocab.data?.predicates);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return predicates.filter((p) => !needle || p.name.toLowerCase().includes(needle) || p.description.toLowerCase().includes(needle));
  }, [predicates, q]);

  const busy = create.isPending || update.isPending;
  const reset = () => {
    setEditing(null);
    setName('');
    setDesc('');
    setPstate('approved');
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    const onErr = (err: unknown) => toast(errMsg(err, t, t('ont.pred.failed')));
    if (editing) {
      update.mutate({ name: editing, body: { description: desc.trim(), state: pstate } }, { onSuccess: reset, onError: onErr });
    } else {
      create.mutate({ name: name.trim(), description: desc.trim(), state: pstate }, { onSuccess: reset, onError: onErr });
    }
  };
  const onEdit = (p: VocabPredicate) => {
    setEditing(p.name);
    setName(p.name);
    setDesc(p.description);
    setPstate(p.state ?? 'approved'); // vocab GET now returns the current state
  };
  const onDelete = (n: string) => {
    if (confirmName !== n) {
      setConfirmName(n);
      return;
    }
    del.mutate(n, {
      onSuccess: () => setConfirmName(null),
      onError: (err) => {
        setConfirmName(null);
        toast(errMsg(err, t, t('ont.pred.failed')));
      },
    });
  };

  return (
    <StateWrap query={vocab} isAdmin={isAdmin}>
      <GlassCard className="flex max-h-[calc(100vh-250px)] flex-col p-3">
        <form onSubmit={onSubmit} className="mb-2.5 flex flex-wrap items-center gap-2">
          <div className="min-w-[130px] flex-1"><SearchInput value={name} onChange={editing ? () => {} : setName} placeholder={t('ont.pred.name')} testid="ont-pred-name" /></div>
          <div className="min-w-[160px] flex-[1.6]"><SearchInput value={desc} onChange={setDesc} placeholder={t('ont.pred.description')} testid="ont-pred-desc" /></div>
          <select
            value={pstate}
            onChange={(e) => setPstate(e.target.value as PredicateState)}
            data-testid="ont-pred-state"
            aria-label={t('ont.pred.state.label')}
            className="flex-none rounded-md px-2 py-2 font-mono text-[11px] text-ink-1"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
          >
            {PREDICATE_STATES.map((s) => (
              <option key={s} value={s}>
                {t(`ont.pred.state.${s}`)}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={busy || !name.trim()}
            data-testid="ont-pred-save"
            className="flex-none rounded-btn bg-btn-primary px-4 py-2 font-body text-[12px] font-semibold text-white disabled:opacity-50"
            style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
          >
            {editing ? t('ont.pred.update') : t('ont.pred.add')}
          </button>
          {editing && (
            <button type="button" onClick={reset} className="flex-none rounded-btn px-3 py-2 font-mono text-[11px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              {t('ont.pred.cancel')}
            </button>
          )}
        </form>
        <SearchInput value={q} onChange={setQ} placeholder={t('ont.searchPredicates')} testid="ont-pred-search" />
        <div className="mt-2 px-1 font-mono text-[10px] text-ink-3">{t('ont.shown', { count: filtered.length })}</div>
        <div className="mt-1 min-h-0 flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="grid place-items-center py-10 font-mono text-[12px] text-ink-3">{t('ont.empty')}</div>
          ) : (
            filtered.map((p) => (
              <div key={p.name} data-testid="ont-predicate" className="flex items-center gap-3 border-b border-[var(--card-hairline)] px-2.5 py-2.5 last:border-0">
                <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: ACCENT, boxShadow: `0 0 6px ${ACCENT}` }} />
                <span className="flex-none truncate font-mono text-[12.5px] text-ink-1" style={{ maxWidth: 190 }}>{p.name}</span>
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink-3">{p.description}</span>
                <button type="button" onClick={() => onEdit(p)} className="flex-none rounded-sm px-2 py-1 font-mono text-[10.5px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                  {t('ont.pred.edit')}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(p.name)}
                  disabled={del.isPending}
                  data-testid="ont-pred-delete"
                  className="flex-none rounded-sm px-2 py-1 font-mono text-[10.5px] text-red disabled:opacity-50"
                  style={{ background: 'color-mix(in srgb, var(--red) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 38%, transparent)' }}
                >
                  {confirmName === p.name ? t('set.confirmDelete') : t('ont.pred.delete')}
                </button>
              </div>
            ))
          )}
        </div>
      </GlassCard>
    </StateWrap>
  );
}

// Alias candidates — same source of truth as the Decisions Inbox. Pending shows
// the approve/reject flow with a direction control (approve-with-merge collapses
// source → target by default; ⇄ flips it so the source survives instead);
// Resolved shows already-approved aliases read-only (#45).
const ALIAS_STATUSES: AliasStatus[] = ['pending', 'approved'];

// Retroactive discovery panel. threshold is pg_trgm similarity (higher = stricter).
// Preview (dry_run) shows what WOULD be persisted without touching the DB.
function AliasScanPanel() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const scan = useScanAliasCandidates();
  const [threshold, setThreshold] = useState(0.65);
  const [maxPerName, setMaxPerName] = useState(3);
  const [nameFilter, setNameFilter] = useState('');
  const [result, setResult] = useState<{ res: AliasScanResponse; preview: boolean } | null>(null);
  const busy = scan.isPending;
  const [lastOp, setLastOp] = useState<'preview' | 'scan' | null>(null);

  const run = (dry: boolean) => {
    if (busy) return;
    setLastOp(dry ? 'preview' : 'scan'); // H1: show the loading label only on the clicked button
    setResult(null); // BC1: drop a prior result so a failed new scan can't show stale numbers
    scan.mutate(
      { threshold, max_per_name: maxPerName, ...(nameFilter.trim() ? { name_filter: nameFilter.trim() } : {}), dry_run: dry },
      {
        onSuccess: (res) => {
          setResult({ res, preview: dry });
          if (!dry) toast(t('ont.aliasScan.result', { found: res.found, inserted: res.inserted, updated: res.updated }));
        },
        onError: (e) => toast(errMsg(e, t, t('ont.aliasScan.failed'))),
      },
    );
  };

  const preview = result?.res.candidates ?? [];

  return (
    <GlassCard className="flex flex-col gap-3 p-3">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: ACCENT }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: ACCENT, boxShadow: `0 0 8px ${ACCENT}` }} />
        {t('ont.aliasScan.title')}
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between">
          <label htmlFor="alias-threshold" className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('ont.aliasScan.threshold')}</label>
          <span className="font-mono text-[13px] tabular-nums text-ink-1">{threshold.toFixed(2)}</span>
        </div>
        <input
          id="alias-threshold"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={threshold}
          onChange={(e) => setThreshold(parseFloat(e.target.value))}
          data-testid="alias-scan-threshold"
          className="w-full"
          style={{ accentColor: 'var(--sec-ontology)' }}
        />
        <span className="font-mono text-[9.5px] text-ink-3">{threshold < 0.6 ? t('ont.aliasScan.noiseHint') : t('ont.aliasScan.thresholdHint')}</span>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="alias-maxpername" className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">{t('ont.aliasScan.maxPerName')}</label>
          <input
            id="alias-maxpername"
            type="number"
            min={1}
            max={10}
            value={maxPerName}
            onChange={(e) => setMaxPerName(Math.min(10, Math.max(1, Math.round(Number(e.target.value) || 1))))}
            data-testid="alias-scan-maxpername"
            className="w-[64px] rounded-md px-2.5 py-2 font-mono text-[12px] text-ink-1 outline-none"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline)' }}
          />
        </div>
        <div className="min-w-[140px] flex-1">
          <SearchInput value={nameFilter} onChange={setNameFilter} placeholder={t('ont.aliasScan.nameFilter')} ariaLabel={t('ont.aliasScan.nameFilter')} testid="alias-scan-filter" />
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => run(true)}
          disabled={busy}
          data-testid="alias-scan-preview"
          className="rounded-btn px-3.5 py-2 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
          style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
        >
          {busy && lastOp === 'preview' ? t('ont.aliasScan.previewing') : t('ont.aliasScan.preview')}
        </button>
        <button
          type="button"
          onClick={() => run(false)}
          disabled={busy}
          data-testid="alias-scan-run"
          className="rounded-btn bg-btn-primary px-4 py-2 font-body text-[12px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
        >
          {busy && lastOp === 'scan' ? t('ont.aliasScan.scanning') : t('ont.aliasScan.scan')}
        </button>
      </div>

      {result && (
        <div className="flex flex-col gap-1.5 rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <span className="font-mono text-[11.5px] text-ink-1">
            {result.preview
              ? t('ont.aliasScan.previewResult', { found: result.res.found, inserted: result.res.inserted, updated: result.res.updated })
              : t('ont.aliasScan.result', { found: result.res.found, inserted: result.res.inserted, updated: result.res.updated })}
          </span>
          <span className="font-mono text-[10px] text-ink-3">{t('ont.aliasScan.totalPending', { count: result.res.total_pending })}</span>
          {result.preview && preview.length > 0 && (
            <div className="mt-1 flex flex-col gap-1">
              {preview.slice(0, 6).map((c, i) => (
                <div key={`${c.source_name}-${c.target_node_id}-${i}`} className="flex items-center gap-1.5 font-mono text-[10.5px] text-ink-2">
                  <span className="min-w-0 truncate">{c.source_name}</span>
                  <span className="flex-none text-ink-3">→</span>
                  <span className="min-w-0 truncate">{c.target_node_name ?? `#${c.target_node_id}`}</span>
                  <span className="flex-none tabular-nums text-ink-3">{c.confidence.toFixed(2)}</span>
                </div>
              ))}
              {preview.length > 6 && <span className="font-mono text-[9.5px] text-ink-3">{t('ont.aliasScan.more', { count: preview.length - 6 })}</span>}
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function AliasesTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const [status, setStatus] = useState<AliasStatus>('pending');
  const aliases = useAliasCandidates(isAdmin ? 50 : 0, status);
  const review = useReviewAliasCandidate();
  const [confirmId, setConfirmId] = useState<number | null>(null);
  // Single direction flag — only one confirm is open at a time. openConfirm resets
  // it to false (canonical: target survives) so an invert never leaks across rows.
  const [reverse, setReverse] = useState(false);

  const items = asArray<AliasItem>(aliases.data);
  const acting = review.isPending;
  const isPending = status === 'pending';

  const openConfirm = (id: number) => {
    setReverse(false);
    setConfirmId(id);
  };

  const onReview = (id: number, st: 'approved' | 'rejected', merge?: boolean, rev?: boolean) =>
    review.mutate(
      { id, status: st, ...(merge != null ? { merge } : {}), ...(rev != null ? { reverse: rev } : {}) },
      {
        onSuccess: () => {
          toast(t('ont.aliasReview.done'));
          setConfirmId(null);
        },
        onError: (e) => toast(errMsg(e, t, t('ont.aliasReview.failed'))),
      },
    );

  return (
    <StateWrap query={aliases} isAdmin={isAdmin}>
      <div className="flex flex-col gap-4">
        <div className="flex gap-1.5">
          {ALIAS_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setStatus(s);
                setConfirmId(null);
                setReverse(false);
              }}
              aria-pressed={status === s}
              data-testid={`ont-alias-status-${s}`}
              className="rounded-[20px] px-3 py-1 font-mono text-[10.5px] transition-colors"
              style={
                status === s
                  ? { color: ACCENT, background: 'color-mix(in srgb, var(--sec-ontology) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ontology) 38%, transparent)' }
                  : { color: 'var(--ink-3)', background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }
              }
            >
              {t(`ont.aliasReview.status.${s}`)}
            </button>
          ))}
        </div>

        {isPending && <AliasScanPanel />}

        <GlassCard className="flex max-h-[calc(100vh-340px)] flex-col p-3">
          {items.length === 0 ? (
            <div className="grid place-items-center py-12 font-mono text-[12.5px] text-ink-3">{isPending ? t('ont.aliasReview.empty') : t('ont.aliasReview.emptyResolved')}</div>
          ) : (
            <div role="list" className="min-h-0 flex-1 overflow-y-auto">
              {items.map((a) => {
                const survivor = reverse ? a.source_name : a.target_node_name;
                const absorbed = reverse ? a.target_node_name : a.source_name;
                return (
                  <div key={a.id} data-testid="ont-alias" className="border-b border-[var(--card-hairline)] px-2.5 py-3 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 truncate text-[13px] text-ink-1">{a.source_name}</span>
                      <span className="flex-none text-ink-3">→</span>
                      <span className="min-w-0 truncate text-[13px] text-ink-1">{a.target_node_name}</span>
                      {!isPending && <Marker label={t(`ont.aliasReview.status.${a.status === 'rejected' ? 'rejected' : 'approved'}`)} color={a.status === 'rejected' ? 'var(--red)' : 'var(--grn)'} />}
                    </div>
                    <div className="mt-1 flex items-center gap-3 font-mono text-[10px] text-ink-3">
                      <span>{t('ont.aliasReview.confidence')} {a.confidence.toFixed(2)}</span>
                      <span>{t('ont.aliasReview.occurrences')} {a.occurrences}</span>
                    </div>
                    {isPending && (
                      <div className="mt-2.5">
                        {confirmId === a.id ? (
                          <div className="flex flex-col gap-2.5">
                            <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-ink-3">{t('ont.aliasReview.direction.label')}</span>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded-sm px-2 py-1 font-mono text-[11.5px] text-ink-1" style={{ background: 'color-mix(in srgb, var(--red) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 32%, transparent)' }}>{absorbed}</span>
                              <span className="flex-none text-ink-3">→</span>
                              <span className="rounded-sm px-2 py-1 font-mono text-[11.5px] text-ink-1" style={{ background: 'color-mix(in srgb, var(--sec-ontology) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ontology) 38%, transparent)' }}>{survivor}</span>
                              <button
                                type="button"
                                onClick={() => setReverse((r) => !r)}
                                disabled={acting}
                                data-testid="ont-alias-invert"
                                aria-pressed={reverse}
                                className="flex-none rounded-md px-2.5 py-1.5 font-mono text-[10.5px] transition-colors disabled:opacity-50"
                                style={
                                  reverse
                                    ? { color: 'var(--sec-ontology)', background: 'color-mix(in srgb, var(--sec-ontology) 14%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ontology) 38%, transparent)' }
                                    : { color: 'var(--ink-2)', background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }
                                }
                              >
                                ⇄ {t('ont.aliasReview.direction.invert')}
                              </button>
                            </div>
                            <span className="font-mono text-[11px] leading-relaxed text-ink-1">
                              <span className="text-ink-3">{t('ont.aliasReview.direction.survives')}:</span> {survivor} · <span className="text-ink-3">{t('ont.aliasReview.direction.absorbed')}:</span> {absorbed}
                            </span>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => onReview(a.id, 'approved', true, reverse)}
                                disabled={acting}
                                data-testid="ont-alias-confirm"
                                className="rounded-btn bg-btn-primary px-3.5 py-2 font-body text-[12px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
                                style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
                              >
                                {t('ont.aliasReview.confirmMerge')}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setConfirmId(null);
                                  setReverse(false);
                                }}
                                disabled={acting}
                                className="rounded-btn px-3.5 py-2 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                                style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                              >
                                {t('ont.aliasReview.cancel')}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => openConfirm(a.id)}
                              disabled={acting}
                              data-testid="ont-alias-approve"
                              className="rounded-btn bg-btn-primary px-3.5 py-2 font-body text-[12px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
                              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
                            >
                              {t('ont.aliasReview.approve')}
                            </button>
                            <button
                              type="button"
                              onClick={() => onReview(a.id, 'rejected')}
                              disabled={acting}
                              data-testid="ont-alias-reject"
                              className="rounded-btn px-3.5 py-2 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
                              style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                            >
                              {t('ont.aliasReview.reject')}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </GlassCard>
      </div>
    </StateWrap>
  );
}

// Curated entity dictionary — relocated from Settings (#43). CRUD on the left,
// the same merge-flow detail (EntityDetail) on the right so a curated entity can
// be merged from here, not just inspected.
function DictionaryTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const dict = useEntityDictionary(isAdmin);
  const stop = useStopEntities(isAdmin);
  const save = useSaveEntity();
  const del = useDeleteEntity();

  const [q, setQ] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [type, setType] = useState('');
  const [notes, setNotes] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const entries = asArray<DictEntity>(dict.data);
  const stopSet = useMemo(() => new Set(asArray<StopEntity>(stop.data).map((s) => s.name.toLowerCase())), [stop.data]);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return entries.filter((e) => !needle || e.name.toLowerCase().includes(needle) || e.entity_type.toLowerCase().includes(needle));
  }, [entries, q]);
  const selected = filtered.find((e) => e.id === selectedId) ?? null;

  const reset = () => {
    setEditId(null);
    setName('');
    setType('');
    setNotes('');
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !type.trim() || save.isPending) return;
    // notes sent as a (possibly empty) string so a PUT can clear existing notes.
    save.mutate({ id: editId ?? undefined, body: { name: name.trim(), entity_type: type.trim(), notes: notes.trim() } }, { onSuccess: reset });
  };
  const onEdit = (en: DictEntity) => {
    setEditId(en.id);
    setName(en.name);
    setType(en.entity_type);
    setNotes(en.notes ?? '');
  };
  // Two-step delete: first click arms, second deletes (dict entries can carry graph relations).
  const onDelete = (id: number) => {
    if (confirmId !== id) {
      setConfirmId(id);
      return;
    }
    del.mutate(id, { onSuccess: () => setConfirmId(null), onError: () => { setConfirmId(null); toast(t('set.deleteFailed')); } });
  };

  return (
    <StateWrap query={dict} isAdmin={isAdmin}>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        {/* LIST + CRUD */}
        <GlassCard className="flex max-h-[calc(100vh-250px)] flex-col p-3">
          <form onSubmit={onSubmit} className="mb-2.5 flex flex-wrap gap-2">
            <div className="min-w-[110px] flex-1"><SearchInput value={name} onChange={setName} placeholder={t('set.dict.name')} testid="ont-dict-name" /></div>
            <div className="min-w-[90px] flex-1"><SearchInput value={type} onChange={setType} placeholder={t('set.dict.type')} testid="ont-dict-type" /></div>
            <div className="min-w-[120px] flex-[1.4]"><SearchInput value={notes} onChange={setNotes} placeholder={t('set.dict.notes')} testid="ont-dict-notes" /></div>
            <button
              type="submit"
              disabled={save.isPending || !name.trim() || !type.trim()}
              data-testid="ont-dict-save"
              className="flex-none rounded-btn bg-btn-primary px-4 py-2 font-body text-[12px] font-semibold text-white disabled:opacity-50"
              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}
            >
              {editId == null ? t('set.dict.add') : t('set.dict.update')}
            </button>
            {editId != null && (
              <button type="button" onClick={reset} className="flex-none rounded-btn px-3 py-2 font-mono text-[11px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                {t('set.dict.cancel')}
              </button>
            )}
          </form>
          <SearchInput value={q} onChange={setQ} placeholder={t('ont.searchEntities')} testid="ont-dict-search" />
          <div className="mt-2 px-1 font-mono text-[10px] text-ink-3">{t('ont.shown', { count: filtered.length })}</div>
          <div role="listbox" aria-label={t('ont.tab.dictionary')} className="mt-1 min-h-0 flex-1 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="grid place-items-center py-10 font-mono text-[12px] text-ink-3">{t('set.dict.none')}</div>
            ) : (
              filtered.map((en) => {
                const active = selectedId === en.id;
                return (
                  <div
                    key={en.id}
                    data-testid="ont-dict-row"
                    className="flex items-center gap-2 border-b border-[var(--card-hairline)] px-2.5 py-2.5 last:border-0"
                    style={active ? { background: 'color-mix(in srgb, var(--sec-ontology) 12%, transparent)' } : undefined}
                  >
                    <button type="button" onClick={() => setSelectedId(en.id)} className="min-w-0 flex-1 truncate text-left text-[12.5px] text-ink-1">
                      {en.name}
                    </button>
                    <span className="flex-none font-mono text-[9.5px] text-ink-3">{en.entity_type}</span>
                    <button type="button" onClick={() => onEdit(en)} className="flex-none rounded-sm px-2 py-1 font-mono text-[10.5px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                      {t('set.dict.edit')}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(en.id)}
                      disabled={del.isPending}
                      data-testid="ont-dict-delete"
                      className="flex-none rounded-sm px-2 py-1 font-mono text-[10.5px] text-red disabled:opacity-50"
                      style={{ background: 'color-mix(in srgb, var(--red) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 38%, transparent)' }}
                    >
                      {confirmId === en.id ? t('set.confirmDelete') : t('set.dict.delete')}
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </GlassCard>

        {/* DETAIL — same merge-flow as the Entities tab, so you can merge from here. */}
        <GlassCard className="flex max-h-[calc(100vh-250px)] flex-col p-[18px]">
          {selected ? (
            <EntityDetail key={selected.id} entity={{ name: selected.name, type: selected.entity_type }} inDict isStop={stopSet.has(selected.name.toLowerCase())} />
          ) : (
            <div className="grid h-full place-items-center px-6 text-center font-mono text-[12px] text-ink-3">{t('ont.dictSelectPrompt')}</div>
          )}
        </GlassCard>
      </div>
    </StateWrap>
  );
}

export function OntologyConsole() {
  const { t } = useTranslation();
  const me = useAuthMe();
  const isAdmin = Boolean(me.data?.is_super || me.data?.is_ceo);
  const [tab, setTab] = useState<'entities' | 'predicates' | 'aliases' | 'dictionary'>('entities');

  return (
    <>
      <div className="mb-[18px] mt-1.5 flex items-end justify-between gap-4 px-0.5">
        <div>
          <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('ont.title')}</h1>
          <p className="mt-1.5 text-[12.5px] text-ink-3">{t('ont.subtitle')}</p>
        </div>
        <div role="tablist" aria-label={t('ont.title')} className="flex gap-0.5 rounded-md p-0.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          {(['entities', 'predicates', 'aliases', 'dictionary'] as const).map((tb) => (
            <button
              key={tb}
              type="button"
              role="tab"
              id={`ont-tab-${tb}`}
              aria-selected={tab === tb}
              aria-controls={`ont-panel-${tb}`}
              data-testid={`ont-tab-${tb}`}
              onClick={() => setTab(tb)}
              className={`rounded-[7px] px-3 py-1.5 font-body text-[12.5px] ${tab === tb ? 'text-ink-1' : 'text-ink-3'}`}
              style={tab === tb ? { background: 'var(--card-bg)', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' } : undefined}
            >
              {t(`ont.tab.${tb}`)}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel" id={`ont-panel-${tab}`} aria-labelledby={`ont-tab-${tab}`}>
        {tab === 'entities' ? (
          <EntitiesTab isAdmin={isAdmin} />
        ) : tab === 'predicates' ? (
          <PredicatesTab isAdmin={isAdmin} />
        ) : tab === 'aliases' ? (
          <AliasesTab isAdmin={isAdmin} />
        ) : (
          <DictionaryTab isAdmin={isAdmin} />
        )}
      </div>
    </>
  );
}
