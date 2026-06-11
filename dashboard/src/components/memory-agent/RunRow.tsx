import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { asArray } from '../../lib/asArray';
import type { CellRun } from '../../hooks/useMemoryAgent';

// status → dot color + whether it glows (signal) or pulses (live). Orange is
// reserved for the live "running" state (§ accent = active signal).
const STATUS: Record<string, { color: string; glow?: boolean; pulse?: boolean }> = {
  completed: { color: 'var(--grn)', glow: true },
  failed: { color: 'var(--red)', glow: true },
  running: { color: 'var(--accent)', pulse: true },
  started: { color: 'var(--ink-3)' },
};

function fmtDuration(start: string, end?: string | null): string | null {
  if (!end) return null; // still running
  const ms = Date.parse(end) - Date.parse(start);
  if (!Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

const td = 'px-3 py-2.5 align-top';

export function RunRow({ run }: { run: CellRun }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const st = STATUS[run.status] ?? { color: 'var(--ink-3)' };
  const errors = asArray<unknown>(run.errors);
  const duration = fmtDuration(run.started_at, run.finished_at);

  return (
    <Fragment>
      <tr className="border-b border-[var(--card-hairline)] last:border-0">
        <td className={`${td} font-mono text-[10.5px] text-ink-3`}>{run.id.slice(0, 8)}</td>
        <td className={td}>
          <span className="rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            {run.cell_type}
          </span>
        </td>
        <td className={`${td} text-[12px] text-ink-2`}>{run.agent_identifier ?? '—'}</td>
        <td className={`${td} font-mono text-[10.5px] text-ink-3`}>{run.model}</td>
        <td className={td}>
          <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-ink-2">
            <span
              className={`h-[7px] w-[7px] flex-none rounded-full ${st.pulse ? 'motion-safe:animate-pulse' : ''}`}
              style={{ background: st.color, boxShadow: st.glow || st.pulse ? `0 0 6px ${st.color}` : undefined }}
            />
            {run.status}
          </span>
        </td>
        <td className={`${td} font-mono text-[10.5px] tabular-nums text-ink-3`}>{duration ?? t('ma.telemetry.running')}</td>
        <td className={`${td} font-mono text-[10.5px] tabular-nums text-ink-2`}>{run.items_created}</td>
        <td className={`${td} font-mono text-[10.5px] tabular-nums`}>
          {errors.length > 0 ? (
            <button type="button" onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-ink-2 underline-offset-2 hover:underline">
              <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 5px rgba(222,70,48,0.5)' }} />
              {errors.length}
            </button>
          ) : (
            <span className="text-ink-4">0</span>
          )}
        </td>
      </tr>
      {open && errors.length > 0 && (
        <tr>
          <td colSpan={8} className="px-3 pb-3">
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-md p-2.5 font-mono text-[10.5px] leading-relaxed text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              {errors
                .map((e) => {
                  const s = typeof e === 'string' ? e : JSON.stringify(e, null, 2);
                  return s.length > 500 ? `${s.slice(0, 500)}…` : s;
                })
                .join('\n')}
            </pre>
          </td>
        </tr>
      )}
    </Fragment>
  );
}
