import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPut } from '../lib/api';
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
// reverse flips the merge direction: false (default) collapses source → target
// (target survives); true collapses target → source (source survives).
export function useReviewAliasCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, merge, reverse }: { id: number; status: 'approved' | 'rejected'; merge?: boolean; reverse?: boolean }) => {
      assertNodeId(id); // defense-in-depth: id flows into the URL (adv-seg OBS-2)
      const body: { status: string; merge?: boolean; reverse?: boolean } = { status };
      if (merge != null) body.merge = merge;
      if (reverse != null) body.reverse = reverse;
      return apiPut<unknown>(`/admin/alias-candidates/${id}`, body);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['inbox'] }),
  });
}

// POST /admin/alias-candidates/scan — retroactive discovery across active nodes.
// threshold is pg_trgm similarity (higher = stricter). dry_run returns the
// candidates that WOULD be persisted (preview) without touching the DB.
export interface AliasScanRequest {
  threshold?: number;
  max_per_name?: number;
  name_filter?: string;
  dry_run?: boolean;
}
export interface AliasScanCandidate {
  source_name: string;
  target_node_id: number;
  target_node_name?: string | null;
  confidence: number;
}
export interface AliasScanResponse {
  found: number;
  inserted: number;
  updated: number;
  total_pending: number;
  candidates?: AliasScanCandidate[] | null;
}

export function useScanAliasCandidates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AliasScanRequest) => apiPost<AliasScanResponse>('/admin/alias-candidates/scan', body),
    onSuccess: (_data, vars) => {
      // A dry_run touches nothing — don't refetch the list on a preview.
      if (!vars.dry_run) void qc.invalidateQueries({ queryKey: ['inbox'] });
    },
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
