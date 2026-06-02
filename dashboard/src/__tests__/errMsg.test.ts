import { describe, it, expect } from 'vitest';
import type { TFunction } from 'i18next';
import { errMsg } from '../lib/errMsg';
import { ApiError } from '../lib/api';

// Stub t: echoes the key, appending {{secs}} so the param path is observable.
const t = ((k: string, o?: Record<string, unknown>) => (o && 'secs' in o ? `${k}:${o.secs}` : k)) as unknown as TFunction;

describe('errMsg', () => {
  it('429 with Retry-After → rateLimitedWait carrying secs', () => {
    expect(errMsg(new ApiError(429, 'rate_limited', 7), t, 'fb')).toBe('errors.rateLimitedWait:7');
  });

  it('429 without Retry-After → rateLimited', () => {
    expect(errMsg(new ApiError(429, 'rate_limited'), t, 'fb')).toBe('errors.rateLimited');
  });

  it('403 → forbidden', () => {
    expect(errMsg(new ApiError(403, 'forbidden'), t, 'fb')).toBe('errors.forbidden');
  });

  it('422 array detail → joined "field: msg"', () => {
    const e = new ApiError(422, 'http_422', undefined, { detail: [{ loc: ['body', 'type'], msg: 'bad type' }] });
    expect(errMsg(e, t, 'fb')).toBe('type: bad type');
  });

  it('422 empty detail array → fallback', () => {
    const e = new ApiError(422, 'http_422', undefined, { detail: [] });
    expect(errMsg(e, t, 'fb')).toBe('fb');
  });

  it('422 multi-field detail → "field: msg; field: msg"', () => {
    const e = new ApiError(422, 'http_422', undefined, {
      detail: [
        { loc: ['body', 'type'], msg: 'bad type' },
        { loc: ['body', 'content'], msg: 'too short' },
      ],
    });
    expect(errMsg(e, t, 'fb')).toBe('type: bad type; content: too short');
  });

  it('422 string detail → fallback, never echoed (info-disclosure guard)', () => {
    const e = new ApiError(422, 'http_422', undefined, { detail: 'internal hint memories_v2' });
    expect(errMsg(e, t, 'fb')).toBe('fb');
  });

  it('404 string detail → fallback, never echoed', () => {
    const e = new ApiError(404, 'http_404', undefined, { detail: 'Memory not found in table memories_v2' });
    expect(errMsg(e, t, 'fb')).toBe('fb');
  });

  it('non-ApiError → fallback', () => {
    expect(errMsg(new Error('boom'), t, 'fb')).toBe('fb');
  });
});
