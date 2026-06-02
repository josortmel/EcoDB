import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel, PanelState } from '../components/Panel';
import { StatCard } from '../components/StatCard';
import { useViewStore } from '../stores/view';
import { useActivityStore } from '../stores/activity';
import { useMemoryStats, useGraphStats, useAgentStats, useSearchStats, useKnowledgeStats } from '../hooks/stats';
import { useDocuments } from '../hooks/documents';
import { useInboxSummary } from '../hooks/inbox';
import { asArray } from '../lib/asArray';
import type { InboxClass, TopEntity, DocumentListItem } from '../types/api';

const fmt = (n: number | undefined): string => (n == null ? '—' : n.toLocaleString('en-US'));
const hhmm = (ts: number): string => {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

// ── Attention Inbox (the hero — §10: a decision center, not monitoring) ──
const INBOX_ITEMS: { key: InboxClass; labelKey: 'cc.inbox.stale' | 'cc.inbox.alias' | 'cc.inbox.relations' | 'cc.inbox.lowTrust' }[] = [
  { key: 'stale_memories', labelKey: 'cc.inbox.stale' },
  { key: 'pending_alias_candidates', labelKey: 'cc.inbox.alias' },
  { key: 'unconfirmed_relations', labelKey: 'cc.inbox.relations' },
  { key: 'low_trust_documents', labelKey: 'cc.inbox.lowTrust' },
];

function InboxDot({ on }: { on: boolean }) {
  return (
    <span className="grid h-[14px] w-[14px] flex-none place-items-center rounded-full" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <span
        className={`h-[6px] w-[6px] rounded-full ${on ? 'motion-safe:animate-pulse' : ''}`}
        style={on ? { background: 'var(--accent)', boxShadow: '0 0 6px rgba(245,99,30,0.6)' } : { background: 'var(--ink-4)', opacity: 0.6 }}
      />
    </span>
  );
}

function AttentionInbox() {
  const { t } = useTranslation();
  const setView = useViewStore((s) => s.setView);
  const q = useInboxSummary();
  const classes = q.data?.classes;
  const total = q.data?.total ?? 0;

  return (
    <Panel
      title={t('cc.inbox.title')}
      accent="var(--sec-decisions)"
      tooltip={t('cc.inbox.tip')}
      control={
        total > 0 ? (
          <span className="rounded-md px-2 py-0.5 font-mono text-[11px] font-medium tabular-nums text-white" style={{ background: 'var(--accent)' }}>
            {total}
          </span>
        ) : undefined
      }
    >
      <PanelState
        loading={q.isPending}
        error={q.isError}
        onRetry={() => void q.refetch()}
        empty={!!classes && total === 0}
        emptyLabel={t('cc.inbox.allClear')}
      >
        <div className="flex flex-col">
          {INBOX_ITEMS.map(({ key, labelKey }) => {
            const count = classes?.[key] ?? 0;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setView('decisions')}
                data-testid={`inbox-${key}`}
                className="flex items-center gap-3 rounded-md px-2 py-2.5 text-left transition-colors hover:bg-[var(--inset)]"
              >
                <InboxDot on={count > 0} />
                <span className={`flex-1 font-mono text-[12.5px] ${count > 0 ? 'text-ink-1' : 'text-ink-3'}`}>{t(labelKey)}</span>
                <span
                  className="min-w-[28px] rounded-md px-2 py-0.5 text-center font-mono text-[11px] tabular-nums"
                  style={
                    count > 0
                      ? { background: 'var(--accent)', color: '#fff' }
                      : { background: 'var(--inset)', color: 'var(--ink-2)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }
                  }
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => setView('decisions')}
          className="mt-4 w-full rounded-btn py-2.5 font-body text-[12.5px] font-semibold transition-colors"
          style={{
            color: 'var(--sec-decisions)',
            background: 'color-mix(in srgb, var(--sec-decisions) 13%, transparent)',
            boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-decisions) 34%, transparent)',
          }}
        >
          {t('cc.inbox.review')} →
        </button>
      </PanelState>
    </Panel>
  );
}

// ── Live activity feed (SSE) ──
function ActivityFeed() {
  const { t } = useTranslation();
  const items = useActivityStore((s) => s.items);
  // Loose call for the dynamic (backend-enum) event key + a humanized fallback.
  const tx = t as (k: string, o?: { defaultValue?: string }) => string;
  return (
    <Panel title={t('cc.activity.title')} accent="var(--sec-explorer)" tag={t('cc.activity.tag')} tooltip={t('cc.activity.tip')}>
      {items.length === 0 ? (
        <div className="grid place-items-center py-6 font-mono text-[12px] text-ink-3">{t('cc.activity.empty')}</div>
      ) : (
        <div className="flex max-h-[260px] flex-col overflow-y-auto">
          {items.map((it) => (
            <div key={it.id} className="flex items-center gap-3 border-b border-[var(--card-hairline)] py-2.5 last:border-0">
              <span className="flex-none font-mono text-[10.5px] tabular-nums text-ink-3">{hhmm(it.ts)}</span>
              <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-1">
                {tx(`cc.activity.event.${it.event}`, { defaultValue: it.event.replace(/_/g, ' ') })}
              </span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── Knowledge health (real /api/v1/stats/knowledge) ──
function HealthStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md p-2 text-center" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="font-mono text-[14px] tabular-nums text-ink-1">{value}</div>
      <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-3">{label}</div>
    </div>
  );
}

function KnowledgeHealth() {
  const { t } = useTranslation();
  const q = useKnowledgeStats();
  const k = q.data;
  return (
    <Panel title={t('cc.health.title')} accent="var(--sec-graph)" tag={t('cc.health.tag')} tooltip={t('cc.health.tip')}>
      <PanelState loading={q.isPending} error={q.isError} onRetry={() => void q.refetch()} empty={!k}>
        {k && (
          <>
            <div className="grid grid-cols-3 gap-2">
              <HealthStat label={t('cc.health.entities')} value={fmt(k.entity_count)} />
              <HealthStat label={t('cc.health.orphans')} value={fmt(k.orphan_entity_count)} />
              <HealthStat label={t('cc.health.density')} value={(k.graph_density ?? 0).toFixed(4)} />
              <HealthStat label={t('cc.health.stale')} value={fmt(k.stale_memory_count)} />
              <HealthStat label={t('cc.health.dormant')} value={fmt(k.dormant_memory_count)} />
              <HealthStat label={t('cc.health.duplicates')} value={fmt(k.duplicate_candidate_count)} />
            </div>
            <div className="mt-3">
              <div className="mb-1.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('cc.health.top')}</div>
              <div className="flex flex-col gap-1">
                {asArray<TopEntity>(k.top_entities_by_degree).slice(0, 5).map((e) => (
                  <div key={e.id} className="flex items-center gap-2 text-[11.5px]">
                    <span className="flex-1 truncate text-ink-1">{e.name}</span>
                    <span className="font-mono text-[9.5px] text-ink-3">{e.type}</span>
                    <span className="w-[30px] flex-none text-right font-mono text-[10px] tabular-nums text-ink-2">{e.degree}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </PanelState>
    </Panel>
  );
}

// ── Ingestion snapshot ──
// No dedicated counts endpoint, so we aggregate the document list by status (the
// same source the Ingestion screen uses). The SSE doc events invalidate
// ['documents'], so these counts refresh live as documents move through stages.
const ING_STAGES: { key: 'pending' | 'processing' | 'indexed' | 'duplicate' | 'error'; tone?: 'proc' | 'err' }[] = [
  { key: 'pending' },
  { key: 'processing', tone: 'proc' },
  { key: 'indexed' },
  { key: 'duplicate' },
  { key: 'error', tone: 'err' },
];

function Ingestion() {
  const { t } = useTranslation();
  const setView = useViewStore((s) => s.setView);
  // No counts endpoint, so we aggregate the document list. 100 is the backend's max
  // page (GET /documents caps limit at 100; 500 → 422). If the cap is hit
  // (total === 100) the buckets may undercount — surfaced as a note.
  const q = useDocuments(100);
  // asArray lives INSIDE the memo so its fresh array ref doesn't invalidate the
  // memo every render (it would, since loading/error return a new []).
  const { counts, total } = useMemo(() => {
    const docs = asArray<DocumentListItem>(q.data);
    const counts = { pending: 0, processing: 0, indexed: 0, duplicate: 0, error: 0 };
    for (const d of docs) {
      if (d.status === 'pending') counts.pending++;
      else if (d.status === 'processing') counts.processing++;
      else if (d.status === 'indexed') counts.indexed++;
      else if (d.status === 'duplicate') counts.duplicate++;
      else if (d.status === 'failed') counts.error++;
    }
    return { counts, total: docs.length };
  }, [q.data]);

  return (
    <Panel title={t('cc.ingestion.title')} accent="var(--sec-ingestion)" tag="docling" tooltip={t('cc.ingestion.tip')}>
      <PanelState
        loading={q.isPending}
        error={q.isError}
        onRetry={() => void q.refetch()}
        empty={total === 0}
        emptyLabel={t('cc.ingestion.empty')}
      >
        <div className="grid grid-cols-5 gap-2">
          {ING_STAGES.map((s) => (
            <div
              key={s.key}
              className="min-w-0 rounded-sm py-2.5 text-center"
              style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
            >
              <div
                className="font-mono text-[16px] tabular-nums"
                style={{ color: s.tone === 'proc' ? 'var(--accent)' : s.tone === 'err' ? 'var(--red)' : 'var(--ink-1)' }}
              >
                {counts[s.key]}
              </div>
              <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.04em] text-ink-3">{t(`cc.ingestion.short.${s.key}`)}</div>
            </div>
          ))}
        </div>
        {total === 100 && <div className="mt-1.5 text-center font-mono text-[9.5px] text-ink-3">{t('cc.ingestion.capped')}</div>}
        <button
          type="button"
          onClick={() => setView('ingestion')}
          className="mt-3 w-full rounded-btn py-2 font-body text-[12px] font-semibold"
          style={{
            color: 'var(--sec-ingestion)',
            background: 'color-mix(in srgb, var(--sec-ingestion) 13%, transparent)',
            boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-ingestion) 34%, transparent)',
          }}
        >
          {t('cc.ingestion.open')} →
        </button>
      </PanelState>
    </Panel>
  );
}

export function CommandCenter() {
  const { t } = useTranslation();
  const setView = useViewStore((s) => s.setView);
  const memory = useMemoryStats();
  const graph = useGraphStats();
  const agents = useAgentStats();
  const search = useSearchStats();

  const topType = memory.data?.data?.[0];
  const noSearches = (search.data?.total_queries ?? 0) === 0;

  return (
    <>
      <div className="mb-[18px] mt-1.5 px-0.5">
        <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('cc.title')}</h1>
        <p className="mt-1.5 text-[12.5px] text-ink-3">{t('cc.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:auto-rows-min xl:grid-cols-12">
        <div className="md:col-span-1 xl:col-span-3">
          <StatCard
            label={t('cc.stat.memories')}
            value={fmt(memory.data?.total)}
            sub={topType ? `${topType.label} · ${fmt(topType.count)}` : ''}
            accent
            loading={memory.isPending}
            error={memory.isError}
            onClick={() => setView('explorer')}
            tooltip={t('cc.stat.memoriesTip')}
          />
        </div>
        <div className="md:col-span-1 xl:col-span-3">
          <StatCard
            label={t('cc.stat.graph')}
            value={fmt(graph.data?.nodes_total)}
            unit={t('cc.stat.nodes')}
            sub={t('cc.stat.graphSub', { triples: fmt(graph.data?.triples_total) })}
            loading={graph.isPending}
            error={graph.isError}
            onClick={() => setView('graph')}
            tooltip={t('cc.stat.graphTip')}
          />
        </div>
        <div className="md:col-span-1 xl:col-span-3">
          <StatCard
            label={t('cc.stat.agents')}
            value={fmt(agents.data?.agents?.length)}
            sub={t('cc.stat.agentsSub')}
            loading={agents.isPending}
            error={agents.isError}
            onClick={() => setView('settings')}
            tooltip={t('cc.stat.agentsTip')}
          />
        </div>
        <div className="md:col-span-1 xl:col-span-3">
          <StatCard
            label={t('cc.stat.latency')}
            value={!noSearches && search.data?.p95_latency_ms != null ? String(Math.round(search.data.p95_latency_ms)) : '—'}
            unit={!noSearches && search.data?.p95_latency_ms != null ? t('cc.stat.msP95') : undefined}
            sub={noSearches ? t('cc.stat.noSearches') : t('cc.stat.latencySub')}
            loading={search.isPending}
            error={search.isError}
            tooltip={t('cc.stat.latencyTip')}
          />
        </div>

        <div className="md:col-span-2 xl:col-span-5 xl:row-span-2">
          <AttentionInbox />
        </div>
        <div className="md:col-span-2 xl:col-span-4 xl:row-span-2">
          <ActivityFeed />
        </div>
        <div className="md:col-span-1 xl:col-span-3">
          <KnowledgeHealth />
        </div>
        <div className="md:col-span-1 xl:col-span-3">
          <Ingestion />
        </div>
      </div>
    </>
  );
}
