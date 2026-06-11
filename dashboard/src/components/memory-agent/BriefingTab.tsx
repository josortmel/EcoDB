import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../GlassCard';
import { Panel, PanelState } from '../Panel';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { useToastStore } from '../../stores/toast';
import { ForesightCard } from './ForesightCard';
import { TensionCard } from './TensionCard';
import { TelescopicRow } from './TelescopicRow';
import { MA_ACCENT } from './utils';
import { useBriefing, useDismissForesight, useDismissTension, type ForesightItem, type TensionItem, type ClusterSummary } from '../../hooks/useMemoryAgent';

// Briefing tab (Spec §5 Tab 1) — the default surface of Memory Agent. Shows what
// the system is currently watching: urgency-sorted foresights, open identity
// tensions, and a telescopic narrative preview. agentIdentifier arrives as a
// prop ("Lienzo" default in dev until the agent selector lands). onOpenCluster
// is the cross-tab hand-off to the Clusters tab (wired when that tab ships).
export function BriefingTab({ agentIdentifier = 'Lienzo', onOpenCluster }: { agentIdentifier?: string; onOpenCluster?: (clusterId: string) => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const q = useBriefing(agentIdentifier);
  const dismissForesight = useDismissForesight();
  const dismissTension = useDismissTension();

  const foresights = useMemo(
    () => asArray<ForesightItem>(q.data?.foresights).slice().sort((a, b) => b.urgency_score - a.urgency_score),
    [q.data],
  );
  const tensions = useMemo(() => asArray<TensionItem>(q.data?.identity_tensions), [q.data]);
  const clusters = useMemo(() => {
    const ts = q.data?.telescopic_summary;
    return [
      ...asArray<ClusterSummary>(ts?.weeklies),
      ...asArray<ClusterSummary>(ts?.monthlies),
      ...asArray<ClusterSummary>(ts?.quarterlies),
      ...asArray<ClusterSummary>(ts?.yearlies),
    ];
  }, [q.data]);

  const openCluster = useCallback((id: string) => onOpenCluster?.(id), [onOpenCluster]);

  const onForesightDismiss = (memoryId: string, reason: string) =>
    dismissForesight.mutate(
      { memoryId, reason },
      { onSuccess: () => toast(t('ma.briefing.dismissed')), onError: (e) => toast(errMsg(e, t, t('ma.briefing.dismissFailed'))) },
    );
  const onTensionDismiss = (tensionId: string, reason: string) =>
    dismissTension.mutate(
      { tensionId, reason },
      { onSuccess: () => toast(t('ma.briefing.dismissed')), onError: (e) => toast(errMsg(e, t, t('ma.briefing.dismissFailed'))) },
    );

  if (q.isError) {
    return (
      <GlassCard className="flex flex-col items-center gap-3 p-8 text-center">
        <span className="h-[9px] w-[9px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 8px rgba(222,70,48,0.5)' }} />
        <div className="text-[12.5px] text-ink-2">{errMsg(q.error, t, t('ma.briefing.error'))}</div>
        <button type="button" onClick={() => void q.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">
          {t('ma.briefing.retry')}
        </button>
      </GlassCard>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pb-2">
      <div className="grid flex-none gap-4 lg:grid-cols-2">
        <Panel title={t('ma.briefing.foresights')} accent={MA_ACCENT} tooltip={t('ma.briefing.foresightsHint')}>
          <PanelState loading={q.isPending} empty={!q.isPending && foresights.length === 0} emptyLabel={t('ma.briefing.emptyForesights')}>
            <div className="flex flex-col gap-2.5">
              {foresights.map((f) => (
                <ForesightCard key={f.memory_id} item={f} onDismiss={onForesightDismiss} />
              ))}
            </div>
          </PanelState>
        </Panel>

        <Panel title={t('ma.briefing.tensions')} accent={MA_ACCENT} tooltip={t('ma.briefing.tensionsHint')}>
          <PanelState loading={q.isPending} empty={!q.isPending && tensions.length === 0} emptyLabel={t('ma.briefing.emptyTensions')}>
            <div className="flex flex-col gap-2.5">
              {tensions.map((ti) => (
                <TensionCard key={ti.id} item={ti} onDismiss={onTensionDismiss} />
              ))}
            </div>
          </PanelState>
        </Panel>
      </div>

      <Panel title={t('ma.briefing.telescopic')} accent={MA_ACCENT} tooltip={t('ma.briefing.telescopicHint')} className="flex-none">
        <PanelState loading={q.isPending} empty={!q.isPending && clusters.length === 0} emptyLabel={t('ma.briefing.emptyTelescopic')}>
          <div className="grid gap-2.5 md:grid-cols-2">
            {clusters.map((c) => (
              <TelescopicRow key={c.id} cluster={c} onOpen={openCluster} />
            ))}
          </div>
        </PanelState>
      </Panel>
    </div>
  );
}
