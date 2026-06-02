import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../lib/api';
import type { AuthMe } from '../types/api';

// Bare path — auth router. Consumed by Command Center (FB-CC).
export const useAuthMe = () => useQuery({ queryKey: ['auth', 'me'], queryFn: () => apiGet<AuthMe>('/auth/me') });
