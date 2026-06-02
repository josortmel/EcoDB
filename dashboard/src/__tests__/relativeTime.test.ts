import { describe, it, expect } from 'vitest';
import { relativeAge } from '../lib/relativeTime';

const NOW = 1_700_000_000_000;

describe('relativeAge', () => {
  it('seconds', () => expect(relativeAge(NOW - 5_000, NOW)).toBe('5s'));
  it('minutes', () => expect(relativeAge(NOW - 5 * 60_000, NOW)).toBe('5m'));
  it('hours', () => expect(relativeAge(NOW - 3 * 3_600_000, NOW)).toBe('3h'));
  it('days', () => expect(relativeAge(NOW - 2 * 86_400_000, NOW)).toBe('2d'));
  it('clamps a future timestamp to 0s', () => expect(relativeAge(NOW + 5_000, NOW)).toBe('0s'));

  // Unit boundaries — the exact tick where the unit rolls over.
  it('60s rolls to 1m', () => expect(relativeAge(NOW - 60_000, NOW)).toBe('1m'));
  it('3600s rolls to 1h', () => expect(relativeAge(NOW - 3_600_000, NOW)).toBe('1h'));
  it('86400s rolls to 1d', () => expect(relativeAge(NOW - 86_400_000, NOW)).toBe('1d'));
  it('59s stays in seconds', () => expect(relativeAge(NOW - 59_000, NOW)).toBe('59s'));
  it('epoch-now is 0s', () => expect(relativeAge(0, 0)).toBe('0s'));
  it('epoch to NOW is a large day count', () => expect(relativeAge(0, NOW)).toBe(`${Math.floor(NOW / 86_400_000)}d`));
});
