import { useTranslation } from 'react-i18next';
import { RunRow } from './RunRow';
import type { CellRun } from '../../hooks/useMemoryAgent';

const th = 'px-3 py-2 text-left font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3';

export function RunsTable({ runs }: { runs: CellRun[] }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-[var(--card-hairline)]">
            <th className={th}>{t('ma.telemetry.col.run')}</th>
            <th className={th}>{t('ma.telemetry.col.type')}</th>
            <th className={th}>{t('ma.telemetry.col.agent')}</th>
            <th className={th}>{t('ma.telemetry.col.model')}</th>
            <th className={th}>{t('ma.telemetry.col.status')}</th>
            <th className={th}>{t('ma.telemetry.col.duration')}</th>
            <th className={th}>{t('ma.telemetry.col.items')}</th>
            <th className={th}>{t('ma.telemetry.col.errors')}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <RunRow key={r.id} run={r} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
