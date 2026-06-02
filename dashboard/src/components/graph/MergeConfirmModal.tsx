import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../GlassCard';
import type { GNode } from './graphTypes';

export interface MergeConfirmModalProps {
  source: GNode;
  target: GNode;
  pending: boolean;
  onConfirm: (keepAlias: boolean) => void;
  onCancel: () => void;
}

// merge-from-here confirm (2-step, destructive).
export function MergeConfirmModal({ source, target, pending, onConfirm, onCancel }: MergeConfirmModalProps) {
  const { t } = useTranslation();
  const [keepAlias, setKeepAlias] = useState(false);
  return (
    <div className="absolute inset-0 z-40 grid place-items-center" style={{ background: 'rgba(10,8,6,0.45)' }}>
      <GlassCard className="flex w-[320px] max-w-[92%] flex-col gap-3 p-5">
        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-2">{t('gph.ctx.merge')}</div>
        <div className="text-[12.5px] leading-relaxed text-ink-1">{t('gph.merge.prompt', { source: source.name, target: target.name })}</div>
        <label className="flex cursor-pointer items-start gap-2 font-mono text-[11px] leading-relaxed text-ink-2">
          <input
            type="checkbox"
            checked={keepAlias}
            onChange={(e) => setKeepAlias(e.target.checked)}
            data-testid="gph-merge-keepalias"
            className="mt-0.5 flex-none"
            style={{ accentColor: 'var(--sec-graph)' }}
          />
          <span>{t('gph.merge.keepAlias', { source: source.name, target: target.name })}</span>
        </label>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => onConfirm(keepAlias)}
            disabled={pending}
            data-testid="gph-merge-confirm"
            className="flex-1 rounded-btn bg-btn-primary py-2.5 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
            style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)' }}
          >
            {pending ? t('gph.merge.merging') : t('gph.merge.confirm')}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-btn px-4 py-2.5 font-body text-[12.5px] font-semibold text-ink-1 transition-colors hover:bg-[var(--inset)] disabled:opacity-50"
            style={{ background: 'var(--field-bg)', boxShadow: 'inset 0 1px 0 var(--card-edge), inset 0 0 0 1px var(--card-hairline)' }}
          >
            {t('gph.merge.cancel')}
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
