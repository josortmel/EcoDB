import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPut, apiPost, apiDelete } from '../lib/api';
import { assertUuid } from '../lib/assertUuid';

export type Staleness = 'active' | 'stale' | 'dormant' | 'archived';
export type MemoryType = 'momento' | 'decision' | 'acuerdo' | 'tecnico' | 'descubrimiento' | 'observacion' | 'referencia';
export const MEMORY_TYPES: MemoryType[] = ['momento', 'decision', 'acuerdo', 'tecnico', 'descubrimiento', 'observacion', 'referencia'];
export type Visibility = 'public' | 'private';

// POST /memories/preview (GLiNER dry-run, 10/min) — entities + suggested triples.
export interface PreviewEntity {
  text: string;
  label: string;
  score: number;
  source: string;
}
export interface SuggestedTriple {
  subject: string;
  predicate: string;
  object: string;
}
export interface PreviewResponse {
  entities: PreviewEntity[];
  entity_count: number;
  suggested_triples: SuggestedTriple[];
}

export function useMemoryPreview() {
  return useMutation({ mutationFn: (content: string) => apiPost<PreviewResponse>('/memories/preview', { content }) });
}

// POST /memories (20/min) — creates the real memory, then refreshes the views
// that count it.
export interface CreateMemoryInput {
  content: string;
  type: string;
  visibility?: string;
  tags?: string[];
}
export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation({
    // MemoryCreate requires workspace_id + project_id (the guide omitted them) —
    // default to the general/system pair the MCP save_memory uses, so dashboard
    // memories land alongside the agents'. content_type defaults to 'text'.
    mutationFn: (body: CreateMemoryInput) => apiPost<{ memory_id?: string; id?: string }>('/memories', { workspace_id: 1, project_id: 1, content_type: 'text', ...body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['stats', 'memories'] });
      void qc.invalidateQueries({ queryKey: ['memories', 'recent'] });
      void qc.invalidateQueries({ queryKey: ['inbox', 'summary'] });
    },
  });
}

// PUT /memories/{id} (MemoryUpdate) — edit content/type/visibility/tags. Only the
// provided fields are sent; the rest are left unchanged server-side.
export interface MemoryUpdateInput {
  content?: string;
  type?: MemoryType;
  visibility?: Visibility;
  tags?: string[];
}
export function useUpdateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: MemoryUpdateInput }) => {
      assertUuid(id);
      return apiPut<{ id?: string; memory_id?: string }>(`/memories/${encodeURIComponent(id)}`, patch);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories', 'recent'] });
      void qc.invalidateQueries({ queryKey: ['search'] });
      void qc.invalidateQueries({ queryKey: ['stats', 'memories'] });
    },
  });
}

// DELETE /memories/{id} — soft-deletes (moves to bin). Destructive → the caller
// gates it behind an explicit confirm.
export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      assertUuid(id);
      return apiDelete<unknown>(`/memories/${encodeURIComponent(id)}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories', 'recent'] });
      void qc.invalidateQueries({ queryKey: ['search'] });
      void qc.invalidateQueries({ queryKey: ['stats', 'memories'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] });
    },
  });
}

// PUT /memories/{id}/staleness — toggles a memory between active and stale.
export function useUpdateStaleness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, staleness }: { id: string; staleness: Staleness }) => {
      assertUuid(id);
      return apiPut<{ memory_id: string; staleness: string }>(`/memories/${encodeURIComponent(id)}/staleness`, { staleness });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['memories', 'recent'] });
      void qc.invalidateQueries({ queryKey: ['search'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] }); // summary + details (Decisions Inbox)
    },
  });
}
