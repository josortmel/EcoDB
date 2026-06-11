import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '../GlassCard';

export function ModalShell({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const { t } = useTranslation();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center p-6" style={{ background: 'rgba(8,10,14,0.52)' }} onClick={onClose}>
      <GlassCard className="w-full max-w-lg p-0">
        <div onClick={(e) => e.stopPropagation()} className="flex max-h-[85vh] flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-[var(--card-hairline)] px-5 py-3.5">
            <h2 className="font-mono text-[14px] text-ink-1">{title}</h2>
            <button type="button" onClick={onClose} aria-label={t('ma.configs.common.close')} className="grid h-[28px] w-[28px] place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={14} height={14}>
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="border-t border-[var(--card-hairline)] px-5 py-3.5">{footer}</div>}
        </div>
      </GlassCard>
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="mb-2 mt-5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{children}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{label}</span>
      {children}
    </label>
  );
}

const fieldStyle = (focused: boolean) => ({
  background: 'var(--field-bg)',
  boxShadow: focused ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)' : 'inset 0 0 0 1px var(--card-hairline)',
});

export function TextInput({ value, onChange, placeholder, type = 'text', maxLength }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string; maxLength?: number }) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={placeholder}
      maxLength={maxLength}
      className="w-full rounded-[7px] px-2.5 py-2 font-body text-[12.5px] text-ink-1 outline-none placeholder:text-ink-4"
      style={fieldStyle(focused)}
    />
  );
}

export function SelectInput({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: ReactNode }) {
  const [focused, setFocused] = useState(false);
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      className="w-full rounded-[7px] px-2.5 py-2 font-mono text-[12px] text-ink-1 outline-none"
      style={fieldStyle(focused)}
    >
      {children}
    </select>
  );
}

// Primary (terracotta) action button for modal footers.
export function PrimaryButton({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="rounded-btn bg-btn-primary px-4 py-2 font-body text-[12.5px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-40" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3), inset 0 0 0 1px rgba(150,62,32,0.45)' }}>
      {children}
    </button>
  );
}
