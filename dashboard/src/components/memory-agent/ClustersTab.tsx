import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../GlassCard';
import { PanelState } from '../Panel';
import { asArray } from '../../lib/asArray';
import { errMsg } from '../../lib/errMsg';
import { ClusterCard, type ClusterCardData } from './ClusterCard';
import { ClusterDrawer } from './ClusterDrawer';
import { useClusters, useClusterSearch, type ClusterLevel, type ClusterStatus, type ClusterSummary, type ClusterSearchResult } from '../../hooks/useMemoryAgent';

const LEVELS: ClusterLevel[] = ['weekly', 'monthly', 'quarterly', 'yearly'];
const STATUSES: ClusterStatus[] = ['candidate', 'active', 'rejected', 'superseded'];

function Select({ label, value, anyLabel, options, onChange }: { label: string; value: string; anyLabel: string; options: readonly string[]; onChange: (v: string) => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="min-w-0 rounded-[7px] px-2.5 py-1.5 font-mono text-[11px] text-ink-1 outline-none"
        style={{ background: 'var(--inset)', boxShadow: focused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : `inset 0 0 0 1px ${value ? 'color-mix(in srgb, var(--sec-memory-agent) 40%, transparent)' : 'var(--card-hairline)'}` }}
      >
        <option value="">{anyLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

const toListCard = (c: ClusterSummary): ClusterCardData => ({
  id: c.id,
  label: c.label,
  level: c.level,
  periodStart: c.period_start,
  periodEnd: c.period_end,
  memberCount: c.member_count,
  preview: (c.narrative ?? c.detail ?? '').slice(0, 160),
  score: null,
});
const toSearchCard = (r: ClusterSearchResult): ClusterCardData => ({
  id: r.id,
  label: r.label,
  level: r.level,
  periodStart: r.period_start,
  periodEnd: r.period_end,
  memberCount: r.member_count,
  preview: r.narrative_preview.slice(0, 160),
  score: r.vector_score,
});

// Clusters tab (Spec §5 Tab 3) — browse/search consolidated memory clusters, open
// each in a drawer (narrative + members + telescopic sources). List/detail are
// real (v2.0); semantic search is mocked until Hilo ships POST /clusters/search.
export function ClustersTab({ agentIdentifier, initialClusterId }: { agentIdentifier?: string; initialClusterId?: string }) {
  const { t } = useTranslation();
  const defaultAgent = agentIdentifier ?? 'Lienzo'; // dev default until the agent selector lands
  const [fAgent, setFAgent] = useState(defaultAgent);
  const [fLevel, setFLevel] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => setFAgent(defaultAgent), [defaultAgent]);
  useEffect(() => {
    if (initialClusterId) setOpenId(initialClusterId);
  }, [initialClusterId]);

  const listQ = useClusters({ agentIdentifier: fAgent, level: (fLevel || undefined) as ClusterLevel | undefined, status: (fStatus || undefined) as ClusterStatus | undefined });
  const search = useClusterSearch();

  const cards = useMemo<ClusterCardData[]>(() => {
    if (searched) return asArray<ClusterSearchResult>(search.data?.results).map(toSearchCard);
    return asArray<ClusterSummary>(listQ.data?.items).map(toListCard);
  }, [searched, search.data, listQ.data]);

  const loading = searched ? search.isPending : listQ.isPending;
  const isError = searched ? search.isError : listQ.isError;
  const error = searched ? search.error : listQ.error;
  const refetch = () => (searched ? undefined : void listQ.refetch());

  const runSearch = () => {
    const q = query.trim();
    if (q.length < 3) return;
    search.mutate({ query_text: q, agent_identifier: fAgent || undefined, level: fLevel || undefined, status: fStatus || undefined, limit: 10 });
    setSearched(true);
  };
  const clearSearch = () => {
    setSearched(false);
    setQuery('');
    search.reset();
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <GlassCard className="flex flex-none flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runSearch()}
            placeholder={t('ma.clusters.searchPlaceholder')}
            maxLength={2000}
            className="min-w-[200px] flex-1 rounded-[7px] px-3 py-2 font-body text-[12.5px] text-ink-1 outline-none placeholder:text-ink-4"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
          />
          <button type="button" onClick={runSearch} disabled={query.trim().length < 3} className="rounded-btn px-3.5 py-2 font-body text-[12px] font-semibold text-ink-1 disabled:opacity-40" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>
            {t('ma.clusters.search')}
          </button>
          {searched && (
            <button type="button" onClick={clearSearch} className="font-mono text-[10.5px] text-ink-3 transition-colors hover:text-ink-1">
              {t('ma.clusters.clearSearch')}
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-2.5">
          <label className="flex min-w-0 flex-col gap-1">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.clusters.filter.agent')}</span>
            <input value={fAgent} onChange={(e) => setFAgent(e.target.value)} placeholder={t('ma.clusters.filter.agentPlaceholder')} maxLength={128} className="min-w-0 rounded-[7px] px-2.5 py-1.5 font-mono text-[11px] text-ink-1 outline-none placeholder:text-ink-4" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }} />
          </label>
          <Select label={t('ma.clusters.filter.level')} value={fLevel} anyLabel={t('ma.clusters.filter.any')} options={LEVELS} onChange={setFLevel} />
          <Select label={t('ma.clusters.filter.status')} value={fStatus} anyLabel={t('ma.clusters.filter.any')} options={STATUSES} onChange={setFStatus} />
          <span className="ml-auto rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-2" style={{ background: 'color-mix(in srgb, var(--sec-memory-agent) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)' }}>
            {searched ? t('ma.clusters.originSearch') : t('ma.clusters.originList')}
          </span>
        </div>

        {isError ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
            <span className="text-[12.5px] text-ink-2">{errMsg(error, t, t('ma.clusters.error'))}</span>
            {!searched && (
              <button type="button" onClick={refetch} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">{t('ma.clusters.retry')}</button>
            )}
          </div>
        ) : (
          <PanelState loading={loading} empty={!loading && cards.length === 0} emptyLabel={searched ? t('ma.clusters.emptySearch') : t('ma.clusters.emptyList')}>
            <div className="grid gap-2.5 md:grid-cols-2">
              {cards.map((c) => (
                <ClusterCard key={c.id} data={c} onOpen={setOpenId} />
              ))}
            </div>
          </PanelState>
        )}
      </GlassCard>

      {openId && <ClusterDrawer clusterId={openId} onClose={() => setOpenId(null)} onOpenCluster={setOpenId} />}
    </div>
  );
}
