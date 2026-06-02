import 'i18next';
import type en from '../locales/en.json';

// Makes t() key-safe: t('scaffold.body') autocompletes and a typo is a compile
// error. Mirrors the shape of en.json (the source of truth for keys).
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof en };
  }
}
