import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel } from '../Panel';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { HealthSummary } from './HealthSummary';
import { RunsTable } from './RunsTable';
import { MA_ACCENT } from './utils';
import { useCellRuns, type CellRun } from '../../hooks/useMemoryAgent';

// Data enums (raw values shown as-is — not i18n copy). cell_type + status drive
// the filters; cell_type is a server param, status is filtered client-side
// (the hook exposes cell_type/agent_identifier/limit only).
const CELL_TYPES = ['consolidation', 'foresight', 'skill_distillation'];
const STATUSES = ['completed', 'running', 'failed', 'started'];
const PAGE = 20;

function FilterSelect({ label, value, anyLabel, options, onChange }: { label: string; value: string; anyLabel: string; options: string[]; onChange: (v: string) => void }) {
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

// Telemetry tab (Spec §5 Tab 4) — cell-worker health + run history. Endpoints are
// real (useCellHealth / useCellRuns). Live updates arrive through the global SSE
// event digest; the refresh button is a manual fallback.
export function TelemetryTab({ agentIdentifier }: { agentIdentifier?: string }) {
  const { t } = useTranslation();
  const [fType, setFType] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [fAgent, setFAgent] = useState(agentIdentifier ?? '');
  const [limit, setLimit] = useState(PAGE);

  // The agent selector (prop) is the source of truth — re-seed the filter when it
  // changes, else Telemetry would keep showing the previous agent's runs (BC1_T).
  useEffect(() => setFAgent(agentIdentifier ?? ''), [agentIdentifier]);

  const q = useCellRuns({ cellType: fType || undefined, agentIdentifier: fAgent || undefined, limit });
  const items = useMemo(() => asArray<CellRun>(q.data?.items), [q.data]);
  const shown = useMemo(() => (fStatus ? items.filter((r) => r.status === fStatus) : items), [items, fStatus]);
  const total = q.data?.total ?? 0;
  const canLoadMore = items.length < total;
  // A client-side status filter can hide every row on the loaded pages while more
  // pages still exist (the API has no status param). Say so honestly and keep
  // load-more available rather than claiming "no runs" (BH1).
  const filteredEmpty = fStatus !== '' && shown.length === 0 && canLoadMore;

  const refresh = () => void q.refetch();

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <div className="flex-none">
        <HealthSummary />
      </div>

      <Panel
        title={t('ma.telemetry.runs')}
        accent={MA_ACCENT}
        className="flex-none"
        control={
          <button
            type="button"
            onClick={refresh}
            className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-2 transition-colors hover:text-ink-1"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
          >
            {t('ma.telemetry.refresh')}
          </button>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2.5">
            <FilterSelect label={t('ma.telemetry.filter.type')} value={fType} anyLabel={t('ma.telemetry.filter.any')} options={CELL_TYPES} onChange={setFType} />
            <FilterSelect label={t('ma.telemetry.filter.status')} value={fStatus} anyLabel={t('ma.telemetry.filter.any')} options={STATUSES} onChange={setFStatus} />
            <label className="flex min-w-0 flex-col gap-1">
              <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.telemetry.filter.agent')}</span>
              <input
                value={fAgent}
                onChange={(e) => setFAgent(e.target.value)}
                placeholder={t('ma.telemetry.filter.agentPlaceholder')}
                maxLength={120}
                className="min-w-0 rounded-[7px] px-2.5 py-1.5 font-mono text-[11px] text-ink-1 outline-none placeholder:text-ink-4"
                style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
              />
            </label>
          </div>

          {q.isError ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
              <span className="text-[12.5px] text-ink-2">{errMsg(q.error, t, t('ma.telemetry.error'))}</span>
              <button type="button" onClick={refresh} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">
                {t('ma.telemetry.retry')}
              </button>
            </div>
          ) : q.isPending ? (
            <div className="flex flex-col gap-2.5 py-1">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-[11px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${90 - i * 15}%` }} />
              ))}
            </div>
          ) : (
            <>
              {shown.length === 0 ? (
                <div className="grid place-items-center py-6 text-center font-mono text-[12px] text-ink-3">
                  {filteredEmpty ? t('ma.telemetry.noMatchLoaded') : t('ma.telemetry.empty')}
                </div>
              ) : (
                <RunsTable runs={shown} />
              )}
              {canLoadMore && (
                <div className="mt-3 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setLimit((l) => l + PAGE)}
                    className="rounded-btn px-4 py-2 font-body text-[12px] text-ink-2 transition-colors hover:text-ink-1"
                    style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
                  >
                    {t('ma.telemetry.loadMore')}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}
