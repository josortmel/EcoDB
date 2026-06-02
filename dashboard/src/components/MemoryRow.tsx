import { useTranslation } from 'react-i18next';
import { highlight } from '../lib/highlight';
import { useDetailStore, type MemoryDetail } from '../stores/detail';

// §2.8 memory-type dot colors.
const TYPE_COLOR: Record<string, string> = {
  decision: 'var(--type-decision)',
  tecnico: 'var(--type-tecnico)',
  momento: 'var(--type-momento)',
  observacion: 'var(--type-observacion)',
  referencia: 'var(--type-referencia)',
};

export function MemoryRow({ m, query }: { m: MemoryDetail; query: string }) {
  const { t } = useTranslation();
  const open = useDetailStore((s) => s.open);
  const color = TYPE_COLOR[m.type] ?? 'var(--type-referencia)';
  return (
    <button
      type="button"
      data-testid="memory-row"
      onClick={() => open(m)}
      className="grid w-full grid-cols-[16px_1fr_auto] items-start gap-3.5 border-b border-[var(--card-hairline)] px-3 py-3 text-left transition-colors last:border-0 hover:bg-[var(--inset)]"
      style={m.hot ? { boxShadow: 'inset 2px 0 0 var(--accent)', background: 'rgba(245,99,30,0.05)' } : undefined}
    >
      <span
        className="mt-1 grid h-[14px] w-[14px] place-items-center rounded-full"
        style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
      >
        <span className="h-[6px] w-[6px] rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      </span>
      <span className="min-w-0">
        <span className="line-clamp-2 block text-[13px] leading-snug text-ink-1">{highlight(m.content, query)}</span>
        <span className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[10.5px] text-ink-3">
          <span>{m.ts}</span>
          <span>·</span>
          <span>{m.agent ?? '—'}</span>
          <span>·</span>
          <span>{m.type}</span>
          {m.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="rounded-sm px-1.5 py-0.5 text-[9.5px] text-ink-2"
              style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
            >
              {tag}
            </span>
          ))}
        </span>
      </span>
      {m.stale && (
        <span
          className="mt-0.5 flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px]"
          style={{
            color: 'var(--kind-agent)',
            background: 'color-mix(in srgb, var(--kind-agent) 10%, transparent)',
            boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-agent) 30%, transparent)',
          }}
        >
          {t('exp.staleBadge')}
        </span>
      )}
    </button>
  );
}
