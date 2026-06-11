import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DismissForm, DismissTrigger } from './DismissForm';
import { MA_ACCENT, day } from './utils';
import type { TensionItem } from '../../hooks/useMemoryAgent';

export function TensionCard({ item, onDismiss }: { item: TensionItem; onDismiss: (id: string, reason: string) => void }) {
  const { t } = useTranslation();
  const [dismissing, setDismissing] = useState(false);
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-center justify-between gap-2">
        <span
          className="rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.06em]"
          style={{
            color: MA_ACCENT,
            background: 'color-mix(in srgb, var(--sec-memory-agent) 12%, transparent)',
            boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-memory-agent) 30%, transparent)',
          }}
        >
          {item.tension_type}
        </span>
        <span className="font-mono text-[9.5px] text-ink-3">{day(item.created_at)}</span>
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2">
        <div className="rounded-[7px] p-2.5" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.briefing.observed')}</div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink-1">{item.observed_trait}</div>
        </div>
        <div className="rounded-[7px] p-2.5" style={{ background: 'var(--card-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.briefing.declared')}</div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink-1">{item.declared_trait}</div>
        </div>
      </div>
      {dismissing ? (
        <DismissForm
          onCancel={() => setDismissing(false)}
          onConfirm={(r) => {
            onDismiss(item.id, r);
            setDismissing(false);
          }}
        />
      ) : (
        <DismissTrigger onClick={() => setDismissing(true)} />
      )}
    </div>
  );
}
