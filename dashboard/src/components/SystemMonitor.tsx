import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewStore } from '../stores/view';
import { useSystemStats, useAgentStats } from '../hooks/stats';
import { useAgentPresence } from '../stores/presence';
import { asArray } from '../lib/asArray';
import type { AgentStat } from '../types/api';

const ACCENT = 'var(--sec-settings)'; // neutral/ambient slate

function fmtNum(n?: number): string {
  return n != null ? n.toLocaleString('en-US') : '—';
}

function Chevron({ up }: { up: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={13} height={13} style={{ transform: up ? 'rotate(180deg)' : undefined, transition: 'transform .15s ease-out' }}>
      <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Metric({ label, value, color }: { label: string; value: ReactNode; color: string }) {
  return (
    <div className="min-w-[78px] flex-1 rounded-md px-3 py-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center gap-1.5">
        <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: color }} />
        <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{label}</span>
      </div>
      <div className="mt-1 font-mono text-[15px] leading-none tabular-nums text-ink-1">{value}</div>
    </div>
  );
}

export function SystemMonitor() {
  const { t } = useTranslation();
  const expanded = useViewStore((s) => s.sysExpanded);
  const toggle = useViewStore((s) => s.toggleSys);
  const sys = useSystemStats();
  const agentsQ = useAgentStats();
  const presence = useAgentPresence((s) => s.online);

  const db = sys.data?.db;
  const emb = sys.data?.embeddings;
  const media = sys.data?.media;

  // Embedding-service health drives the dot color for both the Embeddings tile
  // and the collapsed handle strip.
  const embReady = emb?.status === 'ok' && emb.model_loaded === true;
  const embColor = !emb ? 'var(--ink-4)' : embReady ? 'var(--grn)' : 'var(--kind-agent)';
  const embLabel = !emb ? '—' : embReady ? t('appbar.online') : t('appbar.degraded');
  const embValue = sys.isPending ? '…' : !emb ? '—' : emb.model_loaded ? (emb.quantization ?? t('sys.loaded')) : t('sys.loading');

  // Roster from /stats/agents (7d window); "online" is live presence (SSE), never
  // last_activity. Count matches the green chips the user actually sees.
  const agents = asArray<AgentStat>(agentsQ.data?.agents);
  const online = agents.filter((a) => presence.has(a.identifier));
  const agentColor = online.length > 0 ? 'var(--grn)' : 'var(--ink-4)';

  return (
    <div
      className="flex flex-none flex-col overflow-hidden rounded-xl"
      style={{ background: 'var(--tray-bg)', backdropFilter: 'blur(22px) saturate(1.3)', WebkitBackdropFilter: 'blur(22px) saturate(1.3)', boxShadow: 'var(--tray-shadow)' }}
    >
      {expanded && (
        <div className="flex flex-col gap-2.5 px-6 pb-2.5 pt-3">
          <div className="flex flex-wrap gap-2">
            <Metric label={t('sys.metric.memories')} value={sys.isPending ? '…' : fmtNum(db?.memories_count)} color={ACCENT} />
            <Metric label={t('sys.metric.nodes')} value={sys.isPending ? '…' : fmtNum(db?.nodes_count)} color={ACCENT} />
            <Metric label={t('sys.metric.triples')} value={sys.isPending ? '…' : fmtNum(db?.triples_count)} color={ACCENT} />
            <Metric label={t('sys.metric.embeddings')} value={embValue} color={embColor} />
            <Metric label={t('sys.metric.cpu')} value={sys.isPending ? '…' : emb?.cpu_percent != null ? `${emb.cpu_percent.toFixed(1)}%` : '—'} color={ACCENT} />
            <Metric label={t('sys.metric.media')} value={sys.isPending ? '…' : fmtNum(media?.files_count)} color={ACCENT} />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('sys.agentsLabel')}</span>
            {agents.length === 0 ? (
              <span className="font-mono text-[10.5px] text-ink-3">{t('sys.noAgents')}</span>
            ) : (
              agents.map((a) => {
                const on = presence.has(a.identifier);
                return (
                  <span key={a.identifier} className="flex items-center gap-1.5 rounded-sm px-2 py-0.5 font-mono text-[10px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                    <span className="h-[5px] w-[5px] rounded-full" style={{ background: on ? 'var(--grn)' : 'var(--ink-4)', boxShadow: on ? '0 0 5px var(--grn)' : undefined }} />
                    {a.identifier}
                  </span>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Handle strip — always visible, toggles the panel. */}
      <button
        type="button"
        onClick={toggle}
        data-testid="sys-toggle"
        aria-expanded={expanded}
        aria-label={expanded ? t('sys.collapse') : t('sys.expand')}
        className="flex h-[30px] flex-none items-center gap-3 px-6 text-left transition-colors hover:bg-[var(--inset)]"
      >
        <span className="flex items-center gap-2">
          <span className="h-[6px] w-[6px] rounded-full motion-safe:animate-pulse" style={{ background: ACCENT, boxShadow: `0 0 6px ${ACCENT}` }} />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-2">{t('sys.title')}</span>
        </span>
        <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
          <span className="h-[5px] w-[5px] rounded-full" style={{ background: embColor, boxShadow: embColor !== 'var(--ink-4)' ? `0 0 4px ${embColor}` : undefined }} />
          {t('sys.metric.embeddings').toLowerCase()} {embLabel}
        </span>
        <span className="flex items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
          <span className="h-[5px] w-[5px] rounded-full" style={{ background: agentColor, boxShadow: agentColor !== 'var(--ink-4)' ? `0 0 4px ${agentColor}` : undefined }} />
          {online.length} {t('sys.metric.agents').toLowerCase()}
        </span>
        <span className="ml-auto text-ink-3">
          <Chevron up={!expanded} />
        </span>
      </button>
    </div>
  );
}
