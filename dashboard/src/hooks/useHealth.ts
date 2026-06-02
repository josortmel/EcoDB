import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../lib/api';
import type { SystemStats } from '../types/api';

// Lightweight liveness ping. `isError` ⇒ the API is unreachable / intermittent
// (while authenticated → degraded banner, not the first-run screen).
// `dataUpdatedAt` ⇒ when we last had a successful response. Not persisted (the
// 'health' key isn't in the dehydration allowlist).
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<SystemStats>('/api/v1/stats/system'),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 25_000,
    gcTime: 60_000,
    retry: 1,
  });
}
