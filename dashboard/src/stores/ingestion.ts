import { create } from 'zustand';

// Document lifecycle SSE events (DASHBOARD_BACKEND_GUIDE.md §SSE).
export type DocStatus = 'document_indexed' | 'document_failed' | 'duplicate_detected';

export interface IngestionDoc {
  id: string;
  status: DocStatus;
  doc: string;
  docId?: string;
  ts: number;
}

interface IngestionState {
  items: IngestionDoc[];
  // Cumulative session counters (survive the ring-buffer eviction).
  counts: { indexed: number; failed: number; duplicate: number };
  pushDoc: (status: DocStatus, dataRaw: string) => void;
}

const MAX = 60;
const COUNT_KEY: Record<DocStatus, 'indexed' | 'failed' | 'duplicate'> = {
  document_indexed: 'indexed',
  document_failed: 'failed',
  duplicate_detected: 'duplicate',
};

// The SSE `data` is a JSON string; extract a display name + id defensively (the
// exact field names aren't pinned in the guide, so we try the likely ones).
function parseDoc(raw: string): { doc: string; docId?: string } {
  try {
    const p = JSON.parse(raw) as Record<string, unknown>;
    const rawId = p.document_id ?? p.id ?? p.doc_id;
    const docId = rawId != null ? String(rawId) : undefined; // ids can arrive numeric
    const rawName = p.filename ?? p.name ?? p.title ?? p.path ?? rawId;
    return { doc: rawName != null ? String(rawName) : '—', docId };
  } catch {
    return { doc: raw || '—' };
  }
}

// Ring buffer of the live document pipeline, fed by useSSE. Ephemeral UI state,
// never persisted.
export const useIngestionStore = create<IngestionState>((set) => ({
  items: [],
  counts: { indexed: 0, failed: 0, duplicate: 0 },
  pushDoc: (status, dataRaw) => {
    const { doc, docId } = parseDoc(dataRaw);
    const item: IngestionDoc = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      status,
      doc,
      docId,
      ts: Date.now(),
    };
    set((s) => {
      const key = COUNT_KEY[status];
      return { items: [item, ...s.items].slice(0, MAX), counts: { ...s.counts, [key]: s.counts[key] + 1 } };
    });
  },
}));
