import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../components/GlassCard';
import { ApiError } from '../lib/api';
import { displayStatus } from '../lib/displayStatus';
import { useKnowledgeStats } from '../hooks/stats';
import { useDocuments, useDocumentDetail, useDocumentChunks, useReindexDocument, useDeleteDocument, useUploadDocument } from '../hooks/documents';
import { useIngestionStore, type DocStatus, type IngestionDoc } from '../stores/ingestion';
import { useToastStore } from '../stores/toast';
import { errMsg } from '../lib/errMsg';
import { asArray } from '../lib/asArray';
import { relativeAge } from '../lib/relativeTime';
import type { DocumentListItem, DocumentChunk } from '../types/api';

const ACCENT = 'var(--sec-ingestion)'; // §2.9 ingestion #4FA0A0 (teal)

// SSE live events use their own vocabulary (§SSE).
const LIVE_COLOR: Record<DocStatus, string> = {
  document_indexed: 'var(--grn)',
  duplicate_detected: 'var(--kind-agent)',
  document_failed: 'var(--red)',
};

// REST `status` (persisted) uses a different vocabulary — match loosely so an
// unseen value still lands on a sensible color instead of breaking.
function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('index')) return 'var(--grn)';
  if (s.includes('fail') || s.includes('error')) return 'var(--red)';
  if (s.includes('dup')) return 'var(--kind-agent)';
  if (s.includes('process') || s.includes('pending') || s.includes('queue')) return ACCENT;
  return 'var(--ink-3)';
}

function MetricTile({ label, value, sub, color, loading }: { label: string; value: ReactNode; sub: string; color: string; loading?: boolean }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-center gap-2">
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">{label}</span>
      </div>
      <div className="mt-2 font-mono text-[26px] font-medium leading-none tabular-nums text-ink-1">
        {loading ? <span className="inline-block h-[20px] w-[40px] animate-pulse rounded-sm align-middle" style={{ background: 'var(--inset)' }} /> : value}
      </div>
      <div className="mt-1.5 font-mono text-[10px] text-ink-3">{sub}</div>
    </GlassCard>
  );
}

// Live SSE row — transient process feedback, informational (not selectable).
function LiveRow({ item }: { item: IngestionDoc }) {
  const { t } = useTranslation();
  const color = LIVE_COLOR[item.status];
  return (
    <div className="grid w-full grid-cols-[16px_1fr_auto] items-center gap-3 border-b border-[var(--card-hairline)] px-3 py-2 last:border-0">
      <span className="grid h-[14px] w-[14px] place-items-center rounded-full" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
        <span className="h-[6px] w-[6px] rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[12.5px] text-ink-1">{item.doc}</span>
        <span className="font-mono text-[9.5px] uppercase tracking-[0.06em]" style={{ color }}>{t(`ing.status.${item.status}`)}</span>
      </span>
      <span className="flex-none font-mono text-[10px] tabular-nums text-ink-3">{t('ing.ago', { age: relativeAge(item.ts) })}</span>
    </div>
  );
}

// Historical document row — selectable, opens the detail panel.
function DocRow({ doc, active, onClick }: { doc: DocumentListItem; active: boolean; onClick: () => void }) {
  const { t } = useTranslation();
  const color = statusColor(doc.status);
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      data-testid="doc-row"
      onClick={onClick}
      className="grid w-full grid-cols-[16px_1fr_auto] items-center gap-3 border-b border-[var(--card-hairline)] px-3 py-2.5 text-left transition-colors last:border-0 hover:bg-[var(--inset)]"
      style={active ? { background: 'color-mix(in srgb, var(--sec-ingestion) 12%, transparent)' } : undefined}
    >
      <span className="grid h-[14px] w-[14px] place-items-center rounded-full" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
        <span className="h-[6px] w-[6px] rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[12.5px] text-ink-1">{doc.filename}</span>
        <span className="flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-3">
          <span style={{ color }}>{displayStatus(doc.status, t)}</span>
          <span>·</span>
          <span>{doc.doc_type}</span>
        </span>
      </span>
      <span className="flex-none font-mono text-[10px] tabular-nums text-ink-3">{doc.created_at.slice(0, 10)}</span>
    </button>
  );
}

function MetaCell({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="truncate font-mono text-[12px] text-ink-1">{v}</div>
      <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{k}</div>
    </div>
  );
}

function DocDetailPanel({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const detail = useDocumentDetail(id);
  const chunks = useDocumentChunks(id, 20);
  const reindex = useReindexDocument();
  const del = useDeleteDocument();
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Short cooldown after a reindex so back-to-back triggers (incl. across docs,
  // where the keyed remount resets `busy`) can't pile heavy reprocessing on the
  // backend (VS-ING-L2).
  const [cooldown, setCooldown] = useState(false);
  const cdRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (cdRef.current) clearTimeout(cdRef.current); }, []);

  const d = detail.data;
  const busy = reindex.isPending || del.isPending;
  const color = d ? statusColor(d.status) : ACCENT;

  const onReindex = () =>
    reindex.mutate(id, {
      onSuccess: () => {
        toast(t('ing.reindexed'));
        setCooldown(true);
        cdRef.current = setTimeout(() => setCooldown(false), 6000);
      },
      onError: (e) => toast(errMsg(e, t, t('ing.actionFailed'))),
    });
  const onDelete = () =>
    del.mutate(id, {
      onSuccess: () => {
        toast(t('ing.deleted'));
        onDeleted();
      },
      onError: (e) => {
        setConfirmDelete(false);
        toast(errMsg(e, t, t('ing.actionFailed')));
      },
    });

  if (detail.isPending) {
    return (
      <div className="flex flex-col gap-2.5 p-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-[14px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${80 - i * 10}%` }} />
        ))}
      </div>
    );
  }
  if (detail.isError || !d) {
    return <div className="grid h-full place-items-center px-6 text-center font-mono text-[12px] text-ink-3">{t('ing.loadFailed')}</div>;
  }

  const previewChunks = asArray<DocumentChunk>(chunks.data?.chunks);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color }}>
        <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
        {displayStatus(d.status, t)}
      </div>
      <div className="mt-2 break-words text-[16px] font-semibold leading-tight text-ink-1">{d.filename}</div>

      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <MetaCell k={t('ing.docType')} v={d.doc_type} />
        <MetaCell k={t('ing.visibilityLabel')} v={d.visibility} />
        <MetaCell k={t('ing.created')} v={new Date(d.created_at).toLocaleString('en-US', { hour12: false })} />
        <MetaCell k={t('ing.lastIndexed')} v={d.last_indexed ? new Date(d.last_indexed).toLocaleString('en-US', { hour12: false }) : '—'} />
        <MetaCell k={t('ing.retries')} v={String(d.retry_count)} />
        <MetaCell k={t('ing.docId')} v={d.id} />
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('ing.chunks')}</span>
          {chunks.data && <span className="font-mono text-[10px] tabular-nums text-ink-3">{t('ing.chunksCount', { n: chunks.data.total_chunks })}</span>}
        </div>
        {chunks.isPending ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((i) => (
              <span key={i} className="h-[28px] animate-pulse rounded-md" style={{ background: 'var(--inset)' }} />
            ))}
          </div>
        ) : previewChunks.length === 0 ? (
          <div className="font-mono text-[11.5px] text-ink-3">{t('ing.noChunks')}</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {previewChunks.map((c) => (
              <div key={c.chunk_index} className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                <div className="flex items-center justify-between font-mono text-[9.5px] text-ink-3">
                  <span>#{c.chunk_index}</span>
                  {c.section_path && <span className="truncate">{t('ing.chunkSection', { path: c.section_path })}</span>}
                </div>
                <div className="mt-1 line-clamp-3 text-[11.5px] leading-snug text-ink-2">{c.content}</div>
              </div>
            ))}
            {chunks.data && chunks.data.truncated && (
              <div className="px-1 font-mono text-[10px] text-ink-3">{t('ing.chunksMore', { n: chunks.data.total_chunks - previewChunks.length })}</div>
            )}
          </div>
        )}
      </div>

      <div className="mt-5 flex flex-none gap-2.5">
        {confirmDelete ? (
          <>
            <span className="flex flex-1 items-center font-mono text-[11px] text-ink-1">{t('ing.confirmDeletePrompt')}</span>
            <button
              type="button"
              onClick={onDelete}
              disabled={del.isPending}
              data-testid="doc-delete-confirm"
              className="rounded-btn px-3.5 py-2.5 font-body text-[12px] font-semibold text-red transition-[filter] hover:brightness-110 disabled:opacity-50"
              style={{ background: 'color-mix(in srgb, var(--red) 15%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 40%, transparent)' }}
            >
              {del.isPending ? t('ing.deleting') : t('ing.confirmDelete')}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              disabled={del.isPending}
              className="rounded-btn px-3.5 py-2.5 font-body text-[12px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
              style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
            >
              {t('ing.cancel')}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={onReindex}
              disabled={busy || cooldown}
              data-testid="doc-reindex"
              className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
              style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
            >
              {reindex.isPending ? t('ing.reindexing') : t('ing.reindex')}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              disabled={busy}
              data-testid="doc-delete"
              className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-red transition-[filter] hover:brightness-110 disabled:opacity-50"
              style={{ background: 'color-mix(in srgb, var(--red) 15%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--red) 40%, transparent)' }}
            >
              {t('ing.delete')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function Ingestion() {
  const { t } = useTranslation();
  const toast = useToastStore((s) => s.show);
  const liveItems = useIngestionStore((s) => s.items);
  const counts = useIngestionStore((s) => s.counts);
  const knowledge = useKnowledgeStats();
  const docs = useDocuments(50);
  const upload = useUploadDocument();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const docList = asArray<DocumentListItem>(docs.data);
  const dupCandidates = knowledge.data?.duplicate_candidate_count;

  // Upload a document: main opens the picker, reads the file, and POSTs its content
  // (multipart) to /documents/upload — the backend in Docker can't read host paths.
  const onAddDocument = () => {
    if (upload.isPending) return;
    upload.mutate(
      { project_id: 1, visibility: 'public' },
      {
        onSuccess: (r) => {
          if (r.canceled) return; // user dismissed the picker
          toast(t('ing.registered', { name: r.filename ?? '' }));
        },
        onError: (e) => {
          const code = e instanceof ApiError ? e.message : '';
          if (code === 'unsupported_type') toast(t('ing.unsupportedType'));
          else if (code === 'file_too_large') toast(t('ing.fileTooLarge'));
          else toast(errMsg(e, t, t('ing.registerFailed')));
        },
      },
    );
  };

  return (
    <>
      <div className="mb-[18px] mt-1.5 flex items-end justify-between gap-4 px-0.5">
        <div>
          <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('ing.title')}</h1>
          <p className="mt-1.5 text-[12.5px] text-ink-3">{t('ing.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={onAddDocument}
          disabled={upload.isPending}
          data-testid="ing-add-doc"
          className="flex h-11 flex-none items-center gap-2 rounded-md bg-btn-primary px-3.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
          style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={15} height={15} aria-hidden="true"><path d="M12 5v14M5 12h14" strokeLinecap="round" /></svg>
          {upload.isPending ? t('ing.registering') : t('ing.addDocument')}
        </button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile label={t('ing.metric.indexed')} value={counts.indexed} sub={t('ing.metric.session')} color="var(--grn)" />
        <MetricTile label={t('ing.metric.duplicate')} value={counts.duplicate} sub={t('ing.metric.session')} color="var(--kind-agent)" />
        <MetricTile label={t('ing.metric.failed')} value={counts.failed} sub={t('ing.metric.session')} color="var(--red)" />
        <MetricTile
          label={t('ing.metric.dupCandidates')}
          value={dupCandidates != null ? dupCandidates.toLocaleString('en-US') : '—'}
          sub={t('ing.metric.statsSource')}
          color={ACCENT}
          loading={knowledge.isPending}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        {/* LEFT: live activity (top) + indexed documents (bottom) */}
        <div className="flex max-h-[calc(100vh-360px)] flex-col gap-4">
          {/* LIVE — transient SSE process feedback */}
          <GlassCard className="flex max-h-[210px] flex-col p-3">
            <div className="mb-2 flex flex-none items-center justify-between gap-2 px-1">
              <div className="flex items-center gap-2">
                <span className="h-[7px] w-[7px] rounded-full motion-safe:animate-pulse" style={{ background: ACCENT, boxShadow: `0 0 6px ${ACCENT}` }} />
                <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{t('ing.liveSection')}</span>
              </div>
              <span className="font-mono text-[9.5px] tracking-[0.04em] text-ink-3">{t('ing.live')}</span>
            </div>
            {liveItems.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-1.5 px-8 py-6 text-center">
                <span className="font-mono text-[12px] text-ink-2">{t('ing.empty')}</span>
                <span className="max-w-[340px] text-[11px] leading-relaxed text-ink-3">{t('ing.emptyHint')}</span>
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto">
                {liveItems.map((it) => (
                  <LiveRow key={it.id} item={it} />
                ))}
              </div>
            )}
          </GlassCard>

          {/* HISTORICAL — the persistent indexed library */}
          <GlassCard className="flex min-h-0 flex-1 flex-col p-3">
            <div className="mb-2 flex flex-none items-center justify-between gap-2 px-1">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{t('ing.historical')}</span>
              {docs.data && <span className="font-mono text-[9.5px] tabular-nums text-ink-3">{t('ing.historicalCount', { n: docList.length })}</span>}
            </div>
            {docs.isPending ? (
              <div className="flex flex-col gap-2 p-2">
                {[0, 1, 2, 3].map((i) => (
                  <span key={i} className="h-[16px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${90 - i * 8}%` }} />
                ))}
              </div>
            ) : docs.isError ? (
              <div className="grid flex-1 place-items-center px-8 text-center">
                {docs.error instanceof ApiError && docs.error.status === 403 ? (
                  <span className="font-mono text-[12px] text-ink-3">{t('ing.limitedAccess')}</span>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
                    <span className="font-mono text-[12px] text-ink-2">{t('ing.loadError')}</span>
                    <button type="button" onClick={() => void docs.refetch()} className="font-mono text-[12px] text-accent">{t('ing.retry')}</button>
                  </div>
                )}
              </div>
            ) : docList.length === 0 ? (
              <div className="grid flex-1 place-items-center px-8 text-center font-mono text-[12px] text-ink-3">{t('ing.historicalEmpty')}</div>
            ) : (
              <div role="listbox" aria-label={t('ing.historical')} className="min-h-0 flex-1 overflow-y-auto">
                {docList.map((doc) => (
                  <DocRow key={doc.id} doc={doc} active={selectedId === doc.id} onClick={() => setSelectedId(doc.id)} />
                ))}
              </div>
            )}
          </GlassCard>
        </div>

        {/* RIGHT: detail of the selected indexed document */}
        <GlassCard className="flex max-h-[calc(100vh-360px)] flex-col p-[18px]">
          {selectedId ? (
            <DocDetailPanel key={selectedId} id={selectedId} onDeleted={() => setSelectedId(null)} />
          ) : (
            <div className="grid h-full place-items-center px-6 text-center font-mono text-[12px] text-ink-3">{t('ing.selectPrompt')}</div>
          )}
        </GlassCard>
      </div>
    </>
  );
}
