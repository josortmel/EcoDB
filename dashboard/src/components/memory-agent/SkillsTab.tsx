import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { AgentSelect } from './AgentSelect';
import { StatusChips } from './StatusChips';
import { SkillDrawer } from './SkillDrawer';
import { SKILL_STATUS_DOT, skillStatusLabel } from './utils';
import { useSkills, type SkillCard, type SkillStatus } from '../../hooks/useMemoryAgent';

export interface SkillsTabProps {
  agent?: string;
  onAgentChange: (agent: string) => void;
}

function SkillRow({ skill, onOpen }: { skill: SkillCard; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const pct = Math.min(100, Math.round((skill.success_rate ?? 0) * 100));
  return (
    <button type="button" onClick={() => onOpen(skill.id)} className="flex w-full flex-col gap-2 rounded-md p-3 text-left transition-colors hover:bg-[var(--card-bg)]" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[13px] font-medium text-ink-1">{skill.task_signature}</span>
        <span className="flex flex-none items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-3">
          <span className="h-[6px] w-[6px] rounded-full" style={{ background: SKILL_STATUS_DOT[skill.status] ?? 'var(--ink-3)' }} />
          {skillStatusLabel(skill.status, t)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="h-[6px] flex-1 overflow-hidden rounded-full" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--grn)' }} />
        </span>
        <span className="flex-none font-mono text-[10px] tabular-nums text-ink-2">{t('ma.skills.successRate')} {pct}%</span>
      </div>
    </button>
  );
}

export function SkillsTab({ agent, onAgentChange }: SkillsTabProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<'' | SkillStatus>('');
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useSkills(agent, status || undefined);
  const skills = useMemo(() => asArray<SkillCard>(q.data?.items), [q.data]);

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('ma.skills.statusAll') },
      { value: 'active', label: t('ma.skills.statusActive') },
      { value: 'stale', label: t('ma.skills.statusStale') },
      { value: 'candidate', label: t('ma.skills.statusCandidate') },
      { value: 'deprecated', label: t('ma.skills.statusDeprecated') },
    ],
    [t],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <header className="flex flex-none flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-body text-[18px] font-semibold text-ink-1">{t('ma.skills.title')}</h2>
            <p className="mt-1 text-[12.5px] text-ink-3">{t('ma.skills.subtitle')}</p>
          </div>
          <AgentSelect agent={agent} onAgentChange={onAgentChange} />
        </div>
        {agent && <StatusChips value={status} options={statusOptions} onChange={(v) => setStatus(v as '' | SkillStatus)} />}
      </header>

      {!agent ? (
        <div className="grid flex-1 place-items-center font-mono text-[12.5px] text-ink-3">{t('ma.agentSelect.placeholder')}</div>
      ) : q.isError ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
          <span className="text-[12.5px] text-ink-2">{errMsg(q.error, t, t('ma.skills.error'))}</span>
          <button type="button" onClick={() => void q.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">{t('ma.skills.retry')}</button>
        </div>
      ) : q.isPending ? (
        <div className="flex flex-none flex-col gap-2.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-[64px] animate-pulse rounded-md" style={{ background: 'var(--inset)' }} />
          ))}
        </div>
      ) : skills.length === 0 ? (
        <div className="grid flex-1 place-items-center font-mono text-[12.5px] text-ink-3">{status ? t('ma.skills.emptyFilter') : t('ma.skills.empty')}</div>
      ) : (
        <div className="flex flex-none flex-col gap-2.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">{t('ma.skills.total', { count: q.data?.total ?? skills.length })}</div>
          {skills.map((s) => (
            <SkillRow key={s.id} skill={s} onOpen={setOpenId} />
          ))}
        </div>
      )}

      {openId && <SkillDrawer skillId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}
