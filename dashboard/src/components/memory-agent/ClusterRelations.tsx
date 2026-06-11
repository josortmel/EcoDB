import { useTranslation } from 'react-i18next';
import { useDetailStore, type MemoryDetail } from '../../stores/detail';
import { errMsg } from '../../lib/errMsg';
import { asArray } from '../../lib/asArray';
import { day } from './utils';
import { SectionTitle } from './ModalShell';
import { useClusterMembers, useClusterSources, type ClusterMember, type ClusterSummary } from '../../hooks/useMemoryAgent';

function InlineError({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 5px rgba(222,70,48,0.5)' }} />
      <span className="min-w-0 flex-1 text-[12px] text-ink-2">{msg}</span>
      <button type="button" onClick={onRetry} className="flex-none font-mono text-[11px] text-ink-1 underline underline-offset-2">{t('ma.clusters.retry')}</button>
    </div>
  );
}

const toDetail = (m: ClusterMember): MemoryDetail => ({
  id: m.memory_id,
  content: m.content,
  type: m.type,
  tags: asArray<string>(m.tags),
  agent: null,
  ts: day(m.created_at),
});

function ClusterLink({ c, onOpen }: { c: ClusterSummary; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(c.id)}
      className="group flex w-full items-center justify-between gap-2 rounded-md p-2.5 text-left transition-colors hover:bg-[var(--card-bg)]"
      style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <span className="min-w-0 truncate text-[12px] text-ink-1 underline-offset-2 group-hover:underline">{c.label}</span>
      <span className="flex-none font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-3">{c.level}</span>
    </button>
  );
}

// Members (lazy) + telescopic sources/parents for a cluster. Clicking a member
// opens the shared MemoryDrawer (detail store); clicking a source/parent hands
// off to that cluster via onOpenCluster. Errors surface inline with retry rather
// than masquerading as empty state (adv-code BC1_C).
export function ClusterRelations({ clusterId, onOpenCluster }: { clusterId: string; onOpenCluster: (id: string) => void }) {
  const { t } = useTranslation();
  const openMemory = useDetailStore((s) => s.open);
  const membersQ = useClusterMembers(clusterId);
  const sourcesQ = useClusterSources(clusterId);
  const members = asArray<ClusterMember>(membersQ.data?.members);
  const sources = asArray<ClusterSummary>(sourcesQ.data?.sources);
  const parents = asArray<ClusterSummary>(sourcesQ.data?.parent_clusters);

  return (
    <>
      <SectionTitle>{t('ma.clusters.membersTitle')}</SectionTitle>
      {membersQ.isError ? (
        <InlineError msg={errMsg(membersQ.error, t, t('ma.clusters.error'))} onRetry={() => void membersQ.refetch()} />
      ) : membersQ.isPending ? (
        <div className="h-[14px] w-3/5 animate-pulse rounded-sm" style={{ background: 'var(--inset)' }} />
      ) : members.length === 0 ? (
        <p className="text-[12px] text-ink-3">{t('ma.clusters.emptyMembers')}</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {members.map((m) => (
            <button key={m.memory_id} type="button" onClick={() => openMemory(toDetail(m))} className="rounded-md p-2.5 text-left transition-colors hover:bg-[var(--card-bg)]" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              <span className="line-clamp-2 block text-[12px] leading-snug text-ink-1">{m.content}</span>
              <span className="mt-1 block font-mono text-[9.5px] text-ink-3">{m.type} · {day(m.created_at)}</span>
            </button>
          ))}
        </div>
      )}

      {sourcesQ.isError ? (
        <>
          <SectionTitle>{t('ma.clusters.sourcesTitle')}</SectionTitle>
          <InlineError msg={errMsg(sourcesQ.error, t, t('ma.clusters.error'))} onRetry={() => void sourcesQ.refetch()} />
        </>
      ) : (
        <>
          {parents.length > 0 && (
            <>
              <SectionTitle>{t('ma.clusters.parentsTitle')}</SectionTitle>
              <div className="flex flex-col gap-1.5">{parents.map((c) => <ClusterLink key={c.id} c={c} onOpen={onOpenCluster} />)}</div>
            </>
          )}
          {sources.length > 0 && (
            <>
              <SectionTitle>{t('ma.clusters.sourcesTitle')}</SectionTitle>
              <div className="flex flex-col gap-1.5">{sources.map((c) => <ClusterLink key={c.id} c={c} onOpen={onOpenCluster} />)}</div>
            </>
          )}
        </>
      )}
    </>
  );
}
