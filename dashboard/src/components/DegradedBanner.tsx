import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useHealth } from '../hooks/useHealth';
import { relativeAge } from '../lib/relativeTime';

// Floating amber pill shown while the API is unreachable but we have cached data
// (FB10). The UI is NOT blocked — the user keeps the last data plus this notice.
// Amber (not red): degraded ≠ broken.
export function DegradedBanner() {
  const { t } = useTranslation();
  const { isError, dataUpdatedAt } = useHealth();
  const [, tick] = useState(0);

  // Keep the "X ago" fresh while degraded.
  useEffect(() => {
    if (!isError) return;
    const id = setInterval(() => tick((n) => n + 1), 15_000);
    return () => clearInterval(id);
  }, [isError]);

  if (!isError) return null;

  const message =
    dataUpdatedAt > 0 ? t('degraded.cachedAge', { age: relativeAge(dataUpdatedAt) }) : t('degraded.offline');

  return (
    <div
      role="status"
      data-testid="degraded-banner"
      className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center px-4 pt-3"
    >
      <div
        className="flex items-center gap-2.5 rounded-full px-4 py-2"
        style={{
          background: 'color-mix(in srgb, var(--kind-agent) 14%, transparent)',
          boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-agent) 40%, transparent)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}
      >
        <span
          className="h-[7px] w-[7px] flex-none rounded-full"
          style={{ background: 'var(--kind-agent)', boxShadow: '0 0 6px color-mix(in srgb, var(--kind-agent) 60%, transparent)' }}
        />
        <span className="font-mono text-[11px] text-ink-1">{message}</span>
      </div>
    </div>
  );
}
