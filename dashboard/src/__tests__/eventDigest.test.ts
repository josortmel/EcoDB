import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createEventDigest } from '../lib/eventDigest';

describe('createEventDigest', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('immediate: contradiction_detected invalidates synchronously', () => {
    const invalidate = vi.fn();
    createEventDigest(invalidate).push('contradiction_detected');
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith(['inbox', 'summary']);
  });

  it('batch: a burst of memory_created → one flush after 10s, keys deduped', () => {
    const invalidate = vi.fn();
    const d = createEventDigest(invalidate);
    for (let i = 0; i < 5; i++) d.push('memory_created');
    expect(invalidate).not.toHaveBeenCalled();
    vi.advanceTimersByTime(9_999);
    expect(invalidate).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    // 3 unique keys for memory_created — not 5×3
    expect(invalidate).toHaveBeenCalledTimes(3);
    expect(invalidate.mock.calls.map((c) => c[0])).toEqual(
      expect.arrayContaining([
        ['stats', 'memories'],
        ['memories', 'recent'],
        ['stats', 'timeline'],
      ]),
    );
  });

  it('debounce: rapid search_completed → one flush 3s after the last', () => {
    const invalidate = vi.fn();
    const d = createEventDigest(invalidate);
    d.push('search_completed');
    vi.advanceTimersByTime(2_000);
    d.push('search_completed'); // resets the 3s window
    vi.advanceTimersByTime(2_999);
    expect(invalidate).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith(['stats', 'search']);
  });

  it('reset() drops pending without flushing', () => {
    const invalidate = vi.fn();
    const d = createEventDigest(invalidate);
    d.push('memory_created');
    d.reset();
    vi.advanceTimersByTime(20_000);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('reset() then reuse: only the post-reset push flushes', () => {
    const invalidate = vi.fn();
    const d = createEventDigest(invalidate);
    d.push('memory_created'); // discarded
    d.reset();
    d.push('document_failed'); // 3 keys → ['inbox','summary'] + ['documents'] + ['document']
    vi.advanceTimersByTime(10_000);
    expect(invalidate).toHaveBeenCalledTimes(3);
    expect(invalidate).toHaveBeenCalledWith(['inbox', 'summary']);
    expect(invalidate).toHaveBeenCalledWith(['documents']);
    expect(invalidate).toHaveBeenCalledWith(['document']);
  });

  it('a new batch event after a flush opens a fresh window', () => {
    const invalidate = vi.fn();
    const d = createEventDigest(invalidate);
    d.push('memory_created');
    vi.advanceTimersByTime(10_000);
    expect(invalidate).toHaveBeenCalledTimes(3);
    d.push('document_failed'); // 3 keys → ['inbox','summary'] + ['documents'] + ['document']
    vi.advanceTimersByTime(10_000);
    expect(invalidate).toHaveBeenCalledTimes(6);
  });
});
