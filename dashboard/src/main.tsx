import React from 'react';
import ReactDOM from 'react-dom/client';

// Self-hosted fonts (no external CDN) — keeps a strict `default-src 'self'`
// CSP intact and satisfies design.md §6 (DM Mono / Hanken Grotesk are both
// SIL OFL 1.1, so bundling is license-clean). FB2 applies the CSP header.
import '@fontsource/dm-mono/400.css';
import '@fontsource/dm-mono/500.css';
import '@fontsource/hanken-grotesk/400.css';
import '@fontsource/hanken-grotesk/500.css';
import '@fontsource/hanken-grotesk/600.css';

import { I18nextProvider } from 'react-i18next';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import i18n from './lib/i18n';
import { queryClient } from './lib/queryClient';
import { persister, CACHE_MAX_AGE, CACHE_BUSTER, shouldPersist } from './lib/persist';
import { useAuthStore } from './stores/auth';
import { usePaletteStore } from './stores/palette';
import { useComposeStore } from './stores/compose';
import { useIngestionStore } from './stores/ingestion';
import { useActivityStore } from './stores/activity';
import { useDetailStore } from './stores/detail';
import { useViewStore } from './stores/view';

import './styles/tokens.css';
import './index.css';
import { App } from './App';

// Cross-session bleed guard: whenever the session ends (sign out, 401, expired
// key on boot), wipe the in-memory cache AND the persisted localStorage blob, so
// a shared machine / credential rotation never shows the previous user's data.
useAuthStore.subscribe((state, prev) => {
  if (state.status === 'unauthenticated' && prev.status !== 'unauthenticated') {
    queryClient.clear();
    void persister.removeClient();
    usePaletteStore.getState().closePalette(); // don't let the palette survive a session swap
    useComposeStore.getState().closeCompose();
    // Reset the Zustand session stores too — otherwise the next user inherits the
    // previous user's live feed / ingestion queue / open detail (BC1).
    useIngestionStore.setState({ items: [], counts: { indexed: 0, failed: 0, duplicate: 0 } });
    useActivityStore.setState({ items: [] });
    useDetailStore.getState().close();
    useViewStore.setState({ drawer: null, explorerSeed: null }); // don't carry A's open drawer / ⌘K seed into B (VS-BC2a)
  }
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nextProvider i18n={i18n}>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={{
          persister,
          maxAge: CACHE_MAX_AGE,
          buster: CACHE_BUSTER,
          dehydrateOptions: { shouldDehydrateQuery: shouldPersist },
        }}
      >
        <App />
      </PersistQueryClientProvider>
    </I18nextProvider>
  </React.StrictMode>,
);
