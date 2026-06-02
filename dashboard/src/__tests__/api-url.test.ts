import { describe, it, expect } from 'vitest';
import { resolveApiUrl } from '../lib/api-url';

const BASE = 'http://localhost:8080';

// Requirement under test (FB2-H1): a renderer-supplied path must never be able
// to redirect the request — and the Bearer key — off the API origin.
describe('resolveApiUrl — SSRF guard', () => {
  it('resolves a normal absolute path on the API origin', () => {
    expect(resolveApiUrl('/auth/me', BASE)?.href).toBe('http://localhost:8080/auth/me');
    expect(resolveApiUrl('/search?q=x', BASE)?.href).toBe('http://localhost:8080/search?q=x');
  });

  it('rejects @host authority injection', () => {
    expect(resolveApiUrl('@evil.com/steal', BASE)).toBeNull();
  });

  it('rejects protocol-relative and backslash host tricks', () => {
    expect(resolveApiUrl('//evil.com/steal', BASE)).toBeNull();
    expect(resolveApiUrl('/\\evil.com/steal', BASE)).toBeNull();
  });

  it('rejects absolute off-origin URLs', () => {
    expect(resolveApiUrl('http://evil.com', BASE)).toBeNull();
    expect(resolveApiUrl('https://localhost:8080/x', BASE)).toBeNull(); // wrong scheme → wrong origin
  });

  it('rejects non-strings and non-absolute paths', () => {
    expect(resolveApiUrl('', BASE)).toBeNull();
    expect(resolveApiUrl('relative/no-slash', BASE)).toBeNull();
    expect(resolveApiUrl(123, BASE)).toBeNull();
    expect(resolveApiUrl(null, BASE)).toBeNull();
    expect(resolveApiUrl(undefined, BASE)).toBeNull();
  });

  it('honors a custom configured base origin', () => {
    expect(resolveApiUrl('/x', 'http://192.168.1.50:9000')?.href).toBe('http://192.168.1.50:9000/x');
    expect(resolveApiUrl('//evil.com/x', 'http://192.168.1.50:9000')).toBeNull();
  });
});
