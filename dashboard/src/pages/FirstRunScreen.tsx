import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores/auth';
import { BrandMark } from '../components/BrandMark';
import { GlassCard } from '../components/GlassCard';

// Shown when the API can't be reached (transport failure / ECONNREFUSED) — a
// server-down problem, distinct from a 401 (key problem → AuthScreen).
const CHECKS = ['firstRun.checkDocker', 'firstRun.checkPort', 'firstRun.checkKey'] as const;

export function FirstRunScreen() {
  const { t } = useTranslation();
  const retry = useAuthStore((s) => s.retry);
  const status = useAuthStore((s) => s.status);

  return (
    <main className="grid min-h-screen w-full place-items-center p-8">
      <div className="flex w-full max-w-[400px] flex-col items-center">
        <div className="mb-6 flex items-center gap-2.5 text-ink-1">
          <BrandMark size={22} />
          <span className="font-mono text-[19px] text-ink-1">
            Eco<b className="font-medium">DB</b>
          </span>
        </div>

        <GlassCard className="w-full p-6">
          <div className="flex items-center gap-2.5">
            <span
              className="h-[8px] w-[8px] flex-none rounded-full"
              style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }}
            />
            <h1 className="text-[18px] font-semibold text-ink-1">{t('firstRun.title')}</h1>
          </div>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{t('firstRun.subtitle')}</p>

          <ul className="mt-4 flex flex-col gap-3">
            {CHECKS.map((k) => (
              <li key={k} className="flex items-center gap-2.5 text-[13px] text-ink-1">
                <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: 'var(--ink-3)' }} />
                {t(k)}
              </li>
            ))}
          </ul>

          <button
            type="button"
            onClick={() => void retry()}
            disabled={status === 'checking'}
            data-testid="retry-button"
            className="mt-5 w-full rounded-btn bg-btn-primary py-3 font-body text-[13px] font-semibold text-white transition-[filter] hover:brightness-105 disabled:opacity-60"
            style={{
              boxShadow:
                'inset 0 1px 0 rgba(255,255,255,0.30), inset 0 0 0 1px rgba(150,62,32,0.45), 0 5px 14px -5px rgba(180,82,48,0.45)',
            }}
          >
            {t('firstRun.retry')}
          </button>
        </GlassCard>
      </div>
    </main>
  );
}
