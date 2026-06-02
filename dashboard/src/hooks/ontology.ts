import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, ApiError } from '../lib/api';

// Graph node ids are positive integers. Guard before a destructive mutation —
// same defense-in-depth as assertUuid for the memory/document hooks.
export function assertNodeId(id: number): void {
  if (!Number.isInteger(id) || id <= 0) throw new ApiError(0, 'invalid_node_id');
}

// /admin/graph-vocabulary returns entities as {name, type} with NO node id, but
// merge/undo need integer node ids. /graph/search resolves a name → candidates.
export interface NodeMatch {
  id: number;
  name: string;
  similarity?: number;
}
interface GraphSearchResponse {
  query: string;
  matches: NodeMatch[];
}

// GET /graph/search?q=&limit= — q must be ≥3 chars (server constraint).
export async function searchNodes(q: string, limit = 8): Promise<NodeMatch[]> {
  if (q.trim().length < 3) return [];
  const res = await apiGet<GraphSearchResponse>(`/graph/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  return Array.isArray(res.matches) ? res.matches : [];
}

// POST /admin/merge-entities {source_node_id, target_node_id, reason?, keep_as_alias?}
// — merges source INTO target. keep_as_alias:true also records source as an approved
// alias of target. Destructive (reversible via undo-merge). Response is opaque.
export function useMergeEntities() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { source_node_id: number; target_node_id: number; reason?: string; keep_as_alias?: boolean }) => {
      assertNodeId(body.source_node_id);
      assertNodeId(body.target_node_id);
      return apiPost<unknown>('/admin/merge-entities', body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin', 'graph-vocabulary'] });
      void qc.invalidateQueries({ queryKey: ['graph'] });
      void qc.invalidateQueries({ queryKey: ['stats', 'knowledge'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] }); // a manual merge can resolve an alias candidate
    },
  });
}

// POST /admin/undo-merge {source_node_id} — reverts a prior merge of that node.
export function useUndoMerge() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceNodeId: number) => {
      assertNodeId(sourceNodeId);
      return apiPost<unknown>('/admin/undo-merge', { source_node_id: sourceNodeId });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin', 'graph-vocabulary'] });
      void qc.invalidateQueries({ queryKey: ['graph'] });
      void qc.invalidateQueries({ queryKey: ['stats', 'knowledge'] });
      void qc.invalidateQueries({ queryKey: ['inbox'] });
    },
  });
}
