import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore, type AuthError } from '../stores/auth';
import { BrandMark } from '../components/BrandMark';
import { GlassCard } from '../components/GlassCard';

const ERROR_KEYS: Record<AuthError, 'auth.invalid' | 'auth.noSecureStorage' | 'auth.network'> = {
  invalid: 'auth.invalid',
  noSecureStorage: 'auth.noSecureStorage',
  network: 'auth.network',
};

// First-run / re-auth. Not in the prototype (it runs on mock) — built in-language
// per design.md: glass card on the backdrop, accent focus ring on the field,
// terracotta primary CTA (orange is reserved for signal, §3).
export function AuthScreen() {
  const { t } = useTranslation();
  const connect = useAuthStore((s) => s.connect);
  const submitting = useAuthStore((s) => s.submitting);
  const error = useAuthStore((s) => s.error);

  const [key, setKey] = useState('');
  const [show, setShow] = useState(false);
  const [focused, setFocused] = useState(false);

  const canSubmit = key.trim().length > 0 && !submitting;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (canSubmit) void connect(key);
  };

  return (
    <main className="grid min-h-screen w-full place-items-center p-8">
      <div className="flex w-full max-w-[380px] flex-col items-center">
        <div className="mb-6 flex items-center gap-2.5 text-ink-1">
          <BrandMark size={22} />
          <span className="font-mono text-[19px] text-ink-1">
            Eco<b className="font-medium">DB</b>
          </span>
        </div>

        <GlassCard className="w-full p-6">
          <form onSubmit={onSubmit}>
            <h1 className="text-[18px] font-semibold text-ink-1">{t('auth.title')}</h1>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{t('auth.subtitle')}</p>

            <div
              className="mt-5 flex items-center gap-2 rounded-md px-3"
              style={{
                height: '46px',
                background: 'var(--field-bg)',
                boxShadow: focused
                  ? 'inset 0 0 0 1px var(--accent), 0 0 0 3px rgba(245,99,30,0.16)'
                  : 'inset 0 1px 3px var(--inset), inset 0 0 0 1px var(--card-hairline)',
              }}
            >
              <input
                type={show ? 'text' : 'password'}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                placeholder={t('auth.placeholder')}
                aria-label={t('auth.inputLabel')}
                autoFocus
                autoComplete="off"
                spellCheck={false}
                data-testid="api-key-input"
                className="min-w-0 flex-1 border-none bg-transparent font-mono text-[13px] text-ink-1 outline-none placeholder:text-ink-3"
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                aria-label={show ? t('auth.hideKey') : t('auth.showKey')}
                className="flex-none font-mono text-[10.5px] text-ink-3 transition-colors hover:text-ink-1"
              >
                {show ? t('auth.hide') : t('auth.show')}
              </button>
            </div>

            {error && (
              <div
                role="alert"
                data-testid="auth-error"
                className="mt-3 flex items-start gap-2 rounded-md px-3 py-2.5"
                style={{ background: 'rgba(222,70,48,0.08)', boxShadow: 'inset 0 0 0 1px rgba(222,70,48,0.25)' }}
              >
                <span
                  className="mt-[3px] h-[7px] w-[7px] flex-none rounded-full"
                  style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }}
                />
                <span className="text-[12px] leading-relaxed text-ink-1">{t(ERROR_KEYS[error])}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              data-testid="connect-button"
              className="mt-5 w-full rounded-btn bg-btn-primary py-3 font-body text-[13px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-50"
              style={{
                boxShadow:
                  'inset 0 1px 0 rgba(255,255,255,0.30), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)',
              }}
            >
              {submitting ? (
                <span className="inline-flex items-center gap-2">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/90 border-t-transparent" />
                  {t('auth.connecting')}
                </span>
              ) : (
                t('auth.connect')
              )}
            </button>
          </form>
        </GlassCard>
      </div>
    </main>
  );
}
