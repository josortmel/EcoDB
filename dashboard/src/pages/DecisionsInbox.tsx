import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../components/GlassCard';
import { PanelState } from '../components/Panel';
import { ApiError } from '../lib/api';
import { errMsg } from '../lib/errMsg';
import { asArray } from '../lib/asArray';
import { useToastStore } from '../stores/toast';
import { useInboxSummary, useInboxDetails, useAliasCandidates, useReviewAliasCandidate, type AliasItem } from '../hooks/inbox';
import { useUpdateStaleness, type Staleness } from '../hooks/memory';
import type { InboxClass, InboxDetailItem } from '../types/api';

const ACCENT = 'var(--sec-decisions)'; // §2.9 decisions #C98A3C
const LIMIT = 20;
const CLASSES: InboxClass[] = ['stale_memories', 'pending_alias_candidates', 'unconfirmed_relations', 'low_trust_documents'];

const TYPE_COLOR: Record<string, string> = {
  decision: 'var(--type-decision)',
  tecnico: 'var(--type-tecnico)',
  momento: 'var(--type-momento)',
  observacion: 'var(--type-observacion)',
  referencia: 'var(--type-referencia)',
};
const day = (iso?: string): string => (iso ? iso.slice(0, 10) : '—');
const pct = (c?: number): string => `${Math.round((c ?? 0) * 100)}%`;

// The inbox item shape varies by class (alias candidates differ from the rest),
// so the list works against a permissive raw item and narrows in the detail.
type RawItem = {
  id: string | number;
  content?: string;
  type?: string;
  staleness?: string;
  created_at?: string;
  agent_identifier?: string | null;
  source_name?: string;
  target_node_name?: string;
  confidence?: number;
  occurrences?: number;
};

function ClassTab({ active, label, count, onClick, id }: { active: boolean; label: string; count: number; onClick: () => void; id: string }) {
  return (
    <button
      type="button"
      role="tab"
      id={id}
      aria-controls="dec-panel"
      onClick={onClick}
      data-testid="dec-tab"
      aria-selected={active}
      className="flex items-center gap-2 rounded-md px-3 py-2 font-mono text-[11.5px] transition-colors"
      style={active ? { color: ACCENT, background: 'color-mix(in srgb, var(--sec-decisions) 13%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-decisions) 38%, transparent)' } : { color: 'var(--ink-3)', background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <span>{label}</span>
      <span className="min-w-[20px] rounded-[20px] px-1.5 py-0.5 text-center text-[10px] tabular-nums" style={count > 0 ? { background: ACCENT, color: '#fff' } : { background: 'var(--card-bg)', color: 'var(--ink-3)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
        {count}
      </span>
    </button>
  );
}

function Row({ active, onClick, color, lead, meta, badge }: { active: boolean; onClick: () => void; color: string; lead: ReactNode; meta: ReactNode; badge?: ReactNode }) {
  return (
    <button
      type="button"
      role="option"
      data-testid="dec-row"
      onClick={onClick}
      aria-selected={active}
      className="grid w-full grid-cols-[16px_1fr_auto] items-start gap-3 border-b border-[var(--card-hairline)] px-3 py-3 text-left transition-colors last:border-0 hover:bg-[var(--inset)]"
      style={active ? { background: 'color-mix(in srgb, var(--sec-decisions) 9%, transparent)', boxShadow: 'inset 2px 0 0 var(--sec-decisions)' } : undefined}
    >
      <span className="mt-1 grid h-[14px] w-[14px] place-items-center rounded-full" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
        <span className="h-[6px] w-[6px] rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      </span>
      <span className="min-w-0">
        <span className="line-clamp-2 block text-[12.5px] leading-snug text-ink-1">{lead}</span>
        <span className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[10px] text-ink-3">{meta}</span>
      </span>
      {badge}
    </button>
  );
}

function MetaCell({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="truncate font-mono text-[12.5px] capitalize text-ink-1">{v}</div>
      <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{k}</div>
    </div>
  );
}

function ActionBtn({ children, onClick, variant, disabled }: { children: ReactNode; onClick?: () => void; variant: 'resolve' | 'defer' | 'dismiss' | 'off'; disabled?: boolean }) {
  const { t } = useTranslation();
  const off = variant === 'off';
  const style =
    variant === 'resolve'
      ? { background: 'var(--btn-primary)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }
      : variant === 'dismiss'
        ? { background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }
        : { background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' };
  const text = variant === 'resolve' ? 'text-white' : variant === 'dismiss' ? 'text-red' : 'text-ink-1';
  return (
    <button
      type="button"
      onClick={off ? undefined : onClick}
      disabled={off || disabled}
      aria-disabled={off || undefined}
      title={off ? t('dec.requiresBackend') : undefined}
      className={`flex-1 rounded-btn py-2.5 font-body text-[12.5px] font-semibold transition-[filter] hover:brightness-105 disabled:opacity-40 ${text} ${off ? 'opacity-40' : ''}`}
      style={style}
    >
      {children}
    </button>
  );
}

function WhyBox({ text }: { text: string }) {
  const { t } = useTranslation();
  return (
    <div className="mt-4 flex items-start gap-2.5 rounded-md px-3.5 py-3" style={{ background: 'color-mix(in srgb, var(--sec-decisions) 8%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-decisions) 25%, transparent)' }}>
      <span className="mt-[3px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: ACCENT }} />
      <div>
        <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: ACCENT }}>{t('dec.why')}</div>
        <div className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{text}</div>
      </div>
    </div>
  );
}

function StaleDetail({ item, acting, onStale }: { item: InboxDetailItem; acting: boolean; onStale: (id: string, s: Staleness) => void }) {
  const { t } = useTranslation();
  const color = TYPE_COLOR[item.type] ?? 'var(--type-referencia)';
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: ACCENT }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
        {t('dec.class.stale_memories')} · {item.type}
      </div>
      <p className="mt-3 text-[13.5px] leading-relaxed text-ink-1">{item.content}</p>
      <WhyBox text={t('dec.whyText.stale_memories')} />
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <MetaCell k={t('dec.author')} v={item.agent_identifier ?? '—'} />
        <MetaCell k={t('dec.typeLabel')} v={item.type} />
        <MetaCell k={t('dec.staleness')} v={item.staleness || '—'} />
        <MetaCell k={t('dec.created')} v={day(item.created_at)} />
      </div>
      <div className="flex-1" />
      <div className="mt-5 flex gap-2.5">
        <ActionBtn variant="resolve" disabled={acting} onClick={() => onStale(item.id, 'active')}>{t('dec.resolve')}</ActionBtn>
        <ActionBtn variant="defer" disabled={acting} onClick={() => onStale(item.id, 'dormant')}>{t('dec.defer')}</ActionBtn>
        <ActionBtn variant="dismiss" disabled={acting} onClick={() => onStale(item.id, 'archived')}>{t('dec.dismiss')}</ActionBtn>
      </div>
    </div>
  );
}

function AliasDetail({ item, acting, onReview }: { item: AliasItem; acting: boolean; onReview: (id: number, status: 'approved' | 'rejected') => void }) {
  const { t } = useTranslation();
  // Approve runs a graph merge (destructive, needs undo to revert) — gate it
  // behind an explicit confirm (adv-seg VS-MERGE-M1). Reset per item via the key
  // on the parent render.
  const [confirm, setConfirm] = useState(false);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: ACCENT }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: ACCENT, boxShadow: `0 0 8px ${ACCENT}` }} />
        {t('dec.class.pending_alias_candidates')}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[15px] leading-tight text-ink-1">
        <span className="font-semibold">{item.source_name}</span>
        <span className="text-ink-3">→</span>
        <span className="font-semibold">{item.target_node_name}</span>
      </div>
      <WhyBox text={t('dec.whyText.pending_alias_candidates')} />
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <MetaCell k={t('dec.confidence')} v={pct(item.confidence)} />
        <MetaCell k={t('dec.occurrences')} v={String(item.occurrences)} />
      </div>
      <div className="flex-1" />
      {confirm ? (
        <div className="mt-5 flex flex-col gap-2.5">
          <div className="text-[11.5px] leading-snug text-ink-2">{t('dec.mergeConfirm', { source: item.source_name, target: item.target_node_name })}</div>
          <div className="flex gap-2.5">
            <ActionBtn variant="resolve" disabled={acting} onClick={() => onReview(item.id, 'approved')}>{t('dec.confirmMerge')}</ActionBtn>
            <ActionBtn variant="defer" onClick={() => setConfirm(false)}>{t('dec.cancel')}</ActionBtn>
          </div>
        </div>
      ) : (
        <div className="mt-5 flex gap-2.5">
          <ActionBtn variant="resolve" disabled={acting} onClick={() => setConfirm(true)}>{t('dec.resolve')}</ActionBtn>
          <ActionBtn variant="dismiss" disabled={acting} onClick={() => onReview(item.id, 'rejected')}>{t('dec.dismiss')}</ActionBtn>
        </div>
      )}
    </div>
  );
}

function DisabledDetail({ item, decisionClass }: { item: InboxDetailItem; decisionClass: InboxClass }) {
  const { t } = useTranslation();
  const color = TYPE_COLOR[item.type] ?? 'var(--type-referencia)';
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: ACCENT }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
        {t(`dec.class.${decisionClass}`)} · {item.type}
      </div>
      <p className="mt-3 text-[13.5px] leading-relaxed text-ink-1">{item.content}</p>
      <WhyBox text={t(`dec.whyText.${decisionClass}`)} />
      <div className="flex-1" />
      <div className="mt-5 flex gap-2.5">
        <ActionBtn variant="off">{t('dec.resolve')}</ActionBtn>
        <ActionBtn variant="off">{t('dec.dismiss')}</ActionBtn>
      </div>
    </div>
  );
}

export function DecisionsInbox() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const summary = useInboxSummary();
  const staleness = useUpdateStaleness();
  const alias = useReviewAliasCandidate();
  const [decisionClass, setDecisionClass] = useState<InboxClass>('stale_memories');
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  const isAlias = decisionClass === 'pending_alias_candidates';
  const isStale = decisionClass === 'stale_memories';
  // Alias candidates have their own rich endpoint; everything else uses the
  // generic inbox details.
  const details = useInboxDetails(decisionClass, LIMIT, offset, !isAlias);
  const aliasQ = useAliasCandidates(isAlias ? LIMIT : 0);
  const activeQ = isAlias ? aliasQ : details;
  const items = asArray<RawItem>(isAlias ? aliasQ.data : details.data?.items);
  const total = isAlias ? items.length : details.data?.total ?? 0;
  const selected = items.find((i) => i.id === selectedId) ?? items[0] ?? null;
  const acting = staleness.isPending || alias.isPending;

  const is403 = (activeQ.error instanceof ApiError && activeQ.error.status === 403) || (summary.error instanceof ApiError && summary.error.status === 403);

  const onDone = () => {
    toast(t('dec.actionDone'));
    setSelectedId(null);
  };
  const onStale = (id: string, s: Staleness) => staleness.mutate({ id, staleness: s }, { onSuccess: onDone, onError: (e) => toast(errMsg(e, t, t('dec.actionFailed'))) });
  const onReview = (id: number, status: 'approved' | 'rejected') => alias.mutate({ id, status, ...(status === 'approved' ? { merge: true } : {}) }, { onSuccess: onDone, onError: (e) => toast(errMsg(e, t, t('dec.actionFailed'))) });

  const pickClass = (c: InboxClass) => {
    setDecisionClass(c);
    setOffset(0);
    setSelectedId(null);
  };

  return (
    <>
      <div className="mb-[18px] mt-1.5 px-0.5">
        <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('dec.title')}</h1>
        <p className="mt-1.5 text-[12.5px] text-ink-3">{t('dec.subtitle')}</p>
      </div>

      <div role="tablist" aria-label={t('dec.title')} className="mb-4 flex flex-wrap gap-2">
        {CLASSES.map((c) => (
          <ClassTab key={c} id={`dec-tab-${c}`} active={decisionClass === c} label={t(`dec.class.${c}`)} count={summary.data?.classes?.[c] ?? 0} onClick={() => pickClass(c)} />
        ))}
      </div>

      <div role="tabpanel" id="dec-panel" aria-labelledby={`dec-tab-${decisionClass}`}>
        {is403 ? (
          <GlassCard className="p-[18px]">
            <div className="grid place-items-center py-16 font-mono text-[12.5px] text-ink-3">{t('dec.limitedAccess')}</div>
          </GlassCard>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <GlassCard className="flex max-h-[calc(100vh-220px)] flex-col p-2">
              <PanelState loading={activeQ.isPending} error={activeQ.isError} onRetry={() => void activeQ.refetch()} empty={!activeQ.isPending && items.length === 0} emptyLabel={t('dec.allClear')}>
                <div role="listbox" aria-label={t('dec.title')} className="min-h-0 flex-1 overflow-y-auto">
                  {items.map((it) =>
                    isAlias ? (
                      <Row
                        key={it.id}
                        active={selected?.id === it.id}
                        onClick={() => setSelectedId(it.id)}
                        color={ACCENT}
                        lead={
                          <span>
                            {it.source_name} <span className="text-ink-3">→</span> {it.target_node_name}
                          </span>
                        }
                        meta={
                          <>
                            <span>{pct(it.confidence)}</span>
                            <span>·</span>
                            <span>{it.occurrences}×</span>
                          </>
                        }
                      />
                    ) : (
                      <Row
                        key={it.id}
                        active={selected?.id === it.id}
                        onClick={() => setSelectedId(it.id)}
                        color={TYPE_COLOR[it.type ?? ''] ?? 'var(--type-referencia)'}
                        lead={it.content}
                        meta={
                          <>
                            <span>{day(it.created_at)}</span>
                            <span>·</span>
                            <span>{it.agent_identifier ?? '—'}</span>
                            <span>·</span>
                            <span>{it.type ?? '—'}</span>
                          </>
                        }
                        badge={
                          it.staleness === 'stale' ? (
                            <span className="mt-0.5 flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px]" style={{ color: 'var(--kind-agent)', background: 'color-mix(in srgb, var(--kind-agent) 10%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-agent) 30%, transparent)' }}>
                              {t('dec.staleBadge')}
                            </span>
                          ) : undefined
                        }
                      />
                    ),
                  )}
                </div>
                {!isAlias && (
                <div className="mt-1 flex flex-none items-center justify-between gap-2 border-t border-[var(--card-hairline)] px-2 py-2">
                  <span className="font-mono text-[10px] tabular-nums text-ink-3">{t('dec.page', { from: total === 0 ? 0 : offset + 1, to: Math.min(offset + LIMIT, total), total })}</span>
                  <div className="flex gap-1.5">
                    <button type="button" data-testid="dec-prev" onClick={() => setOffset((o) => Math.max(0, o - LIMIT))} disabled={offset === 0} className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-ink-2 transition-colors disabled:opacity-40" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                      {t('dec.prev')}
                    </button>
                    <button type="button" data-testid="dec-next" onClick={() => setOffset((o) => o + LIMIT)} disabled={offset + LIMIT >= total} className="rounded-sm px-2.5 py-1 font-mono text-[11px] text-ink-2 transition-colors disabled:opacity-40" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                      {t('dec.next')}
                    </button>
                  </div>
                </div>
                )}
              </PanelState>
            </GlassCard>

            <GlassCard className="flex max-h-[calc(100vh-220px)] flex-col p-[18px]">
              {selected ? (
                isAlias ? (
                  <AliasDetail key={String(selected.id)} item={selected as unknown as AliasItem} acting={acting} onReview={onReview} />
                ) : isStale ? (
                  <StaleDetail item={selected as unknown as InboxDetailItem} acting={acting} onStale={onStale} />
                ) : (
                  <DisabledDetail item={selected as unknown as InboxDetailItem} decisionClass={decisionClass} />
                )
              ) : (
                <div className="grid h-full place-items-center px-6 text-center font-mono text-[12px] leading-relaxed text-ink-3">{activeQ.isPending ? '' : t('dec.selectPrompt')}</div>
              )}
            </GlassCard>
          </div>
        )}
      </div>
    </>
  );
}
