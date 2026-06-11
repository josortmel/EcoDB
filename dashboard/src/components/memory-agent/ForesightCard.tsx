import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DismissForm, DismissTrigger } from './DismissForm';
import { day } from './utils';
import type { ForesightItem } from '../../hooks/useMemoryAgent';

// Above this score a foresight is "imminent" → it earns the orange signal
// (--accent = live/active/critical only). Below, it stays ink.
const HIGH_URGENCY = 0.66;

export function ForesightCard({ item, onDismiss }: { item: ForesightItem; onDismiss: (id: string, reason: string) => void }) {
  const { t } = useTranslation();
  const [dismissing, setDismissing] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const high = item.urgency_score >= HIGH_URGENCY;
  const dot = high ? 'var(--accent)' : 'var(--ink-4)';
  return (
    <div className="rounded-md p-3" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="flex items-start gap-2.5">
        <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full" style={{ background: dot, boxShadow: high ? `0 0 6px ${dot}` : undefined }} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-snug text-ink-1">{item.content}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] text-ink-3">
            <span>{t('ma.briefing.window', { start: day(item.foresight_start), end: day(item.foresight_end) })}</span>
            <span>·</span>
            <span className={high ? 'text-ink-2' : undefined}>
              {high ? t('ma.briefing.urgencyHigh') : t('ma.briefing.urgencyNormal', { score: item.urgency_score.toFixed(2) })}
            </span>
          </div>
          {item.evidence && (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setEvidenceOpen((o) => !o)}
                className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-ink-1"
              >
                {t('ma.briefing.evidence')} · {evidenceOpen ? t('ma.briefing.collapse') : t('ma.briefing.expand')}
              </button>
              {evidenceOpen && <p className="mt-1 text-[12px] leading-relaxed text-ink-2">{item.evidence}</p>}
            </div>
          )}
          {dismissing ? (
            <DismissForm
              onCancel={() => setDismissing(false)}
              onConfirm={(r) => {
                onDismiss(item.memory_id, r);
                setDismissing(false);
              }}
            />
          ) : (
            <DismissTrigger onClick={() => setDismissing(true)} />
          )}
        </div>
      </div>
    </div>
  );
}
