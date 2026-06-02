import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../components/GlassCard';
import { SearchField } from '../components/SearchField';
import { MemoryRow } from '../components/MemoryRow';
import { highlight } from '../lib/highlight';
import { asArray } from '../lib/asArray';
import type { MemoryDetail } from '../stores/detail';
import { useViewStore } from '../stores/view';
import { useSearch, useRecentMemories, useWorkspaces, useProjects } from '../hooks/search';
import { useAgentStats } from '../hooks/stats';
import { useDocumentChunks, useDocumentDetail } from '../hooks/documents';
import type { SearchResult, RecentMemory, SearchRequest, AgentStat, Workspace, Project, DocumentChunk } from '../types/api';

const TYPES = ['decision', 'tecnico', 'momento', 'observacion', 'referencia'] as const;
const TYPE_COLOR: Record<string, string> = {
  decision: 'var(--type-decision)',
  tecnico: 'var(--type-tecnico)',
  momento: 'var(--type-momento)',
  observacion: 'var(--type-observacion)',
  referencia: 'var(--type-referencia)',
};
const LIMITS = [20, 50, 100] as const;

const day = (iso?: string): string => (iso ? iso.slice(0, 10) : '');
const searchToRow = (r: SearchResult): MemoryDetail => ({
  id: r.id,
  content: r.content,
  type: r.type,
  tags: r.tags,
  ts: day(r.created_at),
  agent: r.agent_identifier,
  visibility: r.visibility,
  trustWarnings: r.trust_warnings,
  scoreBreakdown: r.score_breakdown,
  stale: false,
  hot: (r.trust_warnings?.length ?? 0) > 0,
});
const recentToRow = (r: RecentMemory): MemoryDetail => ({
  id: r.id,
  content: r.content,
  type: r.type,
  tags: r.tags,
  ts: day(r.ts),
  agent: r.agent_identifier,
  stale: r.staleness === 'stale',
});

function Chip({ active, onClick, title, children }: { active: boolean; onClick: () => void; title?: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`flex items-center gap-1.5 rounded-[20px] px-2.5 py-1.5 font-mono text-[10.5px] transition-colors ${active ? 'text-accent' : 'text-ink-3 hover:text-ink-1'}`}
      style={{
        background: active ? 'color-mix(in srgb, var(--accent) 13%, transparent)' : 'var(--inset)',
        boxShadow: active ? 'inset 0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent)' : 'inset 0 0 0 1px var(--card-hairline)',
      }}
    >
      {children}
    </button>
  );
}

// Native select styled to the theme — accessible, keyboard-driven, shows its
// options, no custom dropdown to maintain (anti-slop).
function ScopeSelect({
  label,
  value,
  onChange,
  options,
  anyLabel,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  anyLabel: string;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="min-w-0 rounded-[7px] px-2.5 py-1.5 font-mono text-[11px] text-ink-1 outline-none"
        style={{
          background: 'var(--inset)',
          boxShadow: focused
            ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
            : `inset 0 0 0 1px ${value ? 'color-mix(in srgb, var(--accent) 40%, transparent)' : 'var(--card-hairline)'}`,
        }}
      >
        <option value="">{anyLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function TagsFilter({ tags, onAdd, onRemove }: { tags: string[]; onAdd: (t: string) => void; onRemove: (t: string) => void }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState('');
  const [focused, setFocused] = useState(false);
  const commit = () => {
    const v = draft.trim();
    if (v && !tags.includes(v)) onAdd(v);
    setDraft('');
  };
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('exp.adv.tags')}</span>
      <div
        className="flex flex-wrap items-center gap-1.5 rounded-[7px] px-2 py-1.5"
        style={{
          background: 'var(--inset)',
          boxShadow: focused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : 'inset 0 0 0 1px var(--card-hairline)',
        }}
      >
        {tags.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-mono text-[10px] text-accent"
            style={{ background: 'color-mix(in srgb, var(--accent) 13%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent)' }}
          >
            {tag}
            <button type="button" onClick={() => onRemove(tag)} aria-label={t('exp.adv.removeTag', { tag })} className="text-accent/70 hover:text-accent">
              ×
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commit();
            } else if (e.key === 'Backspace' && !draft && tags.length) {
              onRemove(tags[tags.length - 1]);
            }
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={t('exp.adv.tagsPlaceholder')}
          className="min-w-[100px] flex-1 bg-transparent font-mono text-[11px] text-ink-1 placeholder:text-ink-4 focus:outline-none"
        />
      </div>
    </div>
  );
}

function DocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} width={15} height={15}>
      <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

function DocRow({ r, query, onOpen }: { r: SearchResult; query: string; onOpen: (docId: string) => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      data-testid="doc-row"
      onClick={() => r.document_id && onOpen(r.document_id)}
      disabled={!r.document_id}
      className="grid w-full grid-cols-[16px_1fr] items-start gap-3.5 border-b border-[var(--card-hairline)] px-3 py-3 text-left transition-colors last:border-0 hover:bg-[var(--inset)] disabled:cursor-default disabled:hover:bg-transparent"
    >
      <span className="mt-0.5 flex-none text-ink-3">
        <DocIcon />
      </span>
      <span className="min-w-0">
        <span className="line-clamp-2 block text-[13px] leading-snug text-ink-1">{highlight(r.content, query)}</span>
        <span className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[10.5px] text-ink-3">
          <span>{t('exp.docChunk')}</span>
          <span>·</span>
          <span>{day(r.created_at)}</span>
          {r.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="rounded-sm px-1.5 py-0.5 text-[9.5px] text-ink-2" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              {tag}
            </span>
          ))}
        </span>
      </span>
    </button>
  );
}

function Shimmer() {
  return (
    <div className="flex flex-col gap-3 p-3">
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className="h-[14px] animate-pulse rounded-sm" style={{ background: 'var(--inset)', width: `${88 - i * 8}%` }} />
      ))}
    </div>
  );
}

// Opens the source document of a clicked chunk — title + paginated chunk preview.
function DocPreviewModal({ docId, onClose }: { docId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const detail = useDocumentDetail(docId);
  const chunks = useDocumentChunks(docId);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const list = asArray<DocumentChunk>(chunks.data?.chunks);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-6" style={{ background: 'rgba(8,10,14,0.52)' }} onClick={onClose}>
      <GlassCard className="flex max-h-[80vh] w-full max-w-2xl flex-col p-0">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--card-hairline)] px-5 py-3.5" onClick={(e) => e.stopPropagation()}>
          <div className="min-w-0">
            <h2 className="truncate font-mono text-[14px] text-ink-1">{detail.data?.filename ?? t('exp.preview.title')}</h2>
            <p className="mt-0.5 font-mono text-[10.5px] text-ink-3">{t('exp.preview.chunks', { n: chunks.data?.total_chunks ?? list.length })}</p>
          </div>
          <button type="button" onClick={onClose} className="flex-none font-mono text-[12px] text-ink-2 hover:text-ink-1">
            {t('exp.preview.close')}
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-3" onClick={(e) => e.stopPropagation()}>
          {chunks.isPending ? (
            <Shimmer />
          ) : chunks.isError ? (
            <div className="py-6 text-center font-mono text-[12px] text-ink-2">{t('exp.preview.error')}</div>
          ) : list.length === 0 ? (
            <div className="py-6 text-center font-mono text-[12px] text-ink-3">{t('exp.preview.empty')}</div>
          ) : (
            list.map((c) => (
              <div key={c.chunk_index} className="border-b border-[var(--card-hairline)] py-3 last:border-0">
                {c.section_path && <span className="mb-1 block font-mono text-[9.5px] text-ink-3">{t('exp.preview.section', { path: c.section_path })}</span>}
                <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink-1">{c.content}</p>
              </div>
            ))
          )}
        </div>
      </GlassCard>
    </div>
  );
}

export function KnowledgeExplorer() {
  const { t } = useTranslation();
  // ⌘K can hand off a query (e.g. a document result) — seed the initial state
  // from it, then consume so a later manual nav doesn't re-apply it (BC2).
  const [tab, setTab] = useState<'memories' | 'documents'>(() => useViewStore.getState().explorerSeed?.tab ?? 'memories');
  const [q, setQ] = useState(() => useViewStore.getState().explorerSeed?.query ?? '');
  // Client-side refinements (operate on the fetched set).
  const [fType, setFType] = useState<string | null>(null);
  const [fStale, setFStale] = useState(false);
  const [fVis, setFVis] = useState<string | null>(null);
  // Server-side scope (advanced search) — part of the request, drive a refetch.
  const [advOpen, setAdvOpen] = useState(false);
  const [limit, setLimit] = useState<number>(20);
  const [ultra, setUltra] = useState(false);
  const [inclDocs, setInclDocs] = useState(true);
  const [fAgent, setFAgent] = useState('');
  const [fTags, setFTags] = useState<string[]>([]);
  const [fWs, setFWs] = useState('');
  const [fProj, setFProj] = useState('');
  const [previewDocId, setPreviewDocId] = useState<string | null>(null);
  useEffect(() => {
    if (useViewStore.getState().explorerSeed) useViewStore.getState().consumeExplorerSeed();
  }, []);

  const searching = q.trim().length > 0;
  const wantDocs = tab === 'documents' || inclDocs;

  const searchParams = useMemo<SearchRequest>(() => {
    const p: SearchRequest = { query_text: q, limit, include_documents: wantDocs };
    if (ultra) {
      p.graph_discovery = true;
      p.deep_factor = 4;
    }
    if (wantDocs) p.max_document_results = 20;
    if (fAgent) p.agent_identifier = fAgent;
    if (fTags.length) p.tags = fTags;
    if (fWs) p.workspace_id = Number(fWs);
    if (fProj) p.project_id = Number(fProj);
    return p;
  }, [q, limit, ultra, wantDocs, fAgent, fTags, fWs, fProj]);

  const searchQ = useSearch(searchParams);
  const recentQ = useRecentMemories(30);
  const agentsQ = useAgentStats();
  const workspacesQ = useWorkspaces();
  const projectsQ = useProjects(fWs ? Number(fWs) : null);

  const results = useMemo(() => asArray<SearchResult>(searchQ.data?.results), [searchQ.data]);
  const docResults = useMemo(() => results.filter((r) => r.source_type === 'document_chunk'), [results]);

  const memRows = useMemo<MemoryDetail[]>(() => {
    if (tab === 'documents') return [];
    if (searching) return results.filter((r) => r.source_type === 'memory').map(searchToRow);
    return asArray<RecentMemory>(recentQ.data?.items).map(recentToRow);
  }, [tab, searching, results, recentQ.data]);

  const filteredMem = useMemo(
    () => memRows.filter((r) => (!fType || r.type === fType) && (!fStale || r.stale) && (!fVis || r.visibility === fVis)),
    [memRows, fType, fStale, fVis],
  );

  const showDocs = tab === 'documents' || (tab === 'memories' && inclDocs && searching);
  const visibleCount = tab === 'documents' ? docResults.length : filteredMem.length + (showDocs ? docResults.length : 0);

  const source = searching ? searchQ : recentQ;
  const loading = searching ? searchQ.isPending : tab === 'memories' && recentQ.isPending;
  const error = searching ? searchQ.isError : tab === 'memories' && recentQ.isError;
  const empty = filteredMem.length === 0 && (!showDocs || docResults.length === 0);
  const emptyLabel = tab === 'documents' ? (searching ? t('exp.emptyDocSearch') : t('exp.emptyDocuments')) : t('exp.emptyMemories');

  const scopeCount =
    (fAgent ? 1 : 0) + (fTags.length ? 1 : 0) + (fWs ? 1 : 0) + (fProj ? 1 : 0) + (ultra ? 1 : 0) + (limit !== 20 ? 1 : 0) + (!inclDocs ? 1 : 0);
  const closePreview = useCallback(() => setPreviewDocId(null), []);
  const resetScope = () => {
    setFAgent('');
    setFTags([]);
    setFWs('');
    setFProj('');
    setUltra(false);
    setLimit(20);
    setInclDocs(true);
  };

  const agentOptions = useMemo(() => asArray<AgentStat>(agentsQ.data?.agents).map((a) => ({ value: a.identifier, label: a.identifier })), [agentsQ.data]);
  const wsOptions = useMemo(() => asArray<Workspace>(workspacesQ.data?.items).map((w) => ({ value: String(w.id), label: w.name })), [workspacesQ.data]);
  const projOptions = useMemo(() => asArray<Project>(projectsQ.data?.items).map((p) => ({ value: String(p.id), label: p.name })), [projectsQ.data]);

  return (
    <>
      <div className="mb-[18px] mt-1.5 flex items-end justify-between gap-4 px-0.5">
        <div>
          <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('exp.title')}</h1>
          <p className="mt-1.5 text-[12.5px] text-ink-3">{t('exp.subtitle')}</p>
        </div>
        <div className="flex gap-0.5 rounded-md p-0.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          {(['memories', 'documents'] as const).map((tb) => (
            <button
              key={tb}
              type="button"
              data-testid={`tab-${tb}`}
              onClick={() => setTab(tb)}
              className={`rounded-[7px] px-3 py-1.5 font-body text-[12.5px] ${tab === tb ? 'text-ink-1' : 'text-ink-3'}`}
              style={tab === tb ? { background: 'var(--card-bg)', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' } : undefined}
            >
              {t(`exp.tab.${tb}`)}
            </button>
          ))}
        </div>
      </div>

      <GlassCard className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <SearchField
            value={q}
            onChange={setQ}
            placeholder={t(tab === 'memories' ? 'exp.searchMemories' : 'exp.searchDocuments')}
            resultCount={searching ? visibleCount : undefined}
            loading={loading}
            clearLabel={t('exp.clear')}
          />
          {tab === 'memories' && (
            <>
              <Chip active={fStale} onClick={() => setFStale((s) => !s)}>
                {t('exp.filter.stale')}
              </Chip>
              {TYPES.map((ty) => (
                <Chip key={ty} active={fType === ty} onClick={() => setFType(fType === ty ? null : ty)}>
                  <span className="h-[6px] w-[6px] rounded-full" style={{ background: TYPE_COLOR[ty] }} />
                  {ty}
                </Chip>
              ))}
              <Chip
                active={!!fVis}
                onClick={() => setFVis(fVis === 'public' ? 'private' : fVis === 'private' ? null : 'public')}
              >
                {t('exp.visibility')}: {fVis ?? t('exp.visAll')}
              </Chip>
            </>
          )}
          <Chip active={advOpen} onClick={() => setAdvOpen((s) => !s)}>
            {t('exp.adv.toggle')}
            {scopeCount > 0 && <span className="ml-1 text-accent">· {t('exp.adv.active', { count: scopeCount })}</span>}
          </Chip>
        </div>

        {advOpen && (
          <div className="mt-3 flex flex-col gap-3 rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('exp.adv.limit')}</span>
                <div className="flex gap-0.5 rounded-[7px] p-0.5" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                  {LIMITS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setLimit(n)}
                      className={`rounded-[5px] px-2 py-0.5 font-mono text-[10.5px] ${limit === n ? 'text-ink-1' : 'text-ink-3'}`}
                      style={limit === n ? { background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' } : undefined}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
              <Chip active={ultra} onClick={() => setUltra((s) => !s)} title={t('exp.adv.ultraTip')}>
                ⚡ {t('exp.adv.ultra')}
              </Chip>
              <Chip active={inclDocs} onClick={() => setInclDocs((s) => !s)}>
                {t('exp.adv.docs')}
              </Chip>
              {scopeCount > 0 && (
                <button type="button" onClick={resetScope} className="ml-auto font-mono text-[10.5px] text-ink-3 hover:text-ink-1">
                  {t('exp.adv.reset')}
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ScopeSelect label={t('exp.adv.author')} value={fAgent} onChange={setFAgent} options={agentOptions} anyLabel={t('exp.adv.any')} />
              <ScopeSelect
                label={t('exp.adv.workspace')}
                value={fWs}
                onChange={(v) => {
                  setFWs(v);
                  setFProj('');
                }}
                options={wsOptions}
                anyLabel={t('exp.adv.any')}
              />
              <ScopeSelect label={t('exp.adv.project')} value={fProj} onChange={setFProj} options={projOptions} anyLabel={t('exp.adv.any')} />
              <TagsFilter tags={fTags} onAdd={(tg) => setFTags((s) => [...s, tg])} onRemove={(tg) => setFTags((s) => s.filter((x) => x !== tg))} />
            </div>
          </div>
        )}

        <div className="mt-3 px-1 font-mono text-[10.5px] text-ink-3">
          {t('exp.results', { count: visibleCount })}
          {(searching || fType || fStale || fVis || scopeCount > 0) && ` · ${t('exp.filtered')}`}
        </div>

        <div className="mt-1 max-h-[calc(100vh-300px)] overflow-y-auto">
          {loading ? (
            <Shimmer />
          ) : error ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
              <span className="font-mono text-[12px] text-ink-2">{t('exp.error')}</span>
              <button type="button" onClick={() => void source.refetch()} className="font-mono text-[12px] text-ink-1 underline underline-offset-2">
                {t('exp.retry')}
              </button>
            </div>
          ) : empty ? (
            <div className="grid place-items-center py-10 font-mono text-[12.5px] text-ink-3">{emptyLabel}</div>
          ) : (
            <>
              {filteredMem.map((m) => (
                <MemoryRow key={m.id} m={m} query={q} />
              ))}
              {showDocs && docResults.map((r) => <DocRow key={r.id} r={r} query={q} onOpen={setPreviewDocId} />)}
            </>
          )}
        </div>
      </GlassCard>

      {previewDocId && <DocPreviewModal docId={previewDocId} onClose={closePreview} />}
    </>
  );
}
