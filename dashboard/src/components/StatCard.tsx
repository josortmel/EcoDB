import { useTranslation } from 'react-i18next';
import { GlassCard } from './GlassCard';

interface StatCardProps {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accent?: boolean;
  loading?: boolean;
  error?: boolean;
  onClick?: () => void;
  tooltip?: string;
}

// Condensed, SECONDARY stat (Lienzo: the Inbox owns the hierarchy). Renders a
// <button> only when it navigates; otherwise a plain <div> (a11y — no inert
// button affordance).
export function StatCard({ label, value, unit, sub, accent, loading, error, onClick, tooltip }: StatCardProps) {
  const { t } = useTranslation();
  const inner = (
    <>
      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">{label}</span>
      {loading ? (
        <span className="mt-0.5 h-[22px] w-3/5 animate-pulse rounded-sm" style={{ background: 'var(--inset)' }} />
      ) : (
        <span
          className="font-mono text-[22px] font-medium leading-none tabular-nums"
          style={{ color: accent && !error ? 'var(--accent)' : 'var(--ink-1)' }}
        >
          {error ? '—' : value}
          {unit && !error && <span className="ml-0.5 text-[12px] text-ink-3">{unit}</span>}
        </span>
      )}
      {sub && <span className="truncate font-mono text-[10px] text-ink-3">{error ? t('cc.stat.unavailable') : sub}</span>}
    </>
  );

  return (
    <GlassCard className="p-4">
      {onClick ? (
        <button type="button" onClick={onClick} title={tooltip} className="flex w-full flex-col gap-1.5 text-left">
          {inner}
        </button>
      ) : (
        <div title={tooltip} className={`flex w-full flex-col gap-1.5 ${tooltip ? 'cursor-help' : ''}`}>{inner}</div>
      )}
    </GlassCard>
  );
}
