import { defineConfig } from 'vitest/config';

// Kept separate from vite.config.ts on purpose: the unit tests are pure Node
// (read token files, import the tailwind config) and must not pull in the
// Electron plugin. Also avoids the vitest-bundled-vite vs hoisted-vite type
// clash that occurs when both live in one config.
export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
  },
});
