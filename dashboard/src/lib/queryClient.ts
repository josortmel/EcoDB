import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './api';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Never retry a client error (the wrapper already logs out on 401);
        // a 429 IS retried, but with the Retry-After delay below.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 429) {
          return false;
        }
        return failureCount < 3;
      },
      retryDelay: (attempt, error) => {
        if (error instanceof ApiError && error.retryAfter != null) return error.retryAfter * 1000;
        return Math.min(1000 * 2 ** attempt, 30_000); // exponential backoff, capped
      },
    },
  },
});
