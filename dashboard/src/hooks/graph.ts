import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../lib/api';
import type { SubgraphResponse, GraphAllResponse, NeighborsResponse } from '../types/api';

// Bare paths — graph router.
export const useGraphSubgraph = (center: string, depth = 2, enabled = true) =>
  useQuery({
    queryKey: ['graph', 'subgraph', center, depth],
    queryFn: () => apiGet<SubgraphResponse>(`/graph/subgraph?center=${encodeURIComponent(center)}&depth=${depth}`),
    enabled: enabled && center.trim().length > 0,
  });

// GET /graph/all — the whole graph (nodes ordered by degree DESC, active only).
// limit caps the page; node_count is the true total. clusters/cluster_id ignored.
export const useGraphAll = (limit = 2000, enabled = true) =>
  useQuery({
    queryKey: ['graph', 'all', limit],
    queryFn: () => apiGet<GraphAllResponse>(`/graph/all?limit=${limit}&offset=0`),
    enabled,
    staleTime: 5 * 60 * 1000, // 1414-node payload — don't refetch on window-focus
  });

export const useNeighbors = (node: string, depth = 2) =>
  useQuery({
    queryKey: ['graph', 'neighbors', node, depth],
    queryFn: () => apiGet<NeighborsResponse>(`/graph/neighbors/${encodeURIComponent(node)}?depth=${depth}`),
    enabled: node.trim().length > 0,
  });
