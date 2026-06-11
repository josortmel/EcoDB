import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { MA_ACCENT, day, SKILL_STATUS_DOT, skillStatusLabel } from './utils';
import { SelectInput, PrimaryButton, SectionTitle } from './ModalShell';
import { useSkillDetail, useSetSkillStatus, type SkillSourceCase, type SkillStatus } from '../../hooks/useMemoryAgent';

const STATUSES: SkillStatus[] = ['active', 'stale', 'candidate', 'deprecated'];

function ListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <SectionTitle>{title}</SectionTitle>
      <ul className="flex flex-col gap-1.5">
        {items.map((it, i) => (
          <li key={i} className="rounded-md p-2.5 text-[12.5px] leading-snug text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            {it}
          </li>
        ))}
      </ul>
    </>
  );
}

export function SkillDrawer({ skillId, onClose }: { skillId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const q = useSkillDetail(skillId);
  const setStatus = useSetSkillStatus();
  const [pending, setPending] = useState<SkillStatus | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const d = q.data;
  const pct = Math.min(100, Math.round((d?.success_rate ?? 0) * 100));
  const cases = asArray<SkillSourceCase>(d?.source_cases);
  const current = pending ?? d?.status ?? 'active';
  const changed = !!d && current !== d.status;

  const apply = () =>
    setStatus.mutate(
      { id: skillId, status: current },
      { onSuccess: () => { toast(t('ma.skills.statusUpdated')); setPending(null); }, onError: (e) => { setPending(null); toast(errMsg(e, t, t('ma.configs.common.actionFailed'))); } },
    );

  return (
    <>
      <div onClick={onClose} aria-hidden className="fixed inset-0 z-[60]" style={{ background: 'rgba(8,10,14,0.34)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)' }} />
      <aside role="dialog" aria-modal="true" className="fixed right-0 top-0 z-[61] flex h-screen w-[480px] max-w-[96vw] flex-col" style={{ background: 'var(--card-bg)', backdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', boxShadow: '-1px 0 0 var(--card-edge) inset, -40px 0 70px -26px rgba(0,0,0,0.5)' }}>
        <div className="flex items-start justify-between gap-3 border-b border-[var(--card-hairline)] px-6 pb-4 pt-[22px]">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-2">
              <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: MA_ACCENT, boxShadow: `0 0 8px ${MA_ACCENT}` }} />
              {t('ma.skills.title')}
              {d && (
                <span className="flex items-center gap-1 text-ink-3">
                  <span className="h-[6px] w-[6px] rounded-full" style={{ background: SKILL_STATUS_DOT[d.status] ?? 'var(--ink-3)' }} />
                  {skillStatusLabel(d.status, t)}
                </span>
              )}
            </div>
            <h2 className="mt-2 text-[15px] font-semibold leading-tight text-ink-1">{d?.task_signature ?? '…'}</h2>
            {d?.updated_at && <div className="mt-1 font-mono text-[10px] text-ink-3">{t('ma.skills.updated', { when: day(d.updated_at) })}</div>}
          </div>
          <button type="button" onClick={onClose} aria-label={t('ma.skills.close')} className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={15} height={15}><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" /></svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-6 pt-1">
          {q.isError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
              <span className="text-[12.5px] text-ink-2">{errMsg(q.error, t, t('ma.skills.error'))}</span>
              <button type="button" onClick={() => void q.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">{t('ma.skills.retry')}</button>
            </div>
          ) : q.isPending ? (
            <div className="mt-4 flex flex-col gap-2.5">
              {[0, 1, 2, 3].map((i) => (
                <span key={i} className="h-[40px] animate-pulse rounded-md" style={{ background: 'var(--inset)' }} />
              ))}
            </div>
          ) : (
            <>
              <SectionTitle>{t('ma.skills.successRate')}</SectionTitle>
              <div className="flex items-center gap-2">
                <span className="h-[7px] flex-1 overflow-hidden rounded-full" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                  <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--grn)' }} />
                </span>
                <span className="flex-none font-mono text-[11px] tabular-nums text-ink-1">{pct}%</span>
              </div>

              <ListSection title={t('ma.skills.steps')} items={asArray<string>(d?.steps)} />
              <ListSection title={t('ma.skills.tools')} items={asArray<string>(d?.tools)} />
              <ListSection title={t('ma.skills.failureModes')} items={asArray<string>(d?.failure_modes)} />
              <ListSection title={t('ma.skills.checklist')} items={asArray<string>(d?.validation_checklist)} />

              <SectionTitle>{t('ma.skills.sourceCases')}</SectionTitle>
              {cases.length === 0 ? (
                <p className="text-[12px] text-ink-3">{t('ma.skills.emptyCases')}</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {cases.map((c) => (
                    <div key={c.id} className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                      <div className="flex items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
                        <span className="h-[6px] w-[6px] rounded-full" style={{ background: c.success === true ? 'var(--grn)' : c.success === false ? 'var(--red)' : 'var(--ink-4)' }} />
                        {c.success === true ? t('ma.skills.caseSuccess') : c.success === false ? t('ma.skills.caseFailure') : '—'}
                        <span className="ml-auto">{day(c.created_at)}</span>
                      </div>
                      <p className="mt-1 line-clamp-3 text-[12px] leading-snug text-ink-1">{c.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {d && (
          <div className="flex flex-col gap-2.5 border-t border-[var(--card-hairline)] px-6 py-4">
            <div className="flex items-center gap-2">
              <span className="flex-none font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.skills.setStatus')}</span>
              <SelectInput value={current} onChange={(v) => setPending(v as SkillStatus)}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{skillStatusLabel(s, t)}</option>
                ))}
              </SelectInput>
            </div>
            {changed && (
              <div className="flex gap-2.5">
                <PrimaryButton disabled={setStatus.isPending} onClick={apply}>{t('ma.skills.confirm')}</PrimaryButton>
                <button type="button" onClick={() => setPending(null)} className="rounded-btn px-3 py-2 font-body text-[12px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.skills.cancel')}</button>
              </div>
            )}
          </div>
        )}
      </aside>
    </>
  );
}
