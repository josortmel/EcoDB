import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from './GlassCard';

interface PanelProps {
  title: string;
  accent?: string;
  tag?: string;
  control?: ReactNode;
  className?: string;
  tooltip?: string;
  children: ReactNode;
}

// A titled glass panel: accent dot + uppercase title on the left, a tag or a
// control on the right.
export function Panel({ title, accent, tag, control, className, tooltip, children }: PanelProps) {
  return (
    <GlassCard className={`flex flex-col p-[18px] ${className ?? ''}`}>
      <div className="mb-3 flex flex-none items-center justify-between gap-2.5">
        <div className="flex items-center gap-2">
          {accent && (
            <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: accent, boxShadow: `0 0 6px ${accent}` }} />
          )}
          <span
            title={tooltip}
            className={`font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2 ${tooltip ? 'cursor-help' : ''}`}
          >
            {title}
          </span>
        </div>
        {control ?? (tag && <span className="font-mono text-[9.5px] tracking-[0.04em] text-ink-3">{tag}</span>)}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </GlassCard>
  );
}

function ShimmerRows() {
  return (
    <div className="flex flex-col gap-2.5 py-1">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-[11px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}

interface PanelStateProps {
  loading?: boolean;
  error?: boolean;
  empty?: boolean;
  emptyLabel?: string;
  onRetry?: () => void;
  children: ReactNode;
}

// loading (shimmer) / error (red dot + retry) / empty (quiet) — else content.
export function PanelState({ loading, error, empty, emptyLabel, onRetry, children }: PanelStateProps) {
  const { t } = useTranslation();
  if (loading) return <ShimmerRows />;
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-6 text-center">
        <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
        <span className="font-mono text-[12px] text-ink-2">{t('cc.error')}</span>
        {onRetry && (
          <button type="button" onClick={onRetry} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">
            {t('cc.retry')}
          </button>
        )}
      </div>
    );
  }
  if (empty) return <div className="grid place-items-center py-6 font-mono text-[12px] text-ink-3">{emptyLabel ?? t('cc.empty')}</div>;
  return <>{children}</>;
}
