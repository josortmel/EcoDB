import { useTranslation } from 'react-i18next';
import { useSystemStats, useSearchStats } from '../hooks/stats';

// Embedding-service health + p95 latency (real /stats/system shape).
//   ok && model_loaded → green "Online"
//   status present but not ready → amber "Degraded"
//   error / unreachable        → red "Offline"
//   no response yet            → neutral, no label
// Latency is shown only when /stats/search actually reports a p95.
export function StatusPill() {
  const { t } = useTranslation();
  const system = useSystemStats();
  const search = useSearchStats();

  const emb = system.data?.embeddings;
  const healthy = emb?.status === 'ok' && emb.model_loaded === true;

  // Glow is reserved for signal states (green/red); neutral and amber dots carry
  // none (convention: no-signal dots = ink-4, no glow).
  let dotColor: string;
  let label: string;
  let glow: boolean;
  if (system.isError) {
    dotColor = 'var(--red)';
    label = t('appbar.offline');
    glow = true;
  } else if (!emb) {
    dotColor = 'var(--ink-4)'; // awaiting first response — no signal
    label = '—';
    glow = false;
  } else if (healthy) {
    dotColor = 'var(--grn)';
    label = t('appbar.online');
    glow = true;
  } else {
    dotColor = 'var(--kind-agent)'; // amber: present but not ready (orange reserved for signal, §1.3)
    label = t('appbar.degraded');
    glow = false;
  }

  const latency = search.data?.p95_latency_ms;
  const showLatency = latency != null && latency > 0;

  return (
    <div
      className="inline-flex items-center gap-[9px] rounded-[20px] px-3 py-1.5 font-mono text-[11px] text-ink-2"
      style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
    >
      <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: dotColor, boxShadow: glow ? `0 0 6px ${dotColor}` : undefined }} />
      <span>{label}</span>
      {showLatency && (
        <>
          <span className="text-ink-4">·</span>
          <span className="text-ink-3">{t('appbar.latency', { ms: Math.round(latency) })}</span>
        </>
      )}
    </div>
  );
}
