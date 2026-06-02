import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import tailwindConfig from '../../tailwind.config';

// Verifies the FB1 requirement — the token port — not the implementation:
// Tailwind must reference CSS vars (never hardcode a theme color), and
// tokens.css must carry the exact design.md §2 values incl. §2.8 signal.
describe('design token port (design.md §2)', () => {
  const colors = (tailwindConfig.theme?.extend?.colors ?? {}) as Record<string, unknown>;
  const tokensCss = readFileSync(resolve(__dirname, '../styles/tokens.css'), 'utf8');

  it('tailwind maps brand colors to CSS vars, never raw hex', () => {
    expect(colors.accent).toBe('var(--accent)');
    expect(colors['accent-2']).toBe('var(--accent-2)');
    expect(colors.grn).toBe('var(--grn)');
    expect(colors.red).toBe('var(--red)');
  });

  it('tokens.css defines the surgical orange exactly as #F5631E', () => {
    expect(tokensCss).toMatch(/--accent:\s*#f5631e/i);
  });

  it('tokens.css carries the §2.8 color-coded signal palette', () => {
    expect(tokensCss).toContain('--kind-document: #6e9ecf');
    expect(tokensCss).toContain('--kind-agent: #c4a86a');
    expect(tokensCss).toContain('--type-observacion: #c4a86a');
  });

  it('both themes resolve the ink ramp', () => {
    expect(tokensCss).toContain("[data-theme='light']");
    expect(tokensCss).toContain("[data-theme='dark']");
    expect(tokensCss).toMatch(/--ink-1:\s*#1f1d1a/i); // light primary ink
    expect(tokensCss).toMatch(/--ink-1:\s*#eef1f7/i); // dark primary ink
  });
});
