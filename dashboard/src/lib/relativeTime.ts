// Short, language-neutral magnitude ("5s" / "5m" / "2h" / "3d") for "… ago"
// strings. The surrounding phrasing is localized via i18n; only the number+unit
// is produced here.
export function relativeAge(fromMs: number, nowMs: number = Date.now()): string {
  const s = Math.max(0, Math.round((nowMs - fromMs) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}
