import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { day } from './utils';
import { AgentSelect } from './AgentSelect';
import { StatusChips } from './StatusChips';
import { useForesights, type ForesightItem, type ForesightStatus } from '../../hooks/useMemoryAgent';

export interface ForesightsTabProps {
  agent?: string;
  onAgentChange: (agent: string) => void;
}

const HIGH_URGENCY = 0.66;

function ForesightCard({ item }: { item: ForesightItem }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const high = (item.urgency_score ?? 0) >= HIGH_URGENCY;
  const dot = high ? 'var(--accent)' : 'var(--ink-4)';
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-start gap-2.5">
        <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: dot, boxShadow: high ? `0 0 6px ${dot}` : undefined }} title={high ? t('ma.foresights.urgency') : undefined} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-snug text-ink-1">{item.content}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
            <span>{day(item.foresight_start)} → {day(item.foresight_end)}</span>
            <span>·</span>
            <span>{t('ma.foresights.urgency')} {(item.urgency_score ?? 0).toFixed(2)}</span>
          </div>
          {item.evidence && (
            <div className="mt-2">
              <button type="button" onClick={() => setOpen((o) => !o)} className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-ink-1">
                {open ? '▾' : '▸'} {t('ma.foresights.evidence')}
              </button>
              {open && <p className="mt-1 text-[12px] leading-relaxed text-ink-2">{item.evidence}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ForesightsTab({ agent, onAgentChange }: ForesightsTabProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<'' | ForesightStatus>('');
  const q = useForesights(agent, status || undefined);
  const items = useMemo(
    () => asArray<ForesightItem>(q.data?.items).slice().sort((a, b) => b.urgency_score - a.urgency_score),
    [q.data],
  );

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('ma.foresights.statusAll') },
      { value: 'active', label: t('ma.foresights.statusActive') },
      { value: 'expired', label: t('ma.foresights.statusExpired') },
      { value: 'dismissed', label: t('ma.foresights.statusDismissed') },
    ],
    [t],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <header className="flex flex-none flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-body text-[18px] font-semibold text-ink-1">{t('ma.foresights.title')}</h2>
            <p className="mt-1 text-[12.5px] text-ink-3">{t('ma.foresights.subtitle')}</p>
          </div>
          <AgentSelect agent={agent} onAgentChange={onAgentChange} />
        </div>
        {agent && <StatusChips value={status} options={statusOptions} onChange={(v) => setStatus(v as '' | ForesightStatus)} />}
      </header>

      {!agent ? (
        <div className="grid flex-1 place-items-center font-mono text-[12.5px] text-ink-3">{t('ma.agentSelect.placeholder')}</div>
      ) : q.isError ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
          <span className="text-[12.5px] text-ink-2">{errMsg(q.error, t, t('ma.foresights.error'))}</span>
          <button type="button" onClick={() => void q.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">{t('ma.foresights.retry')}</button>
        </div>
      ) : q.isPending ? (
        <div className="flex flex-none flex-col gap-2.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-[58px] animate-pulse rounded-md" style={{ background: 'var(--inset)' }} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="grid flex-1 place-items-center font-mono text-[12.5px] text-ink-3">{status ? t('ma.foresights.emptyFilter') : t('ma.foresights.empty')}</div>
      ) : (
        <div className="flex flex-none flex-col gap-2.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">{t('ma.foresights.total', { count: q.data?.total ?? items.length })}</div>
          {items.map((f) => (
            <ForesightCard key={f.memory_id} item={f} />
          ))}
        </div>
      )}
    </div>
  );
}
