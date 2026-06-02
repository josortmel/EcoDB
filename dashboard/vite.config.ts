import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import electron from 'vite-plugin-electron/simple';

// Renderer targets Electron's bundled Chromium (Electron 33 ≈ Chromium 130),
// not a generic web target. Preload is forced to CommonJS because Spec §4
// requires sandbox:true, and sandboxed preloads cannot be ES modules.
export default defineConfig({
  base: './',
  plugins: [
    react(),
    electron({
      main: {
        entry: 'src/main.ts',
        vite: {
          build: {
            outDir: 'dist-electron',
            // electron-store stays external (CJS, resolved at runtime from
            // node_modules) — bundling its file/keytar deps is fragile.
            rollupOptions: { external: ['electron', 'electron-store'] },
          },
        },
      },
      preload: {
        input: 'src/preload.ts',
        vite: {
          build: {
            outDir: 'dist-electron',
            rollupOptions: {
              external: ['electron'],
              output: { format: 'cjs', entryFileNames: 'preload.js' },
            },
          },
        },
      },
      renderer: process.env.NODE_ENV === 'test' ? undefined : {},
    }),
  ],
  build: {
    outDir: 'dist',
    target: 'chrome130',
    // Emit every asset as a same-origin file. The prod CSP (Spec §4) has no
    // font-src, so fonts fall back to default-src 'self' — inlined `data:`
    // fonts would be refused. Keeping fonts as files keeps them under 'self'.
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
  },
});
