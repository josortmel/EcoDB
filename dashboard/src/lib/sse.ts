export interface SseFrame {
  event: string;
  data: string;
}

// SSE frames are separated by a blank line; line endings may be LF, CRLF or CR.
const SEPARATORS = ['\r\n\r\n', '\n\n', '\r\r'] as const;

// Earliest complete frame boundary in the buffer, or null if none yet. Looking
// for the FULL separator (not normalizing first) avoids a false boundary when a
// CRLF is split across two stream chunks.
export function nextBoundary(buf: string): { index: number; length: number } | null {
  let best = -1;
  let length = 0;
  for (const sep of SEPARATORS) {
    const i = buf.indexOf(sep);
    if (i !== -1 && (best === -1 || i < best)) {
      best = i;
      length = sep.length;
    }
  }
  return best === -1 ? null : { index: best, length };
}

export function parseSseFrame(frame: string): SseFrame | null {
  let event = 'message';
  const data: string[] = [];
  let sawComment = false;
  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (line === '') continue;
    if (line.startsWith(':')) {
      sawComment = true;
      continue;
    }
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  if (data.length) return { event, data: data.join('\n') };
  // A comment-only frame is a keepalive — surface it as a liveness heartbeat so
  // the renderer's stall watchdog knows the connection is alive.
  if (sawComment) return { event: 'heartbeat', data: '' };
  return null;
}
