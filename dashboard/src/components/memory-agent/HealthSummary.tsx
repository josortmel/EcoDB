import { useTranslation } from 'react-i18next';
import { Panel, PanelState } from '../Panel';
import { relativeAge } from '../../lib/relativeTime';
import { useCellHealth } from '../../hooks/useMemoryAgent';
import { MA_ACCENT } from './utils';

function StatBox({ label, value, signal }: { label: string; value: string; signal?: boolean }) {
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-ink-3">{label}</div>
      <div className="mt-1 flex items-center gap-1.5 font-mono text-[16px] tabular-nums text-ink-1">
        {signal && <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />}
        {value}
      </div>
    </div>
  );
}

export function HealthSummary() {
  const { t } = useTranslation();
  const h = useCellHealth();
  const lastRuns = Object.entries(h.data?.last_run_by_type ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
  const errors = h.data?.errors_24h ?? 0;
  const cost = h.data?.total_cost_30d;

  return (
    <Panel title={t('ma.telemetry.health')} accent={MA_ACCENT}>
      <PanelState loading={h.isPending} error={h.isError} onRetry={() => void h.refetch()}>
        <div className="flex flex-col gap-2.5">
          {lastRuns.length > 0 && (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {lastRuns.map(([type, ts]) => (
                <StatBox key={type} label={type} value={ts ? t('ma.telemetry.ago', { age: relativeAge(Date.parse(ts)) }) : t('ma.telemetry.never')} />
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2.5">
            <StatBox label={t('ma.telemetry.errors24h')} value={String(errors)} signal={errors > 0} />
            <StatBox label={t('ma.telemetry.cost30d')} value={cost != null ? `$${cost.toFixed(2)}` : '—'} />
          </div>
        </div>
      </PanelState>
    </Panel>
  );
}
