import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../stores/toast';
import { errMsg } from '../../lib/errMsg';
import { MA_ACCENT, day } from './utils';
import { SectionTitle } from './ModalShell';
import { ClusterRelations } from './ClusterRelations';
import { useCluster, useNarrateCluster, useSetClusterStatus } from '../../hooks/useMemoryAgent';

// Status → dot color (signal as dot only, never text fill — DESIGN.md §1.3).
const STATUS_DOT: Record<string, string> = {
  active: 'var(--grn)',
  candidate: 'var(--kind-agent)',
  rejected: 'var(--red)',
  superseded: 'var(--ink-3)',
};

export function ClusterDrawer({ clusterId, onClose, onOpenCluster }: { clusterId: string; onClose: () => void; onOpenCluster: (id: string) => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const detailQ = useCluster(clusterId);
  const narrate = useNarrateCluster();
  const setStatus = useSetClusterStatus();

  const [confirm, setConfirm] = useState<'active' | 'rejected' | null>(null);
  const [narrating, setNarrating] = useState(false);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const detail = detailQ.data;
  const isCandidate = detail?.status === 'candidate';
  const acting = setStatus.isPending;

  const changeStatus = (status: 'active' | 'rejected') =>
    setStatus.mutate(
      { clusterId, status },
      {
        onSuccess: () => {
          toast(t(status === 'active' ? 'ma.clusters.approved' : 'ma.clusters.rejected'));
          onClose();
        },
        onError: (e) => {
          setConfirm(null);
          toast(errMsg(e, t, t('ma.clusters.actionFailed')));
        },
      },
    );

  const saveNarrative = () =>
    narrate.mutate(
      { clusterId, narrative: draft.trim() },
      {
        onSuccess: () => {
          toast(t('ma.clusters.narrated'));
          setNarrating(false);
        },
        onError: (e) => toast(errMsg(e, t, t('ma.clusters.actionFailed'))),
      },
    );

  return (
    <>
      <div onClick={onClose} aria-hidden className="fixed inset-0 z-[60]" style={{ background: 'rgba(18,14,10,0.34)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)' }} />
      <aside
        role="dialog"
        aria-modal="true"
        className="fixed right-0 top-0 z-[61] flex h-screen w-[440px] max-w-[94vw] flex-col"
        style={{ background: 'var(--card-bg)', backdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', WebkitBackdropFilter: 'blur(var(--drawer-blur)) saturate(1.6)', boxShadow: '-1px 0 0 var(--card-edge) inset, -40px 0 70px -26px rgba(0,0,0,0.5)' }}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--card-hairline)] px-6 pb-4 pt-[22px]">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-2">
              <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: MA_ACCENT, boxShadow: `0 0 8px ${MA_ACCENT}` }} />
              {detail?.level ?? '—'}
              {detail && (
                <span className="flex items-center gap-1 text-ink-3">
                  <span className="h-[6px] w-[6px] rounded-full" style={{ background: STATUS_DOT[detail.status] ?? 'var(--ink-3)' }} />
                  {detail.status}
                </span>
              )}
            </div>
            <h2 className="mt-2 text-[16px] font-semibold leading-tight text-ink-1">{detail?.label ?? '…'}</h2>
            {detail && (
              <div className="mt-1.5 font-mono text-[11px] text-ink-3">
                {day(detail.period_start)} → {day(detail.period_end)} · {t('ma.clusters.members', { count: detail.member_count })}
              </div>
            )}
          </div>
          <button type="button" onClick={onClose} aria-label={t('ma.clusters.close')} className="grid h-[30px] w-[30px] flex-none place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={15} height={15}>
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-6 pt-1">
          {detailQ.isError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
              <span className="text-[12.5px] text-ink-2">{errMsg(detailQ.error, t, t('ma.clusters.error'))}</span>
              <button type="button" onClick={() => void detailQ.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">{t('ma.clusters.retry')}</button>
            </div>
          ) : (
            <>
              <SectionTitle>{t('ma.clusters.narrativeTitle')}</SectionTitle>
              {narrating ? (
                <div className="flex flex-col gap-2">
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={6} maxLength={5000} placeholder={t('ma.clusters.narratePlaceholder')} className="w-full resize-y rounded-md px-3 py-2.5 text-[13px] leading-relaxed text-ink-1 outline-none placeholder:text-ink-4" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }} />
                  <div className="flex gap-2">
                    <button type="button" disabled={!draft.trim() || narrate.isPending} onClick={saveNarrative} className="rounded-btn bg-btn-primary px-3 py-1.5 font-body text-[12px] font-semibold text-white disabled:opacity-40" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}>{t('ma.clusters.saveNarrative')}</button>
                    <button type="button" onClick={() => setNarrating(false)} className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-2 hover:text-ink-1" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.clusters.cancel')}</button>
                  </div>
                </div>
              ) : (
                <>
                  {detail?.narrative ? (
                    <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-1">{detail.narrative}</p>
                  ) : (
                    <p className="text-[12.5px] text-ink-3">{t('ma.clusters.noNarrative')}</p>
                  )}
                  <button type="button" onClick={() => { setDraft((detail?.narrative ?? '').slice(0, 5000)); setNarrating(true); }} className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-ink-1">{t('ma.clusters.narrate')}</button>
                </>
              )}

              <ClusterRelations clusterId={clusterId} onOpenCluster={onOpenCluster} />
            </>
          )}
        </div>

        {isCandidate && (
          <div className="border-t border-[var(--card-hairline)] px-6 py-4">
            {confirm ? (
              <div className="flex flex-col gap-2.5">
                <span className="font-mono text-[12px] text-ink-1">{t(confirm === 'active' ? 'ma.clusters.confirmApprove' : 'ma.clusters.confirmReject')}</span>
                <div className="flex gap-2.5">
                  <button type="button" disabled={acting} onClick={() => changeStatus(confirm)} className={`flex-1 rounded-btn py-2.5 font-body text-[12.5px] font-semibold disabled:opacity-50 ${confirm === 'active' ? 'bg-btn-primary text-white' : 'text-red'}`} style={confirm === 'active' ? { boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' } : { background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}>{t('ma.clusters.confirm')}</button>
                  <button type="button" disabled={acting} onClick={() => setConfirm(null)} className="rounded-btn px-4 py-2.5 font-body text-[12.5px] text-ink-1 disabled:opacity-50" style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>{t('ma.clusters.cancel')}</button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2.5">
                <button type="button" onClick={() => setConfirm('active')} className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}>{t('ma.clusters.approve')}</button>
                <button type="button" onClick={() => setConfirm('rejected')} className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-red" style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}>{t('ma.clusters.reject')}</button>
              </div>
            )}
          </div>
        )}
      </aside>
    </>
  );
}
