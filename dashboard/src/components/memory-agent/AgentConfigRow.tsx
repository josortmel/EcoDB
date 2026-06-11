import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Toggle } from '../Toggle';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { day } from './utils';
import { cronLabel } from './CronBuilder';
import { useCellConfigs, useUpdateCellConfig, useDeleteCellConfig, useTriggerCell, type AgentSummary, type CellTaskConfig } from '../../hooks/useMemoryAgent';

// Last-run status → dot color (dot only, never text fill — §1.3).
const STATUS_DOT: Record<string, string> = { completed: 'var(--grn)', failed: 'var(--red)', running: 'var(--accent)' };

function ConfigRow({ config, agentIdentifier, onEdit }: { config: CellTaskConfig; agentIdentifier: string; onEdit: (c: CellTaskConfig) => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const update = useUpdateCellConfig();
  const del = useDeleteCellConfig();
  const trigger = useTriggerCell();
  const [confirm, setConfirm] = useState(false);
  const onErr = (e: unknown) => toast(errMsg(e, t, t('ma.configs.common.actionFailed')));

  return (
    <div className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-2" style={{ background: 'color-mix(in srgb, var(--sec-memory-agent) 12%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)' }}>{config.cell_type}</span>
          {config.last_run_status && (
            <span className="flex items-center gap-1 font-mono text-[9.5px] text-ink-3">
              <span className="h-[6px] w-[6px] rounded-full" style={{ background: STATUS_DOT[config.last_run_status] ?? 'var(--ink-3)' }} />
              {config.last_run_status}
            </span>
          )}
        </div>
        <Toggle on={config.enabled} onChange={(on) => update.mutate({ id: config.id, body: { enabled: on } }, { onError: onErr })} label={t('ma.configs.config.enabled')} disabled={update.isPending} />
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
        <span>{config.model}</span>
        <span>·</span>
        <span>{cronLabel(config.schedule_cron ?? null, t)}</span>
        {config.level && (<><span>·</span><span>{config.level}</span></>)}
        {config.last_run && (<><span>·</span><span>{day(config.last_run)}</span></>)}
      </div>

      <div className="mt-2 flex items-center gap-2">
        <button type="button" onClick={() => trigger.mutate({ cellType: config.cell_type, agentIdentifier, level: config.level ?? undefined }, { onSuccess: () => toast(t('ma.configs.config.triggered')), onError: onErr })} disabled={trigger.isPending} className="rounded-btn px-2.5 py-1 font-body text-[11px] text-ink-1 disabled:opacity-50" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.configs.config.trigger')}</button>
        <button type="button" onClick={() => onEdit(config)} className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 hover:text-ink-1">{t('ma.configs.config.edit')}</button>
        {confirm ? (
          <span className="flex items-center gap-1.5">
            <button type="button" disabled={del.isPending} onClick={() => del.mutate(config.id, { onSuccess: () => toast(t('ma.configs.config.deleted')), onError: onErr })} className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-red">{t('ma.configs.config.delete')}</button>
            <button type="button" onClick={() => setConfirm(false)} className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 hover:text-ink-1">{t('ma.configs.common.cancel')}</button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} className="ml-auto font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 hover:text-red">{t('ma.configs.config.delete')}</button>
        )}
      </div>
    </div>
  );
}

export function AgentConfigRow({ agent, onEditConfig, onNewConfig }: { agent: AgentSummary; onEditConfig: (c: CellTaskConfig) => void; onNewConfig: (agentIdentifier: string) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // Lazy: the hook gates on params.enabled (Lienzo wired it into useQuery), so the
  // query only fires when this agent is expanded — no N+1 across the list (BC1_CFG).
  const q = useCellConfigs({ agentIdentifier: agent.identifier, enabled: open });
  const configs = asArray<CellTaskConfig>(q.data?.items);

  return (
    <div className="rounded-md" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between gap-3 p-3 text-left">
        <span className="flex min-w-0 items-center gap-2">
          <span className="text-ink-3">{open ? '▾' : '▸'}</span>
          <span className="truncate text-[13px] text-ink-1">{agent.display_name ?? agent.identifier}</span>
        </span>
        <span className="flex flex-none items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
          <span>{t('ma.configs.agents.configsCount', { count: agent.cell_configs_count })}</span>
          <span>·</span>
          <span>{t('ma.configs.agents.clustersCount', { count: agent.clusters_count })}</span>
          <span>·</span>
          <span>{agent.last_cell_run ? day(agent.last_cell_run) : t('ma.configs.agents.never')}</span>
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-2 border-t border-[var(--card-hairline)] p-3">
          {q.isError ? (
            <div className="flex items-center gap-2">
              <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 5px rgba(222,70,48,0.5)' }} />
              <span className="flex-1 text-[12px] text-ink-2">{errMsg(q.error, t, t('ma.configs.common.error'))}</span>
              <button type="button" onClick={() => void q.refetch()} className="font-mono text-[11px] text-ink-1 underline underline-offset-2">{t('ma.configs.common.retry')}</button>
            </div>
          ) : q.isPending ? (
            <span className="h-[12px] w-2/5 animate-pulse rounded-sm" style={{ background: 'var(--card-bg)' }} />
          ) : configs.length === 0 ? (
            <span className="text-[12px] text-ink-3">{t('ma.configs.config.empty')}</span>
          ) : (
            configs.map((c) => <ConfigRow key={c.id} config={c} agentIdentifier={agent.identifier} onEdit={onEditConfig} />)
          )}
          <button type="button" onClick={() => onNewConfig(agent.identifier)} className="self-start font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 hover:text-ink-1">{t('ma.configs.config.newConfig')}</button>
        </div>
      )}
    </div>
  );
}
