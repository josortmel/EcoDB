import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from '../locales/en.json';

// English is the only bundled language for now. Spanish is a confirmed future
// requirement — when it lands, add `es.json` with the same shape and register
// it under `resources.es.translation`; nothing else changes (drop-in).
//
// Keys are organized by screen. Data enums (memory types decision/tecnico/…,
// agent names) are NOT translated — they are DB values and never go through t().
export const resources = { en: { translation: en } } as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: 'en',
  fallbackLng: 'en',
  defaultNS: 'translation',
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
  react: { useSuspense: false }, // resources are inline → ready synchronously
});

// Keep <html lang> in sync with the active language (matters once es lands).
i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng;
});

export default i18n;
