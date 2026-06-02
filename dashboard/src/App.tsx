import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useThemeStore } from './stores/theme';
import { useAuthStore } from './stores/auth';
import { ThemeToggle } from './components/ThemeToggle';
import { BrandMark } from './components/BrandMark';
import { AuthScreen } from './pages/AuthScreen';
import { FirstRunScreen } from './pages/FirstRunScreen';
import { AppShell } from './components/AppShell';
import { useSSE } from './hooks/useSSE';
import { DegradedBanner } from './components/DegradedBanner';

// Shown while the boot auth check runs, so the auth screen never flashes before
// we know whether a stored key is still valid.
function Splash() {
  const { t } = useTranslation();
  return (
    <main className="grid min-h-screen w-full place-items-center">
      <div className="flex flex-col items-center gap-4 text-ink-1">
        <span className="motion-safe:animate-pulse">
          <BrandMark size={30} />
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">{t('splash.loading')}</span>
      </div>
    </main>
  );
}

// Authenticated app shell. The SSE subscription lives here (shell level) so it
// runs across all future screens, not per-screen.
function Authed() {
  useSSE(); // call once — mounted here at shell level; no singleton guard, so a second mount = a second SSE connection
  return (
    <>
      <DegradedBanner />
      <AppShell />
    </>
  );
}

export function App() {
  const theme = useThemeStore((s) => s.theme);
  const status = useAuthStore((s) => s.status);
  const checkAuth = useAuthStore((s) => s.checkAuth);

  // The store is the source of truth for the theme; mirror it to the DOM.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Boot: validate any stored key once.
  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  return (
    <>
      {status !== 'authenticated' && (
        <div className="fixed right-4 top-4 z-50">
          <ThemeToggle />
        </div>
      )}
      {status === 'checking' ? (
        <Splash />
      ) : status === 'unreachable' ? (
        <FirstRunScreen />
      ) : status === 'unauthenticated' ? (
        <AuthScreen />
      ) : (
        <Authed />
      )}
    </>
  );
}
