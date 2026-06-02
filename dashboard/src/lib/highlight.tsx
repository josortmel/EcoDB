import type { ReactNode } from 'react';

// Wraps case-insensitive matches of `query` in <mark> (accent highlight).
export function highlight(text: string, query: string): ReactNode {
  const q = query.trim();
  if (!q) return text;
  const lower = text.toLowerCase();
  const ql = q.toLowerCase();
  const parts: ReactNode[] = [];
  let i = 0;
  let key = 0;
  let idx = lower.indexOf(ql, i);
  while (idx !== -1) {
    if (idx > i) parts.push(text.slice(i, idx));
    parts.push(<mark key={key++}>{text.slice(idx, idx + ql.length)}</mark>);
    i = idx + ql.length;
    idx = lower.indexOf(ql, i);
  }
  if (i < text.length) parts.push(text.slice(i));
  return parts;
}
