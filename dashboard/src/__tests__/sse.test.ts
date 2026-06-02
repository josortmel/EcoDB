import { describe, it, expect } from 'vitest';
import { parseSseFrame, nextBoundary } from '../lib/sse';

// Requirement (BC2): the parser must handle LF, CRLF and CR line endings and
// must never leak a stray \r into the data.
describe('parseSseFrame', () => {
  it('parses event + data (LF)', () => {
    expect(parseSseFrame('event: memory_created\ndata: {"id":1}')).toEqual({
      event: 'memory_created',
      data: '{"id":1}',
    });
  });

  it('parses CRLF frames without trailing \\r in data', () => {
    const frame = 'event: search_completed\r\ndata: hello';
    expect(parseSseFrame(frame)).toEqual({ event: 'search_completed', data: 'hello' });
  });

  it('joins multi-line data', () => {
    expect(parseSseFrame('data: a\r\ndata: b')).toEqual({ event: 'message', data: 'a\nb' });
  });

  it('treats a comment-only frame as a heartbeat', () => {
    expect(parseSseFrame(':keepalive')).toEqual({ event: 'heartbeat', data: '' });
  });

  it('returns null for an empty frame', () => {
    expect(parseSseFrame('')).toBeNull();
  });
});

describe('nextBoundary', () => {
  it('finds an LF\\nLF boundary', () => {
    expect(nextBoundary('a\n\nb')).toEqual({ index: 1, length: 2 });
  });

  it('finds a CRLF boundary', () => {
    expect(nextBoundary('a\r\n\r\nb')).toEqual({ index: 1, length: 4 });
  });

  it('picks the earliest boundary', () => {
    // 'x\n\n' (LF\nLF at 1) comes before a later CRLF
    expect(nextBoundary('x\n\ny\r\n\r\n')).toEqual({ index: 1, length: 2 });
  });

  it('returns null when no complete boundary yet', () => {
    expect(nextBoundary('event: x\r')).toBeNull();
  });
});
