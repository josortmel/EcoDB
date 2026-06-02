import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPut, apiDelete, ApiError } from '../lib/api';
import { assertUuid } from '../lib/assertUuid';
import type { DocumentListItem, DocumentDetail, DocumentChunksResponse } from '../types/api';

// GET /documents — historical, persistent list (bare path). The SSE doc events
// invalidate ['documents'] so this refreshes live (see eventDigest).
export const useDocuments = (limit = 50) =>
  useQuery({
    queryKey: ['documents', limit],
    queryFn: () => apiGet<DocumentListItem[]>(`/documents?limit=${limit}`),
  });

// Multipart upload via the main-process bridge. The backend runs in Docker and
// can't read host paths, so we send the file CONTENT (not a path) to
// POST /documents/upload. The dialog + read + POST all happen in main; the host
// path never reaches the renderer.
export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { project_id?: number; visibility?: 'public' | 'private' }) => {
      const r = await window.ecodb.uploadDocument(args);
      if (r.canceled) return { canceled: true as const };
      if (!r.ok) throw new ApiError(r.status ?? 0, r.error ?? `http_${r.status ?? 0}`, undefined, r.data);
      return { canceled: false as const, filename: r.filename, data: r.data };
    },
    onSuccess: (res) => {
      if (!res.canceled) void qc.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}

// GET /documents/{id} — fuller detail than the list row.
export const useDocumentDetail = (id: string | null, enabled = true) =>
  useQuery({
    queryKey: ['document', id],
    queryFn: () => {
      assertUuid(id as string);
      return apiGet<DocumentDetail>(`/documents/${encodeURIComponent(id as string)}`);
    },
    enabled: enabled && !!id,
  });

// GET /documents/{id}/chunks — paginated chunk preview.
export const useDocumentChunks = (id: string | null, limit = 20, enabled = true) =>
  useQuery({
    queryKey: ['document', id, 'chunks', limit],
    queryFn: () => {
      assertUuid(id as string);
      return apiGet<DocumentChunksResponse>(`/documents/${encodeURIComponent(id as string)}/chunks?limit=${limit}`);
    },
    enabled: enabled && !!id,
  });

// PUT /documents/{id}/reindex — no body; response is opaque, 200 = success.
export function useReindexDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      assertUuid(id);
      return apiPut<unknown>(`/documents/${encodeURIComponent(id)}/reindex`, undefined);
    },
    onSuccess: (_d, id) => {
      void qc.invalidateQueries({ queryKey: ['documents'] });
      void qc.invalidateQueries({ queryKey: ['document', id] });
    },
  });
}

// DELETE /documents/{id} — 204, no body. Destructive → caller gates with a confirm.
export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      assertUuid(id);
      return apiDelete<unknown>(`/documents/${encodeURIComponent(id)}`);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['documents'] }),
  });
}

// NOTE: PUT /admin/documents/{id}/trust-tier is intentionally NOT wired here. The
// tier is write-only server-side (GET never returns it), so a setter in the
// general Ingestion view would let the user write blind. It belongs in the
// Decisions Inbox (low_trust_documents), where a flagged item gives real context.
