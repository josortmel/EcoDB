import { useTranslation } from 'react-i18next';
import { day } from './utils';

export interface ClusterCardData {
  id: string;
  label: string;
  level: string;
  periodStart: string;
  periodEnd: string;
  memberCount: number;
  preview: string;
  score?: number | null;
}

export function ClusterCard({ data, onOpen }: { data: ClusterCardData; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={() => onOpen(data.id)}
      className="flex w-full flex-col gap-1.5 rounded-md p-3 text-left transition-colors hover:bg-[var(--card-bg)]"
      style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[13px] font-medium text-ink-1">{data.label}</span>
        <span
          className="flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-2"
          style={{ background: 'color-mix(in srgb, var(--sec-memory-agent) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)' }}
        >
          {data.level}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
        <span>{day(data.periodStart)}</span>
        <span>→</span>
        <span>{day(data.periodEnd)}</span>
        <span>·</span>
        <span>{t('ma.clusters.members', { count: data.memberCount })}</span>
        {data.score != null && (
          <span className="rounded-sm px-1.5 py-0.5 text-ink-2" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            {t('ma.clusters.score', { value: data.score.toFixed(2) })}
          </span>
        )}
      </div>
      {data.preview && <p className="line-clamp-2 text-[12px] leading-relaxed text-ink-2">{data.preview}</p>}
    </button>
  );
}
