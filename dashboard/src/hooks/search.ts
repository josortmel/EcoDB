import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost } from '../lib/api';
import type {
  SearchResponse,
  SearchRequest,
  RecentMemoriesResponse,
  WorkspacesResponse,
  ProjectsResponse,
} from '../types/api';

// Bare paths — search + memories routers. params carries the advanced-search
// scope (limit/agent/tags/workspace/project/ultrasearch); undefined keys are
// dropped by JSON serialization so the backend applies its defaults.
export const useSearch = (params: SearchRequest) => {
  // Defaults live in the body so queryKey === payload (no phantom cache misses).
  const body = { limit: 20, include_documents: true, ...params };
  return useQuery({
    queryKey: ['search', body],
    queryFn: () => apiPost<SearchResponse>('/search', body),
    enabled: params.query_text.trim().length > 0,
  });
};

export const useRecentMemories = (limit = 20) =>
  useQuery({
    queryKey: ['memories', 'recent', limit],
    queryFn: () => apiGet<RecentMemoriesResponse>(`/memories/recent?limit=${limit}`),
  });

// Scope selectors for advanced search — rarely change, so cache them a while.
export const useWorkspaces = () =>
  useQuery({
    queryKey: ['workspaces'],
    queryFn: () => apiGet<WorkspacesResponse>('/workspaces'),
    staleTime: 5 * 60_000,
  });

export const useProjects = (workspaceId: number | null) =>
  useQuery({
    queryKey: ['projects', workspaceId],
    queryFn: () => apiGet<ProjectsResponse>(`/workspaces/${workspaceId}/projects`),
    enabled: workspaceId != null,
    staleTime: 5 * 60_000,
  });
