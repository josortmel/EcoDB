import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { day } from './utils';
import type { ClusterSummary } from '../../hooks/useMemoryAgent';

export function TelescopicRow({ cluster, onOpen }: { cluster: ClusterSummary; onOpen: (clusterId: string) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const narrative = cluster.narrative ?? '';
  const long = narrative.length > 200;
  const shown = open ? narrative : narrative.slice(0, 200);
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <button type="button" onClick={() => onOpen(cluster.id)} className="group flex w-full items-center justify-between gap-2 text-left">
        <span className="min-w-0 truncate text-[13px] font-medium text-ink-1 underline-offset-2 group-hover:underline">{cluster.label}</span>
        <span className="flex flex-none items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
          <span className="uppercase tracking-[0.06em]">{cluster.level}</span>
          <span>·</span>
          <span>{t('ma.briefing.members', { count: cluster.member_count })}</span>
        </span>
      </button>
      <div className="mt-1 font-mono text-[9.5px] text-ink-3">{t('ma.briefing.window', { start: day(cluster.period_start), end: day(cluster.period_end) })}</div>
      {narrative && (
        <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">
          {shown}
          {long && !open ? '…' : ''}
        </p>
      )}
      {long && (
        <button type="button" onClick={() => setOpen((o) => !o)} className="mt-1.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-ink-1">
          {open ? t('ma.briefing.collapse') : t('ma.briefing.expand')}
        </button>
      )}
    </div>
  );
}
