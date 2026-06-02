import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../lib/api';
import type {
  MemoryStats,
  GraphStats,
  AgentStats,
  SearchStats,
  SystemStats,
  KnowledgeStats,
  TimelineResponse,
} from '../types/api';

// PREFIX: stats is one of the only two `/api/v1`-prefixed router groups
// (the other is events). Everything else is bare. See backend guide §2.
const S = '/api/v1/stats';

export const useMemoryStats = () => useQuery({ queryKey: ['stats', 'memories'], queryFn: () => apiGet<MemoryStats>(`${S}/memories`) });
export const useGraphStats = () => useQuery({ queryKey: ['stats', 'graph'], queryFn: () => apiGet<GraphStats>(`${S}/graph`) });
export const useAgentStats = () => useQuery({ queryKey: ['stats', 'agents'], queryFn: () => apiGet<AgentStats>(`${S}/agents`) });
export const useSearchStats = () => useQuery({ queryKey: ['stats', 'search'], queryFn: () => apiGet<SearchStats>(`${S}/search`) });
export const useSystemStats = () => useQuery({ queryKey: ['stats', 'system'], queryFn: () => apiGet<SystemStats>(`${S}/system`) });
export const useKnowledgeStats = () =>
  useQuery({ queryKey: ['stats', 'knowledge'], queryFn: () => apiGet<KnowledgeStats>(`${S}/knowledge`) });

export const useTimeline = (period = 30) =>
  useQuery({ queryKey: ['stats', 'timeline', period], queryFn: () => apiGet<TimelineResponse>(`${S}/timeline?period=${period}`) });
