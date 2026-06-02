import { ApiError } from './api';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Server-issued ids are UUIDs. Asserting the shape before building a path catches
// schema drift / a bad id early instead of firing a malformed request
// (defense-in-depth). Throws an ApiError(0) so the mutation/query error path is clean.
export function assertUuid(id: string): void {
  if (!UUID_RE.test(id)) throw new ApiError(0, 'invalid_id');
}
