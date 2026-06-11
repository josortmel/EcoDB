import { useState } from 'react';
import { useTranslation } from 'react-i18next';

// Reason capture shared by foresight + tension dismissal. The backend requires a
// non-empty reason (DismissBody min_length=1), so Confirm stays disabled until
// the field has content. maxLength caps the payload (adv-seg VS4). The form
// unmounts on confirm (parent flips local state immediately), so there's no
// in-flight double-submit to guard — hence no global-pending gate (that would
// silently disable sibling forms, adv-code BC2).
export function DismissForm({ onConfirm, onCancel }: { onConfirm: (reason: string) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [reason, setReason] = useState('');
  const [focused, setFocused] = useState(false);
  const canConfirm = reason.trim().length > 0;
  return (
    <div className="mt-2.5 flex flex-col gap-2">
      <label className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{t('ma.briefing.dismissReason')}</label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={t('ma.briefing.dismissReasonPlaceholder')}
        rows={2}
        maxLength={500}
        className="resize-none rounded-[7px] px-2.5 py-1.5 font-body text-[12px] text-ink-1 outline-none placeholder:text-ink-4"
        style={{
          background: 'var(--inset)',
          boxShadow: focused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : 'inset 0 0 0 1px var(--card-hairline)',
        }}
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!canConfirm}
          onClick={() => onConfirm(reason.trim())}
          className="rounded-btn px-3 py-1.5 font-body text-[12px] font-semibold text-red transition-[filter] hover:brightness-105 disabled:opacity-40"
          style={{ background: 'rgba(222,70,48,0.12)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.38)' }}
        >
          {t('ma.briefing.confirm')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-btn px-3 py-1.5 font-body text-[12px] text-ink-2 transition-colors hover:text-ink-1"
          style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}
        >
          {t('ma.briefing.cancel')}
        </button>
      </div>
    </div>
  );
}

export function DismissTrigger({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" onClick={onClick} className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3 transition-colors hover:text-red">
      {t('ma.briefing.dismiss')}
    </button>
  );
}
