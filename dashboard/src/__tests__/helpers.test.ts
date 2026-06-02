import { describe, it, expect } from 'vitest';
import type { TFunction } from 'i18next';
import { assertUuid } from '../lib/assertUuid';
import { assertNodeId } from '../hooks/ontology';
import { sameTags } from '../lib/sameTags';
import { displayStatus } from '../lib/displayStatus';
import { ApiError } from '../lib/api';

describe('assertUuid', () => {
  it('passes a valid UUID', () => {
    expect(() => assertUuid('67e4297c-e654-4940-bb8a-df027a795039')).not.toThrow();
  });
  it('throws ApiError on a non-UUID', () => {
    expect(() => assertUuid('not-a-uuid')).toThrow(ApiError);
    expect(() => assertUuid('123')).toThrow();
    expect(() => assertUuid('')).toThrow();
    // a near-miss (wrong segment lengths) must still reject
    expect(() => assertUuid('67e4297c-e654-4940-bb8a-df027a79503')).toThrow();
  });
});

describe('assertNodeId', () => {
  it('passes a positive integer', () => {
    expect(() => assertNodeId(3)).not.toThrow();
    expect(() => assertNodeId(1)).not.toThrow();
  });
  it('throws on 0, negative, or non-integer', () => {
    expect(() => assertNodeId(0)).toThrow(ApiError);
    expect(() => assertNodeId(-1)).toThrow();
    expect(() => assertNodeId(1.5)).toThrow();
    expect(() => assertNodeId(Number.NaN)).toThrow();
  });
});

describe('sameTags', () => {
  it('is order-insensitive', () => {
    expect(sameTags(['a', 'b'], ['b', 'a'])).toBe(true);
    expect(sameTags([], [])).toBe(true);
    expect(sameTags(['x'], ['x'])).toBe(true);
  });
  it('detects real differences', () => {
    expect(sameTags(['a'], ['a', 'b'])).toBe(false);
    expect(sameTags(['a', 'b'], ['a', 'c'])).toBe(false);
    expect(sameTags(['a', 'b'], ['a'])).toBe(false);
  });
});

describe('displayStatus', () => {
  // Stub t: localizes the known key, otherwise returns the i18next defaultValue.
  const t = ((k: string, o?: { defaultValue?: string }) => (k === 'ing.statusValue.indexed' ? 'Indexed' : o?.defaultValue ?? k)) as unknown as TFunction;

  it('localizes a known status code', () => {
    expect(displayStatus('indexed', t)).toBe('Indexed');
  });
  it('falls back to the raw value for an unknown code', () => {
    expect(displayStatus('weird_new_state', t)).toBe('weird_new_state');
  });
});
