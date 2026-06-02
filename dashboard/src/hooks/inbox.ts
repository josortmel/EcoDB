import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPut } from '../lib/api';
import { assertNodeId } from './ontology';
import type { InboxSummary, InboxDetailsResponse, InboxClass } from '../types/api';

export type AliasStatus = 'pending' | 'approved' | 'rejected';

// Alias candidate (pending_alias_candidates) — its own rich endpoint, not the
// generic inbox-details shape.
export interface AliasItem {
  id: number;
  source_name: string;
  target_node_name: string;
  target_node_id?: number;
  confidence: number;
  occurrences: number;
  status?: string;
}

// GET /admin/alias-candidates?status= → list by status (pending | approved | rejected).
export function useAliasCandidates(limit: number, status: AliasStatus = 'pending') {
  return useQuery({
    queryKey: ['inbox', 'alias-candidates', status, limit],
    queryFn: () => apiGet<AliasItem[]>(`/admin/alias-candidates?status=${status}&limit=${limit}`),
    enabled: limit > 0,
  });
}

// PUT /admin/alias-candidates/{id} — approve (optionally merging) or reject.
export function useReviewAliasCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, merge }: { id: number; status: 'approved' | 'rejected'; merge?: boolean }) => {
      assertNodeId(id); // defense-in-depth: id flows into the URL (adv-seg OBS-2)
      return apiPut<unknown>(`/admin/alias-candidates/${id}`, merge != null ? { status, merge } : { status });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['inbox'] }),
  });
}

// Bare paths (no /api/v1) — admin router.
export const useInboxSummary = () =>
  useQuery({ queryKey: ['inbox', 'summary'], queryFn: () => apiGet<InboxSummary>('/admin/attention-inbox/summary') });

export const useInboxDetails = (decisionClass: InboxClass, limit = 20, offset = 0, enabled = true) =>
  useQuery({
    queryKey: ['inbox', 'details', decisionClass, limit, offset],
    queryFn: () =>
      apiGet<InboxDetailsResponse>(
        `/admin/attention-inbox/details?decision_class=${decisionClass}&limit=${limit}&offset=${offset}`,
      ),
    enabled,
  });
