import type { Config } from 'tailwindcss';

// All design tokens resolve to CSS custom properties defined in
// src/styles/tokens.css, which switch on [data-theme="light"|"dark"].
// Tailwind never hardcodes a theme color — it only references the vars,
// so every utility is theme-aware for free. Source of truth: design.md §2.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        accent: 'var(--accent)',
        'accent-2': 'var(--accent-2)',
        grn: 'var(--grn)',
        red: 'var(--red)',
        ink: {
          1: 'var(--ink-1)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
          4: 'var(--ink-4)',
        },
        bd: {
          1: 'var(--bd-1)',
          2: 'var(--bd-2)',
          3: 'var(--bd-3)',
        },
        chart: {
          line: 'var(--chart-line)',
          bar: 'var(--chart-bar)',
          grid: 'var(--chart-grid)',
        },
        node: {
          DEFAULT: 'var(--node)',
          hot: 'var(--node-hot)',
        },
        // §2.8 color-coded signal — entity kind (CmdK icons, Drawer kicker)
        kind: {
          memory: 'var(--kind-memory)',
          document: 'var(--kind-document)',
          node: 'var(--kind-node)',
          agent: 'var(--kind-agent)',
        },
        // §2.8 color-coded signal — memory type (MemoryRow type dot)
        type: {
          decision: 'var(--type-decision)',
          tecnico: 'var(--type-tecnico)',
          momento: 'var(--type-momento)',
          observacion: 'var(--type-observacion)',
          referencia: 'var(--type-referencia)',
        },
        // §2.9 per-section color — nav rail + active state
        sec: {
          command: 'var(--sec-command)',
          explorer: 'var(--sec-explorer)',
          graph: 'var(--sec-graph)',
          decisions: 'var(--sec-decisions)',
          ingestion: 'var(--sec-ingestion)',
          ontology: 'var(--sec-ontology)',
          settings: 'var(--sec-settings)',
          insights: 'var(--sec-insights)',
        },
      },
      fontFamily: {
        mono: ['DM Mono', 'ui-monospace', 'monospace'],
        body: ['Hanken Grotesk', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        xl: 'var(--r-xl)',
        lg: 'var(--r-lg)',
        md: 'var(--r-md)',
        sm: 'var(--r-sm)',
        btn: 'var(--r-btn)',
      },
      boxShadow: {
        elev: 'var(--elev)',
        'elev-hi': 'var(--elev-hi)',
      },
      backgroundImage: {
        'glass-card': 'var(--card-bg)',
        'glass-tray': 'var(--tray-bg)',
        screen: 'var(--screen-bg)',
        'btn-primary': 'var(--btn-primary)', // §3 terracota
      },
      spacing: {
        grid: '16px',
        card: '16px',
        'card-lg': '18px',
        tray: '22px',
      },
    },
  },
  plugins: [],
} satisfies Config;
